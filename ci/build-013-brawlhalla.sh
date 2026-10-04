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
DXMT_SHA="35a4db11bd1bda380c5176a3bc6c1878f7192101"
OFFICIAL_IPA_SHA="71e900cbc140778bd6fa67c1062821981ed98e6bfb674d853cfeefd6d242e1c0"
VCREDIST_SHA="cc0ff0eb1dc3f5188ae6300faef32bf5beeba4bdd6e8e445a9184072096b713b"
LLVM_MINGW_SHA="bd85a3975723815cef28dbbd2ca2cb0c926f6b348a12a0453f39f7af273cb3f7"
MESA_VERSION="26.2.3"
MESA_MSVC_SHA="3f3613adb43cfd0f2e665ce2400b130c275f0b3317cb3a05566320a3a67589ed"
IPA_NAME="Madeira-0.1.3-Injustice-GTAIV-R8.1.ipa"

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
record "strategy=R8.1: preserve R7 Injustice heal; GTAIV keeps application-owned Reset and official mode table; guard the exact DXMT FlushDrawBatch Copy-blit wild Texture pointer proven by the R6 log; per-HWND Metal path retained"
record "jobs=$JOBS"
record "xcode=$(xcodebuild -version | tr '\n' ' ')"

say "Install minimal deterministic prerequisites"
brew install bison flex cabextract xz pkg-config cmake ccache p7zip meson ninja
export PATH="$(brew --prefix bison)/bin:$(brew --prefix flex)/bin:$PATH"
hash -r
bison --version | head -1 | tee -a "$REPORT"
flex --version | head -1 | tee -a "$REPORT"
cabextract --version | head -1 | tee -a "$REPORT"

say "Clone exact official Madeira 0.1.3 and exact Wine submodule"
rm -rf "$SRC"
git clone --no-tags https://github.com/willfaust/Madeira.git "$SRC"
git -C "$SRC" checkout --detach "$UPSTREAM_SHA"
git -C "$SRC" submodule update --init wine FEX dxmt
git -C "$SRC/FEX" submodule update --init --recursive
git -C "$SRC/dxmt" submodule update --init --recursive
test "$(git -C "$SRC" rev-parse HEAD)" = "$UPSTREAM_SHA"
test "$(git -C "$SRC/wine" rev-parse HEAD)" = "$WINE_SHA"
test "$(git -C "$SRC/FEX" rev-parse HEAD)" = "$FEX_SHA"
test "$(git -C "$SRC/dxmt" rev-parse HEAD)" = "$DXMT_SHA"


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
anchor='''

void *arm64ec_redirect_ptr( HMODULE module, void *ptr, const IMAGE_ARM64EC_METADATA *metadata )
'''
helper='''

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
if s.count(anchor)!=1:
    raise SystemExit(f"arm64ec_redirect_ptr anchor count={s.count(anchor)}")
s=s.replace(anchor, helper+anchor, 1)
sig.write_text(s)

sp=spec.read_text()
old='''@ extern -private -arch=arm64,arm64ec p_ios_jit_reverse_translate_addr
'''
new=old+'''@ cdecl -arch=arm64ec __wine_ios_sync_pointer(ptr ptr)
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
test -x "$MINGW_DIR/bin/i686-w64-mingw32-clang"

say "Patch pinned i386 D3D9 shim for GTA IV configured resolution and real Present pacing"
python3 - "$SRC/dxmt/src/d3d9shim/d3d9shim_main.c" "$SRC/dxmt/src/d3d9shim/d3d9shim_custom.c" <<'PY' | tee -a "$REPORT"
import pathlib, sys
main=pathlib.Path(sys.argv[1])
custom=pathlib.Path(sys.argv[2])

m=main.read_text()
old='''        shim_mode = D3D9SHIM_MODE_DEFAULT;
        d3d9shim_trace("[d3d9] MADEIRA_D3D9 unset: forwarding to "
                       "d3d9-emulated.dll (Documents/madeira-d3d9.txt = "
                       "native selects the native ARM64 frontend)");
        return;
'''
new='''        shim_mode = D3D9SHIM_MODE_DEFAULT;
        d3d9shim_trace("[d3d9] clayton-25 default: native ARM64 first for Create9+Create9Ex; emulated fallback on native create failure");
        return;
'''
if m.count(old)!=1:
    raise SystemExit(f"default-mode log anchor count={m.count(old)}")
m=m.replace(old,new,1)
old='''static int
forwarding(void)
{
    return shim_mode == D3D9SHIM_MODE_EMULATED
           || shim_mode == D3D9SHIM_MODE_DEFAULT;
}
'''
new='''static int
forwarding(void)
{
    /* clayton-25: default is native-first, while an explicit emulated knob
     * still forwards every export. fall_back_to_emulated() keeps the shipped
     * safety net when the native unix side cannot initialise. */
    return shim_mode == D3D9SHIM_MODE_EMULATED;
}
'''
if m.count(old)!=1:
    raise SystemExit(f"forwarding anchor count={m.count(old)}")
m=m.replace(old,new,1)
main.write_text(m)

t=custom.read_text()
anchor='''/* ------------------------------------------------------------------------
 * Reset / ResetEx
 * ------------------------------------------------------------------------ */
'''
helper=r'''/* R8 GTA IV correction: keep detection in the 32-bit shim only for targeted
 * diagnostics. The R6 log disproved forced mode conversion and guest-side
 * Present sleeping: GTA must own its Reset parameters so RT/DS resources stay
 * coherent and the game's normal loading transition can complete. */
static int
d3d9shim_is_gtaiv(void)
{
    static LONG cached;
    char path[MAX_PATH];
    char *base;
    DWORD n;
    LONG value = InterlockedCompareExchange(&cached, 0, 0);

    if (value)
        return value > 0;
    n = GetModuleFileNameA(NULL, path, sizeof(path));
    if (!n || n >= sizeof(path)) {
        InterlockedExchange(&cached, -1);
        return 0;
    }
    path[n] = 0;
    base = path + n;
    while (base > path && base[-1] != '\\' && base[-1] != '/')
        --base;
    if (!_stricmp(base, "GTAIV.exe")) {
        InterlockedExchange(&cached, 1);
        d3d9shim_log_once("[gtaiv-r8] detected GTAIV.exe; native Reset parameters remain application-owned");
        return 1;
    }
    InterlockedExchange(&cached, -1);
    return 0;
}



'''
if t.count(anchor)!=1:
    raise SystemExit(f"Reset section anchor count={t.count(anchor)}")
