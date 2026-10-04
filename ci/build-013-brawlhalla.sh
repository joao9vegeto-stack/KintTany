#!/bin/bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$ROOT/work"
SRC="$WORK/Madeira-013-src"
OUT="$WORK/output"
REPORT="$WORK/build-report.txt"

UPSTREAM_SHA="4e9d45a74294cd820120791c4b3f2b79adf4fc70"
WINE_SHA="4f5b19718f4de88ecc5cb0dc08b119497a67ba8f"
FEX_SHA="26859e184ad90f0e811d7f8bbd943a4b1573a2c3"
OFFICIAL_IPA_SHA="71e900cbc140778bd6fa67c1062821981ed98e6bfb674d853cfeefd6d242e1c0"
VCREDIST_SHA="cc0ff0eb1dc3f5188ae6300faef32bf5beeba4bdd6e8e445a9184072096b713b"
LLVM_MINGW_SHA="bd85a3975723815cef28dbbd2ca2cb0c926f6b348a12a0453f39f7af273cb3f7"
MESA_VERSION="26.2.3"
MESA_MSVC_SHA="3f3613adb43cfd0f2e665ce2400b130c275f0b3317cb3a05566320a3a67589ed"
IPA_NAME="Madeira-0.1.3-Ruby-Pioinfo-Sync-Fix.ipa"

mkdir -p "$WORK" "$OUT"
: > "$REPORT"

on_err() {
    rc=$?
    {
      echo
      echo "BUILD FAILED rc=$rc"
      echo "at: $BASH_COMMAND"
      echo "date: $(date -u +%FT%TZ)"
    } >> "$REPORT"
    exit "$rc"
}
trap on_err ERR

say() { printf '\n==== %s ====\n' "$*"; }
record() { printf '%s\n' "$*" | tee -a "$REPORT"; }

JOBS="$(sysctl -n hw.ncpu 2>/dev/null || echo 4)"
if [ "$JOBS" -gt 8 ]; then JOBS=8; fi

record "base=Madeira v0.1.3"
record "upstream=$UPSTREAM_SHA"
record "wine=$WINE_SHA"
record "strategy=official IPA + AIR FullChain + VC runtime + ProcessDebugObjectHandle guard + actual madsync + non-Steam Steam-env cleanup + FEX InvalidationTracker heap relocation + ARM64EC image-map dedupe + Mesa x64 WGL/llvmpipe fallback + Ruby/MSVCRT __pioinfo PE-pool mirror"
record "jobs=$JOBS"
record "xcode=$(xcodebuild -version | tr '\n' ' ')"

say "Install minimal deterministic prerequisites"
brew install bison flex cabextract xz pkg-config cmake ccache p7zip
export PATH="$(brew --prefix bison)/bin:$(brew --prefix flex)/bin:$PATH"
hash -r
bison --version | head -1 | tee -a "$REPORT"
flex --version | head -1 | tee -a "$REPORT"
cabextract --version | head -1 | tee -a "$REPORT"

say "Clone exact official Madeira 0.1.3 and exact Wine submodule"
rm -rf "$SRC"
git clone --no-tags https://github.com/willfaust/Madeira.git "$SRC"
git -C "$SRC" checkout --detach "$UPSTREAM_SHA"
git -C "$SRC" submodule update --init wine FEX
git -C "$SRC/FEX" submodule update --init --recursive
test "$(git -C "$SRC" rev-parse HEAD)" = "$UPSTREAM_SHA"
test "$(git -C "$SRC/wine" rev-parse HEAD)" = "$WINE_SHA"
test "$(git -C "$SRC/FEX" rev-parse HEAD)" = "$FEX_SHA"


say "Patch ARM64EC Wine CRT __pioinfo dual-view publication for Ruby"
python3 - "$SRC/wine/dlls/ntdll/signal_arm64ec.c" "$SRC/wine/dlls/ntdll/ntdll.spec" "$SRC/wine/dlls/msvcrt/file.c" <<'PY' | tee -a "$REPORT"
import pathlib, sys
sig=pathlib.Path(sys.argv[1])
spec=pathlib.Path(sys.argv[2])
crt=pathlib.Path(sys.argv[3])

s=sig.read_text()
helper_marker="pioinfo-sync-helper rev=clayton-6"
if helper_marker in s:
    raise SystemExit("clayton-6 helper already present in pristine ntdll")
old='''void *__attribute__((naked)) xlate_ios_jit_rev( void *ptr )
{
    asm( ".seh_proc \\"#xlate_ios_jit_rev\\"\\n\\t"
         ".seh_endprologue\\n\\t"
         "cbz x0, 1f\\n\\t"                                 /* NULL → return NULL */
         "adrp x16, p_ios_jit_reverse_translate_addr\\n\\t"
         "ldr x16, [x16, #:lo12:p_ios_jit_reverse_translate_addr]\\n\\t"
         "cbz x16, 1f\\n\\t"                                /* fn-ptr unset → identity */
         "br x16\\n\\t"                                     /* tail-call unix fn */
         "1: ret\\n\\t"
         ".seh_endproc" );
}
'''
new=old+'''
/* clayton-6: keep one pointer-valued image global coherent in both Madeira
 * views. Callers may run from either view, so reverse first (pool -> PE), then
 * forward (PE -> pool) if reverse was identity. */
static const char ios_pioinfo_sync_helper_marker[] __attribute__((used)) =
    "pioinfo-sync-helper rev=clayton-6";

void * CDECL __wine_ios_sync_pointer( void **slot, void *value )
{
    void *peer;

    if (!slot) return NULL;
    InterlockedExchangePointer( (void *volatile *)slot, value );

    peer = xlate_ios_jit_rev( slot );
    if (!peer || peer == slot) peer = xlate_ios_jit( slot );

    if (peer && peer != slot)
        InterlockedExchangePointer( (void *volatile *)peer, value );
    return peer;
}
'''
if s.count(old)!=1:
    raise SystemExit(f"xlate_ios_jit_rev anchor count={s.count(old)}")
