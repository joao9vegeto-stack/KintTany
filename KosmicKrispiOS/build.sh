#!/usr/bin/env bash
# Reproducible KosmicKrisp iOS arm64 static ICD build based on PsTJohn M2/M3/M3B.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${KK_BUILD_DIR:-$ROOT/build}"
MESA_SHA="bfe063f723d436e5cdef8a98f058d4e44a64810c"
SPIRV_SHA="e328468fd329342f1f60c12fdd19cc0faaa88f32"
MESA_PRIMARY="https://gitlab.freedesktop.org/mesa/mesa.git"
MESA_MIRROR="https://github.com/Kenji-NX/mesa.git"
SPIRV_URL="https://github.com/KhronosGroup/SPIRV-LLVM-Translator.git"
MESON_VERSION="1.9.1"
LLVM_FORMULA="llvm@20"
mkdir -p "$OUT"; cd "$OUT"
for cmd in git xcodebuild xcrun cmake ninja brew python3; do command -v "$cmd" >/dev/null || { echo "Missing $cmd" >&2; exit 2; }; done
if [[ "${KK_SKIP_PREREQUISITES:-0}" != 1 ]]; then
  brew update
  for pkg in cmake pkg-config libclc "$LLVM_FORMULA" spirv-tools ninja; do brew list "$pkg" >/dev/null 2>&1 || brew install "$pkg"; done
fi
python3 -m venv "$OUT/venv"
source "$OUT/venv/bin/activate"
python -m pip install --upgrade pip
python -m pip install "meson==$MESON_VERSION" mako packaging pyyaml
LLVM_PREFIX="$(brew --prefix "$LLVM_FORMULA")"
TRANSLATOR_PREFIX="$OUT/deps/spirv-llvm-translator-20"
rm -rf "$OUT/spirv-llvm-translator-src" "$OUT/spirv-llvm-translator-build" "$TRANSLATOR_PREFIX"
git clone --filter=blob:none --no-checkout "$SPIRV_URL" "$OUT/spirv-llvm-translator-src"
git -C "$OUT/spirv-llvm-translator-src" fetch --depth=1 origin "$SPIRV_SHA"
git -C "$OUT/spirv-llvm-translator-src" checkout --detach "$SPIRV_SHA"
test "$(git -C "$OUT/spirv-llvm-translator-src" rev-parse HEAD)" = "$SPIRV_SHA"
cmake -S "$OUT/spirv-llvm-translator-src" -B "$OUT/spirv-llvm-translator-build" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$TRANSLATOR_PREFIX" \
  -DLLVM_DIR="$LLVM_PREFIX/lib/cmake/llvm" -DLLVM_SPIRV_INCLUDE_TESTS=OFF \
  -DBUILD_SHARED_LIBS=OFF -DLLVM_LINK_LLVM_DYLIB=OFF
cmake --build "$OUT/spirv-llvm-translator-build" --target LLVMSPIRVLib llvm-spirv -j3
cmake --install "$OUT/spirv-llvm-translator-build"
test -f "$TRANSLATOR_PREFIX/lib/libLLVMSPIRVLib.a"
test "$(PKG_CONFIG_PATH="$TRANSLATOR_PREFIX/lib/pkgconfig" pkg-config --modversion LLVMSPIRVLib)" = "20.1.0.0"

rm -rf "$OUT/mesa-src"
if git clone --filter=blob:none --no-checkout "$MESA_PRIMARY" "$OUT/mesa-src"; then
  echo "official GitLab" > "$OUT/mesa-source.txt"
else
  rm -rf "$OUT/mesa-src"
  git clone --filter=blob:none --no-checkout "$MESA_MIRROR" "$OUT/mesa-src"
  echo "synchronized GitHub mirror fallback" > "$OUT/mesa-source.txt"
fi
git -C "$OUT/mesa-src" fetch --depth=1 origin "$MESA_SHA"
git -C "$OUT/mesa-src" checkout --detach "$MESA_SHA"
test "$(git -C "$OUT/mesa-src" rev-parse HEAD)" = "$MESA_SHA"
for patch in "$ROOT/patches/0001-kosmickrisp-ios-m2.patch" "$ROOT/patches/0002-kosmickrisp-ios-m3-metal-wsi.patch" "$ROOT/patches/0003-kosmickrisp-ios-m3b-smoke-target.patch" "$ROOT/patches/0004-kosmickrisp-ios-macho-weak-import.patch"; do
  git -C "$OUT/mesa-src" apply --check "$patch"
  git -C "$OUT/mesa-src" apply "$patch"
