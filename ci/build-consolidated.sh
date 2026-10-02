#!/bin/bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$ROOT/work"
SRC="$WORK/Madeira-src"
OUT="$WORK/output"
REPORT="$WORK/build-report.txt"
TEST_REPORT="$WORK/test-results.txt"
UPSTREAM_SHA="ca3183ea3dfb0fd706aff1bea2abb871b5d27aec"
FEX_SHA="26859e184ad90f0e811d7f8bbd943a4b1573a2c3"
WINE_SHA="4f5b19718f4de88ecc5cb0dc08b119497a67ba8f"
DXMT_SHA="a5e0cd3d41bf248fd1c030a2e1c515ba3522f4ef"
DOCK_SHA="3cadfbea700e4da4b04e331dd7ef1ba633dfacef"
LLVM_SHA="8dfdcc7b7bf66834a761bd8de445840ef68e4d1a"
OFFICIAL_IPA_SHA="045aeb8fd4c71c2e6a78fb4511f94c56f8ed7af14c47a3b0ea2937a4fc8bfcee"
IPA_NAME="Madeira-0.1.1-Consolidated-LSE.ipa"
ZIP_NAME="Madeira-0.1.1-Consolidated-LSE-artifact.zip"

mkdir -p "$WORK" "$OUT"
: > "$REPORT"
: > "$TEST_REPORT"

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
if [ "$JOBS" -gt 6 ]; then JOBS=6; fi
record "branch=madeira011-consolidated"
record "upstream=$UPSTREAM_SHA"
record "jobs=$JOBS"
record "xcode=$(xcodebuild -version | tr '\n' ' ')"

say "Install deterministic build prerequisites"
brew install autoconf automake bison flex libtool llvm pkg-config meson ccache ninja cmake xz
export PATH="$(brew --prefix bison)/bin:$(brew --prefix flex)/bin:$(brew --prefix llvm)/bin:$PATH"
hash -r
bison --version | head -1 | tee -a "$REPORT"
flex --version | head -1 | tee -a "$REPORT"
clang --version | head -1 | tee -a "$REPORT"

if ! xcrun --sdk iphoneos --find metal >/dev/null 2>&1; then
    xcodebuild -downloadComponent MetalToolchain
fi
xcrun --sdk iphoneos --find metal | tee -a "$REPORT"

say "Clone exact Madeira 0.1.1 source and public submodules"
rm -rf "$SRC"
git clone --no-tags https://github.com/willfaust/Madeira.git "$SRC"
git -C "$SRC" checkout --detach "$UPSTREAM_SHA"
git -C "$SRC" submodule update --init --recursive
test "$(git -C "$SRC" rev-parse HEAD)" = "$UPSTREAM_SHA"
test "$(git -C "$SRC/FEX" rev-parse HEAD)" = "$FEX_SHA"
test "$(git -C "$SRC/wine" rev-parse HEAD)" = "$WINE_SHA"
test "$(git -C "$SRC/dxmt" rev-parse HEAD)" = "$DXMT_SHA"
test "$(git -C "$SRC/madeira-dock" rev-parse HEAD)" = "$DOCK_SHA"
record "FEX=$FEX_SHA"
record "wine=$WINE_SHA"
record "dxmt=$DXMT_SHA"
record "madeira-dock=$DOCK_SHA"

say "Overlay only the authoritative LSE source file"
cp "$ROOT/build/ntdll-unix/signal_arm64_ios.c" "$SRC/build/ntdll-unix/signal_arm64_ios.c"
git -C "$SRC" diff --check
DIFF_FILES="$(git -C "$SRC" diff --name-only)"
test "$DIFF_FILES" = "build/ntdll-unix/signal_arm64_ios.c"
grep -Fq "static int ios_mach_emulate_lse_rmw" "$SRC/build/ntdll-unix/signal_arm64_ios.c"
grep -Fq "[lse-rmw-emul]" "$SRC/build/ntdll-unix/signal_arm64_ios.c"
grep -Fq "ml629" "$SRC/build/ntdll-unix/signal_arm64_ios.c"
grep -Fq "ml626" "$SRC/build/ntdll-unix/signal_arm64_ios.c"
grep -Fq "[store-undecoded]" "$SRC/build/ntdll-unix/signal_arm64_ios.c"
python3 - <<'PY' | tee -a "$REPORT"
m=0x3f20fc00
assert (0xb8f50314 & m) == 0x38200000
assert (0xb8e40304 & m) == 0x38200000
assert (0xc80afec9 & m) != 0x38200000
print("mask-checks=PASS")
PY

