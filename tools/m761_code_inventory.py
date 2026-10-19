#!/usr/bin/env python3
"""M7.61 read-only code inventory, *only* verified executable PPC64 spans.

Do not classify all PT_LOAD X bytes as code. Do not assume a prologue gives a
known function boundary, and do not infer any call from string/data xrefs.
This command never builds/runs the title or reads host files as guest sys_fs.
"""
import argparse
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path
from generate_m761_owner_batch import ELF_SHA,authenticate,spans,emit

def sx(v,n):
    return v-(1<<n) if v & (1<<(n-1)) else v

def analyze(path):
    digest=authenticate(path)
    raw=Path(path).read_bytes()
    if raw[:7]!=b"\x7fELF\x02\x02\x01" or struct.unpack_from(">H",raw,18)[0]!=21:
        raise ValueError("Not PPC64 big-endian original ELF")
    e_entry=struct.unpack_from(">Q",raw,24)[0]
    offset=struct.unpack_from(">Q",raw,32)[0]
    stride,count=struct.unpack_from(">HH",raw,54)
    if stride<56 or offset+stride*count>len(raw):
        raise ValueError("Truncated ELF program headers")
    segments=[]
    for n in range(count):
        typ,fl,fo,va,_,filesz,memsz,align=struct.unpack_from(">IIQQQQQQ",raw,offset+n*stride)
        if typ==1:
            if fo+filesz>len(raw) or filesz>memsz:
                raise ValueError("Invalid file-backed segment")
            segments.append(dict(index=n,va=va,end=va+filesz,mem_end=va+memsz,
                                 offset=fo,filesz=filesz,memsz=memsz,flags=fl,align=align))
    executable=[s for s in segments if s["flags"]&1]
    if len(executable)!=1:
        raise ValueError("Unexpected executable segments")
    descriptor=next((s for s in segments if s["va"]<=e_entry and e_entry+8<=s["end"]),None)
    if descriptor is None: raise ValueError("No file-backed entry descriptor")
    entry_offset=descriptor["offset"]+e_entry-descriptor["va"]
    code,toc=struct.unpack_from(">II",raw,entry_offset)
    if code!=0x00010410 or toc!=0x0083f2b0:
        raise ValueError("Entry/TOC differs from validated native bootstrap")
    _,lifted=emit()
    accepted={int(x["pc"],16):x for x in lifted["accepted"]}
    edges=[];unknown=[];confirmed_pcs=set()
    for start,words in spans():
        if start not in accepted:
            unknown.append({"candidate":"0x%08X"%start,"state":"backend_rejected"})
            continue
        for index,word in enumerate(words):
            pc=start+4*index
            confirmed_pcs.add(pc)
            op=word>>26
            edge=None
            if op in (16,18):
                if op==18:
                    displacement=sx(word&0x03fffffc,26)
                    target=(displacement if word&2 else pc+displacement)&0xffffffff
                    edge_type="direct_call" if word&1 else "direct_jump"
                else:
                    displacement=sx(word&0xfffc,16)
                    target=(displacement if word&2 else pc+displacement)&0xffffffff
                    edge_type="conditional_call" if word&1 else "conditional_branch"
                executable_target=any(s["va"]<=target<s["end"] for s in executable)
                edge=dict(pc="0x%08X"%pc,kind=edge_type,target="0x%08X"%target,
                          target_file_backed_executable=executable_target)
                edges.append(edge)
            elif op==19 and ((word>>1)&1023) in (16,528):
                edges.append(dict(pc="0x%08X"%pc,
                                  kind="bclr_indirect" if ((word>>1)&1023)==16 else "bcctr_indirect",
                                  target="UNRESOLVED_RUNTIME"))
            elif op==17 and word==0x44000002:
                edges.append(dict(pc="0x%08X"%pc,kind="syscall",
                                  target="DYNAMIC_LV2_SERVICE"))
    executable_words=sum(s["filesz"]//4 for s in executable)
    if executable_words<len(confirmed_pcs):raise ValueError("Code inventory exceeds X")
    kinds=Counter(e["kind"] for e in edges)
    return {
       "schema":"ascension-m761-executable-code-inventory-1",
       "method":"PPC64 BE PT_LOAD X SHA-gated + strict existing AOT lifter on bounded structural candidates; no whole-section linear sweep",
       "source_elf_sha256":digest,"source_elf_size":len(raw),
       "ppu_elf_machine":21,
       "e_entry_descriptor":"0x%08X"%e_entry,
       "ppu_entry_code":"0x%08X"%code,"ppu_toc":"0x%08X"%toc,
       "file_backed_executable_segments":[{k:("0x%X"%v if k in ("va","end","mem_end","offset","flags") else v) for k,v in s.items()} for s in executable],
       "executable_words_denominator":executable_words,
       "structural_function_candidates_discovered":len(spans()),
       "structural_candidate_words":sum(len(w) for _,w in spans()),
       "strictly_lifted_entries":len(accepted),
       "strictly_lifted_distinct_instruction_pcs":len(confirmed_pcs),
       "unclassified_executable_words":executable_words-len(confirmed_pcs),
       "unclassified_note":"May include actual instructions, literal pools, data, unknown branch targets or unreachable code. NOT counted as valid code or proven non-code.",
       "backend_rejected_candidates":unknown,
       "rejections_with_opcodes":lifted["rejected"],
       "edges_summary":dict(kinds),"edges":edges,
       "functions":[dict(start="0x%08X"%p,end="0x%08X"%(p+len(w)*4),
                         word_count=len(w),accepted_by_lifter=p in accepted,
                         observed_on_device=(p==0x003e16e0 and False),
                         reachability=("ACTUAL_UNRESOLVED_STOP" if p==0x003e16e0 else "NÃO MEDIDO"),
                         source_bytes_sha256=hashlib.sha256(struct.pack(">"+str(len(w))+"I",*w)).hexdigest())
                    for p,w in spans()],
       "source_code_translation_arm64":"NÃO MEDIDO",
       "object_compiled":"NÃO MEDIDO",
       "linked_macho":"NÃO MEDIDO",
       "executed_guest_aot_distinct":"NÃO MEDIDO",
       "guest_fs_open":"NÃO MEDIDO",
       "guest_fs_read":"NÃO MEDIDO",
       "psarc":"NÃO MEDIDO","rsx":"NÃO MEDIDO",
       "note":"The 26 regions are structural candidates; NOT a whole-game function inventory. Avoid equating any executable-section denominator with valid instructions."
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--elf",required=True,type=Path)
    ap.add_argument("--output",required=True,type=Path)
    args=ap.parse_args()
    report=analyze(args.elf)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print("M7.61 read-only owner inventory: %d/%d candidates lifted; PPC=%d; remaining X words unclassified=%d" %
          (report["strictly_lifted_entries"],report["structural_function_candidates_discovered"],
           report["strictly_lifted_distinct_instruction_pcs"],report["unclassified_executable_words"]))
if __name__=="__main__":main()
