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
  # Fail if any of the 59 TRUE NPUA80918 guest AOT symbols is missing.
  # Both symbol checks are performed again on the FINAL linked iOS Mach-O.
  xcrun nm -g ios-probe/AscensionPrivateAOT.o > m78-owner-aot-object-symbols.txt
  for pc in \
  00010200 00010380 00010410 00010434 00010444 00010534 \
  000107a4 00010814 002c1024 002c10c8 002c10d0 002c10e4 \
  002c1104 002c1114 002c1124 002c1148 002c1154 002c1168 \
  002c1174 002c118c 002c11b4 002c11c0 002c11d4 002c11e8 \
  002c1200 002c1214 002c1564 002c1570 002c15e4 002c15f4 \
  002c164c 003678ec 003a4c1c 003a4c38 00455a10 00455eac \
  00455f9c 00455fa4 00455fb8 005232b0 00523318 00523350 \
  00523360 00523390 00523428 00525c00 0052a710 0052a78c \
  0052a7bc 0052e118 0052e180 0052e3b0 0052e3f4 0052e4f0 \
  0052e544 00531a74 00531cac 00539998 00539a50; do
    grep -Fq "_ar_game_ppu_${pc}" m78-owner-aot-object-symbols.txt
  done
  AOT_OBJECTS+=(ios-probe/AscensionPrivateAOT.o)
  AOT_COMPILE_DEFINES+=(-DASCENSION_PRIVATE_AOT_LINKED)
fi
# Stage the native PPU bridge as an ARM64 object and link the prebuilt
# IOS PPU core archive; never compile or bundle the user's PS3 ELF.
test -s ios-ppu-core/libAscensionPPUCore-ios-arm64.a
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror \
    -I upstream/runtime/ppu -I runtime \
    ${AOT_COMPILE_DEFINES[@]+"${AOT_COMPILE_DEFINES[@]}"} \
    -c ios/ARLivePPUBridge.c -o ios-probe/ARLivePPUBridge.o
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror \
    -I upstream/runtime/ppu -I runtime \
    -c ios/ARNativePPUContinuous.c -o ios-probe/ARNativePPUContinuous.o
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror \
    -I upstream/runtime/ppu -I runtime \
    -c ios/ARLivePPUContinuous.c -o ios-probe/ARLivePPUContinuous.o
# M7.7: compile the generic PS3 lightweight mutex HLE for the iPhone.
# This is OS service logic, NOT game-derived translated code.
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror \
    -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_lwmutex.c -o ios-probe/ppu_lwmutex.o
# M7.9: compile actual PS3 LV2 memory/time ABI services for native AOT.
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror \
    -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_lv2_bootstrap.c -o ios-probe/ppu_lv2_bootstrap.o
# M7.10 native 79.8MHz PPU timebase for already-translated PPC mftb.
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror \
    -c runtime/ppu_timebase.c -o ios-probe/ppu_timebase.o
# M7.12: native fail-closed guest ELF executable read-only inspection.
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror \
    -c runtime/ppu_m712_exec_window.c -o ios-probe/ppu_m712_exec_window.o
# M7.11: native SYSUTIL and sparse virtual memory. No game ELF embedded.
M711_OBJECTS=()
for module in ppu_mmapper ppu_mmapper_reserve ppu_mmapper_alloc \
              ppu_mmapper_map ppu_mmapper_release ppu_native_sysutil \
              ppu_m711_bind_memory ppu_m711_bind_sysutil; do
  xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c "runtime/${module}.c" -o "ios-probe/${module}.o"
  M711_OBJECTS+=("ios-probe/${module}.o")
