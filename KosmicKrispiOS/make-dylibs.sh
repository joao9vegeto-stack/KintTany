#!/usr/bin/env bash
# Create the two Frameworks dylibs expected by SDL_Vulkan_LoadLibrary.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-$ROOT/build/Frameworks}"
BUILD_IOS="$ROOT/build/build-ios"
test -d "$BUILD_IOS"
STATIC_ARCHIVES=()
while IFS= read -r -d '' archive; do
  [[ "$archive" == *"/libkk-ios-smoke-objects.a" ]] && continue
  STATIC_ARCHIVES+=("$archive")
done < <(find "$BUILD_IOS" -name '*.a' -print0)
test "${#STATIC_ARCHIVES[@]}" -gt 0
mkdir -p "$OUT"
SDKROOT="$(xcrun --sdk iphoneos --show-sdk-path)"
TARGET="arm64-apple-ios17.4"
KK_LINK_FLAGS=()
for archive in "${STATIC_ARCHIVES[@]}"; do
  KK_LINK_FLAGS+=("-Wl,-force_load,$archive")
done
xcrun --sdk iphoneos clang -target "$TARGET" -isysroot "$SDKROOT" -dynamiclib \
  "${KK_LINK_FLAGS[@]}" \
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
