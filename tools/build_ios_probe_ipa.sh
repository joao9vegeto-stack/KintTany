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
# M7.56: signed owner PPC division loop with exact BEQ successors.
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_m756_native_divloop.c -o ios-probe/ppu_m756_native_divloop.o
# M7.57: guest PPC branches translated into signed Apple ARM64 (13+3 ops).
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_m757_native_batch.c -o ios-probe/ppu_m757_native_batch.o
# M7.58: reproducible whole-PC-range AOT generated by existing CFG lifter.
# Only its static owner PPC words are inputs; no ELF/game data stored in IPA.
python3 tools/generate_m758_owner_aot.py --output runtime/ppu_m758_generated.c
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_m758_generated.c -o ios-probe/ppu_m758_generated.o
# M7.59: 42 PPC words until next branch; no runtime interpreter.
python3 tools/generate_m759_owner_aot.py --output runtime/ppu_m759_generated.c
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_m759_generated.c -o ios-probe/ppu_m759_generated.o
# M7.61: a whole authenticated multi-span guest AOT batch; no PPC interpreter.
python3 tools/generate_m761_owner_batch.py --output runtime/ppu_m761_generated.c --report m761-owner-batch.json
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -Wno-unused-label -Wno-unused-function -Wno-parentheses-equality \
    -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_m761_generated.c -o ios-probe/ppu_m761_generated.o
xcrun nm -g ios-probe/ppu_m761_generated.o | grep -Fq '_ar_m761_native_003e16e0'
# M7.62: immutable semantic AOT snapshot produced by OFFLINE complete ELF
# inventory. Original GOWA.ELF is NOT on GitHub runner / IPA.
python3 - <<'PY'
import base64,gzip,hashlib
from pathlib import Path
encoded=Path("runtime/m762_semantic_snapshot.gz.b64").read_text()
raw=gzip.decompress(base64.b64decode(encoded,validate=True))
digest=hashlib.sha256(raw).hexdigest()
assert digest=="07b74c4557b4951c3c113c998dc5895932e28b33cf240fdc13f9315fe7d84eb3",digest
Path("m762-semantic-snapshot.json").write_bytes(raw)
print("M7.62 canonical offline semantic snapshot",digest)
PY
python3 tools/m762_pipeline.py --snapshot m762-semantic-snapshot.json --output-dir runtime | tee m762-generation.log
M762_OBJECTS=()
for src in runtime/ppu_m762_0{0..6}.c runtime/ppu_m762_install.c; do
  test -s "$src"
  dst="ios-probe/$(basename "${src%.c}").o"
  xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c "$src" -o "$dst"
  M762_OBJECTS+=("$dst")
done
xcrun nm -g "${M762_OBJECTS[@]}" > m762-objects-nm.txt
grep -Fq '_ar_m762_native_002c53b0' m762-objects-nm.txt
grep -Fq '_ar_m762_register_discovered' m762-objects-nm.txt
# M7.63 strict full-ELF OPD/CFG semantic-family batch, no guest interpreter.
python3 - <<'PY'
import base64,gzip,hashlib
from pathlib import Path
raw=gzip.decompress(base64.b64decode(Path("runtime/m763_semantic_snapshot.gz.b64").read_text(),validate=True))
actual=hashlib.sha256(raw).hexdigest()
assert actual=="d7f7e024263d888c1b834a7ecddb1cafb862f64a0b066f6dbccb596026c854e7", actual
Path("m763-semantic-snapshot.json").write_bytes(raw)
PY
python3 tools/m763_expand.py --snapshot m763-semantic-snapshot.json --output-dir runtime | tee m763-generation.log
M763_OBJECTS=()
for src in runtime/ppu_m763_[0-9][0-9].c runtime/ppu_m763_install.c; do
  test -s "$src"
  dst="ios-probe/$(basename "${src%.c}").o"
  xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c "$src" -o "$dst"
  M763_OBJECTS+=("$dst")
