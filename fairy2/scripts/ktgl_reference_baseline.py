#!/usr/bin/env python3
"""Read-only KTGL AArch64 reference parity gate. Never builds/changes an IPA.

The two v458752 resource reader paths are DISTINCT. A failed G1S first read
does not itself prove which path ran or an nn::os event ordering defect.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
from pathlib import Path

# Half-open guest main+ offsets, measured in original Fairy Tail 2 v458752.
CODE_REGIONS = (
    ("KTGL_archive_direct_entry", 0xC11800, 0xC11950),
    ("KTGL_archive_async_entry", 0xC10510, 0xC10668),
    ("KTGL_resource_factory", 0xC10690, 0xC109B0),
    ("KTGL_chunk_async_dispatch", 0xC10D80, 0xC10EE8),
    ("KTGL_chunk_direct_seek", 0xC119A0, 0xC11B50),
    ("KTGL_chunk_direct_read", 0xC11B60, 0xC11FC0),
    ("KTGL_chunk_inflate", 0xC0EF70, 0xC0F0F0),
    ("KTGL_reader_adapter", 0xC09718, 0xC09740),
    ("KTGL_G1T_native_parser", 0x6120E0, 0x612140),
    ("KTGL_G1S_native_parser", 0x6E7B60, 0x6E7C20),
)
# Build-specific AArch64 instructions, not replacement/patched opcodes.
WITNESSES = (
    (0xC10630, "18000094", "async-caller BL to common factory"),
    (0xC1191C, "ff7f01a9", "direct caller zeroes producer-option pair"),
    (0xC11924, "5bfbff97", "direct-caller BL to common factory"),
    (0xC09728, "000840f9080040f9041140f980001fd6",
     "adapter forwards read through backing virtual+0x20"),
)

def insist(ok: bool, msg: str):
    if not ok:
        raise ValueError("[KTGL original/AOT baseline] " + msg)

def sha(data: bytes):
    return hashlib.sha256(data).hexdigest()

def reconstruct_nso(nso: bytes) -> tuple[bytes, int]:
    """NSO0 text, ro, data with header bounds, compression flags and LZ4."""
    import lz4.block
    insist(len(nso) >= 0x100 and nso[:4] == b"NSO0", "expected NSO0")
    flags = struct.unpack_from("<I", nso, 0xC)[0]
    pieces = []
    for i, name in enumerate(("text", "ro", "data")):
        disk, mem, unpacked_len = struct.unpack_from("<III", nso, 0x10 + 16 * i)
        packed_len = struct.unpack_from("<I", nso, 0x60 + 4 * i)[0]
        insist(0 < unpacked_len < 512 * 1024 * 1024, f"{name} size invalid")
        insist(disk >= 0x100 and packed_len > 0 and disk + packed_len <= len(nso),
               f"{name} compressed bytes truncated")
        insist(mem < 1024 * 1024 * 1024 and mem + unpacked_len < 1024 * 1024 * 1024,
               f"{name} address out of bounds")
        part = nso[disk:disk + packed_len]
        if flags & (1 << i):
            try:
                data = lz4.block.decompress(part, uncompressed_size=unpacked_len)
            except (lz4.block.LZ4BlockError, ValueError) as exc:
                raise ValueError(f"{name} LZ4 decode failed: {exc}") from exc
        else:
            insist(len(part) == unpacked_len, f"{name} stored length mismatch")
            data = part
        insist(len(data) == unpacked_len, f"{name} inflated size mismatch")
        pieces.append((mem, data))
    insist(pieces[0][0] == 0, "main .text not at guest offset zero")
    image = bytearray(max(offset + len(data) for offset, data in pieces))
    for offset, data in pieces:
        image[offset:offset + len(data)] = data
    return bytes(image), len(pieces[0][1])

def branch_target(code: bytes, at: int) -> int:
    word = int.from_bytes(code[at:at + 4], "little")
    insist((word & 0xFC000000) == 0x94000000, f"expected BL at main+0x{at:x}")
    imm26 = word & 0x03FFFFFF
    if imm26 & 0x02000000:
        imm26 -= 0x04000000
    return at + (imm26 << 2)

def audit(original_nso: Path, rewritten_main: Path, profile: Path | None = None) -> dict:
    nso = original_nso.read_bytes()
    aot = rewritten_main.read_bytes()
    original, text_len = reconstruct_nso(nso)
    regions = []
    for name, first, end in CODE_REGIONS:
        insist(first < end <= text_len and first % 4 == end % 4 == 0,
               f"{name} outside original code region")
        insist(end <= len(aot), f"{name} outside AOT code")
        old, new = original[first:end], aot[first:end]
        bad = next((n for n in range(0, len(old), 4)
                    if old[n:n + 4] != new[n:n + 4]), None)
        if bad is not None:
            raise ValueError(f"[KTGL original/AOT baseline] {name}: "
                             f"rewriter changed main+0x{first + bad:x}")
        regions.append({"name": name, "start": f"main+0x{first:x}",
                        "end_exclusive": f"main+0x{end:x}", "bytes": end - first,
                        "source_sha256": sha(old), "aot_identical": True})
    for at, expected_hex, label in WITNESSES:
        expected = bytes.fromhex(expected_hex)
        insist(original[at:at + len(expected)] == expected, f"wrong source {label}")
        insist(aot[at:at + len(expected)] == expected, f"AOT changed {label}")
    insist(branch_target(original, 0xC10630) == 0xC10690,
           "async entry does not call common factory")
    insist(branch_target(original, 0xC11924) == 0xC10690,
           "direct entry does not call common factory")
    fields = None
    if profile is not None:
        cfg = {}
        for line in profile.read_text().splitlines():
            if not line or line.startswith("#"):
                continue
            entry = line.split("\t")
            if len(entry) >= 2:
                cfg[entry[0]] = entry[1]
        insist(cfg.get("title_id") == "0100B9801F872000", "wrong title in profile")
        insist(cfg.get("package") == "v458752", "profile version unsupported")
        insist(cfg.get("sys_resource") == "0x1000000", "profile NPDM VA unverified")
        fields = {k: cfg.get(k) for k in (
            "title_id", "package", "modules", "mem_reserve", "mem_alias",
            "app_pool", "sys_resource", "romfs_marker")}
    return {
        "title_id": "0100B9801F872000", "build": "v458752",
        "status": "read-only source parity; NOT a runtime/gameplay fix",
        "original_nso_sha256": sha(nso),
        "decompressed_original_sha256": sha(original),
        "rewritten_main_sha256": sha(aot),
        "original_code_verified_bytes": sum(x["bytes"] for x in regions),
        "critical_aarch64_regions": regions,
        "profile": fields,
        "references": [
            {"game": "Romance of the Three Kingdoms 8 Remake",
             "title_id": "0100C2A01A730000", "tested": "iPhone",
             "commonality": "modern KTGL RDB/FDATA with mode4 zlib blocks"},
            {"game": "Atelier Ryza DX", "title_id": "0100199023B2E000",
             "tested": "Mac, not iPhone", "commonality": "KTGL G1T/G1S and chunked zlib"},
            {"game": "Hyrule Warriors: Age of Calamity",
             "title_id": "01002B00111A2000", "tested": "iPhone",
             "commonality": "KTGL RDB and KIDS resource jobs"},
        ],
        "guest_paths": [
            {"caller": "main+0xc10630", "factory": "main+0xc10690",
             "kind": "event-driven", "producer": "main+0xc10d80"},
            {"caller": "main+0xc11924", "factory": "main+0xc10690",
             "kind": "direct/on-demand", "reader": "main+0xc11b60",
             "inflater": "main+0xc0ef70"},
        ],
        "unknown": "device log does not establish the failed G1T/G1S reader's backing vtable or which of two producers is responsible",
        "not_a_gameplay_fix": True, "shader_rebuild": False, "ipa_built": False,
    }

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original-nso", type=Path, required=True)
    p.add_argument("--patched-main", type=Path, required=True)
    p.add_argument("--profile", type=Path)
    p.add_argument("--report", type=Path, required=True)
    a = p.parse_args()
    data = audit(a.original_nso, a.patched_main, a.profile)
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print("KTGL SOURCE/AOT PARITY PASS:", data["original_code_verified_bytes"],
          "original AArch64 bytes intact in", len(data["critical_aarch64_regions"]),
          "path regions; report", a.report)

if __name__ == "__main__":
    main()
