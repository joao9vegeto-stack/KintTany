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
import re
from pathlib import Path
import sys

EXPECTED_SHA256 = "99c05272eddd827878983ddf6b3c85628ba04e027fded93d1c1dc26956c19a77"
ENTRY_PCS = (
    0x00010200, 0x00010380, 0x00010410, 0x00010434, 0x00010444, 0x00010534, 0x000107a4, 0x00010814, 0x002c1024, 0x002c10c8, 0x002c10d0, 0x002c10e4, 0x002c1104, 0x002c1114, 0x002c1124, 0x002c1148, 0x002c1154, 0x002c1168, 0x002c1174, 0x002c118c, 0x002c11b4, 0x002c11c0, 0x002c11d4, 0x002c11e8, 0x002c1200, 0x002c1214, 0x002c1564, 0x002c1570, 0x002c15e4, 0x002c15f4, 0x002c164c, 0x003678ec, 0x003a4c1c, 0x003a4c38, 0x00455a10, 0x00455eac, 0x00455f9c, 0x00455fa4, 0x00455fb8, 0x005232b0, 0x00523318, 0x00523350, 0x00523360, 0x00523390, 0x00523428, 0x00525c00, 0x0052a710, 0x0052a78c, 0x0052a7bc, 0x0052e118, 0x0052e180, 0x0052e3b0, 0x0052e3f4, 0x0052e4f0, 0x0052e544, 0x00531a74, 0x00531cac, 0x00539998, 0x00539a50
)
EXPECTED_SYMBOLS = tuple(f"ar_game_ppu_{pc:08x}" for pc in ENTRY_PCS)
OWNER_ELF_SHA256 = "4bf75c897b82d1beb25514cbadaff3d03e1b0c7bf849fa5d289be4f9183462b5"
M712_NEXT_PC = "ar_game_ppu_002c1664"
M712_MAX_SOURCE = 4 * 1024 * 1024


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
        raise ValueError("AOT source SHA256 mismatched M7.11")
    for symbol in (*EXPECTED_SYMBOLS,"ar_private_aot_install_sha256"):
        if symbol.encode("ascii") not in source:
            raise ValueError("AOT required entry missing: "+symbol)
    return source



def decode_owner_m712(value: str) -> tuple[bytes, list[str], str]:
    """Stage revised owned AOT, not the previous fixed-size M7.11 blob.

    Source is trusted ONLY as an owner-supplied Actions secret, not from git.
    ELF identity, all earlier guest entrypoints and the real missing PC are
    independently enforced, and all symbols must later exist in final Mach-O.
    """
    if not value or len(value) > 48000:
        raise ValueError("M7.12 owner AOT secret absent or unreasonably large")
    try:
        compressed = base64.b64decode(value.strip(), validate=True)
    except (ValueError, binascii.Error) as err:
        raise ValueError("M7.12 AOT secret is not strict base64") from err
    if not compressed or len(compressed) > 36000:
        raise ValueError("M7.12 AOT compressed size rejected")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as stream:
            source = stream.read(M712_MAX_SOURCE + 1)
    except (OSError, EOFError) as err:
        raise ValueError("M7.12 AOT gzip corrupt") from err
    if len(source) > M712_MAX_SOURCE:
        raise ValueError("M7.12 AOT decompressed bytes exceed bound")
    if b"\x00" in source:
        raise ValueError("M7.12 AOT source is not plain text")
    # This SHA is the authenticated original user ELF, NOT merely the
    # arbitrary checksum of a new Actions secret.
    elf_match = re.search(
        rb"ar_source_sha256\s*\[\s*32\s*\]\s*=\s*\{([^}]+)\}", source)
    if not elf_match:
        raise ValueError("M7.12 AOT ELF identity missing")
    octets = re.findall(rb"0x([0-9a-fA-F]{1,2})\b", elf_match.group(1))
    if len(octets) != 32 or bytes(int(x, 16) for x in octets).hex() != OWNER_ELF_SHA256:
        raise ValueError("M7.12 AOT original NPUA80918 ELF SHA256 mismatched")
    if b"ar_private_aot_install_sha256" not in source:
        raise ValueError("M7.12 AOT authenticated installer missing")
    names = sorted(set(x.decode("ascii") for x in re.findall(
        rb"\bar_game_ppu_[0-9a-f]{8}\b", source)))
    required = set(EXPECTED_SYMBOLS) | {M712_NEXT_PC}
    missing = required.difference(names)
    if missing:
        raise ValueError("M7.12 required native game entries missing: " + ", ".join(sorted(missing)[:8]))
    if len(names) <= len(EXPECTED_SYMBOLS) or len(names) > 8192:
        raise ValueError("M7.12 game AOT symbol count rejected")
    digest = hashlib.sha256(source).hexdigest()
    return source, names, digest


def main() -> int:
    source, symbols, source_sha256 = decode_owner_m712(
        os.environ.get("ASCENSION_AOT_SOURCE_GZIP_B64", ""))
    runner_temp = Path(os.environ["RUNNER_TEMP"]).resolve()
    if not runner_temp.is_dir():
        raise ValueError("RUNNER_TEMP unavailable")
    out = runner_temp / "ascension_m712_owner_aot.c"
    out.write_bytes(source)
    out.chmod(0o600)
    index = runner_temp / "ascension_m712_symbol_manifest.txt"
    index.write_text("\n".join(symbols) + "\n", encoding="ascii")
    with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as stream:
        stream.write("ASCENSION_PRIVATE_AOT_C=" + str(out) + "\n")
        stream.write("ASCENSION_AOT_SYMBOL_LIST=" + str(index) + "\n")
        stream.write("ASCENSION_AOT_EXPECTED_SYMBOL_COUNT=" + str(len(symbols)) + "\n")
        stream.write("ASCENSION_AOT_SOURCE_SHA256=" + source_sha256 + "\n")
    print(f"M7.12 owner AOT ELF SHA256 verified; {len(symbols)} real native entries staged; source SHA256={source_sha256}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError,KeyError) as exc:
        print("M7.12 native AOT staging failed: "+str(exc),file=sys.stderr)
        sys.exit(1)
