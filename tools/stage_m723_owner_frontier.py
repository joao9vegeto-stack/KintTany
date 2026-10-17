#!/usr/bin/env python3
"""M7.23 stage ONE original-ELF-authenticated, privately generated AOT block.

Never commit, echo, print, log, or artifact the secret or generated C source.
All four Actions secrets are additive; previous 1418 ARM64 entrypoints remain.
"""
from __future__ import annotations
import base64,binascii,gzip,hashlib,io,os,re,sys
from pathlib import Path

ELF_SHA256="4bf75c897b82d1beb25514cbadaff3d03e1b0c7bf849fa5d289be4f9183462b5"
SOURCE_SHA256="ed8955f008960f86326e04672fdde5362474217a8e0a3d4e07bd1c8697f70bed"
ENTRY="003c511c"
AOT_NAME="ar_m722_ppu_"+ENTRY
INSTALLER_NAME="ar_m722_install_sha256"
MAX_B64=8192
MAX_GZIP=8192
MAX_SOURCE=16384

def stage_decode(encoded: str) -> bytes:
    if not encoded or not encoded.strip() or len(encoded.strip())>MAX_B64:
        raise ValueError("M7.23 required owner-private frontier secret missing/oversize")
    try:
        compressed=base64.b64decode(encoded.strip(),validate=True)
    except (binascii.Error,ValueError) as exc:
        raise ValueError("M7.23 invalid strict Base64") from exc
    if not compressed or len(compressed)>MAX_GZIP:
        raise ValueError("M7.23 compressed owner source size refused")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(compressed),mode="rb") as stream:
            source=stream.read(MAX_SOURCE+1)
    except (OSError,EOFError) as exc:
        raise ValueError("M7.23 invalid gzip") from exc
    if not source or len(source)>MAX_SOURCE or b"\x00" in source:
        raise ValueError("M7.23 owner AOT source not bounded plain C")
    if hashlib.sha256(source).hexdigest()!=SOURCE_SHA256:
        raise ValueError("M7.23 owner-private AOT source SHA256 mismatch")
    text=source.decode("utf-8","strict")
    defs=re.findall(r"\bint\s+(ar_m722_ppu_[0-9a-f]{8})\s*\(",text)
    if defs != [AOT_NAME]:
        raise ValueError("M7.23 expected exactly one named game native entry")
    if len(re.findall(r"\bint\s+ar_m722_install_sha256\s*\(",text))!=1:
        raise ValueError("M7.23 expected exactly one owner ELF installer")
    if not re.search(r"return\s+ar_register\s*\(\s*UINT32_C\s*\(\s*0x003c511c\s*\)\s*,\s*ar_m722_ppu_003c511c\s*\)",text):
        raise ValueError("M7.23 ELF-verified AOT entry registration missing")
    digest_def=re.search(r"ar_m722_elf_sha256\s*\[\s*32\s*\]\s*=\s*\{([^}]+)\}",text)
    if not digest_def:
        raise ValueError("M7.23 source original ELF digest gate missing")
    octets=re.findall(r"0x([0-9a-fA-F]{2})\b",digest_def.group(1))
    if len(octets)!=32 or bytes(int(x,16) for x in octets).hex()!=ELF_SHA256:
        raise ValueError("M7.23 source ELF fingerprint differs from owner GOWA.ELF")
    return source

def prior_aot_entries(paths: list[str]) -> set[str]:
    result=set()
    for file in paths:
        lines=Path(file).read_text(encoding="ascii").splitlines()
        if not lines:raise ValueError("M7.23 previous AOT manifest empty")
        for line in lines:
            m=re.fullmatch(r"ar_(?:game_ppu_|bulk_ppu_|bulk2_ppu_)([0-9a-f]{8})",line)
            if not m:raise ValueError("M7.23 previous owner AOT manifest invalid")
            result.add(m.group(1))
    return result

def main()->int:
    prior=prior_aot_entries([
        os.environ["ASCENSION_AOT_SYMBOL_LIST"],
        os.environ["ASCENSION_BULK_SYMBOL_LIST"],
        os.environ["ASCENSION_BULK2_SYMBOL_LIST"]])
    if len(prior)!=1414:
        raise ValueError("M7.23 missing prior 64+500+850 owner AOT entries")
    if ENTRY in prior or ENTRY in {"003c4d94","003c4da4","003c4db4","003c4dc4"}:
        raise ValueError("M7.23 duplicate owner-private guest entry")
    source=stage_decode(os.environ.get("ASCENSION_AOT_FRONTIER_GZIP_B64",""))
    tmp=Path(os.environ["RUNNER_TEMP"]).resolve()
    if not tmp.is_dir():raise ValueError("M7.23 temporary private directory missing")
    path=tmp/"ascension_m723_frontier_private.c"
    path.write_bytes(source)
    path.chmod(0o600)
    symbol_file=tmp/"ascension_m723_frontier_symbols.txt"
    symbol_file.write_text(AOT_NAME+"\n",encoding="ascii")
    with open(os.environ["GITHUB_ENV"],"a",encoding="utf-8") as env:
        env.write("ASCENSION_PRIVATE_FRONTIER_C="+str(path)+"\n")
        env.write("ASCENSION_FRONTIER_SYMBOL_LIST="+str(symbol_file)+"\n")
        env.write("ASCENSION_FRONTIER_AOT_COUNT=1\n")
    print("M7.23 accepted 1 authenticated owner-private PPC block; 25 words; target 0x003c511c; source SHA256 "+SOURCE_SHA256)
    print("M7.23 existing 1418 native entrypoints protected; expected total 1419 ARM64 AOT entries")
    return 0

if __name__=="__main__":
    try:sys.exit(main())
    except (ValueError,KeyError,UnicodeError,OSError) as exc:
        print("M7.23 signed private frontier staging rejected: "+str(exc),file=sys.stderr)
        sys.exit(1)