s=s.replace(old,new,1)
sig.write_text(s)

sp=spec.read_text()
old='''@ extern -private -arch=arm64,arm64ec p_ios_jit_reverse_translate_addr
'''
new=old+'''@ cdecl -private -arch=arm64ec __wine_ios_sync_pointer(ptr ptr)
'''
if sp.count(old)!=1:
    raise SystemExit(f"ntdll.spec reverse-hook anchor count={sp.count(old)}")
sp=sp.replace(old,new,1)
spec.write_text(sp)

c=crt.read_text()
marker="[pioinfo-sync] rev=clayton-6"
if marker in c:
    raise SystemExit("clayton-6 msvcrt marker already present in pristine source")

old='''ioinfo * MSVCRT___pioinfo[MSVCRT_MAX_FILES/MSVCRT_FD_BLOCK_SIZE] = { 0 };
'''
new=old+'''
#ifdef __arm64ec__
/* Private ntdll ARM64EC helper added by clayton-6. */
extern void * CDECL __wine_ios_sync_pointer( void **slot, void *value );
#endif
'''
if c.count(old)!=1:
    raise SystemExit(f"__pioinfo declaration anchor count={c.count(old)}")
c=c.replace(old,new,1)

old='''    if(InterlockedCompareExchangePointer((void**)&MSVCRT___pioinfo[fd/MSVCRT_FD_BLOCK_SIZE], block, NULL))
    {
        if (ioinfo_is_crit_init(&block[0]))
        {
            for(i = 0; i < MSVCRT_FD_BLOCK_SIZE; ++i)
                DeleteCriticalSection(&block[i].crit);
        }
        free(block);
    }
    return TRUE;
'''
new='''    {
        const int block_index = fd / MSVCRT_FD_BLOCK_SIZE;
        ioinfo *winner;

        winner = InterlockedCompareExchangePointer((void**)&MSVCRT___pioinfo[block_index], block, NULL);
        if (winner)
        {
            if (ioinfo_is_crit_init(&block[0]))
            {
                for(i = 0; i < MSVCRT_FD_BLOCK_SIZE; ++i)
                    DeleteCriticalSection(&block[i].crit);
            }
            free(block);
        }
        else winner = block;

#ifdef __arm64ec__
        {
            void *slot = &MSVCRT___pioinfo[block_index];
            void *peer = __wine_ios_sync_pointer((void **)slot, winner);
            static LONG sync_count;
            LONG n = InterlockedIncrement(&sync_count);

            if (n <= 16)
                ERR("[pioinfo-sync] rev=clayton-6 #%ld fd=%d block=%d slot=%p peer=%p value=%p\\n",
                    n, fd, block_index, slot, peer, winner);
        }
#endif
    }
    return TRUE;
'''
if c.count(old)!=1:
    raise SystemExit(f"alloc_pioinfo_block publication anchor count={c.count(old)}")
c=c.replace(old,new,1)
crt.write_text(c)

if helper_marker not in s or "__wine_ios_sync_pointer" not in sp or marker not in c:
    raise SystemExit("clayton-6 source verification failed")
print("wine-pioinfo-source=PASS rev=clayton-6")
print("wine-pioinfo-cause=Ruby direct __pioinfo data import vs msvcrt JIT-pool data")
PY

say "Patch FEX InvalidationTracker storage out of the executable JIT-pool image"
python3 - "$SRC/FEX/Source/Windows/ARM64EC/Module.cpp" <<'PY' | tee -a "$REPORT"
import pathlib, sys
p=pathlib.Path(sys.argv[1])
t=p.read_text()
marker="invalidation-tracker-heap rev=clayton-2"
if marker in t:
    raise SystemExit("tracker-heap marker already present in pristine FEX source")

old='''std::optional<FEX::Windows::InvalidationTracker> InvalidationTracker;'''
new='''/* madeira-log(10): InvalidationTracker used to live inline in this module's
 * .data. On iOS the ARM64EC image executes from the RX JIT-pool copy, so the
 * object's std::shared_mutex also lived in executable alias memory. The main
 * thread repeatedly parks in RtlWaitOnAddress at tracker+0x38, with no alert
 * ever sent. Put the object itself on the ordinary writable heap; only this
 * owning pointer remains in image .data. */
static const char ios_tracker_heap_marker[] __attribute__((used)) =
    "invalidation-tracker-heap rev=clayton-2";
fextl::unique_ptr<FEX::Windows::InvalidationTracker> InvalidationTracker;'''
if t.count(old)!=1:
    raise SystemExit(f"InvalidationTracker declaration anchor count={t.count(old)}")
t=t.replace(old,new,1)

old='''  InvalidationTracker.emplace(*CTX, Threads);'''
new='''  InvalidationTracker = fextl::make_unique<FEX::Windows::InvalidationTracker>(*CTX, Threads);
#ifdef FEX_IOS_HOST
  LogMan::Msg::EFmt("[tracker-heap] rev=clayton-2 tracker={} (must be outside JIT RX/RW image copies)",
                    static_cast<void*>(InvalidationTracker.get()));
#endif'''
if t.count(old)!=1:
    raise SystemExit(f"InvalidationTracker construction anchor count={t.count(old)}")
t=t.replace(old,new,1)

p.write_text(t)
if marker not in t:
    raise SystemExit("tracker-heap marker missing after source patch")
print("fex-source-patch=PASS InvalidationTracker std::optional inline storage -> heap unique_ptr")
print("fex-source-marker="+marker)