say "Build and run the mandatory LSE semantic probe"
clang -std=c11 -O2 -Wall -Wextra -Werror "$ROOT/ci/lse-rmw-probe.c" -o "$WORK/lse-rmw-probe"
"$WORK/lse-rmw-probe" | tee -a "$TEST_REPORT"

say "Download official 0.1.1 only for preserved redistributable resources and entitlements"
curl -fL --retry 5 --retry-all-errors \
  "https://github.com/willfaust/Madeira/releases/download/v0.1.1/Madeira-0.1.1.ipa" \
  -o "$WORK/Madeira-0.1.1-official.ipa"
echo "$OFFICIAL_IPA_SHA  $WORK/Madeira-0.1.1-official.ipa" | shasum -a 256 -c -
rm -rf "$WORK/official"
mkdir -p "$WORK/official"
ditto -x -k "$WORK/Madeira-0.1.1-official.ipa" "$WORK/official"
OFFICIAL_APP="$WORK/official/Payload/Madeira.app"
test -d "$OFFICIAL_APP"
if [ -d "$OFFICIAL_APP/x86_64-vcruntime" ]; then
    rm -rf "$SRC/app/Madeira/x86_64-vcruntime"
    cp -R "$OFFICIAL_APP/x86_64-vcruntime" "$SRC/app/Madeira/"
fi
/usr/bin/codesign -d --entitlements :- "$OFFICIAL_APP" > "$WORK/original-entitlements.plist" 2>/dev/null
plutil -lint "$WORK/original-entitlements.plist"

say "Install exact llvm-mingw used by the Madeira build record"
mkdir -p "$SRC/toolchains" "$SRC/research"
MINGW_TAR="$WORK/llvm-mingw.tar.xz"
MINGW_DIR="$SRC/toolchains/llvm-mingw-20260421-ucrt-macos-universal"
if [ ! -d "$MINGW_DIR" ]; then
    curl -fL --retry 5 --retry-all-errors \
      "https://github.com/mstorsjo/llvm-mingw/releases/download/20260421/llvm-mingw-20260421-ucrt-macos-universal.tar.xz" \
      -o "$MINGW_TAR"
    echo "bd85a3975723815cef28dbbd2ca2cb0c926f6b348a12a0453f39f7af273cb3f7  $MINGW_TAR" | shasum -a 256 -c -
    tar -C "$SRC/toolchains" -xf "$MINGW_TAR"
fi
export PATH="$MINGW_DIR/bin:$PATH"
test -x "$MINGW_DIR/bin/arm64ec-w64-mingw32-clang"

say "Configure and build Wine host tree for generated headers/tools"
mkdir -p "$SRC/wine/build-macos"
if [ ! -f "$SRC/wine/build-macos/config.status" ]; then
  (
    cd "$SRC/wine/build-macos"
    ../configure \
      --without-x --without-vulkan --without-freetype --without-gnutls \
      --without-gstreamer --without-cups --without-gphoto --without-sane \
      --without-opencl --without-pcap --without-pcsclite --without-usb \
      --without-mingw --disable-tests
  )
fi
make -C "$SRC/wine/build-macos" -j"$JOBS"

say "Configure ARM64EC Wine header tree without replacing tracked PE payloads"
mkdir -p "$SRC/wine/build-arm64ec"
if [ ! -f "$SRC/wine/build-arm64ec/config.status" ]; then
  (
    cd "$SRC/wine/build-arm64ec"
    ../configure --enable-archs=arm64ec --without-x --disable-tests --enable-winegstreamer
  )