t=t.replace(anchor, helper+anchor,1)

old='''    device_window = parameters->hDeviceWindow;
    if (!device_window && extra)
        device_window = extra->focus_window;
    /* Same ordering rule as CreateDevice: a zero extent is filled from the
     * client rect, so push the cache first. */
    d3d9shim_window_push(device_window, !parameters->Windowed);
'''
new='''    device_window = parameters->hDeviceWindow;
    if (!device_window && extra)
        device_window = extra->focus_window;

    /* R8: pass GTA's requested mode through unchanged. R6 forced the
     * backbuffer to Madeira's launch size while GTA kept an 800x600 depth
     * surface, producing the exact RT/DS mismatch in the R6 device log.
     * Window geometry still follows the successful native Reset below. */
    if (d3d9shim_is_gtaiv() && extra
        && (parameters->Windowed
            || parameters->BackBufferWidth != extra->backbuffer_width
            || parameters->BackBufferHeight != extra->backbuffer_height))
        d3d9shim_log_once("[gtaiv-r8] Reset passed through unchanged to keep render-target/depth-stencil dimensions coherent");

    /* Same ordering rule as CreateDevice: a zero extent is filled from the
     * client rect, so push the cache first. */
    d3d9shim_window_push(device_window, !parameters->Windowed);
'''
if t.count(old)!=1:
    raise SystemExit(f"custom_reset window anchor count={t.count(old)}")
t=t.replace(old,new,1)

old='''    hr = has_flags ? (HRESULT)p.present_ex.ret : (HRESULT)p.present.ret;
    d3d9shim_unlock(dev);
    return hr;
'''
new='''    hr = has_flags ? (HRESULT)p.present_ex.ret : (HRESULT)p.present.ret;
    d3d9shim_unlock(dev);
    return hr;
'''
if t.count(old)!=1:
    raise SystemExit(f"custom_present return anchor count={t.count(old)}")
t=t.replace(old,new,1)
custom.write_text(t)

for marker in (
    "clayton-25 default: native ARM64 first",
    "[gtaiv-r8] detected GTAIV.exe; native Reset parameters remain application-owned",
    "[gtaiv-r8] Reset passed through unchanged to keep render-target/depth-stencil dimensions coherent",
):
    if marker not in main.read_text() + custom.read_text():
        raise SystemExit("missing source marker: "+marker)
print("d3d9shim-source=PASS R8 GTA Reset pass-through + no guest Present sleep + clayton-25 native-first")
PY

say "Configure minimal i386 Wine build tree for the rebuilt D3D9 shim"
I386_B="$SRC/wine/build-i386-r8"
rm -rf "$I386_B"
mkdir -p "$I386_B"
(
  cd "$I386_B"
  ../configure --enable-archs=i386 --without-x --without-vulkan                --without-freetype --without-gnutls --disable-tests                --enable-winegstreamer
)
# The DXMT PE shim needs Wine's generated headers/import side. Building these
# four roots is much smaller than rebuilding the full 700+ module i386 farm.
make -C "$I386_B/dlls/ntdll" -j"$JOBS"
make -C "$I386_B/dlls/kernel32" -j"$JOBS"
make -C "$I386_B/dlls/user32" -j"$JOBS"
make -C "$I386_B/dlls/gdi32" -j"$JOBS"

say "Build only the pinned DXMT i386 d3d9shim target"
DXMT_BUILD="$SRC/dxmt/build-pe-i386-r8"
DXMT_CROSS="$WORK/dxmt-cross-i386-r8.txt"
rm -rf "$DXMT_BUILD"
cat > "$DXMT_CROSS" <<EOF
[binaries]
c = '$MINGW_DIR/bin/i686-w64-mingw32-clang'
cpp = '$MINGW_DIR/bin/i686-w64-mingw32-clang++'
ar = '$MINGW_DIR/bin/i686-w64-mingw32-ar'
strip = '$MINGW_DIR/bin/i686-w64-mingw32-strip'
windres = '$MINGW_DIR/bin/i686-w64-mingw32-windres'
dlltool = '$MINGW_DIR/bin/i686-w64-mingw32-dlltool'

[properties]
needs_exe_wrapper = true

[host_machine]
system = 'windows'
cpu_family = 'x86'
cpu = 'i686'
endian = 'little'
EOF
(
  cd "$SRC/dxmt"
  SDKROOT="$(xcrun --sdk macosx --show-sdk-path)"     meson setup --cross-file "$DXMT_CROSS" --native-file build-osx.txt       --buildtype release -Dwine_build_path="$I386_B" -Dwine_builtin_dll=true       "$DXMT_BUILD"
  SDKROOT="$(xcrun --sdk macosx --show-sdk-path)"     meson compile -C "$DXMT_BUILD" d3d9shim
)
D3D9_R6_RAW="$(find "$DXMT_BUILD" -type f -path '*/d3d9shim/d3d9shim.dll' -print -quit)"
test -n "$D3D9_R6_RAW" && test -s "$D3D9_R6_RAW"
PATCHED_D3D9_SHIM="$WORK/d3d9shim-r8.dll"
"$MINGW_DIR/bin/i686-w64-mingw32-strip" --strip-debug -o "$PATCHED_D3D9_SHIM" "$D3D9_R6_RAW"
test -s "$PATCHED_D3D9_SHIM"
strings "$PATCHED_D3D9_SHIM" | grep -F "[gtaiv-r8] detected GTAIV.exe; native Reset parameters remain application-owned" | tee -a "$REPORT"
strings "$PATCHED_D3D9_SHIM" | grep -F "[gtaiv-r8] Reset passed through unchanged to keep render-target/depth-stencil dimensions coherent" | tee -a "$REPORT"
strings "$PATCHED_D3D9_SHIM" | grep -F "clayton-25 default: native ARM64 first" | tee -a "$REPORT"
"$MINGW_DIR/bin/llvm-objdump" -p "$PATCHED_D3D9_SHIM" | grep -E 'GetModuleFileNameA|SetWindowPos' | tee -a "$REPORT"
record "d3d9shim-r6-sha256=$(shasum -a 256 "$PATCHED_D3D9_SHIM" | awk '{print $1}')"

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