done
xcrun nm -g "${M763_OBJECTS[@]}" > m763-objects-nm.txt
grep -Fq '_ar_m763_native_002c53bc' m763-objects-nm.txt
grep -Fq '_ar_m763_register_discovered' m763-objects-nm.txt
# M7.64: immutable native CFG B-tail snapshot from full GOWA ELF.
python3 - <<'PY'
import base64,gzip,hashlib,json
from pathlib import Path
raw=gzip.decompress(base64.b64decode(Path('runtime/m764_semantic_snapshot.gz.b64').read_text().strip(),validate=True))
assert hashlib.sha256(raw).hexdigest()=='af303e2ee4b332c4f933ac9894b1f5922d4512a1d4199bbfa5d8328d8ba9fec0'
snap=json.loads(raw)
assert snap['opd_unique']==7643 and len(snap['accepted'])==31
assert any(x['pc']==0x539378 for x in snap['accepted'])
Path('m764-snapshot-ci.json').write_bytes(raw)
PY
python3 tools/m764_cfg_blocks.py --snapshot m764-snapshot-ci.json --output-dir runtime | tee m764-generation.log
M764_OBJECTS=()
for src in runtime/ppu_m764_[0-9][0-9].c runtime/ppu_m764_install.c; do
  test -s "$src"
  dst="ios-probe/$(basename "${src%.c}").o"
  xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c "$src" -o "$dst"
  M764_OBJECTS+=("$dst")
done
xcrun nm -g "${M764_OBJECTS[@]}" > m764-objects-nm.txt
grep -Fq '_ar_m764_native_00539378' m764-objects-nm.txt
grep -Fq '_ar_m764_register_discovered' m764-objects-nm.txt
# M7.64.1: offline-generated immutable six successor blocks, including 0x005392A4.
python3 - <<'PY'
import base64,gzip,hashlib,json
from pathlib import Path
raw=gzip.decompress(base64.b64decode(Path('tools/m764_cfg_successors.py.gz.b64').read_text().strip(),validate=True))
assert hashlib.sha256(raw).hexdigest()=='8404c4135217924479a03795c86d0efb418eda78c58ddb7cdb2f509850e7c47c'
Path('tools/m764_cfg_successors.py').write_bytes(raw)
snap=gzip.decompress(base64.b64decode(Path('runtime/m764c_semantic_snapshot.gz.b64').read_text().strip(),validate=True))
assert hashlib.sha256(snap).hexdigest()=='413409725d9f59d0f3cbec7c85ede61b3229017c151a99aa3acbe7446ef193cf'
s=json.loads(snap)
assert len(s['accepted'])==6 and s['unique_successor_pcs']==26
assert any(q['pc']==0x5392a4 for q in s['accepted'])
Path('m764c-snapshot-ci.json').write_bytes(snap)
PY
python3 tools/m764_cfg_successors.py --snapshot m764c-snapshot-ci.json --output-dir runtime | tee m764c-generation.log
M764C_OBJECTS=()
for src in runtime/ppu_m764c_[0-9][0-9].c runtime/ppu_m764c_install.c; do
  test -s "$src"
  dst="ios-probe/$(basename "${src%.c}").o"
  xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c "$src" -o "$dst"
  M764C_OBJECTS+=("$dst")
done
xcrun nm -g "${M764C_OBJECTS[@]}" > m764c-objects-nm.txt
grep -Fq '_ar_m764c_native_005392a4' m764c-objects-nm.txt
grep -Fq '_ar_m764c_register_successors' m764c-objects-nm.txt
# M7.65 frozen ELF-derived PPC CFG, source bytes excluded from IPA/CI.
python3 - <<'PY'
import base64,gzip,hashlib,json
from pathlib import Path
checks={
 'runtime/m765_ppu_native.gz.b64':('runtime/ppu_m765_00.c','007aee6ecd829662101390982a73233868741fd6377c2a07da0806d8a87da01f'),
 'runtime/m765_ppu_installer.gz.b64':('runtime/ppu_m765_install.c','44ac1ea7a86011057f1841dfc94bb333de8c1c2bc2109f63106acaae27b89075'),
 'runtime/m765_semantic_snapshot.gz.b64':('m765-snapshot-ci.json','9fe737fff36697cf7c59dd3416b8adf0e02901df3ed90ef1dc5384f0da877024')
}
for src,(dst,sha) in checks.items():
 data=gzip.decompress(base64.b64decode(Path(src).read_text().strip(),validate=True))
 if hashlib.sha256(data).hexdigest()!=sha:raise ValueError('frozen AOT checksum mismatch '+src)
 Path(dst).write_bytes(data)