# madeira-log(20261004-010551): clayton-3 conclusively disproved the
# "second IntervalsLock reacquire" theory. The normal NtMapViewOfSection path
# already registered BOTH sechost.dll executable sections successfully, then
# Wine's later arm64ec_notify_image_map called NotifyImageMap for the SAME base.
# That fallback re-entered InvalidationTracker::HandleImageMap and parked during
# the redundant second registration. Fix the cause: remember images fully
# handled by the normal path and make NotifyImageMap intervals-only fallback
# skip an address that is already registered. Use a fixed atomic table so the
# dedupe path itself cannot allocate or take another mutex.
t=p.read_text()
dedupe_marker="image-map-dedupe rev=clayton-4"
if dedupe_marker in t:
    raise SystemExit("image-map dedupe marker already present in pristine FEX source")

old='''void HandleImageMap(uint64_t Address, bool MainImage = false) {
  fextl::string ModulePath = FEX::Windows::GetSectionFilePath(Address);
  fextl::string ModuleName = fextl::string {FEX::Windows::BaseName(ModulePath)};
  InvalidationTracker->HandleImageMap(ModuleName, Address);
  ImageTracker->HandleImageMap(ModulePath, Address, MainImage);
}'''
new='''#ifdef FEX_IOS_HOST
static const char ios_image_map_dedupe_marker[] __attribute__((used)) =
  "image-map-dedupe rev=clayton-4";
static std::atomic<uint64_t> IOSRegisteredImageMaps[256] {};

static bool IOSImageMapIsRegistered(uint64_t Address) {
  if (!Address) return false;
  for (auto& Slot : IOSRegisteredImageMaps) {
    if (Slot.load(std::memory_order_acquire) == Address) return true;
  }
  return false;
}

static void IOSImageMapMarkRegistered(uint64_t Address) {
  if (!Address) return;
  for (auto& Slot : IOSRegisteredImageMaps) {
    uint64_t Value = Slot.load(std::memory_order_acquire);
    if (Value == Address) return;
    if (!Value) {
      uint64_t Expected = 0;
      if (Slot.compare_exchange_strong(Expected, Address, std::memory_order_acq_rel,
                                       std::memory_order_acquire) || Expected == Address) {
        return;
      }
    }
  }
  LogMan::Msg::EFmt("[img-dedupe] rev=clayton-4 registry FULL base={:#x}", Address);
}

static void IOSImageMapForget(uint64_t Address) {
  if (!Address) return;
  for (auto& Slot : IOSRegisteredImageMaps) {
    uint64_t Expected = Address;
    if (Slot.compare_exchange_strong(Expected, 0, std::memory_order_acq_rel,
                                     std::memory_order_acquire)) {
      return;
    }
  }
}
#endif

void HandleImageMap(uint64_t Address, bool MainImage = false) {
  fextl::string ModulePath = FEX::Windows::GetSectionFilePath(Address);
  fextl::string ModuleName = fextl::string {FEX::Windows::BaseName(ModulePath)};
  InvalidationTracker->HandleImageMap(ModuleName, Address);
  ImageTracker->HandleImageMap(ModulePath, Address, MainImage);
#ifdef FEX_IOS_HOST
  IOSImageMapMarkRegistered(Address);
#endif
}'''
if t.count(old)!=1:
    raise SystemExit(f"HandleImageMap anchor count={t.count(old)}")
t=t.replace(old,new,1)

old='''extern "C" void NotifyImageMap(void* Address) {
  if (!InvalidationTracker || !Address) {
    return;
  }

  static std::atomic<uint32_t> Count {0};
  const auto N = ++Count;

  fextl::string ModulePath = FEX::Windows::GetSectionFilePath(reinterpret_cast<uint64_t>(Address));
  fextl::string ModuleName = fextl::string {FEX::Windows::BaseName(ModulePath)};
  InvalidationTracker->HandleImageMap(ModuleName, reinterpret_cast<uint64_t>(Address));

  if (N <= 64) {
    LogMan::Msg::EFmt("[img-map] ml710 #{} intervals-only {} base={}", N, ModuleName, Address);
  }
}'''
new='''extern "C" void NotifyImageMap(void* Address) {
  if (!InvalidationTracker || !Address) {
    return;
  }

  static std::atomic<uint32_t> Count {0};
  const auto N = ++Count;
  const auto MapAddress = reinterpret_cast<uint64_t>(Address);

#ifdef FEX_IOS_HOST
  /* This is a FALLBACK for loader notifications missed by the syscall path,
   * not a second registration path. madeira-log(20261004-010551) proved the
   * duplicate sechost registration can park forever before guest execution. */
  if (IOSImageMapIsRegistered(MapAddress)) {
    if (N <= 64) {
      LogMan::Msg::EFmt("[img-dedupe] rev=clayton-4 #{} SKIP already-registered base={:#x}", N, MapAddress);
    }
    return;
  }
#endif

  fextl::string ModulePath = FEX::Windows::GetSectionFilePath(MapAddress);
  fextl::string ModuleName = fextl::string {FEX::Windows::BaseName(ModulePath)};
  InvalidationTracker->HandleImageMap(ModuleName, MapAddress);
#ifdef FEX_IOS_HOST
  IOSImageMapMarkRegistered(MapAddress);
#endif

  if (N <= 64) {
    LogMan::Msg::EFmt("[img-map] ml710 #{} intervals-only fallback {} base={}", N, ModuleName, Address);
  }
}'''
if t.count(old)!=1:
    raise SystemExit(f"NotifyImageMap anchor count={t.count(old)}")
t=t.replace(old,new,1)

old='''void HandleImageUnmap(uint64_t Address, uint64_t Size) {
  ImageTracker->HandleImageUnmap(Address, Size);
}'''
new='''void HandleImageUnmap(uint64_t Address, uint64_t Size) {
  ImageTracker->HandleImageUnmap(Address, Size);
#ifdef FEX_IOS_HOST
  IOSImageMapForget(Address);
#endif
}'''
if t.count(old)!=1:
    raise SystemExit(f"HandleImageUnmap anchor count={t.count(old)}")
t=t.replace(old,new,1)

p.write_text(t)
if dedupe_marker not in t:
    raise SystemExit("image-map dedupe marker missing after source patch")