# clayton-8: madeira-log(20261004-055107) proves clayton-7 reached the
# Objective-C presentation entry point: surface_flush and winios_surface_present
# fire continuously with changing frame signatures. But there are ZERO
# "compositor attached", "compositor layout" or "layer created" lines.
# Source inspection shows the final blocker: winios_ensure_compositor() has its
# OWN MADEIRA_DESKTOP-only return gate. Open that gate without setting the env
# itself, so direct-game input/launch semantics remain direct while the already
# arriving software frames finally get a UIView/CALayer.
DIRECT_SURFACE_REGISTER_SITE=0x1bf28a4
DIRECT_SURFACE_FRAME_SITE=0x1bf3d40
DIRECT_COMPOSITOR_GATE_SITE=0x1f6d4
DIRECT_COMPOSITOR_CONTINUE=0x1f708
DIRECT_SURFACE_LOG_SITE=0x20fb195
DIRECT_SURFACE_LOG_OLD=b"[winios] desktop mode: window-surface compositing ENABLED\n"
DIRECT_SURFACE_LOG_NEW=b"[winios] clayton-12 software compositor on present only\n"

# clayton-9: Pokemon Anil / Left 4 Dead logs prove raw touch reaches Wine as
# mouse input while the library touch overlay is hidden and player 1 is not
# reserved early. Show the existing control layout at session start and reserve
# a neutral XInput slot before the game enumerates controllers.
TOUCH_SLOT_OPTIN_SITE=0x403c80
TOUCH_SLOT_ARG_SITE=0x4526e0
TOUCH_VISIBLE_SITE=0x579020

# clayton-11: Injustice fight-load UAF.
# The tested run unmaps 0x43c680000..0x43c780000 on RenderingThread, then the
# main thread reads 0x43c6d0000 ~43.6s later. This is a 1 MiB section inside
# the process's 4 GiB WoW64 host window. There are only 16 unique exact-1MiB
# section ranges in the whole run (~16 MiB total), despite >2400 repeated
# notifications. Keep only exact-1MiB, non-image, non-placeholder section
# views whose upper 32 bits match x18/TEB's WoW64 window. Report unmap success
# but leave the view alive until pseudo-process teardown. 64-bit mappings,
# images/DLLs, placeholders, and all other sizes follow the pristine path.
WOW64_SECTION_UNMAP_SITE=0x97ea4c
WOW64_SECTION_UNMAP_CAVE=0x247ff18
WOW64_SECTION_UNMAP_CAVE_SIZE=0x38
WOW64_SECTION_MARKER_SITE=0x247ff60
WOW64_SECTION_MARKER=b"clayton-14 injustice-exact-view-quarantine"

# clayton-26: the R6025 dialog is secondary. The first fatal event in the
# Injustice log is a C0000005 at guest EIP 0x00B52B3D reading guest 0x15570000.
# The host peer (WoW64 window base + 0x15570000) is an anonymous 0x18000-byte
# PROT_NONE region, never materialised, and Wine has no view for it. The old
# exact 0x3c680000 section quarantine does not even occur in that failing run.
#
# Intercept only the unreadable BUS path, only when the guest offset is exactly
# 0x15570000 and the host address is in one of Madeira's 4/5/6 GiB WoW64
# windows. Materialise the exact 0x18000 anonymous hole RW and resume the
# translated instruction. All other faults fall back to pristine bus_handler.
INJUSTICE_HOLE_SITE=0x994334
INJUSTICE_HOLE_CAVE=0x247ff90
INJUSTICE_HOLE_CAVE_SIZE=0x48
INJUSTICE_HOLE_MARKER_SITE=0x247ffd8
INJUSTICE_HOLE_MARKER=b"clayton-26 injustice-guest-hole-heal"
MPROTECT_STUB=0x1fb0550
BUS_UNREADABLE_NORMAL=0x994338
BUS_READABLE_PATH=0x994500
BUS_RESUME_PATH=0x994b90

# R8: preserve the official D3D9 mode table and Reset safety gate. The R6
# device log proves the forced 1280x720 Reset left GTA's depth-stencil at
# 800x600, and bypassing the losable-resource guard allowed an inconsistent
# resource set to survive into the asynchronous encoder. The per-HWND Metal
# path below remains enabled; only the unsafe mode/Reset overrides are removed.
D3D9_GTA_MODE_WIDTH_SITE=0x22a47fc
D3D9_GTA_MODE_HEIGHT_SITE=0x22a4800
D3D9_GTA_RESET_LOSABLE_GATE_SITE=0x1aade04

# clayton-18: GTA IV now creates and resets the native D3D9 device, and its
# Present loop runs, but the visible Wine client stays white. The log proves
# Winios has a real hwnd=0x20030 compositor while DXMT never creates the
# per-HWND CAMetalLayer. In direct-game mode IOSDisplayShim instead returns
# the fullscreen singleton layer, so the later 800x600 window/reset is split
# from the layer that receives Metal. Force the already-shipped per-window
# branch: it calls winios_metal_layer_for_hwnd(hwnd), so Metal is attached
# inside the same window/compositor that the screenshot actually shows.
D3D9_WINDOW_LAYER_GATE_SITE=0x1c724

