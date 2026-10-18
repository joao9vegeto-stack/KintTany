#!/usr/bin/env bash
# Build a genuine unsigned iPhone diagnostic IPA (no PS3 game or license).
set -euo pipefail
SDK="$(xcrun --sdk iphoneos --show-sdk-path)"
APP="ios-probe/Payload/AscensionRecompProbe.app"
mkdir -p "$APP"
cp ios/Probe-Info.plist "$APP/Info.plist"
{
  printf '#define AR_M750_BUILD_SHA "%s"\n' "${GITHUB_SHA:-LOCAL_BUILD}"
  printf '#define AR_M750_BUILD_BRANCH "%s"\n' "${GITHUB_REF_NAME:-AscensionRecomp}"
  printf '#define AR_M750_BUILD_RUN_ID "%s"\n' "${GITHUB_RUN_ID:-LOCAL_BUILD}"
  printf '#define AR_M750_BUILD_RUN_NUMBER "%s"\n' "${GITHUB_RUN_NUMBER:-NAO_MEDIDO}"
} > ios-probe/ARBuildProvenance.h
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
# M7.43 GOWA.ELF 6251 AOT offline batch (generated C compressed losslessly).
# Every generated module must decode, match the original C SHA-256, compile
# using Apple clang ARM64, and retain all 6251 symbols in final Mach-O.
# The source ELF is NOT in the git tree or the IPA.
GOWA2_OBJECTS=()
test -s runtime/gowa2-offline/symbols.txt.gz.b64 || {
  echo 'M7.43 GOWA2 offline AOT source payload not staged' >&2
  exit 78
}
python3 tools/gowa2_offline_stage.py --source runtime/gowa2-offline \
  --dest ios-probe/gowa2-staged | tee m743-gowa2-stage.log
for chunk in 00 01 02 03 04 05 06 07 08; do
  unit="ppu_gowa2_offline_aot_${chunk}"
  xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O0 -Wall -Wextra -Werror -Wno-unused-label -Wno-unused-function -Wno-parentheses-equality \
    -I upstream/runtime/ppu -I runtime \
    -c "ios-probe/gowa2-staged/${unit}.c" -o "ios-probe/${unit}.o"
  xcrun nm -g "ios-probe/${unit}.o" >> m743-gowa2-objects-nm.txt
  GOWA2_OBJECTS+=("ios-probe/${unit}.o")
done
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O0 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/gowa2-offline/ppu_gowa2_offline_aot_install.c \
    -o ios-probe/ppu_gowa2_offline_aot_install.o
GOWA2_OBJECTS+=(ios-probe/ppu_gowa2_offline_aot_install.o)
python3 tools/verify_gowa2_macho.py ios-probe/gowa2-staged/symbols.txt \
  m743-gowa2-objects-nm.txt | tee m743-gowa2-object-verified.log
