#!/usr/bin/env python3
"""Produce a reproducible next-AOT candidate from a PHYSICAL iPhone TXT + owner ELF.

No PPC interpretation, no guess of function boundaries, no simulated guest FS.
Works with v10 historical reports, and richer AOT_TRIAGE_JSON in M7.60+.
"""
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

def read_elf_instruction(data: bytes, pc: int):
    if len(data)<64 or data[:7]!=b'\x7fELF\x02\x02\x01':
        raise ValueError('Expected ELF64 big-endian original PPC owner executable')
    table=struct.unpack_from('>Q',data,32)[0]
    ent_size,num=struct.unpack_from('>HH',data,54)
    if ent_size<56 or not num or table+num*ent_size>len(data):
        raise ValueError('ELF program header table invalid')
    for k in range(num):
        pos=table+k*ent_size
        typ,flags,off,va,_,filelen,memlen,_=struct.unpack_from('>IIQQQQQQ',data,pos)
        if typ!=1 or not(flags&1) or filelen>memlen or off+filelen>len(data):
            continue
        if va<=pc and pc+4<=va+filelen:
            at=off+(pc-va)
            return struct.unpack_from('>I',data,at)[0],at
    raise ValueError(f'Guest PC 0x{pc:08x} is outside file-backed executable PT_LOAD')

def signed(x,bits):
    return x-(1<<bits) if (x>>(bits-1))&1 else x

def branch(pc,w):
    op=w>>26
    if op==18:
        off=signed(w&0x03fffffc,26)
        return {'kind':'bl' if w&1 else 'b',
                'target':f'0x{(off if w&2 else pc+off)&0xffffffff:08X}',
                'terminal':not bool(w&1)}
    if op==16:
        off=signed(w&0xfffc,16)
        return {'kind':'bcl' if w&1 else 'bc',
                'target':f'0x{(off if w&2 else pc+off)&0xffffffff:08X}',
                'fallthrough':f'0x{pc+4:08X}', 'bo':(w>>21)&31,
                'bi':(w>>16)&31,'terminal':False}
    if op==19 and ((w>>1)&1023) in (16,528):
        return {'kind':'bclr_or_bcctr','target':'indirect',
                'terminal':True}
    if op==17:
        return {'kind':'sc','terminal':True}
    return None

def analyze(report: str, elf: bytes, max_words: int):
    m=re.search(r'^PC de parada=0x([0-9a-fA-F]+)',report,re.M)
    if not m:
        raise ValueError('No measured physical PC de parada found in report')
    stop=int(m.group(1),16)
    old=json.loads(re.search(r'^AOT_TRIAGE_JSON=(\{.+\})$',report,re.M).group(1)) if re.search(r'^AOT_TRIAGE_JSON=(\{.+\})$',report,re.M) else None
    first_real=re.search(r'^opcode ELF=0x([0-9A-Fa-f]+) \| opcode RAM=0x([0-9A-Fa-f]+)',report,re.M)
    if first_real and (int(first_real.group(1),16)!=int(first_real.group(2),16)):
        raise ValueError('Device guest RAM differs from ELF at stop; investigate first')
    word,off=read_elf_instruction(elf,stop)
    if first_real and word!=int(first_real.group(1),16):
        raise ValueError('Provided owner ELF and device report disagree on stop word')
    if stop&3:raise ValueError('Unaligned stop PC')
    records=[]
    for i in range(max_words):
        pc=stop+4*i
        try:
            w,at=read_elf_instruction(elf,pc)
        except ValueError:
            break
        rec={'pc':f'0x{pc:08X}','opcode':f'0x{w:08X}'}
        b=branch(pc,w)
        if b:rec['control_flow']=b
        records.append(rec)
        # do not stop at BL: include known PPC words after call where useful.
        if b and b['terminal']:break
        # at first conditional branch, stop conservatively: no CFG invented
        if b and b['kind'] in ('bc','bcl'):break
    return {'schema':'ascension-offline-AOT-candidate-1',
            'owner_elf_sha256':hashlib.sha256(elf).hexdigest(),
            'pc_guest_missing':f'0x{stop:08X}',
            'file_offset':f'0x{off:X}',
            'device_ram_elf_match': bool(first_real),
            'source_device_triage':old is not None,
            'previous_aot':old.get('previous_aot') if old else None,
            'first_exec_count':len(old['first_aot']) if old else None,
            'first_exec_truncated':old.get('first_truncated') if old else None,
            'recent_compacted_runs':old.get('recent_runs') if old else None,
            'guest_fs_positive_bytes':old.get('guest_fs_positive_bytes') if old else None,
            'candidate_word_count':len(records),
            'candidate_is_function':False,
            'notice':'Conservative executable PT_LOAD slice, not proven function boundaries or executed AOT',
            'ppc_words':records}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--max-words',type=int,default=64)
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    if not 1<=a.max_words<=256:
        p.error('--max-words must be between 1 and 256')
    result=analyze(a.report.read_text(),a.elf.read_bytes(),a.max_words)
    raw=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if a.output:
        a.output.write_text(raw)
        print(f'Generated {a.output}, {result["candidate_word_count"]} executable PPC words')
    else:
        print(raw,end='')
if __name__=='__main__':main()
