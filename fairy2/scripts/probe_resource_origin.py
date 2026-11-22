#!/usr/bin/env python3
"""Fairy Tail 2: Linux-only, bounded read-only RDB/RDX/FDATA source proof."""
import argparse,hashlib,json,os,struct,zlib
from pathlib import Path
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
ROM_ID="1zrfginchdoUzhUIHl9vii-8TE_xLNcDo"
SIZE=7889449169
N=14770
ROOT="Motor/ReleasePackage/KIDS_PLATFORM_NX/release/"
M=1024*1024
TARGETS={0xfb9ebd24:0xafbec60c,0xac9ed13e:0x7bcd279f}
IDRK=struct.Struct("<8sQQQIIII")
def sha(x):return hashlib.sha256(x).hexdigest()
class Range:
    def __init__(self):
        raw=os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON","")
        if not raw:raise RuntimeError("Missing Google service-account secret")
        auth=service_account.Credentials.from_service_account_info(json.loads(raw),scopes=["https://www.googleapis.com/auth/drive.readonly"])
        self.s=AuthorizedSession(auth)
        self.url="https://www.googleapis.com/drive/v3/files/"+ROM_ID
        r=self.s.get(self.url,params={"fields":"id,name,size"},timeout=40)
        r.raise_for_status()
        self.size=int(r.json()["size"])
        if self.size!=SIZE:raise ValueError("Unknown RomFS size")
    def read(self,off,n):
        if off<0 or n<0 or n>8*M or off+n>self.size:raise ValueError("Invalid range")
        if not n:return b""
        h=f"bytes={off}-{off+n-1}"
        with self.s.get(self.url,params={"alt":"media"},headers={"Range":h,"Accept-Encoding":"identity"},stream=True,timeout=(25,120)) as r:
            if r.status_code!=206:raise RuntimeError("Drive ignored Range; refuse entire image HTTP "+str(r.status_code))
            if r.headers.get("Content-Range")!=f"bytes {off}-{off+n-1}/{self.size}":raise RuntimeError("Wrong Content-Range")
            b=r.content
        if len(b)!=n:raise RuntimeError("Truncated range")
        return b
def chunked(s,off,n):
    if n<0 or n>64*M:raise ValueError("Read cap")
    return b"".join(s.read(off+i,min(8*M,n-i)) for i in range(0,n,8*M))
class Rom:
    def __init__(self,s):
        self.s=s
        magic,start,nbytes,count=struct.unpack("<8sQQQ",s.read(0,32))
        if magic!=b"DMROMFS1" or count!=N or start+nbytes!=SIZE or nbytes>64*M:raise ValueError("RomFS identity")
        raw=chunked(s,start,nbytes)
        E=struct.Struct("<QQIHBB")
        entries=[E.unpack_from(raw,i*E.size) for i in range(count)]
        names=raw[count*E.size:]
        self.files={}; seen=set(); stack=[(0,"")]
        while stack:
            i,p=stack.pop()
            if i in seen:raise ValueError("Duplicate RomFS entry")
            seen.add(i)
            a,b,pos,nl,t,f=entries[i]
            if t==0:
                if a+b>count:raise ValueError("Bad child")
                for j in range(a,a+b):
                    aa,bb,np,nn,tt,ff=entries[j]
                    if np+nn>len(names):raise ValueError("Bad name")
                    name=names[np:np+nn].decode()
                    stack.append((j,p+("/" if p else "")+name))
            elif t==1:
                if a+b>start:raise ValueError("File overlaps index")
                self.files[p]={"offset":a,"size":b,"damaged":bool(f&1)}
            else:raise ValueError("Bad type")
        if len(seen)!=count:raise ValueError("Orphan entries")
        self.info={"size":SIZE,"entries":count,"files":len(self.files),"index_bytes":nbytes}
    def at(self,path,off,n):
        item=self.files[path]
        if off<0 or n<0 or off+n>item["size"]:raise ValueError("Outside archive")
        return self.s.read(item["offset"]+off,n)
    def get(self,path):
        item=self.files[path]
        return chunked(self.s,item["offset"],item["size"])
    def basename(self,name):
        return [p for p in self.files if p.rsplit("/",1)[-1].lower()==name.lower()]
def records(b):
    if b[:8]!=b"_DRK0000":raise ValueError("Wrong RDB magic")
    pos=32
    while pos+IDRK.size<=len(b):
        m,es,cs,unc,par,fileid,typ,flags=IDRK.unpack_from(b,pos)
        if m!=b"IDRK0000" or es<48 or cs>es-48 or pos+es>len(b):raise ValueError(f"Bad IDRK at {pos:x}")
        yield {"offset":pos,"size":es,"stored":cs,"plain":unc,"param":par,"file":fileid,"type":typ,"flags":flags,"data":pos+es-cs}
        pos=(pos+es+3)&~3
