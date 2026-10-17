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
# M7.18: owner-ELF-derived native C blocks from separate 2nd Actions secret.
# Secret source is staged into RUNNER_TEMP and never committed to Git.
if [[ -n "${ASCENSION_PRIVATE_BULK_C:-}" ]]; then
  test -f "$ASCENSION_PRIVATE_BULK_C"
  test "${ASCENSION_BULK_COUNT:?}" = "500"
  xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
      -std=c11 -O2 -Wall -Wextra -Werror -Wno-unused-label \
      -I upstream/runtime/ppu -I runtime \
      -c "$ASCENSION_PRIVATE_BULK_C" -o ios-probe/AscensionPrivateBulk.o
  xcrun nm -g ios-probe/AscensionPrivateBulk.o > m718-bulk-object-symbols.txt
  grep -Eq ' [Tt] _ar_bulk_install_sha256$' m718-bulk-object-symbols.txt
  python3 tools/verify_m718_macho.py m718-bulk-object-symbols.txt \
      "${ASCENSION_BULK_SYMBOL_LIST:?}" "${ASCENSION_BULK_COUNT:?}"
  AOT_OBJECTS+=(ios-probe/AscensionPrivateBulk.o)
  AOT_COMPILE_DEFINES+=(-DASCENSION_PRIVATE_BULK_AOT_LINKED)
fi
# M7.19: staged 850 owner-only PPC AOT entries from third GitHub secret.
if [[ -n "${ASCENSION_PRIVATE_BULK2_C:-}" ]]; then
  test -f "$ASCENSION_PRIVATE_BULK2_C"
  test "${ASCENSION_BULK2_COUNT:?}" = "850"
  xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
      -std=c11 -O2 -Wall -Wextra -Werror -Wno-unused-label \
      -I upstream/runtime/ppu -I runtime \
      -c "$ASCENSION_PRIVATE_BULK2_C" -o ios-probe/AscensionPrivateBulk2.o
  xcrun nm -g ios-probe/AscensionPrivateBulk2.o > m719-bulk2-object-symbols.txt
  grep -Eq ' [Tt] _ar_bulk2_install_sha256$' m719-bulk2-object-symbols.txt
  python3 tools/verify_m719_macho.py m719-bulk2-object-symbols.txt \
      "${ASCENSION_BULK2_SYMBOL_LIST:?}" "${ASCENSION_BULK2_COUNT:?}"
  AOT_OBJECTS+=(ios-probe/AscensionPrivateBulk2.o)
  AOT_COMPILE_DEFINES+=(-DASCENSION_PRIVATE_BULK2_AOT_LINKED)
fi
if [[ -n "${ASCENSION_PRIVATE_FRONTIER_C:-}" ]]; then
  test -s "$ASCENSION_PRIVATE_FRONTIER_C"
  test "${ASCENSION_FRONTIER_AOT_COUNT:?}" = "1"
  xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
      -std=c11 -O2 -Wall -Wextra -Werror -Wno-unused-label \
      -I upstream/runtime/ppu -I runtime \
      -c "$ASCENSION_PRIVATE_FRONTIER_C" -o ios-probe/AscensionPrivateFrontier.o
  xcrun nm -g ios-probe/AscensionPrivateFrontier.o > m723-frontier-object-symbols.txt
  grep -Eq ' [Tt] _ar_m722_install_sha256$' m723-frontier-object-symbols.txt
  grep -Eq ' [Tt] _ar_m722_ppu_003c511c$' m723-frontier-object-symbols.txt
  AOT_OBJECTS+=(ios-probe/AscensionPrivateFrontier.o)
  AOT_COMPILE_DEFINES+=(-DASCENSION_PRIVATE_FRONTIER_AOT_LINKED)
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
# M7.13: compile owner-observed PPC instructions as native ARM64.
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_m713_aot_fragment.c -o ios-probe/ppu_m713_aot_fragment.o
# M7.14: owner-observed guest stores + bounded read-only instruction batch.
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_m714_native_batch.c -o ios-probe/ppu_m714_native_batch.o
# M7.15: strict ARM64 AOT continuation for original PPC load-then-store sequence.
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_m715_aot_fragment.c -o ios-probe/ppu_m715_aot_fragment.o
# M7.16: native 15-word conditional PPC block (both successor edges).
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_m716_native_branch.c -o ios-probe/ppu_m716_native_branch.o
# M7.31: authenticated owner ELF two-instruction CR4+BLR native AOT.
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_m731_native_mtocrf.c -o ios-probe/ppu_m731_native_mtocrf.o
# M7.17: bounded reachability scan of authentic PPC ELF, READ-ONLY.
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I runtime \
    -c runtime/ppu_m717_graph.c -o ios-probe/ppu_m717_graph.o