print("fex-source-patch=PASS duplicate loader image-map notifications are skipped after normal registration")
print("fex-source-marker="+dedupe_marker)
PY

say "Install exact llvm-mingw recorded by Madeira"
mkdir -p "$SRC/toolchains"
MINGW_TAR="$WORK/llvm-mingw.tar.xz"
MINGW_DIR="$SRC/toolchains/llvm-mingw-20260421-ucrt-macos-universal"
curl -fL --retry 5 --retry-all-errors   "https://github.com/mstorsjo/llvm-mingw/releases/download/20260421/llvm-mingw-20260421-ucrt-macos-universal.tar.xz"   -o "$MINGW_TAR"
echo "$LLVM_MINGW_SHA  $MINGW_TAR" | shasum -a 256 -c -
tar -C "$SRC/toolchains" -xf "$MINGW_TAR"
export PATH="$MINGW_DIR/bin:$PATH"
test -x "$MINGW_DIR/bin/arm64ec-w64-mingw32-clang"

say "Verify FEX diagnostic rollback: normal block limit restored"
python3 - "$SRC/FEX/FEXCore/Source/Interface/Config/Config.json.in" <<'PY' | tee -a "$REPORT"
import pathlib,sys
t=pathlib.Path(sys.argv[1]).read_text()
needle='''      "MaxInst": {
        "Type": "int32",
        "Default": "5000",'''
if t.count(needle) != 1:
    raise SystemExit("FEX MaxInst is not restored to upstream 5000")
print("fex-maxinst=5000 PASS (clayton-5 diagnostic removed)")
PY

say "Build patched ARM64EC FEX module"
FEX_BUILD="$SRC/FEX/build-arm64ec"
rm -rf "$FEX_BUILD"
cmake -S "$SRC/FEX" -B "$FEX_BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_TOOLCHAIN_FILE="$SRC/FEX/Data/CMake/toolchain_mingw.cmake" \
  -DMINGW_TRIPLE=arm64ec-w64-mingw32 \
  -DFEX_IOS_HOST_BUILD=ON \
  -DCMAKE_C_FLAGS=-DFEX_IOS_HOST \
  -DCMAKE_CXX_FLAGS=-DFEX_IOS_HOST \
  -DCMAKE_ASM_FLAGS=-DFEX_IOS_HOST \
  -DENABLE_LTO=OFF \
  -DTUNE_CPU=none \
  -DCMAKE_DISABLE_FIND_PACKAGE_fmt=ON \
  -DENABLE_FEX_ALLOCATOR=ON -DENABLE_JEMALLOC_GLIBC_ALLOC=ON -DENABLE_OFFLINE_RUNTIME=ON \
  -DBUILD_FEXCONFIG=ON -DENABLE_CLANG_THUNKS=ON -DENABLE_CCACHE=ON \
  -DBUILD_TESTING=OFF -DBUILD_THUNKS=OFF -DENABLE_ASSERTIONS=OFF
cmake --build "$FEX_BUILD" --target arm64ecfex -j"$JOBS"
PATCHED_FEX="$FEX_BUILD/Bin/libarm64ecfex.dll"
test -s "$PATCHED_FEX"
strings "$PATCHED_FEX" | grep -F "invalidation-tracker-heap rev=clayton-2" | tee -a "$REPORT"
strings "$PATCHED_FEX" | grep -F "image-map-dedupe rev=clayton-4" | tee -a "$REPORT"
python3 - "$PATCHED_FEX" <<'PY' | tee -a "$REPORT"
import hashlib,struct,sys
p=sys.argv[1]; d=open(p,'rb').read()
pe=struct.unpack_from('<I',d,0x3c)[0]
if d[pe:pe+4] != b'PE\0\0': raise SystemExit("patched FEX: invalid PE")
m=struct.unpack_from('<H',d,pe+4)[0]
if m not in (0x8664,0xA641): raise SystemExit(f"patched FEX machine={m:#x}")
print(f"patched-fex=PASS machine={m:#x} sha256={hashlib.sha256(d).hexdigest()} size={len(d)}")
PY

say "Configure the exact ARM64EC Wine tree"
B="$SRC/wine/build-arm64ec"
mkdir -p "$B"
(
  cd "$B"
  ../configure --enable-archs=arm64ec --without-x --disable-tests --enable-winegstreamer
)

say "Build the complete Wine system-DLL chain required by Brawlhalla Adobe AIR"
WINE_DLL_NAMES=(ntdll msvcrt msi mscms cabinet sxs mspatcha odbccp32)
for mod in "${WINE_DLL_NAMES[@]}"; do
  echo "Building Wine ARM64EC module: $mod.dll"
  make -C "$B/dlls/$mod" -j"$JOBS"
done

NTDLL="$B/dlls/ntdll/arm64ec-windows/ntdll.dll"
MSVCRT="$B/dlls/msvcrt/arm64ec-windows/msvcrt.dll"
MSI="$B/dlls/msi/arm64ec-windows/msi.dll"
MSCMS="$B/dlls/mscms/arm64ec-windows/mscms.dll"
CABINET="$B/dlls/cabinet/arm64ec-windows/cabinet.dll"
SXS="$B/dlls/sxs/arm64ec-windows/sxs.dll"
MSPATCHA="$B/dlls/mspatcha/arm64ec-windows/mspatcha.dll"
ODBCCP32="$B/dlls/odbccp32/arm64ec-windows/odbccp32.dll"
WINE_DLL_PATHS=("$NTDLL" "$MSVCRT" "$MSI" "$MSCMS" "$CABINET" "$SXS" "$MSPATCHA" "$ODBCCP32")

for p in "${WINE_DLL_PATHS[@]}"; do
  test -s "$p"
done

