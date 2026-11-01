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
for patch in "$ROOT/patches/0001-kosmickrisp-ios-m2.patch" "$ROOT/patches/0002-kosmickrisp-ios-m3-metal-wsi.patch" "$ROOT/patches/0003-kosmickrisp-ios-m3b-smoke-target.patch"; do
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
exec xcrun --sdk iphoneos clang -target arm64-apple-ios17.4 -isysroot "$SDKROOT" "$@"
EOF
cat > "$OUT/toolchain/ios-clangxx" <<'EOF'
#!/bin/bash
set -euo pipefail
SDKROOT="$(xcrun --sdk iphoneos --show-sdk-path)"
exec xcrun --sdk iphoneos clang++ -target arm64-apple-ios17.4 -isysroot "$SDKROOT" "$@"
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
meson compile -C "$OUT/build-ios" kk-ios-smoke
ARCHIVE="$OUT/build-ios/src/kosmickrisp/vulkan/libkk.a"
SMOKE="$OUT/build-ios/src/kosmickrisp/kk-ios-smoke"
test -f "$ARCHIVE" && test -f "$SMOKE"
cp "$ARCHIVE" "$OUT/libkk-kosmickrisp-ios-arm64.a"
cp "$SMOKE" "$OUT/KosmicKrispM3B"
mkdir -p "$OUT/include"
rm -rf "$OUT/include/vulkan"
cp -R "$OUT/mesa-src/include/vulkan" "$OUT/include/vulkan"
file "$OUT/libkk-kosmickrisp-ios-arm64.a" | tee "$OUT/file.txt"
lipo -info "$OUT/libkk-kosmickrisp-ios-arm64.a" | tee "$OUT/lipo.txt"
nm -g "$OUT/libkk-kosmickrisp-ios-arm64.a" > "$OUT/symbols.txt"
grep -q vk_icdGetInstanceProcAddr "$OUT/symbols.txt"
OBJ="$(find "$OUT/build-ios" -name '*.o' -type f | head -1)"
test -n "$OBJ"
xcrun vtool -show-build "$OBJ" > "$OUT/build-version.txt"
grep -E -qi "platform[[:space:]]+IOS|platform[[:space:]]+2" "$OUT/build-version.txt"
cat > "$OUT/KosmicKrispiOS-build.txt" <<EOF
KosmicKrispiOS standalone build
Mesa/KosmicKrisp: $MESA_SHA
SPIRV-LLVM-Translator: $SPIRV_SHA
Meson: $MESON_VERSION
LLVM: llvm@20
iOS target: arm64-apple-ios17.4
M3 Metal WSI: applied
M3B direct ICD/CAMetalLayer smoke: compiled
Physical device runtime validation: pending integrator
EOF
shasum -a 256 "$OUT/libkk-kosmickrisp-ios-arm64.a" "$OUT/KosmicKrispM3B" "$ROOT"/patches/*.patch > "$OUT/SHA256SUMS"
echo "PASS: KosmicKrisp iOS arm64 archive and M3B smoke executable built."
