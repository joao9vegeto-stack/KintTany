#!/bin/bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/out"
WORK="$ROOT/.madeirajon-work"
REPORT="$OUT/build-report.txt"
IPA_NAME="MadeiraJon-0.1.1-Source-LSE-Exclusive.ipa"
ZIP_NAME="MadeiraJon-0.1.1-Source-artifact.zip"

UPSTREAM_SHA="ca3183ea3dfb0fd706aff1bea2abb871b5d27aec"
FEX_SHA="26859e184ad90f0e811d7f8bbd943a4b1573a2c3"
WINE_SHA="4f5b19718f4de88ecc5cb0dc08b119497a67ba8f"
DXMT_SHA="a5e0cd3d41bf248fd1c030a2e1c515ba3522f4ef"
DOCK_SHA="3cadfbea700e4da4b04e331dd7ef1ba633dfacef"
LLVM_SHA="8dfdcc7b7bf66834a761bd8de445840ef68e4d1a"

rm -rf "$OUT" "$WORK"
mkdir -p "$OUT" "$WORK"
: > "$REPORT"

trap 'rc=$?; echo "FAILED rc=$rc command=$BASH_COMMAND" | tee -a "$REPORT"; exit $rc' ERR
say(){ printf '\n===== %s =====\n' "$*"; }
rec(){ printf '%s\n' "$*" | tee -a "$REPORT"; }

JOBS="$(sysctl -n hw.ncpu 2>/dev/null || echo 4)"
[ "$JOBS" -le 6 ] || JOBS=6

rec "branch=MadeiraJon"
rec "head=$(git -C "$ROOT" rev-parse HEAD)"
rec "upstream-parent=$UPSTREAM_SHA"
rec "xcode=$(xcodebuild -version | tr '\n' ' ')"
rec "jobs=$JOBS"
test "$(git -C "$ROOT" rev-parse HEAD^)" = "$UPSTREAM_SHA" || rec "note=head has CI commit(s) after source-fix commit"
test "$(git -C "$ROOT/FEX" rev-parse HEAD)" = "$FEX_SHA"
test "$(git -C "$ROOT/wine" rev-parse HEAD)" = "$WINE_SHA"
test "$(git -C "$ROOT/dxmt" rev-parse HEAD)" = "$DXMT_SHA"
test "$(git -C "$ROOT/madeira-dock" rev-parse HEAD)" = "$DOCK_SHA"

grep -Fq "ios_mach_emulate_lse_rmw" "$ROOT/build/ntdll-unix/signal_arm64_ios.c"
grep -Fq "ios_mach_emulate_store_exclusive" "$ROOT/build/ntdll-unix/signal_arm64_ios.c"
grep -Fq "[lse-rmw-emul]" "$ROOT/build/ntdll-unix/signal_arm64_ios.c"
grep -Fq "[exclusive-store-emul]" "$ROOT/build/ntdll-unix/signal_arm64_ios.c"

say "Install build prerequisites"
brew install autoconf automake bison flex libtool llvm pkg-config meson ccache ninja cmake xz sevenzip
export PATH="$(brew --prefix bison)/bin:$(brew --prefix flex)/bin:$(brew --prefix llvm)/bin:$PATH"
hash -r

if ! xcrun --sdk iphoneos --find metal >/dev/null 2>&1; then
    xcodebuild -downloadComponent MetalToolchain
fi
METAL="$(xcrun --sdk iphoneos --find metal)"
METALLIB="$(xcrun --sdk iphoneos --find metallib)"
rec "metal=$METAL"

say "Install exact llvm-mingw"
mkdir -p "$ROOT/toolchains"
MINGW_TAR="$WORK/llvm-mingw.tar.xz"
MINGW_DIR="$ROOT/toolchains/llvm-mingw-20260421-ucrt-macos-universal"
if [ ! -d "$MINGW_DIR" ]; then
    curl -fL --retry 5 --retry-all-errors       "https://github.com/mstorsjo/llvm-mingw/releases/download/20260421/llvm-mingw-20260421-ucrt-macos-universal.tar.xz"       -o "$MINGW_TAR"
    echo "bd85a3975723815cef28dbbd2ca2cb0c926f6b348a12a0453f39f7af273cb3f7  $MINGW_TAR" | shasum -a 256 -c -
    tar -C "$ROOT/toolchains" -xf "$MINGW_TAR"