# clayton-27 / R8.1: the R6 GTA log does not merely stall. Its first fatal
# native event is inside MTLD3D9Device::FlushDrawBatch's Copy-blit walker:
#   ldr x8,[x25]          ; PendingBlitOp::src_tex wrapper
#   ldr x26,[x8,#0x40]    ; Texture::allocation
# with x8=0x7369642e72696100 ("\0air.dis..." as bytes), an impossible host
# object pointer. The destination path has the same unchecked dereference.
# Madeira's launch address map is below 64 GiB, so reject only NULL or a
# wrapper with any bit >=36 set, skip that one corrupt blit, and keep the
# render loop alive. The caves sit in zero padding at the end of __TEXT,
# after __oslogstring and before the next segment.
GTA_BLIT_SRC_SITE=0x1ad7bb8
GTA_BLIT_DST_SITE=0x1ad7bec
GTA_BLIT_SRC_CONT=0x1ad7bc0
GTA_BLIT_DST_CONT=0x1ad7bf4
GTA_BLIT_SKIP=0x1ad7c84
GTA_BLIT_SRC_CAVE=0x2481220
GTA_BLIT_DST_CAVE=0x2481260
GTA_BLIT_CAVE_END=0x24812a0
GTA_BLIT_MARKER_SITE=0x24812b0
GTA_BLIT_MARKER=b"clayton-27 gtaiv-dxmt-blit-pointer-guard"

# clayton-20: R3's binary-port of the DXMT CPU-cache experiment is removed.
# Injustice was stable in R2 and regressed to R6025 only after R3. Keep all
# DXMT resource-option instructions pristine while retaining the GTA window fix.

def u32(off): return struct.unpack_from("<I",d,off)[0]
def put32(off,v): struct.pack_into("<I",d,off,v)
def enc_b(pc,target):
    delta=target-pc
    if delta%4: raise SystemExit("unaligned B target")
    imm=delta//4
    if not (-(1<<25)<=imm<(1<<25)): raise SystemExit("B out of range")
    return 0x14000000 | (imm & 0x03ffffff)
def enc_bl(pc,target):
    delta=target-pc
    if delta%4: raise SystemExit("unaligned BL target")
    imm=delta//4
    if not (-(1<<25)<=imm<(1<<25)): raise SystemExit("BL out of range")
    return 0x94000000 | (imm & 0x03ffffff)
def enc_cbz_x(rt,pc,target):
    delta=target-pc
    if delta%4: raise SystemExit("unaligned CBZ target")
    imm=delta//4
    if not (-(1<<18)<=imm<(1<<18)): raise SystemExit("CBZ out of range")
    return 0xB4000000 | ((imm & 0x7ffff)<<5) | rt
def enc_cbnz_x(rt,pc,target):
    delta=target-pc
    if delta%4: raise SystemExit("unaligned CBNZ.X target")
    imm=delta//4
    if not (-(1<<18)<=imm<(1<<18)): raise SystemExit("CBNZ.X out of range")
    return 0xB5000000 | ((imm & 0x7ffff)<<5) | rt
def enc_cbz_w(rt,pc,target):
    delta=target-pc
    if delta%4: raise SystemExit("unaligned CBZ.W target")
    imm=delta//4
    if not (-(1<<18)<=imm<(1<<18)): raise SystemExit("CBZ.W out of range")
    return 0x34000000 | ((imm & 0x7ffff)<<5) | rt
def enc_cbnz_w(rt,pc,target):
    delta=target-pc
    if delta%4: raise SystemExit("unaligned CBNZ.W target")
    imm=delta//4
    if not (-(1<<18)<=imm<(1<<18)): raise SystemExit("CBNZ.W out of range")
    return 0x35000000 | ((imm & 0x7ffff)<<5) | rt
def enc_bcond(cond,pc,target):
    delta=target-pc
    if delta%4: raise SystemExit("unaligned B.cond target")
    imm=delta//4
    if not (-(1<<18)<=imm<(1<<18)): raise SystemExit("B.cond out of range")
    return 0x54000000 | ((imm & 0x7ffff)<<5) | cond
def enc_tbnz_w(rt,bit,pc,target):
    delta=target-pc
    if delta%4: raise SystemExit("unaligned TBNZ target")
    imm=delta//4
    if not (-(1<<13)<=imm<(1<<13)): raise SystemExit("TBNZ out of range")
    if not (0 <= bit < 32): raise SystemExit("TBNZ bit out of range")
    return 0x37000000 | ((bit & 0x1f)<<19) | ((imm & 0x3fff)<<5) | rt

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
if u32(DIRECT_SURFACE_REGISTER_SITE) != 0x34000128:
    raise SystemExit(f"unexpected direct-surface register gate {u32(DIRECT_SURFACE_REGISTER_SITE):#010x}")
if u32(DIRECT_SURFACE_FRAME_SITE) != 0x34000228:
    raise SystemExit(f"unexpected direct-surface frame gate {u32(DIRECT_SURFACE_FRAME_SITE):#010x}")
if u32(DIRECT_COMPOSITOR_GATE_SITE) != 0xD000FDC0:
    raise SystemExit(f"unexpected direct-compositor gate {u32(DIRECT_COMPOSITOR_GATE_SITE):#010x}")
if d[DIRECT_SURFACE_LOG_SITE:DIRECT_SURFACE_LOG_SITE+len(DIRECT_SURFACE_LOG_OLD)] != DIRECT_SURFACE_LOG_OLD:
    raise SystemExit("unexpected direct-surface log literal")
if u32(TOUCH_SLOT_OPTIN_SITE) != 0x360024E0:
    raise SystemExit(f"unexpected touch early-slot opt-in branch {u32(TOUCH_SLOT_OPTIN_SITE):#010x}")
if u32(TOUCH_SLOT_ARG_SITE) != 0xB9425E60:
    raise SystemExit(f"unexpected touch reserve argument load {u32(TOUCH_SLOT_ARG_SITE):#010x}")
if u32(TOUCH_VISIBLE_SITE) != 0x12000100:
    raise SystemExit(f"unexpected touch-controls visible assignment {u32(TOUCH_VISIBLE_SITE):#010x}")
