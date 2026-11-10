#!/usr/bin/env python3
"""Inspect compressed XOWUE guest switch-table blob for static data/vtable material."""
from __future__ import annotations
import base64, hashlib, json, zlib
from pathlib import Path

def main():
    import importlib.util, subprocess
    path=Path("tools/xowue_tables.guest.bin.z")
    raw=path.read_bytes()
    codec="unknown"; decoded=raw
    errors=[]
    attempts=[("zlib",lambda:zlib.decompress(raw)),
              ("raw-deflate",lambda:zlib.decompress(raw,-zlib.MAX_WBITS)),
              ("gzip",lambda:zlib.decompress(raw,31)),
              ("xz-lzma",lambda:__import__("lzma").decompress(raw))]
    for label,fn in attempts:
        try:
            decoded=fn(); codec=label; break
        except Exception as exc:
            errors.append(f"{label}: {exc}")
    if codec=="unknown":
        # Try optional codecs if installed on the macOS runner.
        for module,label,call in [
          ("zstandard","zstd",lambda m:m.ZstdDecompressor().decompress(raw)),
          ("lz4.frame","lz4-frame",lambda m:m.decompress(raw)),
          ("brotli","brotli",lambda m:m.decompress(raw)),
        ]:
            if importlib.util.find_spec(module.split(".")[0]) is None: continue
            try:
                m=__import__(module,fromlist=["*"])
                decoded=call(m); codec=label; break
            except Exception as exc:
                errors.append(f"{label}: {exc}")
    file_info=subprocess.run(["file",str(path)],capture_output=True,text=True).stdout.strip()
    targets=(0x820FD3B8,0x835E004C,0x835D0794,0x82575250,0x82575108)
    needles={f"0x{x:08X}":x.to_bytes(4,"big") for x in targets}
    hits={}
    for name,needle in needles.items():
        offsets=[]; start=0
        while True:
            p=decoded.find(needle,start)
            if p<0: break
            offsets.append(p); start=p+1
        hits[name]=offsets[:128]
    out={
      "file":str(path),"compressed_bytes":len(raw),"compressed_sha256":hashlib.sha256(raw).hexdigest(),
      "codec":codec,"file_identification":file_info,"codec_errors":errors,
      "magic_hex":raw[:96].hex(),"decoded_bytes":len(decoded),"decoded_sha256":hashlib.sha256(decoded).hexdigest(),
      "decoded_prefix_hex":decoded[:1024].hex(),
      "target_big_endian_address_hits":hits,
      "payload_base64":base64.b64encode(decoded).decode("ascii"),
      "interpretation":"A compact table is not presumed to be a full XEX image; address hits are evidence only."
    }
    Path("xowue-guest-tables-inspection.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("XOWUE_GUEST_TABLES_INSPECTION "+json.dumps({
      "compressed_bytes":len(raw),"codec":codec,"decoded_bytes":len(decoded),
      "target_hits":{k:len(v) for k,v in hits.items()},
      "prefix_hex":decoded[:64].hex()}))
if __name__=="__main__": main()