s=json.loads(Path('m765-snapshot-ci.json').read_text())
assert s['schema']=='ascension-m765-executable-frontier-cfg-1'
assert s['source_sha256']=='4bf75c897b82d1beb25514cbadaff3d03e1b0c7bf849fa5d289be4f9183462b5'
assert s['total_examined']==27 and len(s['accepted'])==18 and len(s['rejected'])==9
assert any(b['pc']==0x539308 and b['ir']==[['bc',4,6,0x5392f4,0x53930c]] for b in s['accepted'])
assert any(b['pc']==0x53930c and b['ir'][-1]==['bl',0x539654,0x539324] for b in s['accepted'])
print('M7.65 strict CFG 18 blocks/33 edges; device execution NOT MEASURED')
PY
M765_OBJECTS=()
for src in runtime/ppu_m765_00.c runtime/ppu_m765_install.c; do
  test -s "$src"
  dst="ios-probe/$(basename "${src%.c}").o"
  xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c "$src" -o "$dst"
  M765_OBJECTS+=("$dst")
done
xcrun nm -g "${M765_OBJECTS[@]}" > m765-objects-nm.txt
grep -Fq '_ar_m765_native_00539308' m765-objects-nm.txt
grep -Fq '_ar_m765_native_0053930c' m765-objects-nm.txt
grep -Fq '_ar_m765_register_frontier' m765-objects-nm.txt
# M7.66 strict PPC CFG frozen offline IR; source ELF never enters CI/IPA.
python3 - <<'PY'
import base64,gzip,hashlib,json
from pathlib import Path
files={
 'tools/m766_cfg.py.gz.b64':('tools/m766_cfg.py','f903c2fc09e0db48976a01e386da8d2a07c2ea714a6bcd45a99f042aec98ad05'),
 'runtime/m766-snapshot.json.gz.b64':('m766-snapshot-ci.json','c69d5507ee4290c6df8a1ccc372be0f494d45b96792d1dd881f3d71634d6e0d7')
}
for src,(dest,sha) in files.items():
 data=gzip.decompress(base64.b64decode(Path(src).read_text().strip(),validate=True))
 assert hashlib.sha256(data).hexdigest()==sha,src
 Path(dest).write_bytes(data)
s=json.loads(Path('m766-snapshot-ci.json').read_text())
assert s['schema']=='ascension-m766-executable-frontier-cfg-1'
assert s['source_sha256']=='4bf75c897b82d1beb25514cbadaff3d03e1b0c7bf849fa5d289be4f9183462b5'
assert s['total_examined']==274 and len(s['accepted'])==254 and len(s['rejected'])==20
assert len(s['edges'])==369
assert sum(bool(b['import_veneer_requires_binding']) for b in s['accepted'])==7
assert next(b for b in s['accepted'] if b['pc']==0x5394e8)['ir'][0]==['lwz',9,2,-22428]
assert next(b for b in s['accepted'] if b['pc']==0x669a84)['import_veneer_requires_binding']
print('M7.66 frozen PPC CFG: 254 native full blocks, 20 strict rejections, 369 edges, 7 HLE/import gated')
PY
python3 tools/m766_cfg.py --snapshot m766-snapshot-ci.json --output-dir runtime | tee m766-generation.log
M766_OBJECTS=()
for src in runtime/ppu_m766_[0-9][0-9].c runtime/ppu_m766_install.c; do
  test -s "$src"
  dst="ios-probe/$(basename "${src%.c}").o"
  xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c "$src" -o "$dst"
  M766_OBJECTS+=("$dst")
done
xcrun nm -g "${M766_OBJECTS[@]}" > m766-objects-nm.txt
grep -Fq '_ar_m766_native_005394e8' m766-objects-nm.txt
grep -Fq '_ar_m766_native_00669a84' m766-objects-nm.txt
grep -Fq '_ar_m766_register_frontier' m766-objects-nm.txt
# M7.69: ORIGINAL ASCENSION (NPUA80918) static PPC CFG, offline owner SHA authenticated.
# No GOWA ELF/SELF/RAP/PSARC or guest asset included in GitHub/CI/IPA.
python3 - <<'PY'
import base64,gzip,hashlib,json
from pathlib import Path
files={
 'tools/m769_cfg.py.gz.b64':('tools/m769_cfg.py','f00f833b5776acd773f35c76f07e5009679531afc77feb5e9937d5bbcf3a33d4')
}
for src,(dest,sha) in files.items():
 raw=gzip.decompress(base64.b64decode(Path(src).read_text().strip(),validate=True))
 assert hashlib.sha256(raw).hexdigest()==sha,src
 Path(dest).write_bytes(raw)