if u32(WOW64_SECTION_UNMAP_SITE) != 0x3748034A:
    raise SystemExit(f"unexpected NtUnmapViewOfSection system-view branch {u32(WOW64_SECTION_UNMAP_SITE):#010x}")
if d[WOW64_SECTION_UNMAP_CAVE:WOW64_SECTION_UNMAP_CAVE+WOW64_SECTION_UNMAP_CAVE_SIZE] != b"\0"*WOW64_SECTION_UNMAP_CAVE_SIZE:
    raise SystemExit("WOW64 section-quarantine cave is not zero-filled")
if d[WOW64_SECTION_MARKER_SITE:WOW64_SECTION_MARKER_SITE+len(WOW64_SECTION_MARKER)] != b"\0"*len(WOW64_SECTION_MARKER):
    raise SystemExit("WOW64 section-quarantine marker space is not zero-filled")
if u32(INJUSTICE_HOLE_SITE) != 0x34000E6B:
    raise SystemExit(f"unexpected Injustice bus unreadable branch {u32(INJUSTICE_HOLE_SITE):#010x}")
if d[INJUSTICE_HOLE_CAVE:INJUSTICE_HOLE_CAVE+INJUSTICE_HOLE_CAVE_SIZE] != b"\0"*INJUSTICE_HOLE_CAVE_SIZE:
    raise SystemExit("Injustice guest-hole cave is not zero-filled")
if d[INJUSTICE_HOLE_MARKER_SITE:INJUSTICE_HOLE_MARKER_SITE+len(INJUSTICE_HOLE_MARKER)] != b"\0"*len(INJUSTICE_HOLE_MARKER):
    raise SystemExit("Injustice guest-hole marker space is not zero-filled")
if u32(D3D9_GTA_MODE_WIDTH_SITE) != 1152 or u32(D3D9_GTA_MODE_HEIGHT_SITE) != 648:
    raise SystemExit(f"unexpected D3D9 tail mode {u32(D3D9_GTA_MODE_WIDTH_SITE)}x{u32(D3D9_GTA_MODE_HEIGHT_SITE)}")
if u32(D3D9_GTA_RESET_LOSABLE_GATE_SITE) != 0x35001B28:
    raise SystemExit(f"unexpected D3D9 Reset losable-resource gate {u32(D3D9_GTA_RESET_LOSABLE_GATE_SITE):#010x}")
if u32(D3D9_WINDOW_LAYER_GATE_SITE) != 0x34000780:
    raise SystemExit(f"unexpected Metal per-window branch gate {u32(D3D9_WINDOW_LAYER_GATE_SITE):#010x}")
if u32(GTA_BLIT_SRC_SITE) != 0xF9400328 or u32(GTA_BLIT_SRC_SITE+4) != 0xF940211A:
    raise SystemExit(f"unexpected D3D9 Copy source dereference {u32(GTA_BLIT_SRC_SITE):#010x} {u32(GTA_BLIT_SRC_SITE+4):#010x}")
if u32(GTA_BLIT_DST_SITE) != 0xF9400728 or u32(GTA_BLIT_DST_SITE+4) != 0xF940211A:
    raise SystemExit(f"unexpected D3D9 Copy destination dereference {u32(GTA_BLIT_DST_SITE):#010x} {u32(GTA_BLIT_DST_SITE+4):#010x}")
if d[GTA_BLIT_SRC_CAVE:GTA_BLIT_CAVE_END] != b"\0"*(GTA_BLIT_CAVE_END-GTA_BLIT_SRC_CAVE):
    raise SystemExit("GTA D3D9 blit guard cave is not zero-filled")
if d[GTA_BLIT_MARKER_SITE:GTA_BLIT_MARKER_SITE+len(GTA_BLIT_MARKER)] != b"\0"*len(GTA_BLIT_MARKER):
    raise SystemExit("GTA D3D9 blit guard marker space is not zero-filled")

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

# Software renderer: allow pCreateWindowSurface so Pokemon/mkxp-z can present.
# Keep the pristine frame/geometry gate so a D3D9 Metal game (Injustice/L4D)
# does not get the green GDI compositor layered above its healthy Metal view.
put32(DIRECT_SURFACE_REGISTER_SITE,0xD503201F)
# clayton-21: R3 proved the GTA CAMetalLayer is created for hwnd=0x20030 but
# with frame 0x0. The missing half is this direct-mode geometry callback:
# winios_drv_window_pos_changed skipped winios_window_frame unless
# MADEIRA_DESKTOP=1. Allow the callback so the per-HWND Metal sublayer receives
# the real client rect and becomes visible. This does not enable the GDI
# surface-create path globally; it only forwards geometry.
put32(DIRECT_SURFACE_FRAME_SITE,0xD503201F)

# Final missing link: bypass only winios_ensure_compositor's desktop-env probe.
# At 0x1f6d4 the pristine binary starts loading "MADEIRA_DESKTOP". Branch
# directly to the code that creates/finds the UIWindow and compositor instead.
# This does NOT modify the environment variable, so ContentView/direct input
# still sees a normal direct-game session.
put32(DIRECT_COMPOSITOR_GATE_SITE,enc_b(DIRECT_COMPOSITOR_GATE_SITE,DIRECT_COMPOSITOR_CONTINUE))

d[DIRECT_SURFACE_LOG_SITE:DIRECT_SURFACE_LOG_SITE+len(DIRECT_SURFACE_LOG_OLD)] = \
    DIRECT_SURFACE_LOG_NEW + b"\0" * (len(DIRECT_SURFACE_LOG_OLD)-len(DIRECT_SURFACE_LOG_NEW))

# Touch controls / XInput session bootstrap.
put32(TOUCH_SLOT_OPTIN_SITE,0xD503201F)  # nop: no MADEIRA_PAD_EARLY_SLOT opt-in required
put32(TOUCH_SLOT_ARG_SITE,0x52800020)    # mov w0,#1: touch-capable player 1
put32(TOUCH_VISIBLE_SITE,0x52800020)     # mov w0,#1: controls.visible = true at begin()