fi
export PATH="$MINGW_DIR/bin:$PATH"
arm64ec-w64-mingw32-clang --version | head -1 | tee -a "$REPORT"

say "Configure Wine native generated-header tree"
mkdir -p "$ROOT/wine/build-macos"
if [ ! -f "$ROOT/wine/build-macos/config.status" ]; then
(
  cd "$ROOT/wine/build-macos"
  ../configure     --without-x --without-vulkan --without-freetype --without-gnutls     --without-gstreamer --without-cups --without-gphoto --without-sane     --without-opencl --without-pcap --without-pcsclite --without-usb     --disable-tests
)
fi
make -C "$ROOT/wine/build-macos" -j"$JOBS" tools/widl/widl tools/winebuild/winebuild\nmake -C "$ROOT/wine/build-macos" -j"$JOBS" include

say "Configure ARM64EC Wine generated-header tree"
mkdir -p "$ROOT/wine/build-arm64ec"
if [ ! -f "$ROOT/wine/build-arm64ec/config.status" ]; then
(
  cd "$ROOT/wine/build-arm64ec"
  ../configure --enable-archs=arm64ec --without-x --disable-tests --enable-winegstreamer
)
fi
make -C "$ROOT/wine/build-arm64ec" -j"$JOBS" include || true
for h in dwrite.h dwrite_3.h mfobjects.h mftransform.h; do
    if [ ! -f "$ROOT/wine/build-arm64ec/include/$h" ]; then
        make -C "$ROOT/wine/build-arm64ec" -j"$JOBS" "include/$h" || true
    fi
    if [ ! -f "$ROOT/wine/build-arm64ec/include/$h" ] && [ -f "$ROOT/wine/build-macos/include/$h" ]; then
        cp "$ROOT/wine/build-macos/include/$h" "$ROOT/wine/build-arm64ec/include/$h"
    fi
    test -f "$ROOT/wine/build-arm64ec/include/$h"
done

say "Build GnuTLS, FFmpeg and FreeType from tracked/public source"
bash "$ROOT/build/gnutls-ios/build.sh"
bash "$ROOT/build/ffmpeg/build.sh"
rm -rf "$ROOT/research/freetype"
git clone --depth 1 --branch VER-2-13-3 https://github.com/freetype/freetype.git "$ROOT/research/freetype"
bash "$ROOT/build/freetype-ios/build.sh"

say "Build FEX iOS core from pinned source"
bash "$ROOT/build/fex-ios/build.sh"
test -f "$ROOT/FEX/build-ios/FEXCore/Source/libFEXCore.a"
test -f "$ROOT/FEX/build-ios/FEXCore/Source/libFEXCore_Base.a"

say "Build iOS wineserver base from Wine source"
WS="$ROOT/build/wineserver"
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
  -I"$ROOT/wine/include" -I"$ROOT/wine/include/wine"
  -I"$ROOT/wine/build-macos/include" -I"$WS" -I"$ROOT/wine/server"
  -I"$ROOT/build/ntdll-unix/shims" -I"$ROOT/build/madsync" -DHAVE_LINUX_NTSYNC_H=1
  -include "$WS/config_ios.h" -include stdarg.h -include "$WS/unicode_fix.h"
  -include "$WS/wineserver_ios_kill.h"
  -DBINDIR=\"/usr/local/bin\" -DDATADIR=\"/usr/local/share\"
  -D__WINESRC__ -DWINE_IOS=1 -Dmain=wineserver_main
  -Wno-implicit-function-declaration
)
for n in "${BASE_SERVER_FILES[@]}"; do
    echo "base wineserver: $n"
    xcrun -sdk iphoneos clang "${WS_FLAGS[@]}" -c "$ROOT/wine/server/$n.c" -o "$WOBJ/$n.o"
