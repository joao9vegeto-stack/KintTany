#!/usr/bin/env python3
"""Inspect compressed XOWUE guest switch-table blob for static data/vtable material."""
from __future__ import annotations
import base64, hashlib, json, zlib
from pathlib import Path

def main():
    path=Path("tools/xowue_tables.guest.bin.z")
    raw=path.read_bytes()
    try:
        decoded=zlib.decompress(raw)
        codec="zlib"
    except zlib.error:
        try:
            decoded=zlib.decompress(raw,-zlib.MAX_WBITS)
            codec="raw-deflate"
        except zlib.error:
            try:
                decoded=zlib.decompress(raw,31)
                codec="gzip"
            except zlib.error as exc:
                raise SystemExit(f"guest table archive could not be decompressed: {exc}")
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
      "codec":codec,"decoded_bytes":len(decoded),"decoded_sha256":hashlib.sha256(decoded).hexdigest(),
      "decoded_prefix_hex":decoded[:1024].hex(),
      "target_big_endian_address_hits":hits,
      "decoded_full_base64":base64.b64encode(decoded).decode("ascii"),
      "interpretation":"A compact decompressed table is not presumed to be a full XEX image; address hits are evidence only."
    }
    Path("xowue-guest-tables-inspection.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("XOWUE_GUEST_TABLES_INSPECTION "+json.dumps({
      "compressed_bytes":len(raw),"codec":codec,"decoded_bytes":len(decoded),
      "target_hits":{k:len(v) for k,v in hits.items()},
      "prefix_hex":decoded[:64].hex()}))
if __name__=="__main__": main()
