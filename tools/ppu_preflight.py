#!/usr/bin/env python3
"""Read-only PPU ELF64 preflight. Exports metadata, never executable bytes."""
import argparse
from collections import Counter
import hashlib
import json
import struct
from pathlib import Path

class PPUError(ValueError):
    pass

def analyze(path: Path):
    data = path.read_bytes()
    if len(data) < 64 or data[:7] != b'\x7fELF\x02\x02\x01':
        raise PPUError("ELF64 big endian required")
    (etype,machine,version,entry,phoff,shoff,flags,ehsize,phsize,phnum,shsize,shnum,shstridx) = struct.unpack_from(">HHIQQQIHHHHHH",data,16)
    if etype != 2 or machine != 21 or version != 1:
        raise PPUError("not PS3 PPU ET_EXEC")
    if phnum > 256 or shnum > 4096 or phsize < 56 or shsize < 64:
        raise PPUError("invalid ELF table sizes")
    if phoff + phnum * phsize > len(data) or shoff + shnum * shsize > len(data):
        raise PPUError("ELF table out of bounds")
    ph = [struct.unpack_from(">IIQQQQQQ",data,phoff+i*phsize) for i in range(phnum)]
    sh = [struct.unpack_from(">IIQQQQIIQQ",data,shoff+i*shsize) for i in range(shnum)]
    if shstridx >= len(sh):
        raise PPUError("invalid shstrtab index")
    strs = sh[shstridx]
    if strs[4]+strs[5] > len(data):
        raise PPUError("string table truncated")
    namestr = data[strs[4]:strs[4]+strs[5]]
    def secname(s):
        pos = s[0]
        end = namestr.find(b'\x00',pos) if pos < len(namestr) else -1
        return namestr[pos:end].decode("utf8","replace") if end >= 0 else "?"
    sections = [dict(index=i,name=secname(s),address=hex(s[3]),size=s[5],flags=hex(s[2]),kind=s[1]) for i,s in enumerate(sh)]
    loads = [(i,p) for i,p in enumerate(ph) if p[0]==1 and p[5]>0]
    def read(va,n):
        for i,p in loads:
            if p[3] <= va and va+n <= p[3]+p[5]:
                off = p[2] + va-p[3]
                if off+n <= len(data):
                    return data[off:off+n]
        return None
    def u32(va):
        d = read(va,4)
        return struct.unpack(">I",d)[0] if d else None
    def cstring(va):
        if not va: return ""
        chars=[]
        for i in range(128):
            b=read(va+i,1)
            if not b or b==b'\x00':break
            chars.append(b)
        return b''.join(chars).decode("latin1","replace")
    cranges=[(p[3],p[3]+p[5]) for _,p in loads if p[1]&1]
    def iscode(va):return any(lo<=va<hi for lo,hi in cranges)
    containing=[(s[5],i,s) for i,s in enumerate(sh) if s[5]>0 and s[3]<=entry<s[3]+s[5]]
    if not containing:raise PPUError("entry OPD section missing")
    size,opdi,opdsec=min(containing)
    raw=read(opdsec[3],size)
    if raw is None:raise PPUError("OPD not PT_LOAD mapped")
    funcs=[];tocs=[]
    for off in range(0,len(raw)-7,8):
        func,toc=struct.unpack_from(">II",raw,off)
        if iscode(func):
            funcs.append(func);tocs.append(toc)
    entryraw=read(entry,8)
    if not entryraw:raise PPUError("entry OPD is unmapped")
    entryfunc,entrytoc=struct.unpack(">II",entryraw)
    if not iscode(entryfunc):raise PPUError("entry descriptor not pointing to executable code")
    ptprx=next((p for p in ph if p[0]==0x60000002),None)
    imports=[];warnings=[]
    if ptprx:
        hdr=read(ptprx[3],32)
        if hdr and struct.unpack_from(">I",hdr,4)[0]==0x1B434CEC:
            start,stop=struct.unpack_from(">II",hdr,24)
            va=start
            entries=[]
            for _ in range(512):
                if va>=stop:break
                row=read(va,0x1c)
                if not row: warnings.append("truncated libstub");break
                size=row[0]
                if size<0x1c or va+size>stop:
                    warnings.append("malformed libstub");break
                nfunc=struct.unpack_from(">H",row,6)[0]
                name=cstring(struct.unpack_from(">I",row,0x10)[0])
                nidtab,stubtab=struct.unpack_from(">II",row,0x14)
                entries.append([name,nfunc,nidtab,stubtab]);va+=size
            ns=sorted(e[2] for e in entries if e[2]);ss=sorted(e[3] for e in entries if e[3])
            def span(start,starts,fallback):
                bigger=[a for a in starts if a>start]
                end=min(bigger) if bigger else fallback
                return (end-start)//4 if end and end>start else None
            for name,nfunc,nid,stub in entries:
                if nfunc==0 and nid and stub:
                    choices=[n for n in (span(nid,ns,start),span(stub,ss,None)) if n and 0<n<=4096]
                    if choices:nfunc=min(choices)
                for i in range(min(nfunc,4096)):
                    ni=u32(nid+4*i);st=u32(stub+4*i)
                    if ni is not None and st is not None:
                        imports.append((name,ni,st))
        else:warnings.append("unexpected proc_prx_param magic")
    counts=Counter(name for name,_,_ in imports)
    return {
        "schema":"ascension-recomp/ppu-preflight-v1",
        "input_sha256":hashlib.sha256(data).hexdigest(),
        "elf_size_bytes":len(data),
        "ppu_entry_opd":hex(entry),
        "ppu_entry_code":hex(entryfunc),
        "ppu_entry_toc":hex(entrytoc),
        "opd_section":sections[opdi],
        "opd_valid_descriptors":len(funcs),
        "opd_unique_functions":len(set(funcs)),
        "module_toc":hex(Counter(tocs).most_common(1)[0][0]) if tocs else None,
        "load_segments":[{"virtual_address":hex(p[3]),"filesz":p[5],"memsz":p[6],"flags":hex(p[1]),"offset":hex(p[2])} for _,p in loads],
        "section_summary":sections,
        "imports_total":len(imports),
        "import_libraries":dict(counts),
        "imports_sample":[{"library":name,"nid":hex(nid),"stub":hex(stub)} for name,nid,stub in imports[:20]],
        "warnings":warnings,
        "note":"Metadata only. No executable bytes or license data."
    }

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("elf",type=Path)
    p.add_argument("--output","-o",type=Path,required=True)
    args=p.parse_args()
    result=analyze(args.elf)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf8")
    print("ELF size:",result["elf_size_bytes"])
    print("Entry code:",result["ppu_entry_code"],"TOC:",result["ppu_entry_toc"])
    print("OPD functions:",result["opd_unique_functions"])
    print("Firmware imports:",result["imports_total"],"libraries:",len(result["import_libraries"]))
    print("Warnings:",result["warnings"])