done
ar rcs "$ROOT/app/Madeira/libwineserver.a" "$WOBJ"/*.o
rm -f "$WOBJ/libwineserver.a"
bash "$ROOT/build/wineserver/build.sh"
test -f "$ROOT/app/Madeira/libwineserver.a"

say "Build Win32u and corrected ntdll unix archives"
rm -rf "$ROOT/build/win32u-unix/obj" "$ROOT/build/ntdll-unix/obj"
bash "$ROOT/build/win32u-unix/build.sh"
bash "$ROOT/build/ntdll-unix/build.sh"
test -f "$ROOT/app/Madeira/libwin32u_unix.a"
test -f "$ROOT/app/Madeira/libntdll_unix.a"
strings "$ROOT/app/Madeira/libntdll_unix.a" | grep -F "[lse-rmw-emul]" | tee -a "$REPORT"
strings "$ROOT/app/Madeira/libntdll_unix.a" | grep -F "[exclusive-store-emul]" | tee -a "$REPORT"

say "Build full i386 Wine/DXMT WoW64 farm from source"
export JOBS
rm -rf "$ROOT/app/Madeira/i386-windows"
mkdir -p "$ROOT/app/Madeira/i386-windows"
bash "$ROOT/build/wine-i386/build.sh"
test -f "$ROOT/app/Madeira/i386-windows/ntdll.dll"
test -f "$ROOT/app/Madeira/i386-windows/d3d9.dll"
test -f "$ROOT/app/Madeira/i386-windows/d3d9-emulated.dll"
rec "i386-files=$(find "$ROOT/app/Madeira/i386-windows" -maxdepth 1 -type f | wc -l | tr -d ' ')"

say "Build FEX WoW64 backend from pinned source"
bash "$ROOT/build/fex-wow64/build.sh"
test -f "$ROOT/app/Madeira/aarch64-windows/xtajit.dll"

say "Build recorded LLVM 15 iOS static libraries"
LLVM_SRC="$ROOT/toolchains/llvm-project"
LLVM_HOST="$ROOT/toolchains/llvm-host-build"
LLVM_IOS="$ROOT/toolchains/llvm-ios-build"
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
    p.write_text(s.replace('MATCHES "Darwin"', 'MATCHES "Darwin|iOS"'))
PY

cmake -S "$LLVM_SRC/llvm" -B "$LLVM_HOST" -G Ninja   -DCMAKE_BUILD_TYPE=Release   -DLLVM_TARGETS_TO_BUILD= -DLLVM_ENABLE_PROJECTS=   -DLLVM_INCLUDE_TESTS=OFF -DLLVM_INCLUDE_EXAMPLES=OFF   -DLLVM_INCLUDE_BENCHMARKS=OFF -DLLVM_ENABLE_ZLIB=OFF   -DLLVM_ENABLE_ZSTD=OFF -DLLVM_ENABLE_TERMINFO=OFF -DLLVM_ENABLE_LIBXML2=OFF
cmake --build "$LLVM_HOST" --target llvm-tblgen -j"$JOBS"

cmake -S "$LLVM_SRC/llvm" -B "$LLVM_IOS" -G Ninja   -DCMAKE_SYSTEM_NAME=iOS   -DCMAKE_OSX_ARCHITECTURES=arm64   -DCMAKE_OSX_SYSROOT=iphoneos   -DCMAKE_OSX_DEPLOYMENT_TARGET=17.0   -DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY   -DCMAKE_BUILD_TYPE=Release   -DLLVM_HOST_TRIPLE=arm64-apple-ios17.0   -DLLVM_DEFAULT_TARGET_TRIPLE=arm64-apple-ios17.0   -DLLVM_TARGET_ARCH=host   -DLLVM_TARGETS_TO_BUILD= -DLLVM_ENABLE_PROJECTS=   -DLLVM_BUILD_TOOLS=OFF -DLLVM_BUILD_UTILS=OFF   -DLLVM_INCLUDE_TESTS=OFF -DLLVM_INCLUDE_EXAMPLES=OFF   -DLLVM_INCLUDE_BENCHMARKS=OFF -DLLVM_INCLUDE_DOCS=OFF   -DLLVM_ENABLE_ZLIB=OFF -DLLVM_ENABLE_ZSTD=OFF   -DLLVM_ENABLE_TERMINFO=OFF -DLLVM_ENABLE_LIBXML2=OFF   -DLLVM_TABLEGEN="$LLVM_HOST/bin/llvm-tblgen"
cmake --build "$LLVM_IOS" -j"$JOBS"
test -f "$LLVM_IOS/lib/libLLVMCore.a"

say "Build DXMT native iOS side and combine with LLVM"
export MADEIRA_ALLOW_NO_D3D12=1
bash "$ROOT/build/dxmt-ios/build.sh"
test -f "$ROOT/build/dxmt-ios/libdxmt_unix.a"
xcrun -sdk iphoneos libtool -static   -o "$ROOT/app/Madeira/libdxmt_combined.a"   "$ROOT/build/dxmt-ios/libdxmt_unix.a" "$LLVM_IOS/lib/"*.a
test -f "$ROOT/app/Madeira/libdxmt_combined.a"
rec "libdxmt_combined=$(wc -c < "$ROOT/app/Madeira/libdxmt_combined.a" | tr -d ' ')"

say "Preserve D3D9 command metallib compiled as Metal 3.2"
"$METAL" -std=metal3.2 -mios-version-min=18.0 -Os   -c "$ROOT/dxmt/src/dxmt/dxmt_command.metal" -o "$WORK/dxmt_command.air"
"$METALLIB" "$WORK/dxmt_command.air" -o "$WORK/dxmt_command.metallib"
python3 "$ROOT/ci/patch-d3d9-msl32.py"   "$ROOT/app/Madeira/i386-windows/d3d9-emulated.dll"   "$WORK/dxmt_command.metallib"   "$OUT/d3d9-metal32-report.txt"

say "Prepare source-defined resources"
mkdir -p "$ROOT/app/Madeira/x86_64-vcruntime"
# Microsoft VC runtime files are intentionally not part of Madeira source and
# are not required for the 32-bit Expendabros path. Keep the folder present so
# Xcode's resource reference resolves, without borrowing anything from an IPA.
touch "$ROOT/app/Madeira/x86_64-vcruntime/.source-build-placeholder"
bash "$ROOT/build/stage-licenses.sh"

say "Build Madeira Debug app from source"
rm -rf "$WORK/DerivedData"
xcodebuild   -project "$ROOT/app/Madeira.xcodeproj"   -scheme Madeira   -configuration Debug   -destination 'generic/platform=iOS'   -derivedDataPath "$WORK/DerivedData"   CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO DEVELOPMENT_TEAM=""   build | tee "$WORK/xcodebuild.log"

APP="$(find "$WORK/DerivedData/Build/Products" -type d -name Madeira.app -path '*Debug-iphoneos*' -print -quit)"
test -n "$APP"
test -f "$APP/Madeira.debug.dylib"
test -f "$APP/i386-windows/d3d9-emulated.dll"
strings "$APP/Madeira.debug.dylib" | grep -F "[lse-rmw-emul]" | tee -a "$REPORT"
strings "$APP/Madeira.debug.dylib" | grep -F "[exclusive-store-emul]" | tee -a "$REPORT"
rec "runtime-markers=PASS"
rec "wow64-d3d9=PASS"

say "Ad-hoc sign with source Madeira entitlements"
while IFS= read -r -d '' f; do
  /usr/bin/codesign --force --sign - --timestamp=none "$f"
done < <(find "$APP" -type f -name '*.dylib' -print0)
/usr/bin/codesign --force --sign - --timestamp=none   --entitlements "$ROOT/app/Madeira/Madeira.entitlements" "$APP"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$APP"
plutil -lint "$ROOT/app/Madeira/Madeira.entitlements"
cp "$ROOT/app/Madeira/Madeira.entitlements" "$OUT/Madeira.entitlements"

say "Package IPA"
rm -rf "$WORK/package"
mkdir -p "$WORK/package/Payload"
cp -R "$APP" "$WORK/package/Payload/"
(
  cd "$WORK/package"
  ditto -c -k --sequesterRsrc --keepParent Payload "$OUT/$IPA_NAME"
)
test -s "$OUT/$IPA_NAME"
IPA_SHA="$(shasum -a 256 "$OUT/$IPA_NAME" | awk '{print $1}')"
rec "ipa=$IPA_NAME"
rec "ipa-sha256=$IPA_SHA"
rec "signal-source-sha256=$(shasum -a 256 "$ROOT/build/ntdll-unix/signal_arm64_ios.c" | awk '{print $1}')"
rec "status=SUCCESS"
cp "$WORK/xcodebuild.log" "$OUT/xcodebuild.log"

(
  cd "$OUT"
  zip -0 "$ZIP_NAME" "$IPA_NAME" build-report.txt d3d9-metal32-report.txt Madeira.entitlements
)
rec "artifact-zip=$ZIP_NAME"
cat "$REPORT"