done
cp "$ROOT/smoke/kk_ios_smoke.m" "$OUT/mesa-src/src/kosmickrisp/kk_ios_smoke.m"
cat > "$OUT/mesa-src/src/kosmickrisp/kk_ios_smoke_build.h" <<EOF
#define KK_KINTTANY_SHA "standalone-KosmicKrispiOS"
#define KK_MESA_SHA "$MESA_SHA"
EOF
git -C "$OUT/mesa-src" diff --check

export PATH="$LLVM_PREFIX/bin:$TRANSLATOR_PREFIX/bin:$PATH"
export LDFLAGS="-L$TRANSLATOR_PREFIX/lib -L$LLVM_PREFIX/lib"
export CPPFLAGS="-I$TRANSLATOR_PREFIX/include -I$LLVM_PREFIX/include"
export PKG_CONFIG_PATH="$TRANSLATOR_PREFIX/lib/pkgconfig:$LLVM_PREFIX/lib/pkgconfig:$(brew --prefix libclc)/lib/pkgconfig:$(brew --prefix spirv-tools)/lib/pkgconfig"
rm -rf "$OUT/build-host" "$OUT/host-tools"
meson setup "$OUT/build-host" "$OUT/mesa-src" --buildtype=release -Dplatforms=macos -Dvulkan-drivers=kosmickrisp -Dgallium-drivers= -Dopengl=false -Dzstd=disabled -Dmesa-clc=enabled -Dprecomp-compiler=enabled --prefer-static
meson compile -C "$OUT/build-host" mesa_clc vtn_bindgen2 kk_clc
mkdir -p "$OUT/host-tools/bin"
cp "$OUT/build-host/src/compiler/clc/mesa_clc" "$OUT/host-tools/bin/"
cp "$OUT/build-host/src/compiler/spirv/vtn_bindgen2" "$OUT/host-tools/bin/"
cp "$OUT/build-host/src/kosmickrisp/clc/kk_clc" "$OUT/host-tools/bin/"
chmod +x "$OUT/host-tools/bin/"*

mkdir -p "$OUT/toolchain"
cat > "$OUT/toolchain/ios-clang" <<'EOF'
#!/bin/bash
set -euo pipefail
SDKROOT="$(xcrun --sdk iphoneos --show-sdk-path)"
# Mesa's generated WSI/driver dispatch tables must mark unsupported entrypoints
# as weak imports on Mach-O. The generator patch defines VK_ENTRY_WEAK only
# when VK_ENTRY_USE_WEAK is enabled; the iOS cross toolchain must enable it.
exec xcrun --sdk iphoneos clang -target arm64-apple-ios17.4 -isysroot "$SDKROOT" -DVK_ENTRY_USE_WEAK "$@"
EOF
cat > "$OUT/toolchain/ios-clangxx" <<'EOF'
#!/bin/bash
set -euo pipefail
SDKROOT="$(xcrun --sdk iphoneos --show-sdk-path)"
exec xcrun --sdk iphoneos clang++ -target arm64-apple-ios17.4 -isysroot "$SDKROOT" -DVK_ENTRY_USE_WEAK "$@"
EOF
cat > "$OUT/toolchain/ios-ar" <<'EOF'
#!/bin/bash
set -euo pipefail
exec xcrun --sdk iphoneos ar "$@"
EOF
cat > "$OUT/toolchain/ios-strip" <<'EOF'
#!/bin/bash
set -euo pipefail
exec xcrun --sdk iphoneos strip "$@"
EOF
chmod +x "$OUT/toolchain/"*
cat > "$OUT/ios-arm64.cross" <<EOF
[binaries]
c = '$OUT/toolchain/ios-clang'
cpp = '$OUT/toolchain/ios-clangxx'
objc = '$OUT/toolchain/ios-clang'
ar = '$OUT/toolchain/ios-ar'
strip = '$OUT/toolchain/ios-strip'
[host_machine]
system = 'darwin'
cpu_family = 'aarch64'
cpu = 'arm64'
endian = 'little'
[properties]
needs_exe_wrapper = true
EOF
unset LDFLAGS CPPFLAGS PKG_CONFIG_PATH
export PATH="$OUT/host-tools/bin:$PATH"
rm -rf "$OUT/build-ios"
meson setup "$OUT/build-ios" "$OUT/mesa-src" --cross-file "$OUT/ios-arm64.cross" --buildtype=release --wrap-mode=nodownload -Dplatforms=ios -Dvulkan-drivers=kosmickrisp -Dgallium-drivers= -Dopengl=false -Dzstd=disabled -Dmesa-clc=system -Dprecomp-compiler=system -Dllvm=disabled -Dspirv-tools=disabled --prefer-static
ninja -C "$OUT/build-ios" src/kosmickrisp/vulkan/libkk.a
# Compile the iOS smoke harness as an object archive only. Linking a standalone
# executable here is invalid: it bypasses the final app's complete static
# dependency closure and fails on the iOS dynamic_lookup linker restriction.
meson compile -C "$OUT/build-ios" kk-ios-smoke-objects
# Build every static-library target Meson registered for this iOS configuration.
# Building only libkk.a compiles many dependency objects but does not emit the
# separate archives that Xcode must link (WSI, Mesa utilities, C11 threads,
# Vulkan runtime, NIR, etc.). Discover the actual target graph instead of
# guessing an archive count or symbol names.
MESON_ARCHIVE_TARGETS=()
while IFS= read -r target; do
  [[ "$target" == *.a ]] && MESON_ARCHIVE_TARGETS+=("$target")