# M7.20: signed native PPC fallback for missing AOT entries (NO JIT).
# This interpreter is NEVER counted as native ARM64 AOT.
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror \
    -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_m720_fallback.c -o ios-probe/ppu_m720_fallback.o
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
    -O2 -Wl,-dead_strip -I ios -I runtime -I upstream/runtime/ppu -I upstream/libs/video -I upstream/include \
    ios/ARMetalView.m ios/ARProbeApp.m ios/ARShaderProbe.m ios/ARTextureProbe.m ios/ARProbeGuestVM.c \
    ios-probe/ARRSXMethodProbe.o ios-probe/ARGuestDrawProbe.o ios-probe/ARPrivateELFProbe.o \
    ios-probe/ARLivePPUBridge.o ios-probe/ARLivePPUContinuous.o \
    ios-probe/ARNativePPUContinuous.o ios-probe/ppu_lwmutex.o \
    ios-probe/ppu_lv2_bootstrap.o \
    ios-probe/ppu_timebase.o ios-probe/ppu_m712_exec_window.o \
    ios-probe/ppu_m713_aot_fragment.o \
    ios-probe/ppu_m714_native_batch.o \
    ios-probe/ppu_m715_aot_fragment.o \
    ios-probe/ppu_m716_native_branch.o \
    ios-probe/ppu_m731_native_mtocrf.o \
    ios-probe/ppu_m717_graph.o \
    ios-probe/ppu_m720_fallback.o \
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
# M7.12: fail the build unless EVERY manifest entry is defined code in the final Mach-O.
python3 tools/verify_m712_macho.py m78-owner-aot-linked-symbols.txt "${ASCENSION_AOT_SYMBOL_LIST:?}" "${ASCENSION_AOT_EXPECTED_SYMBOL_COUNT:?}"
if [[ -n "${ASCENSION_PRIVATE_BULK_C:-}" ]]; then
  python3 tools/verify_m718_macho.py m78-owner-aot-linked-symbols.txt \
      "${ASCENSION_BULK_SYMBOL_LIST:?}" "${ASCENSION_BULK_COUNT:?}"
  grep -Eq ' [Tt] _ar_bulk_install_sha256$' m78-owner-aot-linked-symbols.txt
fi
if [[ -n "${ASCENSION_PRIVATE_BULK2_C:-}" ]]; then
  python3 tools/verify_m719_macho.py m78-owner-aot-linked-symbols.txt \
      "${ASCENSION_BULK2_SYMBOL_LIST:?}" "${ASCENSION_BULK2_COUNT:?}"
  grep -Eq ' [Tt] _ar_bulk2_install_sha256$' m78-owner-aot-linked-symbols.txt
  grep -Eq ' [Tt] _ar_bulk2_ppu_002c16a4$' m78-owner-aot-linked-symbols.txt
fi
if [[ -n "${ASCENSION_PRIVATE_FRONTIER_C:-}" ]]; then
  test "${ASCENSION_FRONTIER_AOT_COUNT:?}" = "1"
  grep -Eq ' [Tt] _ar_m722_install_sha256$' m78-owner-aot-linked-symbols.txt
  grep -Eq ' [Tt] _ar_m722_ppu_003c511c$' m78-owner-aot-linked-symbols.txt
  test "$(wc -l < "${ASCENSION_FRONTIER_SYMBOL_LIST:?}" | tr -d ' ')" = "1"
