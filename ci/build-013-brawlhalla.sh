#!/bin/bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$ROOT/work"
SRC="$WORK/Madeira-013-src"
OUT="$WORK/output"
REPORT="$WORK/build-report.txt"

UPSTREAM_SHA="4e9d45a74294cd820120791c4b3f2b79adf4fc70"
WINE_SHA="4f5b19718f4de88ecc5cb0dc08b119497a67ba8f"
OFFICIAL_IPA_SHA="71e900cbc140778bd6fa67c1062821981ed98e6bfb674d853cfeefd6d242e1c0"
VCREDIST_SHA="cc0ff0eb1dc3f5188ae6300faef32bf5beeba4bdd6e8e445a9184072096b713b"
LLVM_MINGW_SHA="bd85a3975723815cef28dbbd2ca2cb0c926f6b348a12a0453f39f7af273cb3f7"
IPA_NAME="Madeira-0.1.3-JITAlias-WaitWake.ipa"

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
record "strategy=official IPA + AIR FullChain + VC runtime + ProcessDebugObjectHandle guard + actual madsync + non-Steam Steam-env cleanup + PE RtlWaitOnAddress JIT-alias canonicalization"
record "jobs=$JOBS"
record "xcode=$(xcodebuild -version | tr '\n' ' ')"

say "Install minimal deterministic prerequisites"
brew install bison flex cabextract xz pkg-config
export PATH="$(brew --prefix bison)/bin:$(brew --prefix flex)/bin:$PATH"
hash -r
bison --version | head -1 | tee -a "$REPORT"
flex --version | head -1 | tee -a "$REPORT"
cabextract --version | head -1 | tee -a "$REPORT"

say "Clone exact official Madeira 0.1.3 and exact Wine submodule"
rm -rf "$SRC"
git clone --no-tags https://github.com/willfaust/Madeira.git "$SRC"
git -C "$SRC" checkout --detach "$UPSTREAM_SHA"
git -C "$SRC" submodule update --init wine
test "$(git -C "$SRC" rev-parse HEAD)" = "$UPSTREAM_SHA"
test "$(git -C "$SRC/wine" rev-parse HEAD)" = "$WINE_SHA"

say "Patch PE ntdll WaitOnAddress/WakeAddress to canonicalize JIT aliases"
python3 - "$SRC/wine/dlls/ntdll/sync.c" <<'PY' | tee -a "$REPORT"
import pathlib, sys
p=pathlib.Path(sys.argv[1])
t=p.read_text()
marker='futex-alias-canon rev=clayton-1'
if marker in t:
    raise SystemExit("alias patch marker already present in pristine Wine source")

needle='''static struct futex_queue *get_futex_queue( const void *addr )
{
    ULONG_PTR val = (ULONG_PTR)addr;
'''
insert='''static const char ios_futex_alias_canon_marker[] __attribute__((used)) =
    "futex-alias-canon rev=clayton-1";

/* madeira-log(9): the same logical Win32 wait word can be reached through the
 * JIT pool RX view or its RW alias.  RtlWaitOnAddress keys its waiter table by
 * the raw virtual address, so RX wait + RW wake becomes a permanently lost
 * wake even though both VAs name the same physical bytes.  The unix-side alias
 * probe already knows the authoritative RW view.  Canonicalise ONLY mapped JIT
 * aliases; ordinary addresses are untouched. */
static const void *ios_futex_canonical_addr( const void *addr )
{
    struct ios_jit_alias_probe_params pp;
    static LONG logged;

    if (!addr) return addr;
    memset( &pp, 0, sizeof(pp) );
    pp.size = sizeof(pp);
    pp.version = 1;
    pp.addr = (ULONG64)(ULONG_PTR)addr;
    WINE_UNIX_CALL( unix_ios_jit_alias_probe, &pp );
    if (pp.rw && pp.rw != (ULONG64)(ULONG_PTR)addr)
    {
        if (InterlockedIncrement( &logged ) <= 32)
            ERR( "[futex-alias] canonical %p -> %p slot=%u base=%s end=%s\\n",
                 addr, (void *)(ULONG_PTR)pp.rw, pp.slot,
                 wine_dbgstr_longlong(pp.base), wine_dbgstr_longlong(pp.end) );
        return (const void *)(ULONG_PTR)pp.rw;
    }
    return addr;
}

static struct futex_queue *get_futex_queue( const void *addr )
{
    ULONG_PTR val = (ULONG_PTR)addr;
'''
if t.count(needle)!=1: raise SystemExit(f"helper insertion anchor count={t.count(needle)}")
t=t.replace(needle,insert)

old='''{
    struct futex_queue *queue = get_futex_queue( addr );
    struct futex_entry entry;
    NTSTATUS ret;
'''
new='''{
    struct futex_queue *queue;
    struct futex_entry entry;
    NTSTATUS ret;

    addr = ios_futex_canonical_addr( addr );
    queue = get_futex_queue( addr );
'''
if t.count(old)!=1: raise SystemExit(f"RtlWaitOnAddress anchor count={t.count(old)}")
t=t.replace(old,new,1)

