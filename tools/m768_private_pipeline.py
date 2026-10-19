#!/usr/bin/env python3
"""M7.68: audited bring-your-own-GOWA offline lift/build orchestrator.

No game bytes/code are copied into GitHub, CI or the IPA. Run on the owner's
macOS machine with Xcode and a checkout of the pinned upstream ps3recomp.

`audit` is safe and deterministic on Linux; `lift`/`compile` operate only on
private working paths. Refuses to claim that TODO/no-op functions are complete.
"""
import argparse, hashlib, json, os, pathlib, platform, re, shlex, subprocess, sys, time, zipfile

OWNER_SHA = '4bf75c897b82d1beb25514cbadaff3d03e1b0c7bf849fa5d289be4f9183462b5'
ENGINE_SHA = '39a36296511c445707adabcd312f0b740cfbd694'
TABLE_SHA = '310e7f838243a07c76e7198aa13a3d5170fb8e648d1208908685ce0d75010cb9'
PREFIX = 'GOWA_M7.67_BULK_AUDIT/'

def sha(path):
    d=hashlib.sha256()
    with path.open('rb') as fp:
        for b in iter(lambda: fp.read(8 << 20), b''): d.update(b)
    return d.hexdigest()

def fail(msg):
    raise RuntimeError(msg)

def command(args, cwd, log):
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('w') as o:
        o.write('+ ' + shlex.join(str(x) for x in args) + '\n')
        o.flush()
        rc=subprocess.run([str(x) for x in args],cwd=cwd,stdout=o,stderr=subprocess.STDOUT,check=False).returncode
    if rc: fail(f'command failed exit={rc}; see {log}; argv: {shlex.join(str(x) for x in args)}')

def validate(args):
    elf, bundle = pathlib.Path(args.elf).resolve(),pathlib.Path(args.bundle).resolve()
    if not elf.is_file() or not bundle.is_file(): fail('owner ELF and inventory ZIP required')
    if elf.stat().st_size != 8_717_136 or sha(elf) != OWNER_SHA: fail('GOWA.ELF size or SHA256 mismatch; abort')
    with zipfile.ZipFile(bundle) as z:
        def read(n): return z.read(PREFIX+n)
        opd=json.loads(read('analysis/GOWA_FUNCTIONS_OPD.json'))
        recovered=json.loads(read('analysis/GOWA_FUNCTIONS_RECOVERED.json'))
        imports=json.loads(read('analysis/GOWA_IMPORTS.json'))
        a=json.loads(read('analysis/gowa_inventory_summary.json'))
        rec=json.loads(read('analysis/gowa_runtime_reconciliation.json'))
        spu=json.loads(read('analysis/gowa_spu_summary.json'))
        table=read('source_context/ppu_recomp_table.cpp')
        assert len(opd)==7643 and len(recovered)==16841 and len(imports)==350
        assert a['sha256']==rec['elf_sha256']==OWNER_SHA
        assert a['upstream_ps3recomp_commit']==ENGINE_SHA
        assert hashlib.sha256(table).hexdigest()==TABLE_SHA
        exact=[v for v in imports if int(v['stub'],16)==0x669a84]
        assert len(exact)==1 and exact[0]['library']=='sysPrxForUser' and int(exact[0]['nid'],16)==0x2f85c0ef
        assert rec['runtime_stop_pc']=='0x00669A84' and rec['aot_first_count']==143
        assert spu['embedded_spu_images']==4
        # Explicit source limitations: no staged ELF bytecode is counted as a usable native function.
        out={'schema':'ascension-m768-private-lift-preflight-1','status':'INPUTS_VERIFIED',
             'owner_elf_sha256':OWNER_SHA,'owner_elf_bytes':elf.stat().st_size,
             'audit_zip_sha256':sha(bundle),'upstream_ps3recomp_expected_commit':ENGINE_SHA,
             'opd_descriptors':len(opd),'recovered_intervals_CANDIDATE':len(recovered),
             'imports':len(imports),'named_nids':314,'unresolved_nid_names':36,
             'offline_cpp_table_entries':29849,'offline_cpp_table_sha256':TABLE_SHA,
             'offline_cpp_generated_source_complete':False,
             'spu_elf_embedded':4,'spu_range_candidates':spu['detected_function_ranges'],
             'decoded_nonplaceholder_words':1942057,'known_opcodes_without_semantics':15797,
             'explicit_spr_noops':33,'undecoded_word_candidates_not_proven_code':148861,
             'physical_m767_distinct_aot':143,'physical_m767_native_dispatches':1901,
             'physical_m767_stop_pc':'0x00669A84','guest_fs_positive_bytes':0,
             'ios_ppu_generated':0,'ios_ppu_compiled':0,'ios_ppu_linked':0,
             'ios_ppu_registered':0,'ios_ppu_device_executed':'NOT_MEASURED',
             'spu_arm64_compiled':0,'first_guest_frame':'NOT_MEASURED'}
        root=pathlib.Path(args.workdir).resolve();root.mkdir(parents=True,exist_ok=True)
        (root/'input_audit.json').write_text(json.dumps(out,indent=2)+'\n')
        if args.stage in ('lift','compile'):
            analysis=root/'analysis'/'gowa';analysis.mkdir(parents=True,exist_ok=True)
            for n in ('GOWA_FUNCTIONS_RECOVERED.json','GOWA_FUNCTIONS_OPD.json','GOWA_IMPORTS.json'):
                (analysis/n).write_bytes(read('analysis/'+n))
            # Avoid committing these raw derived outputs. All generated code stays outside repo.
        return out

