#!/usr/bin/env bash
# Experimental PPU CPU bridge only, never private commercial game code.
set -euo pipefail
test "$(uname -s)" = Darwin
sdk="$(xcrun --sdk iphoneos --show-sdk-path)"
output=ios-ppu-core
mkdir -p "$output/objects" "$output/include/upstream/runtime/ppu" "$output/include/upstream/include"
for src in runtime/ppu_bridge.c runtime/elf_image.c runtime/ppu_tls.c runtime/lv2_smoke.c runtime/ppu_thread_services.c; do
  name="$(basename "$src" .c)"
  obj="$output/objects/$name.o"
  xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$sdk" \
    -std=c17 -O2 -ffp-contract=off -fno-strict-aliasing \
    -DASCENSION_NATIVE_ONLY=1 -DASCENSION_M772_LINKED=1 \
    -I upstream/runtime/ppu -I runtime -c "$src" -o "$obj"
  test -s "$obj"
done
/usr/bin/libtool -static -o "$output/libAscensionPPUCore-ios-arm64.a" "$output"/objects/*.o
xcrun lipo -info "$output/libAscensionPPUCore-ios-arm64.a"
file "$output/libAscensionPPUCore-ios-arm64.a"
xcrun nm -g "$output/libAscensionPPUCore-ios-arm64.a" > "$output/exports.txt"
# The archive must carry the strict dispatcher compiled with NATIVE_ONLY.
grep -q 'ASCENSION_NATIVE_ONLY' runtime/ppu_bridge.c
for sym in _ar_run _ar_load_elf_image _ar_sys_initialize_tls _ar_sys_ppu_thread_get_id _ar_guest_syscall; do
  grep -q "$sym" "$output/exports.txt"
done
shasum -a 256 "$output/libAscensionPPUCore-ios-arm64.a" > "$output/SHA256.txt"
cp runtime/*.h "$output/include/"
cp upstream/runtime/ppu/ppu_context.h "$output/include/upstream/runtime/ppu/"
cp -R upstream/include/ps3emu "$output/include/upstream/include/"
cat > "$output/README.txt" <<'EOF'
AscensionRecomp experimental iOS arm64 PPU static library.
Guest dispatch, ELF image loader, TLS, LV2 memory info and per-thread ID.
Headers: -I include -I include/upstream/runtime/ppu
NOT a game, app, IPA, complete SPU/SPURS or RSX backend.
No proprietary executable, assets, game code or licenses included.
EOF
echo "iOS PPU core archive created with no game bytes."