# clayton-14: keep ONLY the exact fight-load view proven stale by the
# successful Injustice run: guest 0x3c680000 -> host 0x43c680000, size 1 MiB.
# The previous 1MiB-wide filter was intentionally conservative but can retain
# unrelated mappings. This exact-address filter preserves normal lifetime for
# every other view and therefore avoids contaminating startup / C++ objects.
q=WOW64_SECTION_UNMAP_CAVE
qcode=[
    enc_tbnz_w(10,9,q+0x00,q+0x30),      # original VPROT_SYSTEM -> system path
    0xF940126B,                           # ldr x11,[x19,#0x20] (view->size)
    0xF144017F,                           # cmp x11,#0x100,lsl#12 (1 MiB)
    enc_bcond(1,q+0x0c,q+0x34),           # b.ne normal
    0xD360FD0C,                           # lsr x12,x8,#32
    0xD360FE4D,                           # lsr x13,x18,#32
    0xEB0D019F,                           # cmp x12,x13
    enc_bcond(1,q+0x1c,q+0x34),           # b.ne normal
    0x52A78D0C,                           # movz w12,#0x3c68,lsl#16
    0x6B0C011F,                           # cmp w8,w12 (guest low32 == 0x3c680000?)
    enc_bcond(1,q+0x28,q+0x34),           # b.ne local normal path (B.cond range-safe)
    enc_b(q+0x2c,0x97eb68),               # exact match -> long B to success + unlock
    enc_b(q+0x30,0x97eab4),               # pristine VPROT_SYSTEM path
    enc_b(q+0x34,0x97ea50),               # pristine normal path
]
put32(WOW64_SECTION_UNMAP_SITE,enc_b(WOW64_SECTION_UNMAP_SITE,q))
for i,ins in enumerate(qcode): put32(q+i*4,ins)
d[WOW64_SECTION_MARKER_SITE:WOW64_SECTION_MARKER_SITE+len(WOW64_SECTION_MARKER)] = WOW64_SECTION_MARKER

# clayton-26: heal the REAL first Injustice failure, before its UE3 crash
# handler turns the C0000005 into the visible MSVC R6025 dialog.
h=INJUSTICE_HOLE_CAVE
hcode=[
    enc_cbnz_w(11,h+0x00,h+0x08),            # unreadable probe -> compatibility checks
    enc_b(h+0x04,BUS_READABLE_PATH),          # readable probe -> pristine path (long B)
    0xF9400E88,                               # ldr x8,[x20,#0x18] = siginfo->si_addr
    0x52A2AAE9,                               # mov w9,#0x15570000
    0x6B09011F,                               # cmp w8,w9 (guest offset)
    enc_bcond(1,h+0x14,h+0x44),               # b.ne -> local normal stub
    0xD360FD0A,                               # lsr x10,x8,#32 (WoW64 host window id)
    0xF100115F,                               # cmp x10,#4
    enc_bcond(3,h+0x20,h+0x44),               # b.lo -> normal
    0xF1001D5F,                               # cmp x10,#7
    enc_bcond(2,h+0x28,h+0x44),               # b.hs -> normal (accept only 4,5,6)
    0xAA0803E0,                               # mov x0,x8 (region base)
    0xB27107E1,                               # mov x1,#0x18000
    0x52800062,                               # mov w2,#3 (PROT_READ|PROT_WRITE)
    enc_bl(h+0x38,MPROTECT_STUB),             # mprotect(base,0x18000,RW)
    enc_cbnz_w(0,h+0x3c,h+0x44),              # failure -> local normal stub
    enc_b(h+0x40,BUS_RESUME_PATH),            # success -> fix x18 + return/retry
    enc_b(h+0x44,BUS_UNREADABLE_NORMAL),      # pristine unreadable path
]
put32(INJUSTICE_HOLE_SITE,enc_b(INJUSTICE_HOLE_SITE,h))
for i,ins in enumerate(hcode): put32(h+i*4,ins)
d[INJUSTICE_HOLE_MARKER_SITE:INJUSTICE_HOLE_MARKER_SITE+len(INJUSTICE_HOLE_MARKER)] = INJUSTICE_HOLE_MARKER

# R8: DO NOT rewrite the adapter-mode table and DO NOT bypass the native
# losable-resource Reset guard. Both locations were validated pristine above.

# GTA IV's Wine client/compositor exists and follows its mode changes. Keep
# DXMT's CAMetalLayer in that SAME hwnd instead of returning
# the unrelated fullscreen singleton. NOP the cbz after madeira_desktop_mode():
# both desktop and direct-game sessions enter the existing per-window path.
put32(D3D9_WINDOW_LAYER_GATE_SITE,0xD503201F)

# R8.1 exact native crash guard. Both trampolines replay the original wrapper
# load, reject only NULL / >=64-GiB impossible wrapper addresses, then replay
# the original allocation load. A valid pointer returns immediately after the
# two overwritten instructions. A corrupt pointer marks the blit pass active
# and rejoins the existing Copy-case tail, skipping only this poisoned op.
src=GTA_BLIT_SRC_CAVE
src_skip=src+0x1c
src_code=[
    0xF9400328,                               # ldr x8,[x25]
    enc_cbz_x(8,src+0x04,src_skip),
    0xD364FD09,                               # lsr x9,x8,#36
    enc_cbnz_x(9,src+0x0c,src_skip),
    0xF940211A,                               # ldr x26,[x8,#0x40]
    enc_cbz_x(26,src+0x14,src_skip),
    enc_b(src+0x18,GTA_BLIT_SRC_CONT),
    0x5280005B,                               # mov w27,#2 (Blit)
    enc_b(src+0x20,GTA_BLIT_SKIP),
]
dst=GTA_BLIT_DST_CAVE
dst_skip=dst+0x1c
dst_code=[
    0xF9400728,                               # ldr x8,[x25,#8]
    enc_cbz_x(8,dst+0x04,dst_skip),
    0xD364FD09,                               # lsr x9,x8,#36
    enc_cbnz_x(9,dst+0x0c,dst_skip),
    0xF940211A,                               # ldr x26,[x8,#0x40]
    enc_cbz_x(26,dst+0x14,dst_skip),
    enc_b(dst+0x18,GTA_BLIT_DST_CONT),
    0x5280005B,                               # mov w27,#2 (Blit)
    enc_b(dst+0x20,GTA_BLIT_SKIP),
]
put32(GTA_BLIT_SRC_SITE,enc_b(GTA_BLIT_SRC_SITE,src))
put32(GTA_BLIT_DST_SITE,enc_b(GTA_BLIT_DST_SITE,dst))
for i,ins in enumerate(src_code): put32(src+i*4,ins)
for i,ins in enumerate(dst_code): put32(dst+i*4,ins)
d[GTA_BLIT_MARKER_SITE:GTA_BLIT_MARKER_SITE+len(GTA_BLIT_MARKER)] = GTA_BLIT_MARKER

