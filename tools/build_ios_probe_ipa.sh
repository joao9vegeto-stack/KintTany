#!/usr/bin/env bash
# Build a genuine unsigned iPhone diagnostic IPA (no PS3 game or license).
set -euo pipefail
SDK="$(xcrun --sdk iphoneos --show-sdk-path)"
APP="ios-probe/Payload/AscensionRecompProbe.app"
mkdir -p "$APP"
cp ios/Probe-Info.plist "$APP/Info.plist"
# Compile guest-like register writes with a C compiler to preserve the
# public C ABI; clang++ treats .c inputs as C++ in its driver mode.
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -I upstream/libs/video -I upstream/include \
    -c ios/ARRSXMethodProbe.c -o ios-probe/ARRSXMethodProbe.o
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -I upstream/libs/video -I upstream/include \
    -c ios/ARGuestDrawProbe.c -o ios-probe/ARGuestDrawProbe.o
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -c ios/ARPrivateELFProbe.c \
    -o ios-probe/ARPrivateELFProbe.o
# M7.4: compile game-derived AOT only in a PRIVATE local macOS build.
# Public GitHub Actions never sets this variable or uploads private code.
AOT_OBJECTS=()
AOT_COMPILE_DEFINES=()
if [[ -n "${ASCENSION_PRIVATE_AOT_C:-}" ]]; then
  test -f "$ASCENSION_PRIVATE_AOT_C"
  xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
      -std=c11 -O2 -Wall -Wextra -Werror -Wno-unused-label \
      -I upstream/runtime/ppu -I runtime \
      -c "$ASCENSION_PRIVATE_AOT_C" -o ios-probe/AscensionPrivateAOT.o
  xcrun nm -g ios-probe/AscensionPrivateAOT.o | grep -q '_ar_private_aot_install_sha256'
  AOT_OBJECTS+=(ios-probe/AscensionPrivateAOT.o)
  AOT_COMPILE_DEFINES+=(-DASCENSION_PRIVATE_AOT_LINKED)
fi
# Stage the native PPU bridge as an ARM64 object and link the prebuilt
# IOS PPU core archive; never compile or bundle the user's PS3 ELF.
test -s ios-ppu-core/libAscensionPPUCore-ios-arm64.a
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror \
    -I upstream/runtime/ppu -I runtime \
    "${AOT_COMPILE_DEFINES[@]}" \
    -c ios/ARLivePPUBridge.c -o ios-probe/ARLivePPUBridge.o
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror \
    -I upstream/runtime/ppu -I runtime \
    -c ios/ARNativePPUContinuous.c -o ios-probe/ARNativePPUContinuous.o
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror \
    -I upstream/runtime/ppu -I runtime \
    -c ios/ARLivePPUContinuous.c -o ios-probe/ARLivePPUContinuous.o
xcrun nm -g ios-probe/ARLivePPUBridge.o | grep -q '_ar_m70_native_runtime_probe'
xcrun nm -g ios-probe/ARLivePPUContinuous.o | grep -q '_ar_m71_private_continuous_probe'
xcrun nm -g ios-probe/ARRSXMethodProbe.o | grep -q '_ar_probe_rsx_clear_flip'
xcrun --sdk iphoneos clang++ -target arm64-apple-ios17.0 \
    -isysroot "$SDK" -fobjc-arc -fmodules -stdlib=libc++ \
    -O2 -Wl,-dead_strip -I ios -I upstream/libs/video -I upstream/include \
    ios/ARMetalView.m ios/ARProbeApp.m ios/ARShaderProbe.m ios/ARTextureProbe.m ios/ARProbeGuestVM.c \
    ios-probe/ARRSXMethodProbe.o ios-probe/ARGuestDrawProbe.o ios-probe/ARPrivateELFProbe.o \
    ios-probe/ARLivePPUBridge.o ios-probe/ARLivePPUContinuous.o \
    ios-probe/ARNativePPUContinuous.o \
    "${AOT_OBJECTS[@]}" \
    ios-ppu-core/libAscensionPPUCore-ios-arm64.a \
    build-ios-runtime/libAscensionRSXGuest-ios-arm64.a \
    -framework UIKit -framework Foundation -framework QuartzCore \
    -framework Metal -framework CoreGraphics -framework CoreFoundation \
    -framework Security -framework Accelerate \
    -lz -lc++ -o "$APP/AscensionRecompProbe"
test -s "$APP/AscensionRecompProbe"
file "$APP/AscensionRecompProbe" | tee m41-executable-file.txt
xcrun lipo -info "$APP/AscensionRecompProbe" | tee m41-executable-arch.txt
/usr/libexec/PlistBuddy -c 'Print CFBundleIdentifier' "$APP/Info.plist"
(cd ios-probe && zip -q -r ../AscensionRecompProbe-0.6.14-unsigned.ipa Payload)
test -s AscensionRecompProbe-0.6.14-unsigned.ipa
shasum -a 256 AscensionRecompProbe-0.6.14-unsigned.ipa > m41-ipa-sha256.txt
echo 'UNSIGNED DIAGNOSTIC APP: UIKit CAMetalLayer + real PS3Recomp Metal backend; NO GOWA GAME included' > m41-status.txt