python3 - "${WINE_DLL_PATHS[@]}" <<'PY' | tee -a "$REPORT"
import hashlib, struct, sys
for path in sys.argv[1:]:
    d=open(path,'rb').read()
    pe=struct.unpack_from('<I',d,0x3c)[0]
    if d[pe:pe+4] != b'PE\0\0':
        raise SystemExit(f"not PE: {path}")
    machine=struct.unpack_from('<H',d,pe+4)[0]
    if machine not in (0x8664, 0xA641):
        raise SystemExit(f"unexpected Wine ARM64EC-target PE machine {machine:#x}: {path}")
    print(f"wine-module={path.split('/')[-1]} target=arm64ec-windows pe-machine={machine:#x} sha256={hashlib.sha256(d).hexdigest()} size={len(d)}")
PY

# Record imports for diagnosis. The four newly-added MSI dependencies are
# explicitly required by Wine's dlls/msi/Makefile.in at this pinned revision.
if command -v llvm-readobj >/dev/null 2>&1; then
  for p in "${WINE_DLL_PATHS[@]}"; do
    echo "---- imports: $(basename "$p") ----" | tee -a "$REPORT"
    llvm-readobj --coff-imports "$p" 2>/dev/null | grep -E 'Name: .*\.dll' | sed 's/^/  /' | tee -a "$REPORT" || true
  done
fi

say "Download and verify official Madeira 0.1.3 IPA"
OFFICIAL="$WORK/Madeira-0.1.3-official.ipa"
curl -fL --retry 5 --retry-all-errors   "https://github.com/willfaust/Madeira/releases/download/v0.1.3/Madeira-0.1.3.ipa"   -o "$OFFICIAL"
echo "$OFFICIAL_IPA_SHA  $OFFICIAL" | shasum -a 256 -c -

rm -rf "$WORK/official"
mkdir -p "$WORK/official"
ditto -x -k "$OFFICIAL" "$WORK/official"
APP="$WORK/official/Payload/Madeira.app"
test -d "$APP"

say "Preserve official 0.1.3 entitlements"
codesign -d --entitlements :- "$APP" > "$WORK/original-entitlements.plist" 2>/dev/null
plutil -lint "$WORK/original-entitlements.plist"
cp "$WORK/original-entitlements.plist" "$OUT/original-entitlements.plist"

say "Patch native ProcessDebugObjectHandle low-pointer fault in official 0.1.3"
DYLIB="$APP/Madeira.debug.dylib"
test -s "$DYLIB"
echo "27ae9665d41fb344e495ac870f63bb1528133920b08f10f7b4a5776e822d7f23  $DYLIB" | shasum -a 256 -c -

python3 - "$DYLIB" <<'PY' | tee -a "$REPORT"
import hashlib, pathlib, struct, sys
p=pathlib.Path(sys.argv[1])
d=bytearray(p.read_bytes())
PATCH_SITE=0x9552ac
CAVE=0x247fef8

# madeira-log(8) proved the previous sync patch touched the standalone
# madeira_cfg_sync_engine copy, but wineserver's madsync_enabled has the config
# logic inlined and therefore stayed disabled.  Patch the ACTUAL branch in
# _madsync_enabled: with inproc-sync absent, go directly to its ENABLED path.
# Explicit inproc-sync=0 still follows the original disabled path.
MADSYNC_DEFAULT_SITE=0x1a3f4
MADSYNC_ENABLED_SITE=0x9a55c4

# Upstream v0.1.3 deliberately publishes Thumper's Steam identity to generic
# launches.  For a non-Steam direct executable this contaminates the guest
# environment.  Route the generic fallback through the already-shipped cleanup
# path that unsets SteamAppPath/SteamGameId/SteamAppId.  Correct direct-Steam
# launches still retain their per-game identity.
STEAM_FALLBACK_SITE=0x143f0
STEAM_CLEAN_TAIL_SITE=0x14294

def u32(off): return struct.unpack_from("<I",d,off)[0]
def put32(off,v): struct.pack_into("<I",d,off,v)
def enc_b(pc,target):
    delta=target-pc
    if delta%4: raise SystemExit("unaligned B target")
    imm=delta//4
    if not (-(1<<25)<=imm<(1<<25)): raise SystemExit("B out of range")
    return 0x14000000 | (imm & 0x03ffffff)
def enc_cbz_x(rt,pc,target):
    delta=target-pc
    if delta%4: raise SystemExit("unaligned CBZ target")
    imm=delta//4
    if not (-(1<<18)<=imm<(1<<18)): raise SystemExit("CBZ out of range")
    return 0xB4000000 | ((imm & 0x7ffff)<<5) | rt
def enc_bcond(cond,pc,target):
    delta=target-pc
    if delta%4: raise SystemExit("unaligned B.cond target")
    imm=delta//4
    if not (-(1<<18)<=imm<(1<<18)): raise SystemExit("B.cond out of range")
    return 0x54000000 | ((imm & 0x7ffff)<<5) | cond

if u32(PATCH_SITE) != 0xB4000073:
    raise SystemExit(f"unexpected patch-site instruction {u32(PATCH_SITE):#010x}")
if d[CAVE:CAVE+0x20] != b"\0"*0x20:
    raise SystemExit("inter-section trampoline space is not empty")
if u32(MADSYNC_DEFAULT_SITE) != 0x1A9F1508:
    raise SystemExit(f"unexpected standalone sync-engine instruction {u32(MADSYNC_DEFAULT_SITE):#010x}")
if u32(MADSYNC_ENABLED_SITE) != 0x34000360:
    raise SystemExit(f"unexpected madsync_enabled branch {u32(MADSYNC_ENABLED_SITE):#010x}")
if u32(STEAM_FALLBACK_SITE) != 0xF000FD20:
    raise SystemExit(f"unexpected Steam fallback instruction {u32(STEAM_FALLBACK_SITE):#010x}")
if u32(STEAM_CLEAN_TAIL_SITE) != 0xF000FD21:
    raise SystemExit(f"unexpected Steam cleanup-tail instruction {u32(STEAM_CLEAN_TAIL_SITE):#010x}")

