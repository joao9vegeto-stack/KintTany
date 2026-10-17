#!/usr/bin/env python3
"""Stage user-owned GOWA.ELF-derived native AOT from NEW Actions secret.

M7.18 does not replace the 64-entry M7.12 owner module; it adds 500
distinct, original-ELF-fingerprinted native basic blocks. Never log/commit
the decoded C, ELF, or secret. Strict digest and symbol verification.
"""
from __future__ import annotations
import base64
import binascii
import gzip
import hashlib
import io
import os
from pathlib import Path
import re
import sys

ELF_SHA256 = "4bf75c897b82d1beb25514cbadaff3d03e1b0c7bf849fa5d289be4f9183462b5"
SOURCE_SHA256 = "621a811560e5e6f5f921f2099088879e64fb3850c68dec3b4828f8ebedfad9d1"
BLOCK_COUNT = 500
MAX_B64_CHARS = 48000
MAX_GZIP_BYTES = 36000
MAX_SOURCE_BYTES = 1024 * 1024
REQUIRED = {"003c4e14","003c4cb0","003c4cdc","003c4cd4","003c4e40"}

def decode_bulk_secret(value: str) -> tuple[bytes,list[str]]:
    if not value or not value.strip() or len(value.strip()) > MAX_B64_CHARS:
        raise ValueError("M7.18 bulk secret absent/oversize")
    try:
        compressed = base64.b64decode(value.strip(), validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("M7.18 strict base64 invalid") from error
    if not compressed or len(compressed)>MAX_GZIP_BYTES:
        raise ValueError("M7.18 compressed size out of range")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as stream:
            source = stream.read(MAX_SOURCE_BYTES+1)
    except (OSError, EOFError) as error:
        raise ValueError("M7.18 gzip corrupt") from error
    if len(source)>MAX_SOURCE_BYTES or b"\x00" in source:
        raise ValueError("M7.18 decoded AOT source rejected")
    if hashlib.sha256(source).hexdigest()!=SOURCE_SHA256:
        raise ValueError("M7.18 owner AOT source SHA256 differs from validated batch")
    digest_def=re.search(rb"ar_bulk_elf_sha256\s*\[32\]\s*=\s*\{([^}]+)\}", source)
    if not digest_def:
        raise ValueError("M7.18 bulk ELF hash gate absent")
    octets=re.findall(rb"0x([0-9a-fA-F]{2})\b",digest_def.group(1))
    if len(octets)!=32 or bytes(int(x,16) for x in octets).hex()!=ELF_SHA256:
        raise ValueError("M7.18 original GOWA.ELF fingerprint mismatch")
    names=re.findall(rb"\bint\s+ar_bulk_ppu_([0-9a-f]{8})\s*\(",source)
    entries=[n.decode("ascii") for n in names]
    if len(entries)!=BLOCK_COUNT or len(set(entries))!=BLOCK_COUNT:
        raise ValueError("M7.18 expected 500 unique native AOT entry definitions")
    if not REQUIRED.issubset(entries) or b"ar_bulk_install_sha256" not in source:
        raise ValueError("M7.18 required branch-continuation or installer missing")
    return source, entries

def main() -> int:
    source, entries=decode_bulk_secret(
        os.environ.get("ASCENSION_AOT_BULK_GZIP_B64", ""))
    temp=Path(os.environ["RUNNER_TEMP"]).resolve()
    if not temp.is_dir():
        raise ValueError("RUNNER_TEMP missing")
    source_path=temp/"ascension_m718_private_bulk.c"
    source_path.write_bytes(source)
    source_path.chmod(0o600)
    manifest=temp/"ascension_m718_bulk_symbols.txt"
    manifest.write_text("\n".join("ar_bulk_ppu_"+n for n in entries)+"\n",
                        encoding="ascii")
    with open(os.environ["GITHUB_ENV"],"a",encoding="utf-8") as env:
        env.write("ASCENSION_PRIVATE_BULK_C="+str(source_path)+"\n")
        env.write("ASCENSION_BULK_SYMBOL_LIST="+str(manifest)+"\n")
        env.write("ASCENSION_BULK_COUNT="+str(len(entries))+"\n")
    print("M7.18: 500 unique private ARM64 AOT blocks validated; source SHA256="+SOURCE_SHA256)
    print("M7.18: 68 legacy owner+native entries preserved; 568 total expected on iPhone")
    return 0

if __name__=="__main__":
    try:
        sys.exit(main())
    except (ValueError,KeyError) as error:
        print("M7.18 private batch staging failed: "+str(error),file=sys.stderr)
        sys.exit(1)