fi
grep -Eq ' [Tt] _ar_m713_aot_003c4d94$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m713_register_fragment$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m714_aot_003c4da4$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m714_frontier_inventory$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m715_aot_003c4db4$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m715_register_fragment$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m716_aot_003c4dc4$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m716_register_block$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m731_native_0052da5c$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m731_register_frontier$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m716_verified_successors$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m717_walk$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m717_last_aot_trace$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_trace_snapshot$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_ppc_fallback_step$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_ppc_fallback_attach$' m78-owner-aot-linked-symbols.txt
echo 'M7.11: 59 REAL PPU ARM64 functions verified inside final iOS Mach-O; runtime execution on iPhone not yet tested' > m78-aot-status.txt
echo "M7.12: ${ASCENSION_AOT_EXPECTED_SYMBOL_COUNT} REAL native ARM64 PPC entries linked, including 0x002C1664; iPhone proof pending" >> m78-aot-status.txt
echo "M7.13: +1 verified 4-instruction ARM64 entry 0x003C4D94; total $((ASCENSION_AOT_EXPECTED_SYMBOL_COUNT+1)); iPhone execution pending" >> m78-aot-status.txt
echo "M7.14: +1 ELF-verified static ARM64 fragment (0x003C4DA4), expected total $((ASCENSION_AOT_EXPECTED_SYMBOL_COUNT+2)); read-only 32-word frontier batch, no game RSX submission yet" >> m78-aot-status.txt
echo "M7.15: +1 ELF-verified load/store ARM64 entry at 0x003C4DB4; expected total $((ASCENSION_AOT_EXPECTED_SYMBOL_COUNT+3)); PPU batch available for iPhone report" >> m78-aot-status.txt
echo "M7.16: +1 verified native 15-instruction PPC block (0x003C4DC4), two real BEQ successors; total $((ASCENSION_AOT_EXPECTED_SYMBOL_COUNT+4)); iPhone execution required" >> m78-aot-status.txt
echo "M7.17: static bounded PPC reachability + actual ARM64 AOT dispatch telemetry; owner source unchanged; graph coverage needs iPhone" >> m78-aot-status.txt
echo "M7.18: +${ASCENSION_BULK_COUNT:-0} additional owner-private native PPC AOT blocks; total $((ASCENSION_AOT_EXPECTED_SYMBOL_COUNT+4+${ASCENSION_BULK_COUNT:-0})); exact ELF SHA-256 checked" >> m78-aot-status.txt
echo "M7.19: +${ASCENSION_BULK2_COUNT:-0} authenticated owner-private native PPC blocks beginning 0x002C16A4; total $((ASCENSION_AOT_EXPECTED_SYMBOL_COUNT+4+${ASCENSION_BULK_COUNT:-0}+${ASCENSION_BULK2_COUNT:-0})) entries; iPhone test pending" >> m78-aot-status.txt
echo "M7.20: experimental bounded PPC fallback, native AOT priority preserved, separate trace counters; 1418 AOT entries unchanged; no RSX gameplay claimed" >> m78-aot-status.txt
echo "M7.21: PowerPC64 rlwimi/rlwnm/rldic/rldimi mask semantics verified on synthetic ELF; 1418 native AOT entries preserved; iPhone runtime validation pending" >> m78-aot-status.txt
echo "M7.23: +${ASCENSION_FRONTIER_AOT_COUNT:-0} owner-authenticated native 25-opcode block at 0x003C511C; total $((ASCENSION_AOT_EXPECTED_SYMBOL_COUNT+4+${ASCENSION_BULK_COUNT:-0}+${ASCENSION_BULK2_COUNT:-0}+${ASCENSION_FRONTIER_AOT_COUNT:-0})) AOT entries" >> m78-aot-status.txt
echo 'M7.31: +1 SHA-gated and ELF-verified native ARM64 CR4 transfer + BLR at guest 0x0052DA5C; expected 1420 registered AOT on matching owner ELF; on-device execution not yet proven' >> m78-aot-status.txt
file "$APP/AscensionRecompProbe" | tee m41-executable-file.txt
xcrun lipo -info "$APP/AscensionRecompProbe" | tee m41-executable-arch.txt
/usr/libexec/PlistBuddy -c 'Print CFBundleIdentifier' "$APP/Info.plist"
(cd ios-probe && zip -q -r ../AscensionRecompProbe-0.6.14-unsigned.ipa Payload)
test -s AscensionRecompProbe-0.6.14-unsigned.ipa
shasum -a 256 AscensionRecompProbe-0.6.14-unsigned.ipa > m41-ipa-sha256.txt
echo 'UNSIGNED DIAGNOSTIC APP: UIKit CAMetalLayer + real PS3Recomp Metal backend; NO GOWA GAME included' > m41-status.txt