code=[
    enc_cbz_x(19,CAVE,CAVE+0x18),
    0xF140427F,
    enc_bcond(2,CAVE+0x08,CAVE+0x1c),
    0x528000A0,
    0x72B80000,
    enc_b(CAVE+0x14,0x955268),
    enc_b(CAVE+0x18,0x9552b8),
    enc_b(CAVE+0x1c,0x9552b0),
]
put32(PATCH_SITE,enc_b(PATCH_SITE,CAVE))
for i,ins in enumerate(code): put32(CAVE+i*4,ins)

# Keep the standalone helper untouched; madeira-log(8) proved it is not the
# copy used by wineserver's madsync_enabled.
put32(MADSYNC_DEFAULT_SITE,0x1A9F1508)

# _madsync_enabled @ 0x9a55c4:
#   old: cbz w0, 0x9a5630  -> absent inproc-sync falls into fastsync/disabled
#   new: cbz w0, 0x9a5660  -> absent inproc-sync reaches ENABLED
# Encoding is verified against the exact official 0.1.3 dylib above.
put32(MADSYNC_ENABLED_SITE,0x340004E0)

# Generic/non-Steam fallback now reuses the existing three-unset sequence at
# 0x14270.  Skip its Dock-only diagnostic line after the unsets, then continue
# with one-shot MADEIRA_STEAM_* cleanup.
put32(STEAM_FALLBACK_SITE,enc_b(STEAM_FALLBACK_SITE,0x14270))
put32(STEAM_CLEAN_TAIL_SITE,enc_b(STEAM_CLEAN_TAIL_SITE,0x14444))

p.write_bytes(d)

e=p.read_bytes()
if struct.unpack_from("<I",e,PATCH_SITE)[0] != 0x146CAB13:
    raise SystemExit("patch-site branch read-back mismatch")
expected=[0xB40000D3,0xF140427F,0x540000A2,0x528000A0,0x72B80000,0x179354D7,0x179354EA,0x179354E7]
got=[struct.unpack_from("<I",e,CAVE+i*4)[0] for i in range(8)]
if got != expected: raise SystemExit("trampoline read-back mismatch")
if struct.unpack_from("<I",e,MADSYNC_DEFAULT_SITE)[0] != 0x1A9F1508:
    raise SystemExit("standalone sync helper was unexpectedly changed")
if struct.unpack_from("<I",e,MADSYNC_ENABLED_SITE)[0] != 0x340004E0:
    raise SystemExit("actual madsync_enabled patch read-back mismatch")
if struct.unpack_from("<I",e,STEAM_FALLBACK_SITE)[0] != 0x17FFFFA0:
    raise SystemExit("Steam fallback branch read-back mismatch")
if struct.unpack_from("<I",e,STEAM_CLEAN_TAIL_SITE)[0] != 0x1400006C:
    raise SystemExit("Steam cleanup-tail branch read-back mismatch")
print("native-patch=PASS ProcessDebugObjectHandle ret_len low-page guard")
print("sync-default=PASS actual _madsync_enabled: absent inproc-sync enters ENABLED path; explicit inproc-sync=0 preserved")
print("steam-env-clean=PASS generic launch unsets SteamAppPath/SteamGameId/SteamAppId")
print(f"native-dylib-patched-sha256={hashlib.sha256(e).hexdigest()}")
PY

codesign --force --sign - --timestamp=none "$DYLIB"
codesign --verify --strict --verbose=2 "$DYLIB"

python3 - "$DYLIB" <<'PY' | tee -a "$REPORT"
import pathlib,struct,sys
d=pathlib.Path(sys.argv[1]).read_bytes()
if struct.unpack_from("<I",d,0x9552ac)[0] != 0x146CAB13:
    raise SystemExit("native patch lost after codesign")
expected=[0xB40000D3,0xF140427F,0x540000A2,0x528000A0,0x72B80000,0x179354D7,0x179354EA,0x179354E7]
got=[struct.unpack_from("<I",d,0x247fef8+i*4)[0] for i in range(8)]
if got != expected: raise SystemExit("native trampoline lost after codesign")
checks={
    0x1a3f4:0x1A9F1508,
    0x9a55c4:0x340004E0,
    0x143f0:0x17FFFFA0,
    0x14294:0x1400006C,
}
for off,want in checks.items():
    got=struct.unpack_from("<I",d,off)[0]
    if got != want:
        raise SystemExit(f"native runtime patch lost after codesign at {off:#x}: {got:#010x} != {want:#010x}")
print("native-patch-after-codesign=PASS debug-object + actual-madsync-enabled + Steam-env-clean")
PY

say "Fetch pinned Mesa3D x64 WGL runtime for OpenGL software fallback"
MESA_7Z="$WORK/mesa3d-$MESA_VERSION-release-msvc.7z"
MESA_DIR="$WORK/mesa3d-$MESA_VERSION-msvc"
curl -fL --retry 5 --retry-all-errors \
  "https://github.com/pal1000/mesa-dist-win/releases/download/$MESA_VERSION/mesa3d-$MESA_VERSION-release-msvc.7z" \
  -o "$MESA_7Z"
echo "$MESA_MSVC_SHA  $MESA_7Z" | shasum -a 256 -c -
rm -rf "$MESA_DIR"
mkdir -p "$MESA_DIR"
7z x -y "$MESA_7Z" "-o$MESA_DIR" >/dev/null

MESA_GL="$(find "$MESA_DIR" -type f -path '*/x64/opengl32.dll' -print -quit)"
MESA_GALLIUM="$(find "$MESA_DIR" -type f -path '*/x64/libgallium_wgl.dll' -print -quit)"
test -n "$MESA_GL" && test -s "$MESA_GL"
test -n "$MESA_GALLIUM" && test -s "$MESA_GALLIUM"