AOT_COMPILE_DEFINES+=(-DASCENSION_GOWA2_OFFLINE_AOT_LINKED)
# M7.44: owner-authenticated two-op CROR+BC is genuinely compiled ARM64.
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_m744_native_cror.c -o ios-probe/ppu_m744_native_cror.o
# M7.45: six executable PPC guest instructions compiled Apple ARM64.
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_m745_native_srw.c -o ios-probe/ppu_m745_native_srw.o
# M7.46: whole 69-instruction owner hot loop + three entry points, ARM64.
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_m746_native_loop.c -o ios-probe/ppu_m746_native_loop.o
# M7.47 real FMR + indirect guest call: two SHA-authenticated ARM64 entries.
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_m747_native_fmr.c -o ios-probe/ppu_m747_native_fmr.o
# M7.48: full 31 PPC signed owner VMX startup & 18-opcode suffix.
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_m748_native_vcfsx.c -o ios-probe/ppu_m748_native_vcfsx.o
# M7.49: owner PPC64 FRSP frontier compiled as native Apple ARM64.
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_m749_native_frsp.c -o ios-probe/ppu_m749_native_frsp.o
# M7.50: real 19+5 signed PPC words compiled into native ARM64.
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_m750_native_path.c -o ios-probe/ppu_m750_native_path.o
# M7.51 original owner VMX and genuine guest filesystem HLE.
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_m751_vsubfp.c -o ios-probe/ppu_m751_vsubfp.o
# M7.52: next genuine signed PPC VSLDOI executed as ARM64, not host probe.
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_m752_vsldoi.c -o ios-probe/ppu_m752_vsldoi.o
# M7.53 native owner-verified 4 VMX FP words.
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_m753_native_vectorfp.c -o ios-probe/ppu_m753_native_vectorfp.o
# M7.54: original PPC FCMPU+BC branch taken/not-taken, Apple ARM64.
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_m754_native_fcmp.c -o ios-probe/ppu_m754_native_fcmp.o
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_guest_fs.c -o ios-probe/ppu_guest_fs.o
# Stage the native PPU bridge as an ARM64 object and link the prebuilt
# IOS PPU core archive; never compile or bundle the user's PS3 ELF.
test -s ios-ppu-core/libAscensionPPUCore-ios-arm64.a
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror \
    -I upstream/runtime/ppu -I runtime \
    -DASCENSION_NATIVE_ONLY=1 \
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
# M7.32: nine new owner-authenticated PPC instructions compiled ARM64.
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_m732_native_timezone.c -o ios-probe/ppu_m732_native_timezone.o
# M7.34: natively linked 29-op signed PPC64 arithmetic block.
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_m734_native_math.c -o ios-probe/ppu_m734_native_math.o
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_m734_native_batch.c -o ios-probe/ppu_m734_native_batch.o
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_m735_native_time.c -o ios-probe/ppu_m735_native_time.o
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_m736_native_time.c -o ios-probe/ppu_m736_native_time.o

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
    ios/ARMetalView.m ios/ARProbeApp.m ios/ARGameFolderStore.m ios/ARShaderProbe.m ios/ARTextureProbe.m ios/ARProbeGuestVM.c \
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
    ios-probe/ppu_m732_native_timezone.o \
    ios-probe/ppu_m734_native_math.o \
    ios-probe/ppu_m734_native_batch.o \
    ios-probe/ppu_m735_native_time.o \
    ios-probe/ppu_m736_native_time.o \
    ios-probe/ppu_m744_native_cror.o \
    ios-probe/ppu_m745_native_srw.o \
    ios-probe/ppu_m746_native_loop.o \
    ios-probe/ppu_m747_native_fmr.o \
    ios-probe/ppu_m748_native_vcfsx.o \
    ios-probe/ppu_m749_native_frsp.o \
    ios-probe/ppu_m750_native_path.o \
    ios-probe/ppu_m751_vsubfp.o ios-probe/ppu_m752_vsldoi.o ios-probe/ppu_m753_native_vectorfp.o ios-probe/ppu_m754_native_fcmp.o ios-probe/ppu_guest_fs.o \
    ${GOWA2_OBJECTS[@]+"${GOWA2_OBJECTS[@]}"} \
    ios-probe/ppu_m717_graph.o \
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
python3 tools/verify_gowa2_macho.py ios-probe/gowa2-staged/symbols.txt \
 m78-owner-aot-linked-symbols.txt | tee m743-gowa2-final-verified.log
grep -Eq ' [Tt] _ar_gowa2_offline_aot_install_sha256$' m78-owner-aot-linked-symbols.txt
grep -Fq '_ar_private_aot_install_sha256' m78-owner-aot-linked-symbols.txt
grep -Fq '_ar_ppu_timebase_ticks' m78-owner-aot-linked-symbols.txt
# M7.33 final Mach-O must retain ACTUAL production LV2 service binder.
grep -Eq ' [Tt] _ar_lv2_bind_bootstrap_syscalls$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_lv2_timezone$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m751_register_vsubfp$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m752_register_vsldoi$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m753_register_vectorfp$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m754_register_fcmp_branch$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m754_native_003b064c$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m753_native_003b062c$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m752_native_003b0608$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m751_native_003b0604$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_fs_guest_open$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_fs_guest_read$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_fs_guest_close$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_fs_bind_syscalls$' m78-owner-aot-linked-symbols.txt
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
grep -Eq ' [Tt] _ar_m732_native_005230e0$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m732_register_block$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m734_native_0052aa1c$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m734_register_block$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m734_register_batch$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m735_register_owner$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m736_register_owner$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m736_native_00524b8c$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m735_native_0052ab58$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m734_native_0052a9a0$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m734_native_0052a910$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m716_verified_successors$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m717_walk$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m717_last_aot_trace$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_trace_snapshot$' m78-owner-aot-linked-symbols.txt
if grep -Eq ' [Tt] _ar_ppc_fallback_step$' m78-owner-aot-linked-symbols.txt; then
  echo 'FAIL M7.55: PPC interpreter linked into AOT-only iOS binary' >&2
  exit 81