done < <(ninja -C "$OUT/build-ios" -t targets all | awk -F': ' '$1 ~ /\.a$/ {print $1}' | sort -u)
test "${#MESON_ARCHIVE_TARGETS[@]}" -gt 0 || {
  echo "ERROR: Meson did not expose any iOS static-library targets." >&2
  exit 1
}
printf '%s\n' "${MESON_ARCHIVE_TARGETS[@]}" | tee "$OUT/meson-static-targets.txt"
ninja -C "$OUT/build-ios" "${MESON_ARCHIVE_TARGETS[@]}"

ARCHIVE="$OUT/build-ios/src/kosmickrisp/vulkan/libkk.a"
SMOKE="$OUT/build-ios/src/kosmickrisp/libkk-ios-smoke-objects.a"
KK_DISPATCH_TABLE="$OUT/build-ios/src/kosmickrisp/vulkan/libkk_device_dispatch_table.a"
KK_CMD_DISPATCH_TABLE="$OUT/build-ios/src/kosmickrisp/vulkan/libkk_device_cmd_dispatch_table.a"
WSI_ARCHIVE="$OUT/build-ios/src/vulkan/wsi/libvulkan_wsi.a"
for required in "$ARCHIVE" "$SMOKE" "$KK_DISPATCH_TABLE" "$KK_CMD_DISPATCH_TABLE" "$WSI_ARCHIVE"; do
  test -s "$required" || {
    echo "ERROR: required Meson archive was not produced: $required" >&2
    exit 1
  }
done

STATIC_ARCHIVES=()
while IFS= read -r -d '' archive; do
  STATIC_ARCHIVES+=("$archive")
done < <(find "$OUT/build-ios" -name '*.a' -print0)
LINK_ARCHIVES=()
for archive in "${STATIC_ARCHIVES[@]}"; do
  # The M3B smoke harness is compiled as a build check, never force-loaded
  # into the production app executable.
  [[ "$archive" == "$SMOKE" ]] && continue
  [[ "$archive" == */src/gtest/libgtest.a ]] && continue
  [[ "$archive" == */src/vulkan/runtime/libvulkan_lite_instance.a ]] && continue
  xcrun lipo "$archive" -verify_arch arm64
  LINK_ARCHIVES+=("$archive")
done
test "${#LINK_ARCHIVES[@]}" -gt 0 || {
  echo "ERROR: incomplete iOS static-library target set." >&2
  printf '%s\n' "${LINK_ARCHIVES[@]}" >&2
  exit 1
}
printf '%s\n' "${LINK_ARCHIVES[@]}" | tee "$OUT/static-link-archives.txt"

# Validate the actual Metal WSI objects and the ICD entrypoint, not invented
# internal names such as _wsi_CreateInstance (Mesa exposes WSI through generated
# dispatch tables and wsi_device_entrypoints, not those symbols).
WSI_MEMBERS="$(xcrun ar -t "$WSI_ARCHIVE")"
for member in wsi_common_metal.c.o wsi_common_metal_layer.m.o; do
  grep -F "$member" <<<"$WSI_MEMBERS" >/dev/null || {
    echo "ERROR: Metal WSI object is missing from $WSI_ARCHIVE: $member" >&2
    printf '%s\n' "$WSI_MEMBERS" >&2
    exit 1
  }
done
nm -gU "$ARCHIVE" | grep -F '_vk_icdGetInstanceProcAddr' >/dev/null || {
  echo "ERROR: KosmicKrisp ICD entrypoint is missing from $ARCHIVE" >&2
  exit 1
}

