#!/usr/bin/env python3
"""Apply the eight source files + integration modifications to an EXACT M7.69 git checkout.
Called once at the beginning of the GitHub Actions job for the committed M7.70 sources.
Do not run against main. Unrelated branches/workflows untouched.
"""
from __future__ import annotations
import argparse,hashlib,json,subprocess,sys
from pathlib import Path

BASE='7fab29774f6c44ed2971a7d24eb68f65f487b46a'
BASENAME='AscensionRecomp'
HERE=Path(__file__).resolve().parents[1]
META={'generated_candidates': 3835, 'elf_sha256': '4bf75c897b82d1beb25514cbadaff3d03e1b0c7bf849fa5d289be4f9183462b5', 'frontier_symbol': 'ar_m770_delta_ppu_0052a740', 'protected_PRX_veneers': 7, 'name': 'M7.70 delta offline prepared, NOT installed on iPhone', 'files': {'ppu_m770_delta_00.c': {'sha256': 'f85437b34e63af23c96bacee2eeeb30d8ef8581e6aeb839ded52f17eb7ba6451', 'bytes': 3560551}, 'ppu_m770_delta_01.c': {'sha256': '493e9feb5c7d3b969274de20c5e6cb85a2de67756210acaf67a6975f3beaaf3b', 'bytes': 3585578}, 'ppu_m770_delta_02.c': {'sha256': '65f9e289434802f1fc3205995fc55669b219bba381e10e524a77c92998fd972c', 'bytes': 3332438}, 'ppu_m770_delta_03.c': {'sha256': '4b7108ab9d2fafffa12a385468a5d7267001357235e5f73f7e9b79efffc421f6', 'bytes': 3376324}, 'ppu_m770_delta_04.c': {'sha256': '1dacf3bddcf0a8907fe804de8068720365d569cf3e54cf4b8aed63489847ac03', 'bytes': 3560298}, 'ppu_m770_delta_05.c': {'sha256': 'd260cdff98310112cf75639d875c5f62321d788327d84179d9ba9f97c834b356', 'bytes': 3742811}, 'ppu_m770_delta_06.c': {'sha256': '714017d20de6be364b00ffbf8a22694c7208502967ea27e13bf28ca5f63ede14', 'bytes': 1638850}, 'ppu_m770_delta_install.c': {'sha256': '07f1f31d60e328414f40e9698ee57a38e7371000a2b8dfdab65b250a85fa9cbe', 'bytes': 591337}}, 'integration_py_sha256': '8284967300536a84efa98e3bfc1e388c9408e1b498edf7426b9d794c31df0b6b', 'host_semantic_result': 'PASS with minimal compatible ppu_context header (not upstream)', 'apple_arm64_object_local_count': 8, 'apple_arm64_objects_compiled_without_iphoneos_sdk': True, 'real_github_commit': None, 'real_iphone_test': None}

def replacement(data,old,new,path):
    n=data.count(old)
    if n!=1:raise ValueError(f'{path}: incompatible M7.69 anchor {old[:70]!r}; matches {n}')
    return data.replace(old,new,1)