fi
if grep -Eq ' [Tt] _ar_ppc_fallback_attach$' m78-owner-aot-linked-symbols.txt; then
  echo 'FAIL M7.55: interpreter attach entrypoint still linked into AOT-only iOS binary' >&2
  exit 82
fi
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
echo 'M7.32: +1 SHA-gated ELF-verified 9-instruction native ARM64 function at guest 0x005230E0; total expected 1421 on owner ELF; LV2 #144 writes timezone via the host operating-system timezone.' >> m78-aot-status.txt
echo 'M7.33: actual iOS LV2 144 registration shared with production synthetic regression; AOT count 1421 unchanged, on-device crossing pending.' >> m78-aot-status.txt
echo 'M7.34: 11 new native ARM64 basic blocks (77 real guest PPC instructions) selected from authenticated owner ELF trace. Existing 1421 AOT preserved; count after registration expected 1432 if no overlaps. Native vs fallback distinguished on device.' >> m78-aot-status.txt
echo 'M7.35: +7 original owner-ELF SHA/VM authenticated native AOT entries, 80 distinct PowerPC instructions across time arithmetic and date loop; expected 1439 AOT installed, no claim of cellFs yet.' >> m78-aot-status.txt
echo 'M7.36: one SHA-verified original owner-ELF nine-opcode time continuation AOT at 0x00524B8C; expected 1440 registered native entries. Generic signed MULHW PPC fallback; no filesystem/RSX claim.' >> m78-aot-status.txt
echo 'M7.37: F0 selected game-folder host access with bookmark, read-only manifest and real bounded host file prefix; no cellFs syscall claimed. PPC integer family + fallback budgets 16384/32768; AOT count unchanged.' >> m78-aot-status.txt
echo 'M7.38: fixed ar_ppc_fallback_attach max to 16384 matching iOS request, eliminating M7.37 loader=-38 before AOT. Folder picker message and full local error report. Native execution on iPhone must be rechecked.' >> m78-aot-status.txt
echo 'M7.39: local Files/Documents NPUA80918 importer bypasses inert cloud folder picker; verified synthetic macOS Files-path scan and 4-byte file read, guest sys_fs open/read still pending.' >> m78-aot-status.txt
echo 'M7.40: no-copy in-place read-only PARAM.SFO permission probe for original RPCS3 game installation. Uses NSFileCoordinator and iOS scoped URL; no permission bypass, no game file modifications, VFS not yet demonstrated.' >> m78-aot-status.txt
echo 'M7.41: permissive UTTypeItem file filter for unknown PS3 .SFO extension, asCopy:NO; PPC DCBT/DCBTST cache-hint ISA fallback verified; 1440 owner-native AOT preserved. No guest filesystem or game access implied.' >> m78-aot-status.txt
echo 'M7.42: implemented PowerPC64 NOR/CNTLZD/NAND/EQV/ORC/ANDC generic ISA fallback, correct Rc CR0 and preserved XER/ABI, reg aliasing; native AOT remains 1440; iOS sandbox access to RPCS3 remains unproven.' >> m78-aot-status.txt
echo 'M7.43: verified Apple ARM64 object and FINAL Mach-O contain all 6251 offline GOWA.ELF AOT functions; SHA-gated install after 1440 legacy AOT registrations, no guest execution count until iPhone test.' >> m78-aot-status.txt
file "$APP/AscensionRecompProbe" | tee m41-executable-file.txt
xcrun lipo -info "$APP/AscensionRecompProbe" | tee m41-executable-arch.txt
/usr/libexec/PlistBuddy -c 'Print CFBundleIdentifier' "$APP/Info.plist"
echo 'M7.44: owner ELF CROR+BC 0x003F2860 / 0x003F2864 native ARM64 AOT verified behind SHA gate and registered AFTER 6251 offline entries; next physical iPhone PC not yet proven.' >> m78-aot-status.txt
echo 'M7.45: native SRW/CMPWI/ANDC/ADDI/STW/BC at 0x0052BA70 owner authenticated, generic SRW fallback and iOS security-scoped folder grant order fixed.' >> m78-aot-status.txt
echo 'M7.46: four SHA-gated and PT_LOAD/VM-verified native ARM64 guest entries covering 69 original PPC words incl. 32+5 CTR loops, 64-iteration guard. iPhone not yet tested; guest files/RSX unproven.' >> m78-aot-status.txt
echo 'M7.47: FMR raw-bit preservation enabled in PPC fallback and lifter, two original SHA-verified FMR native ARM64 blocks at 0x003EEF0C and 0x003EEF20. Small copy-mode PARAM.SFO import with independent TITLE_ID parser, app-owned Documents folders, game directory access separate. Device test pending.' >> m78-aot-status.txt
echo 'M7.48: 31 original owner PPC native VMX instructions at 0x003DDF20 and 18-word hot suffix 0x003DDF54. Generic VMX VCFSX 4-lane signed-fixed to IEEE754 RN ties-even added to AOT lifter+fallback. Detect Documents/AscensionRecomp/NPUA80918; empty titles rejected. Not proven on iPhone yet.' >> m78-aot-status.txt
echo 'M7.49: UI local file detection button now ARRANGED/visible. FRSP original 0x003B1D5C statically compiled to ARM64 and registered after executable ELF/VM authentication+whole SHA; scalar FRSP supported in generic lifter and fallback. iPhone physical test pending.' >> m78-aot-status.txt
echo 'M7.50: genuine original fsubs/stfs/12STVX and BDNZ 24 PPC across 2 native AOT entries, ELF+VM authenticated. Reports distinguish build and legacy runtime, no guest cellFs claimed without execution.' >> m78-aot-status.txt
echo 'M7.51: native owner vsubfp 0x003B0604 plus guest-only read-only sys_fs open/read/close, guarded by local manifest; iPhone proof pending.' >> m78-aot-status.txt
echo 'M7.52: VMX VSLDOI at 0x003B0608 owner ELF/PT_LOAD X+VM authenticated; registered ARM64 entry. Correct guest vs host evidence and M7.51 physical baseline, no filesystem success assumed.' >> m78-aot-status.txt
echo 'M7.53: family VMX float vrefp/vmaddfp/vnmsubfp generically supported in PPC lifter and fallback; four owner PPC ops 0x003B062C-0x003B0638 AOT authenticated; iPhone measurement pending.' >> m78-aot-status.txt
echo 'M7.54: generic FCMPU/FCMPO correct CR field and FPSCR FPCC; owner PPC two-word FCMPU+BC 0x003B064C authenticated, both branch successors; no guest file reading proved until physical run.' >> m78-aot-status.txt
echo 'M7.55: iOS core without PPC fallback; unresolved AOT PC fails closed. Whole ELF coverage NOT proven, no gameplay or guest filesystem claimed.' >> m78-aot-status.txt
(cd ios-probe && zip -q -r ../AscensionRecompProbe-0.6.22-unsigned.ipa Payload)
test -s AscensionRecompProbe-0.6.22-unsigned.ipa
shasum -a 256 AscensionRecompProbe-0.6.22-unsigned.ipa > m41-ipa-sha256.txt
echo 'UNSIGNED DIAGNOSTIC APP: UIKit CAMetalLayer + real PS3Recomp Metal backend; NO GOWA GAME included' > m41-status.txt