python3 - "$MESA_GL" "$MESA_GALLIUM" <<'PY' | tee -a "$REPORT"
import hashlib, pathlib, struct, sys
for pth in sys.argv[1:]:
    p=pathlib.Path(pth); d=p.read_bytes()
    if d[:2] != b'MZ': raise SystemExit(f"{p.name}: not PE")
    pe=struct.unpack_from('<I',d,0x3c)[0]
    if d[pe:pe+4] != b'PE\0\0': raise SystemExit(f"{p.name}: invalid PE")
    machine=struct.unpack_from('<H',d,pe+4)[0]
    if machine != 0x8664: raise SystemExit(f"{p.name}: expected x86-64 PE, got {machine:#x}")
    print(f"mesa-runtime={p.name} machine={machine:#x} sha256={hashlib.sha256(d).hexdigest()} size={len(d)}")
print("mesa-runtime-status=READY (x64 WGL; llvmpipe is Mesa's software fallback)")
PY

say "Inject patched FEX, Ruby CRT coherence fix, and Adobe AIR Wine DLL chain into the ARM64EC farm"
mkdir -p "$APP/arm64ec-windows"
cp "$PATCHED_FEX" "$APP/arm64ec-windows/xtajit64.dll"
cp "$NTDLL"    "$APP/arm64ec-windows/ntdll.dll"
cp "$MSVCRT"   "$APP/arm64ec-windows/msvcrt.dll"
cp "$MSI"      "$APP/arm64ec-windows/msi.dll"
cp "$MSCMS"    "$APP/arm64ec-windows/mscms.dll"
cp "$CABINET"  "$APP/arm64ec-windows/cabinet.dll"
cp "$SXS"      "$APP/arm64ec-windows/sxs.dll"
cp "$MSPATCHA" "$APP/arm64ec-windows/mspatcha.dll"
cp "$ODBCCP32" "$APP/arm64ec-windows/odbccp32.dll"

# madeira-log(20261004-013724): mkxp-z now reaches SDL window creation but
# Wine's iOS opengl32 unix side is intentionally a GL-absent stub. Replace only
# the OpenGL runtime with Mesa's native x64 WGL loader + Gallium megadriver.
# FEX executes these x64 PE DLLs; Mesa falls back to llvmpipe when no usable
# hardware OpenGL/D3D12 path exists. This is explicitly a "first pixels"
# compatibility path, not a performance solution.
cp "$MESA_GL"      "$APP/arm64ec-windows/opengl32.dll"
cp "$MESA_GALLIUM" "$APP/arm64ec-windows/libgallium_wgl.dll"

test -s "$APP/arm64ec-windows/xtajit64.dll"
strings "$APP/arm64ec-windows/xtajit64.dll" | grep -F "invalidation-tracker-heap rev=clayton-2" | tee -a "$REPORT"
strings "$APP/arm64ec-windows/xtajit64.dll" | grep -F "image-map-dedupe rev=clayton-4" | tee -a "$REPORT"
if strings "$APP/arm64ec-windows/xtajit64.dll" | grep -F "[first-pixels] rev=clayton-5" >/dev/null; then
  echo "unexpected clayton-5 MaxInst diagnostic survived" >&2
  exit 1
fi
strings "$APP/arm64ec-windows/msvcrt.dll" | grep -F "[pioinfo-sync] rev=clayton-6" | tee -a "$REPORT"
strings "$APP/arm64ec-windows/ntdll.dll" | grep -F "pioinfo-sync-helper rev=clayton-6" | tee -a "$REPORT"
test -s "$APP/arm64ec-windows/opengl32.dll"
test -s "$APP/arm64ec-windows/libgallium_wgl.dll"
python3 - "$APP/arm64ec-windows/opengl32.dll" "$APP/arm64ec-windows/libgallium_wgl.dll" <<'PY' | tee -a "$REPORT"
import hashlib, pathlib, struct, sys
for pth in sys.argv[1:]:
    p=pathlib.Path(pth); d=p.read_bytes()
    pe=struct.unpack_from('<I',d,0x3c)[0]
    machine=struct.unpack_from('<H',d,pe+4)[0]
    if machine != 0x8664: raise SystemExit(f"bundled {p.name}: not x64 ({machine:#x})")
    print(f"bundled-mesa={p.name} sha256={hashlib.sha256(d).hexdigest()} size={len(d)}")
print("bundled-mesa-status=PASS")
PY
AIR_WINE_DLLS=(msi.dll mscms.dll cabinet.dll sxs.dll mspatcha.dll odbccp32.dll)
for name in "${AIR_WINE_DLLS[@]}"; do
  test -s "$APP/arm64ec-windows/$name"
done

# Fail the build if the exact missing chain seen in madeira-log(4) is not
# physically present in the final bundle.
python3 - "$APP/arm64ec-windows" <<'PY' | tee -a "$REPORT"
import hashlib, pathlib, struct, sys
root=pathlib.Path(sys.argv[1])
required=["msi.dll","mscms.dll","cabinet.dll","sxs.dll","mspatcha.dll","odbccp32.dll"]
for name in required:
    p=root/name
    if not p.is_file() or p.stat().st_size == 0:
        raise SystemExit(f"missing required Adobe AIR/Wine DLL: {name}")
    d=p.read_bytes()
    if d[:2] != b'MZ':
        raise SystemExit(f"{name}: not PE")
    pe=struct.unpack_from('<I',d,0x3c)[0]
    if d[pe:pe+4] != b'PE\0\0':
        raise SystemExit(f"{name}: invalid PE signature")
    machine=struct.unpack_from('<H',d,pe+4)[0]
    if machine not in (0x8664,0xA641):
        raise SystemExit(f"{name}: unexpected machine {machine:#x}")
    print(f"air-chain={name} pe-machine={machine:#x} sha256={hashlib.sha256(d).hexdigest()} size={len(d)}")
print("air-chain-status=COMPLETE")
PY

