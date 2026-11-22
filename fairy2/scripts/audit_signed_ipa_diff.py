#!/usr/bin/env python3
"""Compare the first and newest SIGNED Fairy2iOS IPAs without recompiling.

Inputs: original GitHub artifact ZIPs. Output: hashes, guest code differences,
precise manual patch opcode changes; never export game bytes to the report.
"""
from __future__ import annotations
import argparse,hashlib,json,shutil,struct,tempfile,zipfile
from pathlib import Path

TID="0100B9801F872000"
APP="Payload/DmShell.app/"
FW=APP+"Frameworks/DmGame"+TID+".framework/"
EXE="DmGame"+TID
GUEST=[("__TEXT","__dmmainx0"),("__DMmainW","__img"),("__TEXT","__dmmainx1")]
SECTIONS=GUEST+[("__TEXT","__text")]
SITES={
    "KTGL_child_2GiB":[0x21b6924,0x21b6954],
    "global_root_5GiB":[0x5f1b9c,0x1d700bc,0x225de0c,0x2295a44,0x2295a50],
    "G1T_parser":[0x612120],
    "G1S_reader":[0x6e7bb0],
    "KTGL_direct_reader":[0xc11b80,0xc11f9c],
    "mode4_inflater":[0xc0ef8c,0xc0f0d4],
}
def sha(x):return hashlib.sha256(x).hexdigest()
def file_hash(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(8<<20),b""):h.update(b)
    return h.hexdigest()
def need(condition,message):
    if not condition:raise RuntimeError("[Fairy2iOS signed IPA diff] "+message)

def macho_sections(data):
    need(len(data)>32 and struct.unpack_from("<I",data)[0]==0xfeedfacf,
         "framework is not thin arm64 Mach-O")
    head=struct.unpack_from("<IiiIIIII",data)
    need(head[1]==0x0100000c,"framework is not arm64")
    count=head[4];at=32;parts={}
    for _ in range(count):
        need(at+8<=len(data),"truncated Mach-O load command")
        typ,size=struct.unpack_from("<II",data,at)
        need(size>=8 and at+size<=len(data),"invalid Mach-O command size")
        if typ==0x19:
            need(size>=72,"short segment_64")
            ns=struct.unpack_from("<I",data,at+64)[0]
            need(size>=72+ns*80,"short section_64 table")
            for i in range(ns):
                s=at+72+i*80
                name=data[s:s+16].split(b"\0",1)[0].decode()
                seg=data[s+16:s+32].split(b"\0",1)[0].decode()
                _,n,offset=struct.unpack_from("<QQI",data,s+32)
                if (seg,name) in SECTIONS:
                    need(offset+n<=len(data),"section out of file")
                    parts[(seg,name)]=data[offset:offset+n]
        at+=size
    need(all(x in parts for x in SECTIONS),"NXNative guest sections missing")
    return parts

def get_ip_from_artifact(art,d):
    with zipfile.ZipFile(art) as z:
        candidates=[n for n in z.namelist() if n.endswith(".ipa")]
        need(len(candidates)==1,"artifact has no unique IPA")
        ip=Path(d)/(art.stem+".ipa")
        with z.open(candidates[0]) as src,ip.open("wb") as dst:
            shutil.copyfileobj(src,dst,8<<20)
    return ip

def read_artifact(art,d):
    ip=get_ip_from_artifact(art,d)
    with zipfile.ZipFile(ip) as z:
        exe=z.read(FW+EXE)
        sections=macho_sections(exe)
        profile=z.read(FW+"profile.tsv").decode(errors="replace")
        shader=z.getinfo(FW+"msl/b-0724088d3779.img")
        shmap=z.getinfo(FW+"dm/shader_map.tsv")
        provenance={
           "artifact":art.name,"ipa_sha256":file_hash(ip),
           "ipa_size_bytes":ip.stat().st_size,
           "host_exe_sha256":sha(exe),
           "sections":{str(k):{"bytes":len(v),"sha256":sha(v)}
                       for k,v in sections.items()},
           "profile":profile.splitlines(),
           "shader_metallib":{"bytes":shader.file_size,"crc32":hex(shader.CRC)},
           "shader_map":{"bytes":shmap.file_size,"crc32":hex(shmap.CRC)}}
    ip.unlink()
    return provenance,sections

def difference(a,b):
    stop=min(len(a),len(b));spans=[];start=None;words=0
    for p in range(0,stop,4):
        bad=a[p:p+4]!=b[p:p+4]
        if bad:
            words+=1
            if start is None:start=p
        elif start is not None:
            spans.append({"start":hex(start),"end":hex(p),"bytes":p-start})
            start=None
    if start is not None:spans.append({"start":hex(start),"end":hex(stop),"bytes":stop-start})
    return {"before_bytes":len(a),"after_bytes":len(b),
            "changed_4byte_words":words,
            "total_spans":len(spans),"spans":spans[:2000],
            "spans_truncated":len(spans)>2000}

def compare(first,latest):
    meta0,secs0=first;meta1,secs1=latest
    g0=b"".join(secs0[x] for x in GUEST)
    g1=b"".join(secs1[x] for x in GUEST)
    spots={}
    for label,addresses in SITES.items():
        spots[label]=[{"address":"main+0x%x"%at,
                       "first_opcode":g0[at:at+4].hex(),
                       "latest_opcode":g1[at:at+4].hex(),
                       "different":g0[at:at+4]!=g1[at:at+4]} for at in addresses]
    return {
        "first":meta0,"latest":meta1,
        "shader_bytes_crc_unchanged":meta0["shader_metallib"]==meta1["shader_metallib"],
        "shader_map_bytes_crc_unchanged":meta0["shader_map"]==meta1["shader_map"],
        "signed_image_sections":{str(k):difference(secs0[k],secs1[k]) for k in SECTIONS},
        "site_opcodes":spots,
        "guest_concat_sha_first":sha(g0),"guest_concat_sha_latest":sha(g1),
        "guest_concat_bytes_first":len(g0),"guest_concat_bytes_latest":len(g1),
        "no_ipa_build_or_gameplay_test":True,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--first",type=Path,required=True)
    p.add_argument("--latest",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    q=p.parse_args()
    with tempfile.TemporaryDirectory() as d:
        result=compare(read_artifact(q.first,d),read_artifact(q.latest,d))
    q.output.parent.mkdir(exist_ok=True,parents=True)
    q.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    print("FIRST",result["first"]["ipa_sha256"],"LATEST",result["latest"]["ipa_sha256"])
    print("SHADERS SAME",result["shader_bytes_crc_unchanged"])
    for k,v in result["signed_image_sections"].items():
        print(k,v["changed_4byte_words"],"changed words;",v["total_spans"],"spans")
    for k,v in result["site_opcodes"].items():
        print(k,[(s["address"],s["first_opcode"],s["latest_opcode"]) for s in v])
if __name__=="__main__":main()