parts=sorted(Path('runtime').glob('m769-snapshot.part[0-9][0-9].b64'))
assert len(parts)==15, len(parts)
joined=''.join(x.read_text().strip() for x in parts)
raw=gzip.decompress(base64.b64decode(joined,validate=True))
assert hashlib.sha256(raw).hexdigest()=='eead98450296a0145227d08223463093324a1539c1465ae50204ae4fb5450734'
Path('m769-snapshot-ci.json').write_bytes(raw)
a=json.loads(raw)
assert a['schema']=='ascension-m769-scaled-opd-cfg-1'
assert a['source_sha256']=='4bf75c897b82d1beb25514cbadaff3d03e1b0c7bf849fa5d289be4f9183462b5'
assert a['opd_descriptors']==7643 and a['recovered_interval_candidates_not_authoritative']==16841
assert a['source_prx_imports']==350
assert len(a['accepted'])==5437 and len(a['rejected'])==3046
assert a['queued_deferred_not_examined']==6554 and len(a['edges'])==8313
assert sum(b['count'] for b in a['accepted'])==41735
assert a['accepted'][0]['pc']==0x53979c and a['accepted'][0]['ir'][-1]==['bl',0x669a84,0x5397bc]
assert sum(bool(b['import_veneer_requires_binding']) for b in a['accepted'])==7
print('M7.69 owner-ELF 5437 complete PPC CFG blocks; 3046 true rejects; 6554 deferred, not treated as decoded')
PY
python3 tools/m769_cfg.py --snapshot m769-snapshot-ci.json --output-dir runtime | tee m769-generation.log
M769_OBJECTS=()
for src in runtime/ppu_m769_[0-9][0-9].c runtime/ppu_m769_install.c; do
  test -s "$src"
  dst="ios-probe/$(basename "${src%.c}").o"
  xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c "$src" -o "$dst"
  M769_OBJECTS+=("$dst")
done
xcrun nm -g "${M769_OBJECTS[@]}" > m769-objects-nm.txt
grep -Fq '_ar_m769_native_0053979c' m769-objects-nm.txt
grep -Fq '_ar_m769_native_005397bc' m769-objects-nm.txt
grep -Fq '_ar_m769_register_frontier' m769-objects-nm.txt
grep -Fq '_ar_m769_get_stats' m769-objects-nm.txt
# M7.56: capture live guest memory vs PT_LOAD file bytes, not fallback counters.
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_m756_stop_evidence.c -o ios-probe/ppu_m756_stop_evidence.o
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror -I upstream/runtime/ppu -I runtime \
    -c runtime/ppu_guest_fs.c -o ios-probe/ppu_guest_fs.o
# Stage the native PPU bridge as an ARM64 object and link the prebuilt
# IOS PPU core archive; never compile or bundle the user's PS3 ELF.
test -s ios-ppu-core/libAscensionPPUCore-ios-arm64.a
xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \
    -std=c11 -O2 -Wall -Wextra -Werror \
    -I upstream/runtime/ppu -I runtime \
    -DASCENSION_NATIVE_ONLY=1 -DASCENSION_M772_LINKED=1 \
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
if [[ -z "${M772_LIFT_DIR:-}" ]]; then
  echo 'M7.72 ps3recomp lift source is not staged' >&2
  exit 78
fi
python3 tools/m772_build_ios.py \
  --source "$M772_LIFT_DIR" \
  --upstream upstream-m772 \
  --repo . \
  --output ios-probe/m772 \
  --jobs "${M772_JOBS:-3}"
