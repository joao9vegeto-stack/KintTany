#!/usr/bin/env python3
"""Stage exact owner-provided NPUA80918 AOT C from Actions repository secret.

Reads only an environment variable; never logs decoded source or secret.
A SHA mismatch fails the build. Source remains outside the Git tree.
"""
from __future__ import annotations
import base64
import binascii
import gzip
import hashlib
import io
import os
from pathlib import Path
import sys

EXPECTED_SHA256 = "2f2a28334e96bafcb9d0d8920b5372b978646ad22e1b5c4681e0a03aac61747d"
ENTRY_PCS = (
    0x00010200, 0x00010380, 0x00010410, 0x00010434, 0x00010444, 0x00010534, 0x000107a4, 0x00010814, 0x002c1024, 0x002c10c8, 0x002c10d0, 0x002c10e4, 0x002c1570, 0x002c15e4, 0x002c15f4, 0x003678ec, 0x00455a10, 0x00455eac, 0x00455f9c, 0x00455fa4, 0x00455fb8, 0x005232b0, 0x00523318, 0x00523350, 0x00523360, 0x00523390, 0x00523428, 0x00525c00, 0x0052a710, 0x0052a78c, 0x0052a7bc, 0x0052e118, 0x0052e180, 0x0052e3b0, 0x0052e3f4, 0x0052e4f0, 0x0052e544, 0x00531a74, 0x00531cac, 0x00539998, 0x00539a50
)
EXPECTED_SYMBOLS = tuple(f"ar_game_ppu_{pc:08x}" for pc in ENTRY_PCS)


def decode_verified(value: str) -> bytes:
    if not value or len(value) > 48000:
        raise ValueError("AOT secret absent or unreasonably large")
    try:
        compressed = base64.b64decode(value.strip(),validate=True)
    except (ValueError,binascii.Error) as err:
        raise ValueError("AOT secret is not strict base64") from err
    if not compressed or len(compressed)>36000:
        raise ValueError("AOT compressed size rejected")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(compressed),mode="rb") as f:
            source=f.read(256001)
    except (OSError,EOFError) as err:
        raise ValueError("AOT gzip data corrupt") from err
    if len(source)>256000:
        raise ValueError("AOT decompressed bytes exceed bound")
    if hashlib.sha256(source).hexdigest()!=EXPECTED_SHA256:
        raise ValueError("AOT source SHA256 mismatched M7.10")
    for symbol in (*EXPECTED_SYMBOLS,"ar_private_aot_install_sha256"):
        if symbol.encode("ascii") not in source:
            raise ValueError("AOT required entry missing: "+symbol)
    return source


def main() -> int:
    source=decode_verified(os.environ.get("ASCENSION_AOT_SOURCE_GZIP_B64",""))
    runner_temp=Path(os.environ["RUNNER_TEMP"]).resolve()
    if not runner_temp.is_dir():
        raise ValueError("RUNNER_TEMP unavailable")
    out=runner_temp/"ascension_m710_owner_aot.c"
    out.write_bytes(source)
    out.chmod(0o600)
    with open(os.environ["GITHUB_ENV"],"a",encoding="utf-8") as stream:
        stream.write("ASCENSION_PRIVATE_AOT_C="+str(out)+"\n")
    print("M7.10 owner AOT source SHA256 verified; 41 real native entries staged")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError,KeyError) as exc:
        print("M7.10 native AOT staging failed: "+str(exc),file=sys.stderr)
        sys.exit(1)
