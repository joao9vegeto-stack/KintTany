#!/usr/bin/env python3
"""One-off real runtime transaction audit, NO fabricated KTGL resources.

This is a diagnostic port, not a claim of gameplay repair. It preserves
the coherent 5GiB/2GiB allocator and the original G1T/G1S readers.
Logs actual 0x38f972af.fdata ReadFile requests to identify whether RDB data
is delivered to the failing G1T parser. Includes exact emulation of native
G1T validator B.EQ on the real iPhone with its actual guest object.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import repack_ktgl_coherent_config as coherent

base=coherent.base
SOURCE_G1T=0x612120
SOURCE_OPCODE=bytes.fromhex("a0050054")  # original B.EQ main+0x6121d4
BREAK=bytes.fromhex("40403ed4")
G1T_FDATA_IMG_ENTRY=12943
G1T_FDATA_RECORD_OFFSET=3137776
G1T_FDATA_DATA_OFFSET=3137864
G1T_FDATA_COMPRESSED_BYTES=49

ORIG_PATCH=coherent.patch_main
ORIG_VERIFY=coherent.verify_main

def patch_guest(exe:Path,source_report:dict):
    record=ORIG_PATCH(exe,source_report)
    parts,raw=base.main_sections(exe)
    x0=parts["x0"]
    base.require(raw[SOURCE_G1T:SOURCE_G1T+4]==SOURCE_OPCODE,
                 "the actual v458752 G1T original B.EQ differs")
    with exe.open("r+b") as f:
        f.seek(x0["offset"]+SOURCE_G1T)
        base.require(f.read(4)==SOURCE_OPCODE,"G1T branch changed unexpectedly")
        f.seek(x0["offset"]+SOURCE_G1T)
        f.write(BREAK)
    p,a=base.main_sections(exe)
    check=bytearray(raw)
    check[SOURCE_G1T:SOURCE_G1T+4]=BREAK
    base.require(a==bytes(check),"unlisted guest code mutation")
    base.require(p["w"]["data"]==parts["w"]["data"] and
                 p["x1"]["data"]==parts["x1"]["data"],
                 "G1T diagnostic must not change game data or root trampolins")
    record["after_sha256"]=hashlib.sha256(a).hexdigest()
    record["x0_after_sha256"]=hashlib.sha256(p["x0"]["data"]).hexdigest()
    record["one_exact_emulated_original_branch"]={
      "site":"main+0x612120","original":SOURCE_OPCODE.hex(),
      "trap":BREAK.hex(),"if_Z":"main+0x6121d4",
      "otherwise":"main+0x612124","no_branch_result_override":True,
    }
    return record

def verify_guest(exe:Path,record:dict):
    ORIG_VERIFY(exe,record)
    _,raw=base.main_sections(exe)
    base.require(raw[SOURCE_G1T:SOURCE_G1T+4]==BREAK,
                 "G1T diagnostic branch is not protected by signal")
    base.require(record["one_exact_emulated_original_branch"]
                 ["no_branch_result_override"],"G1T parser semantics changed")

def patch_host(repo:Path):
    fs=repo/"engine/dm/host/hle_fs.c"
    code=fs.read_text()
    anchor="    size_t got = 0; int reprep = 0, fd = (int)h; int64_t base = 0;"
    exit_anchor="    *out = got;\n    if (g_fslog)"
    assert code.count(anchor)==1 and code.count(exit_anchor)==1
    assert "FAIRY2_FDATA_TRANSACTION" not in code
    prefix=(
      "    /* FAIRY2_FDATA_TRANSACTION: real 0x38f972af.fdata IMG_K 12943. */\n"
      "    static unsigned f2_actual_fdata_reads;\n"
      "    unsigned f2_key=IMG_H(h)?IMG_K(h):0;\n"
      "    int f2_watch=IMG_H(h) && (f2_key==12943 || f2_key==13660);\n"
      "    unsigned f2_seq=f2_watch ? __atomic_add_fetch(&f2_actual_fdata_reads,1,__ATOMIC_RELAXED):0;\n"
      "    int64_t f2_original_offset=off;\n"
      "    size_t f2_original_wanted=sz;\n"
    )
    suffix=(
      "    if (f2_watch && f2_seq<=256) {\n"
      "        uint64_t words[2]={0};\n"
      "        if (got) memcpy(words,buf,got<sizeof words?got:sizeof words);\n"
      "        uint64_t fnv=0xcbf29ce484222325ull;\n"
      "        if (got<=65536) for(size_t t=0;t<got;t++)\n"
      "            fnv=(fnv^((uint8_t *)buf)[t])*0x100000001b3ull;\n"
      "        LOG(\"FAIRY2_FDATA_TRANSACTION seq=%u entry=%u offset=%#llx want=%#zx clipped=%#zx got=%#zx source_head=%016llx,%016llx fnv64=%016llx dst=%p\",\n"
      "            f2_seq,f2_key,(unsigned long long)f2_original_offset,\n"
      "            f2_original_wanted,sz,got,\n"
      "            (unsigned long long)words[0],(unsigned long long)words[1],\n"
      "            (unsigned long long)fnv,buf);\n"
      "    }\n"
    )
    code=code.replace(anchor,prefix+anchor,1)
    code=code.replace(exit_anchor,"    *out = got;\n"+suffix+"    if (g_fslog)",1)
    fs.write_text(code)

    crash=repo/"engine/dm/host/crash.c"
    host=crash.read_text()
    addon=(Path(__file__).resolve().parent/"ktgl_transaction_trace_host.h").read_text()
    anchor="static void on_crash(int sig, siginfo_t *si, void *uc_) {\n    ucontext_t *uc = uc_;"
    base.require(host.count(anchor)==1 and "FAIRY2_KTGL_TRANSACTION_TRACE_ONLY" not in host,
                 "pinned native signal hook source changed")
    base.require("PSTATE.Z" in addon and "0x6121d4u:0x612124u" in addon,
                 "native trace must preserve exact ARM64 B.EQ outcome")
    host=host.replace(anchor,addon+"\n"+anchor+
        "\n    if (sig == SIGTRAP && f2_g1t_validator_branch(uc)) return;",1)
    crash.write_text(host)

def make(source:Path,source_report:Path,repo:Path,out:Path):
    repo=repo.resolve()
    base.require((repo/".upstream-ref").read_text().strip()==base.hook.ENGINE_PIN,
                 "pinned NXNative engine mismatch")
    patch_host(repo)
    coherent.patch_main=patch_guest
    coherent.verify_main=verify_guest
    try:
        report=coherent.make(source,source_report,repo,out)
    finally:
        coherent.patch_main=ORIG_PATCH
        coherent.verify_main=ORIG_VERIFY
    report.update({
       "purpose":"TRACE ONLY: original FDATA ReadFile + original G1T validator",
       "source_fdata_entry":G1T_FDATA_IMG_ENTRY,
       "source_fdata_record_offset":G1T_FDATA_RECORD_OFFSET,
       "source_fdata_payload_offset":G1T_FDATA_DATA_OFFSET,
       "source_fdata_compressed_size":G1T_FDATA_COMPRESSED_BYTES,
       "g1t_original_branch_emulated":"main+0x612120",
       "gameplay_verified":False,"repair_claimed":False,
       "no_shader_compile":True,"game_data_unchanged":True,
       "original_reader_unchanged":True,"file_read_behavior_unchanged":True,
       "original_G1T_branch_result_unchanged":True,
       "not_for_auto_transfer":True,
    })
    (out/"ktgl-transaction-trace-report.json").write_text(
       json.dumps(report,indent=2)+"\n")
    return report

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--source-ipa",required=True,type=Path)
    a.add_argument("--source-report",required=True,type=Path)
    a.add_argument("--repo",required=True,type=Path)
    a.add_argument("--output",required=True,type=Path)
    n=a.parse_args()
    make(n.source_ipa,n.source_report,n.repo,n.output)