M772_ARCHIVE=ios-probe/m772/libAscensionGOWA-M772-ios-arm64.a
test -s "$M772_ARCHIVE"
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
    ios-probe/ppu_m751_vsubfp.o ios-probe/ppu_m752_vsldoi.o ios-probe/ppu_m753_native_vectorfp.o ios-probe/ppu_m754_native_fcmp.o ios-probe/ppu_m756_native_divloop.o ios-probe/ppu_m757_native_batch.o ios-probe/ppu_m758_generated.o ios-probe/ppu_m759_generated.o ios-probe/ppu_m761_generated.o ios-probe/ppu_m756_stop_evidence.o ios-probe/ppu_guest_fs.o \
    ${M762_OBJECTS[@]+"${M762_OBJECTS[@]}"} \
    ${M763_OBJECTS[@]+"${M763_OBJECTS[@]}"} \
    ${M764_OBJECTS[@]+"${M764_OBJECTS[@]}"} \
    ${M764C_OBJECTS[@]+"${M764C_OBJECTS[@]}"} \
    ${M765_OBJECTS[@]+"${M765_OBJECTS[@]}"} \
    ${M766_OBJECTS[@]+"${M766_OBJECTS[@]}"} \
    ${M769_OBJECTS[@]+"${M769_OBJECTS[@]}"} \
    ${GOWA2_OBJECTS[@]+"${GOWA2_OBJECTS[@]}"} \
    ios-probe/ppu_m717_graph.o \
    ${M711_OBJECTS[@]+"${M711_OBJECTS[@]}"} \
    ${AOT_OBJECTS[@]+"${AOT_OBJECTS[@]}"} \
    "$M772_ARCHIVE" \
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
python3 - <<'PYM772LINKED'
from pathlib import Path
lines=Path("m78-owner-aot-linked-symbols.txt").read_text(errors="replace").splitlines()
defined=[]
for line in lines:
    fields=line.split()
    if len(fields)>=2 and fields[-2] in {"T","t","D","d","B","b","R","r","S","s"}:
        defined.append(fields[-1])
required=("func_0052A740", "func_0052E3F4", "_ar_m772_runtime_attest",
          "_ar_m772_runtime_init", "_ar_m772_dispatch_native",
          "_ppu_recomp_register", "_gowa_spu_0000_at_006B3E00_spu_recomp_register",
          "_gowa_spu_0003_at_006D5900_spu_recomp_register")
missing=[symbol for symbol in required if not any(symbol in name for name in defined)]
if missing: raise SystemExit("M7.72 expected AOT definitions missing from final Mach-O: "+str(missing))
print("M7.72 final ARM64 Mach-O contains frontier, table-registration and SPU registration symbols")
PYM772LINKED
# Every M7.62 native function must appear in the FINAL Mach-O, not merely object.
python3 - <<'PY'
import json,re
from pathlib import Path
s=json.loads(Path("m762-semantic-snapshot.json").read_text())
expected={"_ar_m762_native_%08x"%e["pc"] for e in s["accepted"]}
symbols=Path("m78-owner-aot-linked-symbols.txt").read_text()
missing=sorted(x for x in expected|{"_ar_m762_register_discovered"} if not any(line.endswith(" "+x) and (" T " in line or " t " in line) for line in symbols.splitlines()))
if missing:raise SystemExit("M7.62 unlinked native AOT: "+str(missing[:25]))
Path("m762-final-attestation.json").write_text(json.dumps({
 "schema":"m762-apple-arm64-native-proof-1","native_symbols_final_macho":len(expected),
 "native_symbols_object":len(expected),"source_elf_sha256":s["source_sha256"],
 "aot_executed_on_iphone":"NOT_MEASURED","guest_fs":"NOT_MEASURED",
 "note":"Frozen IR compiled and linked, ELF not present in CI; no global coverage claim"
},indent=2))
print("M7.62 final AOT symbols verified",len(expected))
PY
# M7.63 attest exactly 1582 newly compiled and linked AOT guest functions.
python3 - <<'PY'
import json,re
from pathlib import Path
s=json.loads(Path("m763-semantic-snapshot.json").read_text())
expect={"ar_m763_native_%08x"%q["pc"] for q in s["accepted"]}
installer="ar_m763_register_discovered"
assert len(expect)==1582 and sum(q["count"] for q in s["accepted"])==8313
pattern=re.compile(r"\s[Tt]\s+_?(ar_m763_native_[0-9a-f]{8}|ar_m763_register_discovered)$")
def symbols(name):
 return {m.group(1) for line in Path(name).read_text().splitlines() if (m:=pattern.search(line))}
obj=symbols("m763-objects-nm.txt");final=symbols("m78-owner-aot-linked-symbols.txt")
required=expect|{installer}
if required-obj or required-final:raise SystemExit("M7.63 UNLINKED ARM64 symbols in object/final: %s / %s"%(list(required-obj)[:10],list(required-final)[:10]))
Path("m763-final-attestation.json").write_text(json.dumps({"schema":"m763-apple-arm64-proof-1","new_native_functions_compiled":len(expect),"new_native_functions_linked":len(expect),"ppc_words":8313,"ios_arch":"arm64","device_executed":"NOT_MEASURED","guest_fs":"NOT_MEASURED","raw_ELF_embedded":False},indent=2)+"\n")
print("M7.63 native Apple ARM64 AOT compiled/linked",len(expect),"source PPC",8313)
PY
python3 tools/verify_gowa2_macho.py ios-probe/gowa2-staged/symbols.txt \
 m78-owner-aot-linked-symbols.txt | tee m743-gowa2-final-verified.log