def pointer(b):
    if len(b)<13 or b[:2]!=b"\x01\x04":raise ValueError("Bad external pointer tag")
    p=2
    def uint():
        nonlocal p
        a=struct.unpack_from("<I",b,p)[0];p+=4
        if a&0x80000000:
            h=struct.unpack_from("<I",b,p)[0];p+=4
            return ((a&0x7fffffff)<<32)|h
        return a
    off=uint();size=uint()
    if p+3!=len(b):raise ValueError("Bad pointer length")
    marker,tail=struct.unpack_from("<HB",b,p)
    if tail:raise ValueError("Bad pointer terminator")
    return {"offset":off,"size":size,"marker":marker}
def rdx(b):
    if len(b)%8:raise ValueError("Bad RDX")
    d={}
    for i in range(0,len(b),8):
        marker,folder,sub,h=struct.unpack_from("<HBBI",b,i)
        if marker in d:raise ValueError("Duplicate marker")
        d[marker]={"file":f"0x{h:08x}.fdata","folder":folder,"sub":sub}
    return d
def sample(rom,path,r):
    off,n=r["data"],r["stored"]
    mode=(r["flags"]>>20)&63
    info={"compression":mode,"stored_size":n,"inflated_size":r["plain"]}
    if not n:return {**info,"status":"empty"}
    if mode==0:
        b=rom.at(path,off,min(n,128))
        return {**info,"status":"raw","header64":b[:64].hex(),"header_magic":b[:8].decode("latin1")}
    if mode not in (1,4,5):return {**info,"status":"unknown_compression"}
    hs=4 if mode==1 else 10
    cursor=0
    total=0
    digest=hashlib.sha256()
    first=b""
    chunks=0
    while cursor<n:
        if cursor+hs>n:
            tail=rom.at(path,off+cursor,n-cursor)
            if mode in (4,5) and tail==bytes(2):
                cursor=n
                break
            return {**info,"status":"incomplete_chunk_header","offset":cursor,"trailer":tail.hex()}
        hdr=rom.at(path,off+cursor,hs)
        zsize=struct.unpack_from("<I" if mode==1 else "<H",hdr)[0]
        if not 0<zsize<=8*M or cursor+hs+zsize>n:
            return {**info,"status":"bad_chunk_length","offset":cursor,"chunk":zsize}
        comp=rom.at(path,off+cursor+hs,zsize)
        if mode==5:
            return {**info,"status":"lz4_not_decoded","chunks_read":chunks+1,
                    "first_compressed_sha256":sha(comp)}
        try:plain=zlib.decompress(comp)
        except zlib.error as e:
            return {**info,"status":"zlib_error","offset":cursor,"error":str(e)}
        if not chunks:first=plain[:64]
        total+=len(plain)
        if total>64*M:return {**info,"status":"decompressed_size_limit"}
        digest.update(plain)
        chunks+=1
        cursor+=hs+zsize
    return {**info,"status":"zlib_ok" if total==r["plain"] else "plain_size_mismatch",
            "header64":first.hex(),"header_magic":first[:8].decode("latin1"),
            "full_payload_sha256":digest.hexdigest(),"decoded_length":total,
            "complete_input_bytes":cursor,"chunks":chunks,"is_g1s":first.startswith(b"_S2G"),
            "is_g1t":first.startswith(b"GT1G")}

def audit(rom):
    cache={}
    for name in ("system","root"):
        b=rom.get(ROOT+name+".rdb")
        cache[name]={"raw":b,"sha":sha(b)}
    out={"project":"Fairy2iOS","romfs":rom.info,"resources":{}}
    for fileid,expected_type in TARGETS.items():
        found=[]
        for group,info in cache.items():
            b=info["raw"]
            for r in records(b):
                if r["file"]!=fileid:continue
                x={"index":group,"rdb_sha256":info["sha"],"record":r,"type_match":r["type"]==expected_type}
                if r["flags"]&0x20000 and r["stored"]:
                    loc=pointer(b[r["data"]:r["offset"]+r["size"]])
                    x["pointer"]=loc
                    z=rdx(rom.get(ROOT+group+".rdx")).get(loc["marker"])
                    x["rdx_target"]=z
                    if z:
                        paths=rom.basename(z["file"])
                        x["paths"]=paths
                        if len(paths)==1:
                            path=paths[0]
                            m,es,cs,plain,par,rid,typ,flags=IDRK.unpack(rom.at(path,loc["offset"],IDRK.size))
                            if m!=b"IDRK0000" or es!=loc["size"] or cs>es-48:
                                raise ValueError("FDATA record misaligned")
                            fr={"offset":loc["offset"],"size":es,"stored":cs,"plain":plain,"param":par,
                                "file":rid,"type":typ,"flags":flags,"data":loc["offset"]+es-cs}
                            x["fdata"]=fr
                            x["identity_match"]=rid==fileid and typ==expected_type
                            x["plain_size_match"]=r["plain"]==plain
                            x["payload"]=sample(rom,path,fr)
                else:x["status"]="not external"
                found.append(x)
        out["resources"][f"0x{fileid:08x}"]={"type":f"0x{expected_type:08x}",
            "status":"found" if found else "missing","matches":found}
    return out
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    report=audit(Rom(Range()))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps(report,indent=2,ensure_ascii=False),flush=True)
    if any(z["status"]!="found" for z in report["resources"].values()):
        raise SystemExit("Requested resource absent from both RDB indexes")
if __name__=="__main__":main()