def main(repo: Path):
    if not (repo/'.git').exists():raise ValueError('Requires a real git checkout')
    def git(*a):return subprocess.check_output(['git','-C',str(repo),*a],text=True).strip()
    if git('branch','--show-current')!=BASENAME:raise ValueError('Branch mismatch: refuse changing other branch')
    # HEAD comes from the committed M7.70 workflow; baseline changes are checked by anchored replacements.
    # CI already generates untracked logs, build outputs and pinned upstream checkout.
    # Do not mistake those outputs for user modifications. Strict source SHA256 and
    # one-to-one replacement anchors below enforce the integration contract.
    for name,item in META['files'].items():
        source=HERE/'runtime/m770-delta'/name
        if hashlib.sha256(source.read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError('Source changed: '+name)
    alterations={}
    def load(p):return (repo/p).read_text()
    p='runtime/ppu_bridge.h';s=load(p)
    s=replacement(s,'int ar_register(uint32_t, ar_ppu_fn);',
       'int ar_register(uint32_t, ar_ppu_fn);\n/* M7.70: exact effective AOT handler; read-only. */\nar_ppu_fn ar_registered_handler(uint32_t pc);',p)
    alterations[p]=s
    p='runtime/ppu_bridge.c';s=load(p)
    s=replacement(s,'void ar_ppc_note_failed_call(uint32_t site,uint32_t target){',
       '/* M7.70: query the pointer really installed for this PC. */\nar_ppu_fn ar_registered_handler(uint32_t pc){return lookup(pc,NULL);}\nvoid ar_ppc_note_failed_call(uint32_t site,uint32_t target){',p)
    alterations[p]=s
    p='ios/ARLivePPUBridge.c';s=load(p)
    s=replacement(s,'extern int ar_m769_register_frontier(const uint8_t*,size_t);',
       'extern int ar_m769_register_frontier(const uint8_t*,size_t);\n#ifdef ASCENSION_M770_DELTA_LINKED\nextern int ar_m770_delta_install_sha256(const unsigned char*,size_t);\nextern void ar_m770_delta_get_stats(uint32_t out[7]);\n#endif',p)
    s=replacement(s,'static uint32_t m769_verified_stats[5];',
       'static uint32_t m769_verified_stats[5];\nstatic uint32_t m770_verified_stats[7];\nvoid ar_m770_last_install_stats(uint32_t out[7]) {if(out)memcpy(out,m770_verified_stats,sizeof(m770_verified_stats));}',p)
    s=replacement(s,'memset(m769_verified_stats,0,sizeof(m769_verified_stats));',
       'memset(m769_verified_stats,0,sizeof(m769_verified_stats));\n memset(m770_verified_stats,0,sizeof(m770_verified_stats));',p)
    s=replacement(s,'  ar_m769_get_stats(m769_verified_stats);',
       '''  ar_m769_get_stats(m769_verified_stats);
#ifdef ASCENSION_M770_DELTA_LINKED
  /* M7.70: AFTER authenticated PT_LOAD mapping and M7.69 AOT;
   * BEFORE the very first guest dispatch. No PPC interpreter/fallback.
   * The installer verifies the physical PC's ACTUAL function pointer.
   */
  /* The 28 authenticated PPC bytes used by M7.69's real iPhone stop.
   * Refuse installation if guest RAM has diverged from the owner ELF.
   * This is a frontier check, NOT a claim that all 3835 ranges were checked.
   */
  static const uint8_t m770_frontier_ppc28[28]={
    0x81,0x42,0xa6,0x48,0x7c,0x08,0x02,0xa6,
    0xf8,0x21,0xff,0x91,0xf8,0x01,0x00,0x80,
    0x54,0x6b,0x28,0x34,0x54,0x60,0x18,0x38,
    0x81,0x2a,0x00,0x00
  };
  uint8_t m770_guest_ppc28[28];
  if(ar_vm_read_bytes(0x0052a740u,m770_guest_ppc28,28u)!=AR_OK ||
     memcmp(m770_guest_ppc28,m770_frontier_ppc28,28u)) {
     ar_bridge_shutdown();return -74;
  }
  const int rc770=ar_m770_delta_install_sha256(digest,sizeof(digest));
  ar_m770_delta_get_stats(m770_verified_stats);
  if(rc770!=AR_OK){ar_bridge_shutdown();return -73;}
#endif''',p)
    alterations[p]=s
    p='ios/ARProbeApp.m';s=load(p)
    s=replacement(s,'extern void ar_m769_last_install_stats(uint32_t out[5]);',
       'extern void ar_m769_last_install_stats(uint32_t out[5]);\nextern void ar_m770_last_install_stats(uint32_t out[7]);\nextern ar_ppu_fn ar_m770_delta_prior_frontier_handler(void);',p)
    s=replacement(s,'    ar_m769_last_install_stats(m769Stats);',
       '    ar_m769_last_install_stats(m769Stats);\n    uint32_t m770Stats[7]={0};\n    ar_m770_last_install_stats(m770Stats);',p)
    marker='    NSMutableArray *firstVisits=[NSMutableArray arrayWithCapacity:measured.first_count];'
    s=replacement(s,marker,'''    BOOL m770FrontierExecuted=NO;
    for(uint32_t m770i=0;m770i<measured.first_count;++m770i)
      if(measured.first_pcs[m770i]==0x0052A740u)m770FrontierExecuted=YES;
    /* Never use an interpreter fallback opcode as true PPC evidence. */
    uint32_t m770RealStopOpcode=(missingRead==0 && native[7]) ?
        missingWords[0] : (ownerStop.guest_status==AR_OK ?
        ownerStop.guest_word : (ownerStop.elf_status==AR_OK ?
        ownerStop.elf_word : 0u));
    BOOL m770OpcodeValid=(missingRead==0 && native[7]) ||
        ownerStop.guest_status==AR_OK || ownerStop.elf_status==AR_OK;
    [graphReport appendFormat:
       @"M7.70 BULK DELTA: candidatos_examinados=%u novos_reais=%u "
        "duplicados_mesmo_handler=%u conflitos_handler=%u rejeitados=%u "
        "falhas=%u frontier_handler_0x0052A740_confirmado=%u "
        "frontier_EXECUTADO=%@ handler_preexistente=%p "
        "ultimo_aot=0x%08X proximo_pc=0x%08X "
        "opcode_PPC_real=0x%08X opcode_validado=%@ "
        "dispatches=%u distintas=%u PPC_interpretadas=%u "
        "cellFsOpen=%u cellFsRead=%u bytes_guest=%llu\\n",
       m770Stats[0],m770Stats[1],m770Stats[2],m770Stats[3],
       m770Stats[4],m770Stats[5],m770Stats[6],
       m770FrontierExecuted?@"SIM":@"NÃO",
       (void *)ar_m770_delta_prior_frontier_handler(),
       measured.stop_previous_aot,measured.unresolved_pc,
       m770RealStopOpcode,m770OpcodeValid?@"SIM":@"NÃO",
       measured.aot_dispatches,measured.unique_aot,measured.fallback_steps,
       fsMeasured.open_calls,fsMeasured.read_calls,
       (unsigned long long)fsMeasured.bytes_read];
''' +marker,p)
    s=replacement(s,'      @"m769_offline_full_blocks":@5437,',
       '''      @"m770_examined_runtime":@(m770Stats[0]),
      @"m770_new_runtime":@(m770Stats[1]),
      @"m770_same_handler_duplicates":@(m770Stats[2]),
      @"m770_conflicting_handlers":@(m770Stats[3]),
      @"m770_rejected":@(m770Stats[4]),
      @"m770_failures":@(m770Stats[5]),
      @"m770_frontier_exact_handler":@(m770Stats[6]),
      @"m770_frontier_actually_executed":@(m770FrontierExecuted),
      @"m770_last_guest_stop_opcode":@(m770RealStopOpcode),
      @"m770_guest_fs_open_calls":@(fsMeasured.open_calls),
      @"m770_guest_fs_read_calls":@(fsMeasured.read_calls),
      @"m770_guest_fs_read_bytes":@(fsMeasured.bytes_read),
      @"m769_offline_full_blocks":@5437,''',p)
    alterations[p]=s
    p='ios/Probe-Info.plist';s=load(p)
    s=replacement(s,'<key>CFBundleShortVersionString</key><string>7.69.0</string>',
       '<key>CFBundleShortVersionString</key><string>7.70.0</string>',p)
    s=replacement(s,'<key>CFBundleVersion</key><string>7690</string>',
       '<key>CFBundleVersion</key><string>7700</string>',p)
    alterations[p]=s
    p='tools/build_ios_probe_ipa.sh';s=load(p)
    marker='# M7.56: capture live guest memory vs PT_LOAD file bytes, not fallback counters.'
    s=replacement(s,marker,'''# M7.70: SINGLE BATCH of seven owner-ELF-derived PPC->native C units and installer.
# Compiled WITH Apple iphoneos SDK; never substitute host GCC for Mach-O proof.
M770_OBJECTS=()
for src in runtime/m770-delta/ppu_m770_delta_0[0-6].c runtime/m770-delta/ppu_m770_delta_install.c; do
  test -s "$src"
  dst="ios-probe/$(basename "${src%.c}").o"
  xcrun --sdk iphoneos clang -target arm64-apple-ios17.0 -isysroot "$SDK" \\
    -std=c11 -O0 -Wall -Wextra -Werror -Wno-unused-label -Wno-unused-function -Wno-parentheses-equality \\
    -I upstream/runtime/ppu -I runtime -c "$src" -o "$dst"
  file "$dst" | tee -a m770-apple-arm64-objects.log
  M770_OBJECTS+=("$dst")
done
xcrun nm -g "${M770_OBJECTS[@]}" > m770-objects-nm.txt
grep -Eq ' [Tt] _ar_m770_delta_ppu_0052a740$' m770-objects-nm.txt
grep -Eq ' [Tt] _ar_m770_delta_install_sha256$' m770-objects-nm.txt
AOT_COMPILE_DEFINES+=(-DASCENSION_M770_DELTA_LINKED)
''' +marker,p)
    s=replacement(s,'    ${M769_OBJECTS[@]+"${M769_OBJECTS[@]}"} \\\n',
       '    ${M769_OBJECTS[@]+"${M769_OBJECTS[@]}"} \\\n    ${M770_OBJECTS[@]+"${M770_OBJECTS[@]}"} \\\n',p)
    mark='# M7.33 final Mach-O must retain ACTUAL production LV2 service binder.'
    s=replacement(s,mark,'''# M7.70: verify all 3835 actual AOT symbols and installer in FINAL Mach-O.
python3 - <<'PYM770'
import json,re
from pathlib import Path
m=json.loads(Path('runtime/m770-delta/aot-manifest.json').read_text())
assert m['generated_functions']==3835
assert m['source_sha256']=='4bf75c897b82d1beb25514cbadaff3d03e1b0c7bf849fa5d289be4f9183462b5'
expected={'ar_m770_delta_ppu_%08x'%int(x['start'],0) for x in m['accepted']}
expected.add('ar_m770_delta_install_sha256')
text=Path('m78-owner-aot-linked-symbols.txt').read_text()
found=set(re.findall(r' [Tt] _([a-zA-Z_][a-zA-Z0-9_]*)\\s*$',text,re.M))
missing=sorted(expected-found)
assert len(expected)==3836 and not missing,missing[:20]
assert 'ar_m770_delta_ppu_0052a740' in found
Path('m770-final-attestation.json').write_text(json.dumps({
  'schema':'ascension-m770-apple-arm64-link-proof-v1',
  'baseline_sha':'7fab29774f6c44ed2971a7d24eb68f65f487b46a',
  'ELF_sha256':m['source_sha256'], 'native_delta_C_entrypoints_linked':3835,
  'objects_iphoneos_arm64':8,'actual_registers_iphone':'NOT_MEASURED',
  'frontier_handler_iphone':'NOT_MEASURED','PC_after_frontier':'NOT_MEASURED',
  'cellFsOpen':'NOT_MEASURED','cellFsRead':'NOT_MEASURED',
  'gameplay':'NOT_MEASURED'},indent=2)+'\\n')
print('M7.70 Apple ARM64 Mach-O 3835 delta native handlers linked; runtime NOT_MEASURED')
PYM770
''' +mark,p)
    # Keep earlier v7.69 gates but update the IPA being produced, verified and uploaded.
    s=s.replace('AscensionRecompProbe-7.69.0-unsigned.ipa','AscensionRecompProbe-7.70.0-unsigned.ipa')
    s=s.replace('m769-ipa-sha256.txt','m770-ipa-sha256.txt')
    alterations[p]=s
    for path,d in alterations.items():
        (repo/path).write_text(d)
    for src in sorted((HERE/'runtime/m770-delta').iterdir()):
        to=repo/'runtime/m770-delta'/src.name
        to.parent.mkdir(parents=True,exist_ok=True)
        if to.exists():
            if to.read_bytes()!=src.read_bytes():raise ValueError('M770 source mismatch: '+str(to))
            continue
        to.write_bytes(src.read_bytes())
    src=HERE/'tests/frontier_0052a740_host_test.c'
    dst=repo/'tests/frontier_0052a740_host_test.c'
    if dst.exists():
        if dst.read_bytes()!=src.read_bytes():raise ValueError('Host test changed')
    else:dst.write_bytes(src.read_bytes())
    print('M7.70 integrated in checkout, ONLY branch AscensionRecomp:',len(alterations),'modified files + 8 C + manifest + test')
    print('Now review git diff and build in one commit. Never treat a CI success as iPhone physical evidence.')

if __name__=='__main__':
    pa=argparse.ArgumentParser();pa.add_argument('repo',type=Path)
    a=pa.parse_args()
    try:main(a.repo.resolve())
    except Exception as e:print('M770 INTEGRATION STOPPED:',e,file=sys.stderr);sys.exit(1)