grep -Eq ' [Tt] _ar_gowa2_offline_aot_install_sha256$' m78-owner-aot-linked-symbols.txt
grep -Fq '_ar_private_aot_install_sha256' m78-owner-aot-linked-symbols.txt
grep -Fq '_ar_ppu_timebase_ticks' m78-owner-aot-linked-symbols.txt
# M7.64 actual native tail and installer symbols in FINAL Mach-O.
grep -Eq ' [Tt] _ar_m764_native_00539378$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m764_register_discovered$' m78-owner-aot-linked-symbols.txt
python3 - <<'PY'
import json
from pathlib import Path
snap=json.loads(Path('m764-snapshot-ci.json').read_text())
assert len(snap['accepted'])==31
Path('m764-final-attestation.json').write_text(json.dumps({
 'schema':'m764-apple-arm64-proof-1',
 'semantic_blocks_generated':len(snap['accepted']),
 'real_stop_native_symbol':'ar_m764_native_00539378',
 'native_installer':'ar_m764_register_discovered',
 'final_macho':'SYMBOLS_VERIFIED',
 'device_executed':'NOT_MEASURED',
 'guest_fs':'NOT_MEASURED',
 'source_elf_sha256':snap['source_sha256'],
 'embedded_elf':False},indent=2)+'\n')
PY
# M7.64.1: original next guest CFG block and installer in FINAL Mach-O.
grep -Eq ' [Tt] _ar_m764c_native_005392a4$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m764c_register_successors$' m78-owner-aot-linked-symbols.txt
python3 - <<'PY'
import json
from pathlib import Path
s=json.loads(Path('m764c-snapshot-ci.json').read_text())
Path('m764c-final-attestation.json').write_text(json.dumps({
 'schema':'ascension-m7641-native-successors-1',
 'blocks_in_frozen_IR':len(s['accepted']),
 'first_level_successor_candidates':s['unique_successor_pcs'],
 'linked_symbols_verified':['ar_m764c_native_005392a4','ar_m764c_register_successors'],
 'ios_arch':'arm64','executed_on_iphone':'NOT_MEASURED',
 'cell_fs_guest':'NOT_MEASURED',
 'elf_sha256':s['source_sha256']},indent=2)+'\n')
