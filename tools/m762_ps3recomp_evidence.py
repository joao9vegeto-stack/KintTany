#!/usr/bin/env python3
"""Offline check of user-supplied ps3recomp ZIP vs M7.62 semantic IR. No guest files emitted."""
import argparse,base64,csv,gzip,hashlib,io,json,re,zipfile,collections
from pathlib import Path
SHA="07b74c4557b4951c3c113c998dc5895932e28b33cf240fdc13f9315fe7d84eb3"
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--package",required=True,type=Path);p.add_argument("--snapshot",required=True,type=Path);p.add_argument("--output",required=True,type=Path);a=p.parse_args()
 data=a.package.read_bytes()
 raw=gzip.decompress(base64.b64decode(a.snapshot.read_bytes().strip(),validate=True))
 if hashlib.sha256(raw).hexdigest()!=SHA:raise ValueError("untrusted IR")
 accepted=json.loads(raw)["accepted"]
 with zipfile.ZipFile(io.BytesIO(data)) as z:
  if z.testzip():raise ValueError("zip corrupted")
  for line in z.read("SHA256SUMS.txt").decode().splitlines():
   m=re.fullmatch(r"([a-f0-9]{64})\s+(.+)",line)
   if not m or hashlib.sha256(z.read(m.group(2))).hexdigest()!=m.group(1):
    raise ValueError("SHA-256 source mismatch")
  f=json.loads(z.read("functions.json")); imp=json.loads(z.read("imports.json"))
  rows=list(csv.DictReader(io.StringIO(z.read("function_inventory.csv").decode())))
  imps=list(csv.DictReader(io.StringIO(z.read("imports_nids.csv").decode())))
  if len(f)!=len(rows) or len(f)!=7643 or len(imp)!=len(imps) or len(imp)!=350:raise ValueError("counts mismatch")
  for x,y in zip(f,rows):
   v=int(x["start"],16);end=int(x["end"],16)
   if not(v<end and v%4==0 and v>=0x10000 and end<=0x81e468):raise ValueError("nonexecutable OPD range")
   if x["start"]!=y["guest_start"] or x["end"]!=y["guest_end_exclusive"] or x["opd"]!=y["opd"] or x["toc"]!=y["toc"]:raise ValueError("OPD CSV mismatch")
   if int(y["elf_file_offset"],16)!=v-0x10000:raise ValueError("guest file offset mismatch")
  for x,y in zip(imp,imps):
   if x["library"]!=y["library"] or int(x["nid"],16)!=int(y["nid"],16) or int(x["stub"],16)!=int(y["guest_stub"],16):raise ValueError("NID/stub mismatch")
  ops={int(x["start"],16) for x in f}
  from_opd=sum(x["origin"]=="opd" and x["pc"] in ops for x in accepted)
  cfg=sum(x["origin"]=="direct_call_target" and x["pc"] not in ops for x in accepted)
  counts=dict(collections.Counter(x["library"] for x in imp))
  if (from_opd,cfg)!=(651,154) or len(counts)!=25 or counts.get("sys_fs")!=26:raise ValueError("source origin not aligned")
  if "func_002C53B0" not in z.read("ppu_recomp_table.cpp").decode() or "void func_002C53B0" not in z.read("generated_code_excerpts.cpp").decode():raise ValueError("stop absent upstream")
  evidence={"upstream_opd":len(f),"imports":len(imp),"libraries":len(counts),"import_sys_fs":counts["sys_fs"],"m762_accepted_opd":from_opd,"m762_accepted_cfg":cfg,"ir_sha256":SHA,"game_elf_in_zip":False,"hpp_HLE_implemented":"NOT_MEASURED"}
  a.output.write_text(json.dumps(evidence,sort_keys=True,indent=2)+"\n")
 print("verified",len(f),"OPD;",len(imp),"imports;",from_opd+cfg,"native IR entries")
if __name__=="__main__":main()