# clayton-20: no DXMT resource-cache binary rewriting here. R2's original
# instructions are intentionally preserved to restore Injustice stability.

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
if struct.unpack_from("<I",e,DIRECT_SURFACE_REGISTER_SITE)[0] != 0xD503201F:
    raise SystemExit("direct-surface register gate patch mismatch")
if struct.unpack_from("<I",e,DIRECT_SURFACE_FRAME_SITE)[0] != 0xD503201F:
    raise SystemExit("direct-mode window geometry gate patch mismatch")
if struct.unpack_from("<I",e,DIRECT_COMPOSITOR_GATE_SITE)[0] != enc_b(DIRECT_COMPOSITOR_GATE_SITE,DIRECT_COMPOSITOR_CONTINUE):
    raise SystemExit("direct-compositor creation gate patch mismatch")
if DIRECT_SURFACE_LOG_NEW not in e:
    raise SystemExit("direct-surface runtime marker missing")
for off,want in {
    TOUCH_SLOT_OPTIN_SITE:0xD503201F,
    TOUCH_SLOT_ARG_SITE:0x52800020,
    TOUCH_VISIBLE_SITE:0x52800020,
}.items():
    got=struct.unpack_from("<I",e,off)[0]
    if got != want:
        raise SystemExit(f"touch-input patch mismatch at {off:#x}: {got:#010x} != {want:#010x}")
if struct.unpack_from("<I",e,WOW64_SECTION_UNMAP_SITE)[0] != enc_b(WOW64_SECTION_UNMAP_SITE,WOW64_SECTION_UNMAP_CAVE):
    raise SystemExit("WOW64 section-quarantine entry branch mismatch")
if e[WOW64_SECTION_MARKER_SITE:WOW64_SECTION_MARKER_SITE+len(WOW64_SECTION_MARKER)] != WOW64_SECTION_MARKER:
    raise SystemExit("WOW64 section-quarantine runtime marker missing")
if struct.unpack_from("<I",e,INJUSTICE_HOLE_SITE)[0] != enc_b(INJUSTICE_HOLE_SITE,INJUSTICE_HOLE_CAVE):
    raise SystemExit("Injustice guest-hole entry branch mismatch")
if e[INJUSTICE_HOLE_MARKER_SITE:INJUSTICE_HOLE_MARKER_SITE+len(INJUSTICE_HOLE_MARKER)] != INJUSTICE_HOLE_MARKER:
    raise SystemExit("Injustice guest-hole runtime marker missing")
if struct.unpack_from("<I",e,GTA_BLIT_SRC_SITE)[0] != enc_b(GTA_BLIT_SRC_SITE,GTA_BLIT_SRC_CAVE):
    raise SystemExit("GTA D3D9 Copy source guard entry branch mismatch")
if struct.unpack_from("<I",e,GTA_BLIT_DST_SITE)[0] != enc_b(GTA_BLIT_DST_SITE,GTA_BLIT_DST_CAVE):
    raise SystemExit("GTA D3D9 Copy destination guard entry branch mismatch")
if e[GTA_BLIT_MARKER_SITE:GTA_BLIT_MARKER_SITE+len(GTA_BLIT_MARKER)] != GTA_BLIT_MARKER:
    raise SystemExit("GTA D3D9 blit pointer guard runtime marker missing")
expected_h=[
    enc_cbnz_w(11,INJUSTICE_HOLE_CAVE+0x00,INJUSTICE_HOLE_CAVE+0x08),
    enc_b(INJUSTICE_HOLE_CAVE+0x04,BUS_READABLE_PATH),
    0xF9400E88,0x52A2AAE9,0x6B09011F,
    enc_bcond(1,INJUSTICE_HOLE_CAVE+0x14,INJUSTICE_HOLE_CAVE+0x44),
    0xD360FD0A,0xF100115F,
    enc_bcond(3,INJUSTICE_HOLE_CAVE+0x20,INJUSTICE_HOLE_CAVE+0x44),
    0xF1001D5F,
    enc_bcond(2,INJUSTICE_HOLE_CAVE+0x28,INJUSTICE_HOLE_CAVE+0x44),
    0xAA0803E0,0xB27107E1,0x52800062,
    enc_bl(INJUSTICE_HOLE_CAVE+0x38,MPROTECT_STUB),
    enc_cbnz_w(0,INJUSTICE_HOLE_CAVE+0x3c,INJUSTICE_HOLE_CAVE+0x44),
    enc_b(INJUSTICE_HOLE_CAVE+0x40,BUS_RESUME_PATH),
    enc_b(INJUSTICE_HOLE_CAVE+0x44,BUS_UNREADABLE_NORMAL),
]
got_h=[struct.unpack_from("<I",e,INJUSTICE_HOLE_CAVE+i*4)[0] for i in range(18)]
if got_h != expected_h:
    raise SystemExit("Injustice guest-hole trampoline read-back mismatch")