PY
# M7.65 actual FINAL ARM64 Mach-O linked AOT proof, no guest execution claim.
grep -Eq ' [Tt] _ar_m765_native_00539308$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m765_native_0053930c$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m765_register_frontier$' m78-owner-aot-linked-symbols.txt
python3 - <<'PY'
import json
from pathlib import Path
s=json.loads(Path('m765-snapshot-ci.json').read_text())
m={'schema':'ascension-m765-apple-arm64-1','original_pc':'0x00539308',
'native_blocks_generated':len(s['accepted']),'unsupported_candidates':len(s['rejected']),
'cfg_edges':len(s['edges']),'compile':'iPhoneOS/ARM64',
'final_MachO_symbols_verified':['ar_m765_native_00539308','ar_m765_native_0053930c','ar_m765_register_frontier'],
'iphone_executed':'NOT_MEASURED','guest_cellFsOpen':'NOT_MEASURED','guest_cellFsRead_positive':'NOT_MEASURED'}
Path('m765-final-attestation.json').write_text(json.dumps(m,indent=2)+'\n')
PY
# M7.66 verify 254 native PPC block symbols in final ARM64 Mach-O.
python3 - <<'PY'
import json,re
from pathlib import Path
s=json.loads(Path('m766-snapshot-ci.json').read_text())
nm=Path('m78-owner-aot-linked-symbols.txt').read_text()
linked=set(re.findall(r' [Tt] _([A-Za-z0-9_]+)\s*$',nm,re.M))
all_syms={'ar_m766_native_%08x'%b['pc'] for b in s['accepted']}
missing=sorted(all_syms-linked)
assert not missing,missing[:20]
assert 'ar_m766_register_frontier' in linked
gated=[b['pc'] for b in s['accepted'] if b['import_veneer_requires_binding']]
assert len(gated)==7
Path('m766-final-attestation.json').write_text(json.dumps({
 'schema':'ascension-m766-final-macho-1','canonical_elf_sha256':s['source_sha256'],
 'offline_CFG_candidates':s['total_examined'],'full_blocks_compiled_and_linked':len(all_syms),
 'rejected_blocks':len(s['rejected']),'direct_edges':len(s['edges']),
 'import_veneer_symbols_not_registered':list(map(lambda x:'0x%08X'%x,gated)),
 'source_AOT_entrypoint':'0x005394E8',
 'physical_device_executed':'NOT_MEASURED',
 'guest_fs_read_bytes':'NOT_MEASURED'
},indent=2)+'\n')
print('M7.66 254 native ARM64 CFG entrypoints verified in FINAL Mach-O; iPhone NOT MEASURED')
PY
# M7.67 executable ARM64 provenance + exact PRX/HLE evidence; no guest gameplay claim.
python3 - <<'PY'
import json,re
from pathlib import Path
nm=Path('m78-owner-aot-linked-symbols.txt').read_text()
assert re.search(r' [Tt] _ar_m766_native_005394e8$',nm,re.M)
assert re.search(r' [Tt] _ar_private_import_match$',nm,re.M)
assert re.search(r' [Tt] _ar_private_import_find_nid$',nm,re.M)
assert re.search(r' [Tt] _ar_sys_lwmutex_create$',nm,re.M)
assert re.search(r' [Tt] _ar_m767_last_import_evidence$',nm,re.M)
a=json.loads(Path('runtime/m767-prx-offline-audit.json').read_text())
assert a['library']=='sysPrxForUser' and a['nid']=='0x2f85c0ef'
assert a['stub']=='0x00669A84' and a['imports_total']==350
x={'schema':'ascension-m767-ipa-provenance-1','owner_sha256':a['sha256'],
 'elf_prx_matching_stub':a['stub'],'module':a['library'],'nid':a['nid'],
 'earlier_native_CFG_symbols_preserved':254,
 'real_import_lookup_and_lwmutex_HLE_linked':True,
 'last_guest_slot_live_value':'NOT_MEASURED',
 'actual_game_HLE_call_and_result':'NOT_MEASURED',
 'guest_file_read_positive':'NOT_MEASURED',
 'gameplay':'NOT_MEASURED'}
Path('m767-final-attestation.json').write_text(json.dumps(x,indent=2)+'\n')
print('M7.67 verified native import lookup and genuine sys_lwmutex_create symbol in final Mach-O')
PY
# M7.68 final Mach-O proof and accounting, no entire game native claim.
python3 - <<'PY'
import json
from pathlib import Path
db=json.loads(Path('runtime/m768-bulk-preflight-metrics.json').read_text())
assert db['opd_descriptors']==7643 and db['recovered_candidate_intervals']==16841
assert db['cpp_generated_table_entries']==29849 and db['imports_total']==350
assert db['ios_complete_lift_linked']=='NO' and not db['game_assets_in_repo']
nm=Path('m78-owner-aot-linked-symbols.txt').read_text().splitlines()
symbols=['ar_run','ar_guest_call','ar_m767_last_import_evidence','ar_m766_native_005394e8','ar_sys_lwmutex_create']
for sym in symbols:
 assert any((' T _'+sym) in line or (' t _'+sym) in line for line in nm),sym
proof={'schema':'ascension-m768-native-HLE-continuation-1',
 'owner_sha256':db['verified_offline_private_elf_sha256'],
 'symbol_definitions_verified':symbols,
 'local_full_elf_audit':'PASSED','whole_game_lift_arm64_linked':False,
 'spu_recompiled_game_arm64_linked':False,
 'iphone_hle_return_to_guest_lr':'NOT_MEASURED',
 'guest_fs_positive_read':'NOT_MEASURED','guest_rsx_game_frame':'NOT_MEASURED'}