# The generated Mesa/KosmicKrisp dispatch tables intentionally reference
# unsupported Vulkan entrypoints as optional weak imports. On Mach-O, they must
# remain weak_import (not hidden strong undefineds), or the final iOS link
# rejects hundreds of commands the driver does not implement.
# Check each generated dispatch family, including WSI. A previous build
# checked only the KK command table and missed strong WSI references that then
# failed the final app link.
for symbol in _kk_AcquireNextImageKHR _wsi_QueueSubmit _wsi_AllocateCommandBuffers; do
  if ! nm -m "$ARCHIVE" "$KK_CMD_DISPATCH_TABLE" "$WSI_ARCHIVE" | awk -v symbol="$symbol" '
    $NF == symbol && /weak external/ { found = 1 }
    END { exit !found }
  '; then
    echo "ERROR: expected optional Mach-O weak import is not weak: $symbol" >&2
    nm -m "$ARCHIVE" "$KK_CMD_DISPATCH_TABLE" "$WSI_ARCHIVE" | grep -F "$symbol" >&2 || true
    exit 1
  fi
done

# Meson emits overlapping static archives: parent archives may contain object
# members that are also present in their dependency archives. Force-loading
# every archive duplicates those definitions (the previous iOS link failed
# with 1,515 duplicate symbols). Force-load only the ICD root archive so its
# entrypoint is guaranteed to be included; pass dependency archives as normal
# linker inputs so ld extracts only members needed to resolve remaining
# references. Never use dynamic_lookup to mask missing Vulkan symbols.
LINK_CONFIG="$OUT/KosmicKrispLink.xcconfig"
{
  # SpartanPort iOS build policy (validated by the next fresh Actions run):
# Keep the ICD archive lazy: -u extracts the member defining the ICD entrypoint,
# while force-loading libkk.a also pulls generated WSI dispatch tables whose
# optional Vulkan entrypoints are not implemented by this iOS driver.
printf 'OTHER_LDFLAGS = $(inherited) -Wl,-u,_vk_icdGetInstanceProcAddr %s' "$ARCHIVE"
  for archive in "${LINK_ARCHIVES[@]}"; do
    [[ "$archive" == "$ARCHIVE" ]] && continue
    printf ' %s' "$archive"
  done
  printf '%s\n' ' -framework Metal -framework QuartzCore -framework UIKit -framework Foundation -framework CoreGraphics -lc++ -lz'
} > "$LINK_CONFIG"
cp "$SMOKE" "$OUT/KosmicKrispM3B-smoke-objects.a"
mkdir -p "$OUT/include"
rm -rf "$OUT/include/vulkan"
cp -R "$OUT/mesa-src/include/vulkan" "$OUT/include/vulkan"
rm -rf "$OUT/include/vk_video"
cp -R "$OUT/mesa-src/include/vk_video" "$OUT/include/vk_video"
test -f "$OUT/include/vk_video/vulkan_video_codec_h264std.h"
printf 'Generated static linker configuration: %s\n' "$LINK_CONFIG"
# Record target metadata without guessing which object happens to be first in find order.
printf '%s\n' "target=arm64-apple-ios17.4" "sdk=$(xcrun --sdk iphoneos --show-sdk-version)" > "$OUT/build-version.txt"
cat > "$OUT/KosmicKrispiOS-build.txt" <<EOF
KosmicKrispiOS standalone build
Mesa/KosmicKrisp: $MESA_SHA
SPIRV-LLVM-Translator: $SPIRV_SHA
Meson: $MESON_VERSION
LLVM: llvm@20
iOS target: arm64-apple-ios17.4
M3 Metal WSI: applied
M3B direct ICD/CAMetalLayer smoke source: compiled to ARM64 object archive (not linked or runtime-tested)
Meson iOS static archives: individually force-loaded into the SpartanPort app executable
Mesa/KosmicKrisp static dependencies: lazy archive extraction via ICD -u entrypoint; Metal WSI object members verified
Physical device runtime validation: pending integrator
EOF
shasum -a 256 "${LINK_ARCHIVES[@]}" "$OUT/KosmicKrispM3B-smoke-objects.a" "$OUT/static-link-archives.txt" "$OUT/KosmicKrispLink.xcconfig" "$ROOT"/patches/*.patch > "$OUT/SHA256SUMS"
echo "PASS: KosmicKrisp iOS arm64 static dependency set and M3B smoke objects compiled."