print("native-patch=PASS ProcessDebugObjectHandle ret_len low-page guard")
print("sync-default=PASS actual _madsync_enabled: absent inproc-sync enters ENABLED path; explicit inproc-sync=0 preserved")
print("steam-env-clean=PASS generic launch unsets SteamAppPath/SteamGameId/SteamAppId")
print("direct-surface=PASS rev=clayton-21 compositor remains present-driven while direct WindowPosChanged geometry is forwarded for per-HWND Metal")
print("touch-input=PASS rev=clayton-9 overlay visible at session start + early player-1 XInput reservation")
print("wow64-section-quarantine=PASS rev=clayton-14 only guest 0x3c680000 / host-window peer / size 1MiB is retained")
print("injustice-r6025-root=PASS rev=clayton-26 guest 0x15570000 anonymous 0x18000 PROT_NONE hole materialises RW and retries before secondary R6025")
print("d3d9-mode=PASS R8 official adapter tail mode 1152x648 preserved; no hard-coded GTA resolution")
if struct.unpack_from("<I",e,D3D9_WINDOW_LAYER_GATE_SITE)[0] != 0xD503201F:
    raise SystemExit("per-HWND Metal layer gate patch mismatch")
print("d3d9-reset=PASS R8 official losable-resource Reset guard preserved; no unsafe forced reset")
print("gta-window-metal=PASS rev=clayton-18 DXMT uses Winios per-HWND CAMetalLayer in direct-game sessions")
print("gta-window-geometry=PASS rev=clayton-21 direct-mode WindowPosChanged forwards the client rect to the per-HWND Metal layer")
print("gta-dxmt-blit-guard=PASS rev=clayton-27 exact FlushDrawBatch Copy source/destination dereferences reject impossible >=64GiB wrapper pointers and skip only the poisoned op")
print("dxmt-cpu-cache=REVERTED rev=clayton-20 R3 experiment removed; R2-stable resource-option instructions preserved")
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
    0x1bf28a4:0xD503201F,
    0x1bf3d40:0xD503201F,
    0x1f6d4:0x1400000D,
    0x403c80:0xD503201F,
    0x4526e0:0x52800020,
    0x579020:0x52800020,
    0x97ea4c:0x146C0533,
    0x22a47fc:1152,
    0x22a4800:648,
    0x1aade04:0x35001B28,
    0x1c724:0xD503201F,
    # clayton-20: verify the five R3 DXMT cache sites remain pristine.
    0xa55ef0:0xD2800005,
    0xa55f3c:0xAA0403E3,
    0xa539dc:0xAA1303E0,
    0xa603b4:0x94554B03,
    0xa60428:0x94554E0E,
}
for off,want in checks.items():
    got=struct.unpack_from("<I",d,off)[0]
    if got != want:
        raise SystemExit(f"native runtime patch lost after codesign at {off:#x}: {got:#010x} != {want:#010x}")
if b"[winios] clayton-12 software compositor on present only\n" not in d:
    raise SystemExit("clayton-12 runtime marker lost after codesign")
if b"clayton-14 injustice-exact-view-quarantine" not in d:
    raise SystemExit("clayton-14 runtime marker lost after codesign")
if b"clayton-27 gtaiv-dxmt-blit-pointer-guard" not in d:
    raise SystemExit("clayton-27 GTA blit pointer guard marker lost after codesign")
# Entry branches after signing (absolute targets are deterministic in the official image).
def enc_b(pc,target):
    delta=target-pc
    return 0x14000000 | ((delta//4) & 0x03ffffff)
if struct.unpack_from("<I",d,0x1ad7bb8)[0] != enc_b(0x1ad7bb8,0x2481220):
    raise SystemExit("GTA Copy source guard lost after codesign")
if struct.unpack_from("<I",d,0x1ad7bec)[0] != enc_b(0x1ad7bec,0x2481260):
    raise SystemExit("GTA Copy destination guard lost after codesign")
print("native-patch-after-codesign=PASS debug-object + madsync + Steam-env-clean + software-present compositor + direct window geometry + touch-controls/XInput + WOW64 section quarantine + per-HWND Metal + GTA DXMT blit pointer guard; R3 DXMT cache experiment absent")
PY

say "Install rebuilt GTA-aware i386 D3D9 shim"
D3D9_DLL="$APP/i386-windows/d3d9.dll"
D3D9_SHIM="$APP/i386-windows/d3d9shim.dll"
test -s "$PATCHED_D3D9_SHIM"
cp "$PATCHED_D3D9_SHIM" "$D3D9_DLL"
cp "$PATCHED_D3D9_SHIM" "$D3D9_SHIM"
python3 - "$D3D9_DLL" "$D3D9_SHIM" <<'PY' | tee -a "$REPORT"
import hashlib, pathlib, struct, subprocess, sys
markers=[
 b"[gtaiv-r8] detected GTAIV.exe; native Reset parameters remain application-owned",
 b"[gtaiv-r8] Reset passed through unchanged to keep render-target/depth-stencil dimensions coherent",
 b"clayton-25 default: native ARM64 first",
]
for raw in sys.argv[1:]:
    p=pathlib.Path(raw); d=p.read_bytes()
    if d[:2] != b"MZ": raise SystemExit(f"{p.name}: not PE")
    pe=struct.unpack_from("<I",d,0x3c)[0]
    if d[pe:pe+4] != b"PE\0\0": raise SystemExit(f"{p.name}: bad PE")
    if struct.unpack_from("<H",d,pe+4)[0] != 0x14c:
        raise SystemExit(f"{p.name}: expected i386")
    for m in markers:
        if m not in d: raise SystemExit(f"{p.name}: missing marker {m!r}")
    print(f"d3d9-r8={p.name} sha256={hashlib.sha256(d).hexdigest()} size={len(d)}")
print("d3d9-r8=PASS source-rebuilt shim; GTAIV Reset is application-owned, RT/DS coherence restored, guest Present sleep removed; native-first fallback preserved")
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