Path('m768-final-attestation.json').write_text(json.dumps(proof,indent=2)+'\n')
print('M7.68 real ARM64 runtime/HLE symbols linked; guest execution NOT MEASURED')
PY
# M7.69 verify EVERY one of 5437 native symbols in FINAL Apple ARM64 Mach-O.
python3 - <<'PY'
import json,re
from pathlib import Path
a=json.loads(Path('m769-snapshot-ci.json').read_text())
nm=Path('m78-owner-aot-linked-symbols.txt').read_text()
defined=set(re.findall(r' [Tt] _([A-Za-z0-9_]+)\s*$',nm,re.M))
symbols={'ar_m769_native_%08x'%b['pc'] for b in a['accepted']}
missing=sorted(symbols-defined)
assert len(symbols)==5437 and not missing,missing[:10]
assert 'ar_m769_register_frontier' in defined
assert 'ar_m769_get_stats' in defined
gate=[b['pc'] for b in a['accepted'] if b['import_veneer_requires_binding']]
assert len(gate)==7
proof={'schema':'ascension-m769-owner-elf-arm64-1',
 'title_id':'NPUA80918','owner_sha256':a['source_sha256'],
 'opd_authoritative_count':a['opd_descriptors'],
 'recovered_intervals_not_authoritative':a['recovered_interval_candidates_not_authoritative'],
 'source_PRX_imports':a['source_prx_imports'],
 'CFG_decoded_candidates':a['total_examined'],
 'PPC_complete_native_blocks_generated_and_linked':len(symbols),
 'PPC_instructions_in_these_blocks':sum(b['count'] for b in a['accepted']),
 'reject_count_true_decoder_limits':len(a['rejected']),
 'queued_not_examined':a['queued_deferred_not_examined'],
 'CFG_edges':len(a['edges']),
 'PRX_HLE_veneer_native_symbols_NOT_REGISTERED':list(map(lambda v:'0x%08X'%v,gate)),
 'host_semantic_test':'SEE_m769-host-frontier.log',
 'iphone_new_blocks_registered':'NOT_MEASURED',
 'iphone_distinct_executed':'NOT_MEASURED',
 'guest_cellFsOpen':'NOT_MEASURED','guest_cellFsRead_positive':'NOT_MEASURED',
 'full_game_native_recompilation':False,'gameplay':'NOT_MEASURED'}
Path('m769-final-attestation.json').write_text(json.dumps(proof,indent=2)+'\n')
print('M7.69: 5437 original Ascension PPC complete blocks linked in final iOS ARM64 Mach-O; guest execution not measured')
PY
# M7.33 final Mach-O must retain ACTUAL production LV2 service binder.
grep -Eq ' [Tt] _ar_lv2_bind_bootstrap_syscalls$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_lv2_timezone$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m751_register_vsubfp$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m752_register_vsldoi$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m753_register_vectorfp$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m754_register_fcmp_branch$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m756_register_divloop$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m757_register_owner$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m758_register_owner$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m759_register_owner$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m759_native_002c1378$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m761_native_003e16e0$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m761_register_owner$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m758_native_003c5110$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m757_native_003c5050$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m757_native_003c50c8$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m756_aot_003c4fc4$' m78-owner-aot-linked-symbols.txt
grep -Eq ' [Tt] _ar_m756_capture_stop$' m78-owner-aot-linked-symbols.txt
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
echo 'M7.56: PT_LOAD X offset vs RAM guest measured after AOT and before shutdown; signed 7 original PPC words through BEQ at 0x003C4FDC (two outcomes). Interpreter stays absent; guest FS milestones pending.' >> m78-aot-status.txt
echo 'M7.57: 16 authentic PPC64 instructions in two signed native AppleARM64 AOT spans, 0x003C5050 and 0x003C50C8; no interpreter or guest-FS claim without physical device.' >> m78-aot-status.txt
echo 'M7.58: original ELF executable owner words [0x003C5110,0x003C5180) 28 instructions generated with strict reusable PPC CFG lifter, AOT-only; no guest FS event proven.' >> m78-aot-status.txt
echo 'M7.59: 42 real owner PPC words 0x002C1378..0x002C141C compiled ARM64 with nested BL to 0x0052B840, BC targets 0x002C14A4 and 0x002C1420; guest cellFsOpen/read not yet physically observed.' >> m78-aot-status.txt
(cd ios-probe && zip -q -r ../AscensionRecompProbe-0.6.22-unsigned.ipa Payload)
test -s AscensionRecompProbe-0.6.22-unsigned.ipa
shasum -a 256 AscensionRecompProbe-0.6.22-unsigned.ipa > m41-ipa-sha256.txt
# Retain legacy CI path; new alias has accurate installed bundle version.
cp AscensionRecompProbe-0.6.22-unsigned.ipa AscensionRecompProbe-7.69.0-unsigned.ipa
shasum -a 256 AscensionRecompProbe-7.69.0-unsigned.ipa > m769-ipa-sha256.txt
echo 'UNSIGNED DIAGNOSTIC APP: UIKit CAMetalLayer + real PS3Recomp Metal backend; NO GOWA GAME included' > m41-status.txt