old='''{
    struct futex_queue *queue = get_futex_queue( addr );
    struct futex_entry *entry, *next;
    unsigned int count = 0;
'''
new='''{
    struct futex_queue *queue;
    struct futex_entry *entry, *next;
    unsigned int count = 0;

    addr = ios_futex_canonical_addr( addr );
    queue = get_futex_queue( addr );
'''
if t.count(old)!=1: raise SystemExit(f"RtlWakeAddressAll anchor count={t.count(old)}")
t=t.replace(old,new,1)

old='''{
    struct futex_queue *queue = get_futex_queue( addr );
    struct futex_entry *entry;
    DWORD tid = 0;
'''
new='''{
    struct futex_queue *queue;
    struct futex_entry *entry;
    DWORD tid = 0;

    addr = ios_futex_canonical_addr( addr );
    queue = get_futex_queue( addr );
'''
if t.count(old)!=1: raise SystemExit(f"RtlWakeAddressSingle anchor count={t.count(old)}")
t=t.replace(old,new,1)

p.write_text(t)
if t.count('ios_futex_canonical_addr( addr )') != 3:
    raise SystemExit("expected exactly three runtime canonicalization calls")
print("source-patch=PASS RtlWaitOnAddress + WakeAll + WakeSingle canonicalize JIT aliases to RW")
print("source-marker="+marker)
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

say "Configure the exact ARM64EC Wine tree"
B="$SRC/wine/build-arm64ec"
mkdir -p "$B"
(
  cd "$B"
  ../configure --enable-archs=arm64ec --without-x --disable-tests --enable-winegstreamer
)

say "Build the complete Wine system-DLL chain required by Brawlhalla Adobe AIR"
WINE_DLL_NAMES=(msi mscms cabinet sxs mspatcha odbccp32)
for mod in "${WINE_DLL_NAMES[@]}"; do
  echo "Building Wine ARM64EC module: $mod.dll"
  make -C "$B/dlls/$mod" -j"$JOBS"
done

say "Build patched ARM64EC PE ntdll"
make -C "$B/dlls/ntdll" -j"$JOBS"
NTDLL="$B/dlls/ntdll/arm64ec-windows/ntdll.dll"
test -s "$NTDLL"
strings "$NTDLL" | grep -F "futex-alias-canon rev=clayton-1" | tee -a "$REPORT"
python3 - "$NTDLL" <<'PY' | tee -a "$REPORT"
import hashlib,struct,sys
p=sys.argv[1]; d=open(p,'rb').read(); pe=struct.unpack_from('<I',d,0x3c)[0]
if d[pe:pe+4] != b'PE\0\0': raise SystemExit("patched ntdll: invalid PE")
m=struct.unpack_from('<H',d,pe+4)[0]
if m not in (0x8664,0xA641): raise SystemExit(f"patched ntdll machine={m:#x}")
print(f"patched-ntdll=PASS machine={m:#x} sha256={hashlib.sha256(d).hexdigest()} size={len(d)}")
PY

MSI="$B/dlls/msi/arm64ec-windows/msi.dll"
MSCMS="$B/dlls/mscms/arm64ec-windows/mscms.dll"
CABINET="$B/dlls/cabinet/arm64ec-windows/cabinet.dll"
SXS="$B/dlls/sxs/arm64ec-windows/sxs.dll"
MSPATCHA="$B/dlls/mspatcha/arm64ec-windows/mspatcha.dll"
ODBCCP32="$B/dlls/odbccp32/arm64ec-windows/odbccp32.dll"
WINE_DLL_PATHS=("$MSI" "$MSCMS" "$CABINET" "$SXS" "$MSPATCHA" "$ODBCCP32")

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

say "Inject patched ntdll and the complete Adobe AIR Wine DLL chain into the ARM64EC farm"
mkdir -p "$APP/arm64ec-windows"
cp "$NTDLL"    "$APP/arm64ec-windows/ntdll.dll"
cp "$MSI"      "$APP/arm64ec-windows/msi.dll"
cp "$MSCMS"    "$APP/arm64ec-windows/mscms.dll"
cp "$CABINET"  "$APP/arm64ec-windows/cabinet.dll"
cp "$SXS"      "$APP/arm64ec-windows/sxs.dll"
cp "$MSPATCHA" "$APP/arm64ec-windows/mspatcha.dll"
cp "$ODBCCP32" "$APP/arm64ec-windows/odbccp32.dll"

test -s "$APP/arm64ec-windows/ntdll.dll"
strings "$APP/arm64ec-windows/ntdll.dll" | grep -F "futex-alias-canon rev=clayton-1" | tee -a "$REPORT"
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
 app/'arm64ec-windows'/'ntdll.dll',
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