done
xcrun nm -g ios-probe/ARLivePPUBridge.o | grep -q '_ar_m70_native_runtime_probe'
xcrun nm -g ios-probe/ARLivePPUContinuous.o | grep -q '_ar_m71_private_continuous_probe'
xcrun nm -g ios-probe/ARRSXMethodProbe.o | grep -q '_ar_probe_rsx_clear_flip'
xcrun --sdk iphoneos clang++ -target arm64-apple-ios17.0 \
    -isysroot "$SDK" -fobjc-arc -fmodules -stdlib=libc++ \
    -O2 -Wl,-dead_strip -I ios -I upstream/libs/video -I upstream/include \
    ios/ARMetalView.m ios/ARProbeApp.m ios/ARShaderProbe.m ios/ARTextureProbe.m ios/ARProbeGuestVM.c \
    ios-probe/ARRSXMethodProbe.o ios-probe/ARGuestDrawProbe.o ios-probe/ARPrivateELFProbe.o \
    ios-probe/ARLivePPUBridge.o ios-probe/ARLivePPUContinuous.o \
    ios-probe/ARNativePPUContinuous.o ios-probe/ppu_lwmutex.o \
    ios-probe/ppu_lv2_bootstrap.o \
    ios-probe/ppu_timebase.o ios-probe/ppu_m712_exec_window.o \
    ${M711_OBJECTS[@]+"${M711_OBJECTS[@]}"} \
    ${AOT_OBJECTS[@]+"${AOT_OBJECTS[@]}"} \
    ios-ppu-core/libAscensionPPUCore-ios-arm64.a \
    build-ios-runtime/libAscensionRSXGuest-ios-arm64.a \
    -framework UIKit -framework Foundation -framework QuartzCore \
    -framework Metal -framework CoreGraphics -framework CoreFoundation \
    -framework Security -framework Accelerate \
    -lz -lc++ -o "$APP/AscensionRecompProbe"
test -s "$APP/AscensionRecompProbe"
if [[ -z "${ASCENSION_PRIVATE_AOT_C:-}" ]]; then
  echo 'M7.11 required signed game AOT source not staged: refusing diagnostic-only IPA' >&2
  exit 77
fi
xcrun nm -g "$APP/AscensionRecompProbe" > m78-owner-aot-linked-symbols.txt
grep -Fq '_ar_private_aot_install_sha256' m78-owner-aot-linked-symbols.txt
grep -Fq '_ar_ppu_timebase_ticks' m78-owner-aot-linked-symbols.txt
for pc in \
  00010200 00010380 00010410 00010434 00010444 00010534 \
  000107a4 00010814 002c1024 002c10c8 002c10d0 002c10e4 \
  002c1104 002c1114 002c1124 002c1148 002c1154 002c1168 \
  002c1174 002c118c 002c11b4 002c11c0 002c11d4 002c11e8 \
  002c1200 002c1214 002c1564 002c1570 002c15e4 002c15f4 \
  002c164c 003678ec 003a4c1c 003a4c38 00455a10 00455eac \
  00455f9c 00455fa4 00455fb8 005232b0 00523318 00523350 \
  00523360 00523390 00523428 00525c00 0052a710 0052a78c \
  0052a7bc 0052e118 0052e180 0052e3b0 0052e3f4 0052e4f0 \
  0052e544 00531a74 00531cac 00539998 00539a50; do
  grep -Fq "_ar_game_ppu_${pc}" m78-owner-aot-linked-symbols.txt
done
echo 'M7.11: 59 REAL PPU ARM64 functions verified inside final iOS Mach-O; runtime execution on iPhone not yet tested' > m78-aot-status.txt
file "$APP/AscensionRecompProbe" | tee m41-executable-file.txt
xcrun lipo -info "$APP/AscensionRecompProbe" | tee m41-executable-arch.txt
/usr/libexec/PlistBuddy -c 'Print CFBundleIdentifier' "$APP/Info.plist"
(cd ios-probe && zip -q -r ../AscensionRecompProbe-0.6.14-unsigned.ipa Payload)
test -s AscensionRecompProbe-0.6.14-unsigned.ipa
shasum -a 256 AscensionRecompProbe-0.6.14-unsigned.ipa > m41-ipa-sha256.txt
echo 'UNSIGNED DIAGNOSTIC APP: UIKit CAMetalLayer + real PS3Recomp Metal backend; NO GOWA GAME included' > m41-status.txt
