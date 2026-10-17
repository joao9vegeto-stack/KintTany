#!/usr/bin/env python3
"""M7.19: stage a second PRIVATE owner-ELF-derived PPC -> ARM64 AOT batch.

No game ELF, license, decrypted game source, or Base64 secret in public Git.
The original 64 and M7.18 500 AOT entries remain intact. A strict pinned
source digest, 850 unique code definitions, and preexisting PC manifests
are required before compilation.
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

ELF_SHA256="4bf75c897b82d1beb25514cbadaff3d03e1b0c7bf849fa5d289be4f9183462b5"
SOURCE_SHA256="a81a67cfb4be91919f5043a226ffb5c25cefce4c9d663d3dcdca65b8831fdfc7"
COUNT=850
REQUIRED={"002c16a4","002c16b4","003c5cc8"}
EXTRAS={"003c4d94","003c4da4","003c4db4","003c4dc4"}

def decode(value: str, old_entries: set[str] | None = None) -> tuple[bytes,list[str]]:
    if not value or len(value.strip())>48000:
        raise ValueError("M7.19 missing/oversized owner secret")
    try:
        packed=base64.b64decode(value.strip(),validate=True)
    except (ValueError,binascii.Error) as exc:
        raise ValueError("M7.19 strict Base64 failed") from exc
    if not packed or len(packed)>36000:
        raise ValueError("M7.19 packed source exceeds private-secret bound")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(packed),mode="rb") as f:
            source=f.read(1024*1024+1)
    except (OSError,EOFError) as exc:
        raise ValueError("M7.19 invalid gzip") from exc
    if len(source)>1024*1024 or b"\x00" in source:
        raise ValueError("M7.19 decoded C too large or not plain text")
    if hashlib.sha256(source).hexdigest()!=SOURCE_SHA256:
        raise ValueError("M7.19 source fingerprint mismatch")
    digest=re.search(rb"ar_bulk2_elf_sha256\s*\[32\]\s*=\s*\{([^}]+)\}",source)
    if not digest:
        raise ValueError("M7.19 original ELF fingerprint missing")
    octets=re.findall(rb"0x([0-9a-fA-F]{2})\b",digest.group(1))
    if len(octets)!=32 or bytes(int(x,16) for x in octets).hex()!=ELF_SHA256:
        raise ValueError("M7.19 owner ELF mismatch")
    pcs=[x.decode("ascii") for x in re.findall(
        rb"\bint\s+ar_bulk2_ppu_([0-9a-f]{8})\s*\(",source)]
    if len(pcs)!=COUNT or len(set(pcs))!=COUNT:
        raise ValueError("M7.19 expected exactly 850 unique native AOT entries")
    if not REQUIRED.issubset(pcs) or b"ar_bulk2_install_sha256" not in source:
        raise ValueError("M7.19 required frontier/installer absent")
    if old_entries is not None and (set(pcs) & (old_entries | EXTRAS)):
        raise ValueError("M7.19 duplicated prior NPUA80918 AOT PC")
    return source,pcs

def existing_pcs(paths: list[str]) -> set[str]:
    pcs=set()
    for file in paths:
        for symbol in Path(file).read_text(encoding="ascii").splitlines():
            m=re.fullmatch(r"(?:ar_game_ppu_|ar_bulk_ppu_)([0-9a-f]{8})",symbol)
            if not m:
                raise ValueError("M7.19 prior ARM64 manifest invalid")
            pcs.add(m.group(1))
    return pcs

def main():
    prior=existing_pcs([
        os.environ["ASCENSION_AOT_SYMBOL_LIST"],
        os.environ["ASCENSION_BULK_SYMBOL_LIST"]])
    if len(prior)!=564:
        raise ValueError("M7.19 requires all 64 old + 500 M7.18 entries")
    source,pcs=decode(os.environ.get("ASCENSION_AOT_BULK2_GZIP_B64",""),prior)
    tmp=Path(os.environ["RUNNER_TEMP"]).resolve()
    if not tmp.is_dir():
        raise ValueError("M7.19 RUNNER_TEMP missing")
    code=tmp/"ascension_m719_private_bulk2.c"
    code.write_bytes(source);code.chmod(0o600)
    manifest=tmp/"ascension_m719_bulk2_symbols.txt"
    manifest.write_text("".join("ar_bulk2_ppu_"+pc+"\n" for pc in pcs),encoding="ascii")
    with open(os.environ["GITHUB_ENV"],"a",encoding="utf-8") as env:
        env.write("ASCENSION_PRIVATE_BULK2_C="+str(code)+"\n")
        env.write("ASCENSION_BULK2_SYMBOL_LIST="+str(manifest)+"\n")
        env.write("ASCENSION_BULK2_COUNT="+str(len(pcs))+"\n")
    print(f"M7.19 private batch staged: {len(pcs)} new PPC AOT entries; 1418 linked entries anticipated")
    print("M7.19 source fingerprint verified: "+SOURCE_SHA256)
    return 0

if __name__=="__main__":
    try:sys.exit(main())
    except (ValueError,KeyError) as exc:
        print("M7.19 AOT staging refused: "+str(exc),file=sys.stderr)
        sys.exit(1)