def full_lift(args, result):
    upstream=pathlib.Path(args.upstream).resolve();elf=pathlib.Path(args.elf).resolve()
    work=pathlib.Path(args.workdir).resolve()
    if not (upstream/'tools'/'ppu_loader.py').is_file(): fail('ps3recomp repo checkout missing: tools/ppu_loader.py')
    commit=subprocess.check_output(['git','-C',str(upstream),'rev-parse','HEAD'],text=True).strip()
    if commit!=ENGINE_SHA: fail(f'upstream ps3recomp commit mismatch: {commit} expected {ENGINE_SHA}')
    loaded=work/'analysis'/'gowa';loaded.mkdir(parents=True,exist_ok=True)
    logs=work/'logs';logs.mkdir(exist_ok=True)
    command([sys.executable,upstream/'tools'/'ppu_loader.py',elf,'--output',loaded], upstream, logs/'01_ppu_loader.log')
    # Loader may generate other names; original independently validated maps take precedence.
    recovered=loaded/'GOWA_FUNCTIONS_RECOVERED.json'
    imports=loaded/'GOWA_IMPORTS.json'
    if not recovered.exists() or not imports.exists(): fail('missing source inventory manifests; run audit first')
    base=work/'build'/'ppu';base.mkdir(parents=True,exist_ok=True)
    command([sys.executable,upstream/'tools'/'ppu_lifter.py',elf,'--functions',recovered,
             '--hle-stubs',imports,'--output',base,'--chunks','650','--jobs',str(args.jobs)],upstream,logs/'02_ppu_lift.log')
    # Never declare native coverage based only on emitted function/table entries.
    chunks=sorted(base.rglob('*.cpp'))
    if not chunks: fail('ppu_lifter emitted no .cpp chunks; check 02_ppu_lift.log')
    result['ppu_generated_chunks']=len(chunks)
    result['ios_ppu_generated']=len(chunks)
    spu_extract=work/'build'/'spu_elf';spu_extract.mkdir(parents=True,exist_ok=True)
    command([sys.executable,upstream/'tools'/'extract_spu_images.py',elf,'--output',spu_extract],upstream,logs/'03_spu_extract.log')
    spu_elfs=sorted(spu_extract.glob('*.elf'))
    if not spu_elfs: fail('no SPU ELF emitted: see 03_spu_extract.log')
    for i,p in enumerate(spu_elfs):
        dest=work/'build'/'spu'/p.stem
        dest.mkdir(parents=True,exist_ok=True)
        command([sys.executable,upstream/'tools'/'spu_lifter.py','--auto-functions',p,
                 '--output',dest,'--report',work/'analysis'/f'spu_{p.stem}.json',
                 '--symbol-prefix',f'gowa_{p.stem}_'],upstream,logs/f'04_spu_{i:03d}.log')
    result['spu_elf_extracted']=len(spu_elfs)
    result['spu_lifted_source_units']=len(list((work/'build'/'spu').rglob('*.cpp')))
    command([sys.executable,upstream/'tools'/'gen_hle_nids.py','--all',
             '--out',work/'build'/'ppu_hle_nids.cpp'],upstream,logs/'05_hle_nids.log')
    for pattern in ('ppu_recomp_register(', 'ppu_hle_register_all('):
        paths=list(base.rglob('*.cpp'))+[work/'build'/'ppu_hle_nids.cpp']
        if not any(pattern in p.read_text(errors='replace') for p in paths):
            fail(f'no working generated registration function declaration/body: {pattern}; do not link fake table')
    return chunks

def compile_native(args, result, chunks):
    if platform.system()!='Darwin': fail('iOS ARM64 compile requires macOS Xcode; no Linux substitute')
    work=pathlib.Path(args.workdir).resolve();logs=work/'logs';obj=work/'build'/'arm64-objects';obj.mkdir(parents=True,exist_ok=True)
    sdk=subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],text=True).strip()
    upstream=pathlib.Path(args.upstream).resolve()
    for i,p in enumerate(chunks):
        dest=obj/(f'ppu_{i:04}.o')
        command(['xcrun','--sdk','iphoneos','clang++','-std=c++20','-O2','-c',p,
                 '-target','arm64-apple-ios17.0','-isysroot',sdk,
                 '-I',p.parent,'-I',upstream/'runtime','-I',upstream/'include','-o',dest],
                 upstream,logs/f'06_ppu_{i:04}.log')
    result['ios_ppu_compiled']=len(list(obj.glob('ppu_*.o')))
    # Objects are still NOT linked to IPA/registered/executed. Integration
    # into app's verified link graph remains an independent explicit gate.
    fail('Native object compilation is not app linkage. Supply all produced objects to private iOS target link and audit defined/live symbols; cannot ship incomplete HLE/RSX game.')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--elf',required=True);p.add_argument('--bundle',required=True)
    p.add_argument('--upstream',default='upstream/ps3recomp')
    p.add_argument('--workdir',required=True);p.add_argument('--stage',choices=['audit','lift','compile'],default='audit')
    p.add_argument('--jobs',type=int,default=4)
    args=p.parse_args();root=pathlib.Path(args.workdir).resolve()
    try:
        result=validate(args)
        if args.stage!='audit':
            chunks=full_lift(args,result)
            if args.stage=='compile': compile_native(args,result,chunks)
        result['status']='SUCCESS' if args.stage=='audit' else 'LIFT_GENERATED_NOT_LINKED'
        print(json.dumps(result,indent=2))
    except Exception as e:
        root.mkdir(parents=True,exist_ok=True)
        (root/'first_blocker.json').write_text(json.dumps({'stage':args.stage,'status':'FAILED','reason':str(e),'time_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())},indent=2)+'\n')
        print(f'BLOCKED {e}',file=sys.stderr);raise SystemExit(2)
    finally:
        if 'result' in locals():
            root.mkdir(parents=True,exist_ok=True)
            (root/'status.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