fi
make -C "$SRC/wine/build-arm64ec" -j"$JOBS" include || true
for h in dwrite.h dwrite_3.h; do
    if [ ! -f "$SRC/wine/build-arm64ec/include/$h" ]; then
        make -C "$SRC/wine/build-arm64ec" -j"$JOBS" "include/$h" || true
    fi
    if [ ! -f "$SRC/wine/build-arm64ec/include/$h" ] && [ -f "$SRC/wine/build-macos/include/$h" ]; then
        cp "$SRC/wine/build-macos/include/$h" "$SRC/wine/build-arm64ec/include/$h"
    fi
    test -f "$SRC/wine/build-arm64ec/include/$h"
done

say "Build GnuTLS, FFmpeg and FreeType iOS inputs"
bash "$SRC/build/gnutls-ios/build.sh"
bash "$SRC/build/ffmpeg/build.sh"
rm -rf "$SRC/research/freetype"
git clone --depth 1 --branch VER-2-13-3 https://github.com/freetype/freetype.git "$SRC/research/freetype"
bash "$SRC/build/freetype-ios/build.sh"

say "Build FEX iOS static libraries"
bash "$SRC/build/fex-ios/build.sh"
for f in \
  "$SRC/FEX/build-ios/FEXCore/Source/libFEXCore.a" \
  "$SRC/FEX/build-ios/FEXCore/Source/libFEXCore_Base.a"; do
    test -f "$f"
done

say "Bootstrap a source-built iOS wineserver base archive"
WS="$SRC/build/wineserver"
WOBJ="$WS/obj"
rm -rf "$WOBJ"
mkdir -p "$WOBJ"
SDK="$(xcrun --sdk iphoneos --show-sdk-path)"
BASE_SERVER_FILES=(
  atom change clipboard completion console d3dkmt debugger device directory
  file hook mailslot mutex named_pipe procfs ptrace registry serial signal
  symlink timer token trace
)
WS_FLAGS=(
  -arch arm64 -isysroot "$SDK" -miphoneos-version-min=17.0 -O2
  -I"$SRC/wine/include" -I"$SRC/wine/include/wine"
  -I"$SRC/wine/build-macos/include" -I"$WS" -I"$SRC/wine/server"
  -I"$SRC/build/ntdll-unix/shims" -I"$SRC/build/madsync" -DHAVE_LINUX_NTSYNC_H=1
  -include "$WS/config_ios.h" -include stdarg.h -include "$WS/unicode_fix.h"
  -include "$WS/wineserver_ios_kill.h"
  -DBINDIR=\"/usr/local/bin\" -DDATADIR=\"/usr/local/share\"
  -D__WINESRC__ -DWINE_IOS=1 -Dmain=wineserver_main
  -Wno-implicit-function-declaration
)
for n in "${BASE_SERVER_FILES[@]}"; do
    echo "base wineserver: $n"
    xcrun -sdk iphoneos clang "${WS_FLAGS[@]}" -c "$SRC/wine/server/$n.c" -o "$WOBJ/$n.o"
