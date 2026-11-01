#!/usr/bin/env bash
# Create the two Frameworks dylibs expected by SDL_Vulkan_LoadLibrary.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-$ROOT/build/Frameworks}"
ARCHIVE="$ROOT/build/libkk-kosmickrisp-ios-arm64.a"
test -s "$ARCHIVE"
mkdir -p "$OUT"
SDKROOT="$(xcrun --sdk iphoneos --show-sdk-path)"
TARGET="arm64-apple-ios17.4"
xcrun --sdk iphoneos clang -target "$TARGET" -isysroot "$SDKROOT" -dynamiclib \
  -Wl,-all_load "$ARCHIVE" \
  -framework Metal -framework QuartzCore -framework UIKit -framework Foundation -framework CoreGraphics \
  -Wl,-undefined,dynamic_lookup -Wl,-install_name,@rpath/libKosmicKrisp.dylib \
  -o "$OUT/libKosmicKrisp.dylib"
xcrun --sdk iphoneos clang -target "$TARGET" -isysroot "$SDKROOT" -dynamiclib \
  -I"$ROOT/build/include" "$ROOT/Integration/Dynamic/poptst_vulkan_icd_bridge.c" \
  -Wl,-undefined,dynamic_lookup -Wl,-install_name,@rpath/libvulkan.dylib \
  -o "$OUT/libvulkan.dylib"
nm -gU "$OUT/libKosmicKrisp.dylib" | grep -q vk_icdGetInstanceProcAddr
nm -gU "$OUT/libvulkan.dylib" | grep -q vkGetInstanceProcAddr
file "$OUT/libKosmicKrisp.dylib" "$OUT/libvulkan.dylib"
echo "PASS: SDL-compatible KosmicKrisp dylibs staged in $OUT"