say "Fetch pinned official Microsoft Visual C++ 2022 x64 redistributable (14.44.35211)"
VCREDIST="$WORK/VC_redist.x64-14.44.35211.exe"
curl -fL --retry 5 --retry-all-errors \
  "https://download.visualstudio.microsoft.com/download/pr/7ebf5fdb-36dc-4145-b0a0-90d3d5990a61/CC0FF0EB1DC3F5188AE6300FAEF32BF5BEEBA4BDD6E8E445A9184072096B713B/VC_redist.x64.exe" \
  -o "$VCREDIST"
echo "$VCREDIST_SHA  $VCREDIST" | shasum -a 256 -c -
record "vc-redist-version=14.44.35211"
record "vc-redist-sha256=$VCREDIST_SHA"

V1="$WORK/vcredist-bundle"
V2="$WORK/vcredist-a12"
rm -rf "$V1" "$V2"
mkdir -p "$V1" "$V2"

# Winetricks' vcrun2022 path for this exact x64 package: the Burn bundle
# contains cabinet a12, and a12 contains the amd64 VC runtime payload.
cabextract -d "$V1" "$VCREDIST" -F a12
test -s "$V1/a12"
cabextract -d "$V2" "$V1/a12"

say "Stage the twelve exact x86-64 VC runtime DLLs from the pinned Microsoft cabinet"
rm -rf "$APP/x86_64-vcruntime"
mkdir -p "$APP/x86_64-vcruntime"

VCRT_NAMES=(
  concrt140.dll
  msvcp140.dll
  msvcp140_1.dll
  msvcp140_2.dll
  msvcp140_atomic_wait.dll
  msvcp140_codecvt_ids.dll
  vcamp140.dll
  vccorlib140.dll
  vcomp140.dll
  vcruntime140.dll
  vcruntime140_1.dll
  vcruntime140_threads.dll
)

for name in "${VCRT_NAMES[@]}"; do
  src="$V2/${name}_amd64"
  test -s "$src"
  cp "$src" "$APP/x86_64-vcruntime/$name"
done

python3 - "$APP/x86_64-vcruntime" <<'PY' | tee -a "$REPORT"
import hashlib, pathlib, struct, sys
root=pathlib.Path(sys.argv[1])
files=sorted(root.glob("*.dll"))
if len(files) != 12:
    raise SystemExit(f"expected 12 VC runtime DLLs, found {len(files)}")
for p in files:
    d=p.read_bytes()
    if len(d) < 0x100 or d[:2] != b'MZ':
        raise SystemExit(f"{p.name}: not an MZ PE image")
    pe=struct.unpack_from('<I',d,0x3c)[0]
    if pe + 6 > len(d) or d[pe:pe+4] != b'PE\0\0':
        raise SystemExit(f"{p.name}: invalid PE signature")
    machine=struct.unpack_from('<H',d,pe+4)[0]
    if machine != 0x8664:
        raise SystemExit(f"{p.name}: machine {machine:#x}, expected x86-64 0x8664")
    print(f"vcrt={p.name} machine=x86_64 sha256={hashlib.sha256(d).hexdigest()} size={len(d)}")
PY

test "$(find "$APP/x86_64-vcruntime" -type f -name '*.dll' | wc -l | tr -d ' ')" = "12"

say "Validate final injected payload"
python3 - "$APP" <<'PY' | tee -a "$REPORT"
import hashlib, pathlib, struct, sys
app=pathlib.Path(sys.argv[1])
wine_modules=[
 app/'arm64ec-windows'/'xtajit64.dll',
 app/'arm64ec-windows'/'msi.dll',
 app/'arm64ec-windows'/'mscms.dll',
 app/'arm64ec-windows'/'cabinet.dll',
 app/'arm64ec-windows'/'sxs.dll',
 app/'arm64ec-windows'/'mspatcha.dll',
 app/'arm64ec-windows'/'odbccp32.dll',
]
vcrt=list(sorted((app/'x86_64-vcruntime').glob('*.dll')))
for p in wine_modules:
    d=p.read_bytes(); pe=struct.unpack_from('<I',d,0x3c)[0]
    got=struct.unpack_from('<H',d,pe+4)[0]
    if got not in (0x8664,0xA641):
        raise SystemExit(f"{p.name}: unexpected Wine ARM64EC-target PE machine {got:#x}")
    print(f"payload={p.relative_to(app)} target=arm64ec-windows pe-machine={got:#x} sha256={hashlib.sha256(d).hexdigest()}")
for p in vcrt:
    d=p.read_bytes(); pe=struct.unpack_from('<I',d,0x3c)[0]
    got=struct.unpack_from('<H',d,pe+4)[0]
    if got!=0x8664:
        raise SystemExit(f"{p.name}: machine {got:#x}, expected x86-64 0x8664")
    print(f"payload={p.relative_to(app)} machine=x86_64 sha256={hashlib.sha256(d).hexdigest()}")
print(f"payload-count={len(wine_modules)+len(vcrt)}")
PY

say "Re-sign only the modified outer app with official entitlements"
codesign --force --sign - --timestamp=none   --entitlements "$WORK/original-entitlements.plist" "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"
codesign -d --entitlements :- "$APP" > "$WORK/final-entitlements.plist" 2>/dev/null
plutil -lint "$WORK/final-entitlements.plist"
cp "$WORK/final-entitlements.plist" "$OUT/final-entitlements.plist"

say "Package corrected IPA"
rm -f "$OUT/$IPA_NAME"
(
  cd "$WORK/official"
  ditto -c -k --sequesterRsrc --keepParent Payload "$OUT/$IPA_NAME"
)
test -s "$OUT/$IPA_NAME"
record "ipa=$IPA_NAME"
record "ipa-size=$(stat -f%z "$OUT/$IPA_NAME")"
record "ipa-sha256=$(shasum -a 256 "$OUT/$IPA_NAME" | awk '{print $1}')"
record "status=SUCCESS"
cp "$REPORT" "$OUT/build-report.txt"
cat "$REPORT"