done
ar rcs "$SRC/app/Madeira/libwineserver.a" "$WOBJ"/*.o
rm -f "$WOBJ/libwineserver.a"
bash "$SRC/build/wineserver/build.sh"
test -f "$SRC/app/Madeira/libwineserver.a"

say "Build win32u and ntdll unix sides from source"
rm -rf "$SRC/build/win32u-unix/obj" "$SRC/build/ntdll-unix/obj"
bash "$SRC/build/win32u-unix/build.sh"
bash "$SRC/build/ntdll-unix/build.sh"
test -f "$SRC/app/Madeira/libwin32u_unix.a"
test -f "$SRC/app/Madeira/libntdll_unix.a"
strings "$SRC/app/Madeira/libntdll_unix.a" | grep -F "[lse-rmw-emul]" | tee -a "$REPORT"

say "Build exact recorded LLVM iOS libraries and recreate libdxmt_combined.a"
LLVM_SRC="$SRC/toolchains/llvm-project"
LLVM_HOST="$SRC/toolchains/llvm-host-build"
LLVM_IOS="$SRC/toolchains/llvm-ios-build"
rm -rf "$LLVM_SRC" "$LLVM_HOST" "$LLVM_IOS"
git clone --filter=blob:none --no-checkout https://github.com/llvm/llvm-project.git "$LLVM_SRC"
git -C "$LLVM_SRC" sparse-checkout init --cone
git -C "$LLVM_SRC" sparse-checkout set llvm cmake third-party
git -C "$LLVM_SRC" checkout --detach "$LLVM_SHA"
test "$(git -C "$LLVM_SRC" rev-parse HEAD)" = "$LLVM_SHA"
python3 - "$LLVM_SRC/llvm/cmake/modules/AddLLVM.cmake" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text()
if 'MATCHES "Darwin|iOS"' not in s:
    if 'MATCHES "Darwin"' not in s:
        raise SystemExit("AddLLVM Darwin match not found")
    s=s.replace('MATCHES "Darwin"', 'MATCHES "Darwin|iOS"')
    p.write_text(s)
PY
cmake -S "$LLVM_SRC/llvm" -B "$LLVM_HOST" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DLLVM_TARGETS_TO_BUILD= -DLLVM_ENABLE_PROJECTS= \
  -DLLVM_INCLUDE_TESTS=OFF -DLLVM_INCLUDE_EXAMPLES=OFF \
  -DLLVM_INCLUDE_BENCHMARKS=OFF -DLLVM_ENABLE_ZLIB=OFF
cmake --build "$LLVM_HOST" --target llvm-tblgen -j"$JOBS"
cmake -S "$LLVM_SRC/llvm" -B "$LLVM_IOS" -G Ninja \
  -DCMAKE_SYSTEM_NAME=iOS \
  -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DCMAKE_OSX_SYSROOT=iphoneos \
  -DCMAKE_OSX_DEPLOYMENT_TARGET=17.0 \
  -DCMAKE_BUILD_TYPE=Release \
  -DLLVM_HOST_TRIPLE=arm64-apple-ios17.0 \
  -DLLVM_DEFAULT_TARGET_TRIPLE=arm64-apple-ios17.0 \
  -DLLVM_TARGET_ARCH=host \
  -DLLVM_TARGETS_TO_BUILD= -DLLVM_ENABLE_PROJECTS= \
  -DLLVM_BUILD_TOOLS=OFF -DLLVM_INCLUDE_TESTS=OFF \
  -DLLVM_INCLUDE_EXAMPLES=OFF -DLLVM_INCLUDE_BENCHMARKS=OFF \
  -DLLVM_INCLUDE_DOCS=OFF -DLLVM_ENABLE_ZLIB=OFF \
  -DLLVM_TABLEGEN="$LLVM_HOST/bin/llvm-tblgen"
cmake --build "$LLVM_IOS" --target llvm-libraries -j"$JOBS"
test -f "$LLVM_IOS/lib/libLLVMCore.a"
xcrun -sdk iphoneos libtool -static \
  -o "$SRC/app/Madeira/libdxmt_combined.a" \
  "$SRC/app/libdxmt_unix.a" "$LLVM_IOS/lib/"*.a
test -f "$SRC/app/Madeira/libdxmt_combined.a"

say "Preserve the Consolidated D3D9 Metal 3.2 payload"
METAL="$(xcrun --sdk iphoneos --find metal)"
METALLIB="$(xcrun --sdk iphoneos --find metallib)"
"$METAL" -std=metal3.2 -mios-version-min=18.0 -Os \
  -c "$SRC/dxmt/src/dxmt/dxmt_command.metal" -o "$WORK/dxmt_command.air"
"$METALLIB" "$WORK/dxmt_command.air" -o "$WORK/dxmt_command.metallib"
python3 "$ROOT/ci/patch-d3d9-msl32.py" \
  "$SRC/app/Madeira/i386-windows/d3d9-emulated.dll" \
  "$WORK/dxmt_command.metallib" \
  "$WORK/d3d9-report.txt"
cat "$WORK/d3d9-report.txt" >> "$REPORT"

say "Run all repository host tests and record every result"
PASS=0
FAIL=0
TOTAL=0
for t in "$SRC"/tests/host/check-*.py; do
    TOTAL=$((TOTAL+1))
    name="$(basename "$t")"
    log="$WORK/test-$name.log"
    if (cd "$SRC" && python3 "$t") >"$log" 2>&1; then
        PASS=$((PASS+1))
        echo "PASS $name" | tee -a "$TEST_REPORT"
    else
        FAIL=$((FAIL+1))
        echo "FAIL $name" | tee -a "$TEST_REPORT"
        tail -80 "$log" >> "$TEST_REPORT" || true
    fi
done
record "host-tests total=$TOTAL pass=$PASS fail=$FAIL"
cat "$TEST_REPORT" >> "$REPORT"

say "Stage tracked licences and build the Debug iOS app"
bash "$SRC/build/stage-licenses.sh"
test -d "$SRC/app/Madeira/x86_64-vcruntime"
rm -rf "$WORK/DerivedData"
xcodebuild \
  -project "$SRC/app/Madeira.xcodeproj" \
  -scheme Madeira \
  -configuration Debug \
  -destination 'generic/platform=iOS' \
  -derivedDataPath "$WORK/DerivedData" \
  CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO \
  build | tee "$WORK/xcodebuild.log"

APP="$(find "$WORK/DerivedData/Build/Products" -type d -name Madeira.app -path '*Debug-iphoneos*' -print -quit)"
test -n "$APP"
test -f "$APP/Madeira.debug.dylib"
strings "$APP/Madeira.debug.dylib" | grep -F "[lse-rmw-emul]" | tee -a "$REPORT"
xcrun nm "$APP/Madeira.debug.dylib" | grep -F "ios_mach_emulate_lse_rmw" | tee -a "$REPORT" || true

say "Ad-hoc sign with the exact official 0.1.1 entitlements"
while IFS= read -r -d '' dylib; do
    /usr/bin/codesign --force --sign - --timestamp=none "$dylib"
done < <(find "$APP" -type f -name '*.dylib' -print0)
/usr/bin/codesign --force --sign - --timestamp=none \
  --entitlements "$WORK/original-entitlements.plist" "$APP"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$APP"
/usr/bin/codesign -d --entitlements :- "$APP" > "$WORK/final-entitlements.plist" 2>/dev/null
cmp "$WORK/original-entitlements.plist" "$WORK/final-entitlements.plist" || true

say "Package IPA and explicit artifact ZIP"
rm -rf "$WORK/package"
mkdir -p "$WORK/package/Payload"
cp -R "$APP" "$WORK/package/Payload/"
(
  cd "$WORK/package"
  ditto -c -k --sequesterRsrc --keepParent Payload "$OUT/$IPA_NAME"
)
test -s "$OUT/$IPA_NAME"
IPA_SHA="$(shasum -a 256 "$OUT/$IPA_NAME" | awk '{print $1}')"
record "ipa=$IPA_NAME"
record "ipa-sha256=$IPA_SHA"
record "source-overlay-sha256=$(shasum -a 256 "$ROOT/build/ntdll-unix/signal_arm64_ios.c" | awk '{print $1}')"
cp "$REPORT" "$OUT/build-report.txt"
cp "$TEST_REPORT" "$OUT/test-results.txt"
cp "$WORK/final-entitlements.plist" "$OUT/final-entitlements.plist"
(
  cd "$OUT"
  zip -0 "$ZIP_NAME" "$IPA_NAME" build-report.txt test-results.txt final-entitlements.plist
  unzip -l "$ZIP_NAME" | tee "$WORK/artifact-zip-list.txt"
)
cp "$WORK/artifact-zip-list.txt" "$OUT/artifact-zip-list.txt"
record "artifact-zip=$ZIP_NAME"
record "status=SUCCESS"
cat "$REPORT"
