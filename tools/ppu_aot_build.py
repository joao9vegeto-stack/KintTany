#!/usr/bin/env python3
"""Build a PRIVATE signed-link-ready PPU AOT C module from an owned PPC64 ELF.

Runs outside public CI for a commercial title. Public CI uses synthetic ELF.
A generated source file is commercial-game-derived material: NEVER commit it.
This is a strict *subset* lifter; candidates are not proof of whole-game correctness.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from ppu_cfg_lifter import PPUImage, Unsupported, PROLOGUE, lift

MAX_FUNCS = 8192

def parse_number(v):
    return int(v, 0) if isinstance(v, str) else int(v)

def build(elf: Path, functions: Path, output_dir: Path, require_entry: int | None = None):
    raw = elf.read_bytes()
    image = PPUImage(elf)
    items = json.loads(functions.read_text())
    if not isinstance(items, list) or not items:
        raise ValueError("functions JSON must be a nonempty list")
    if len(items) > 100000:
        raise ValueError("function manifest is unbounded")
    seen = set()
    accepted, rejected, bodies = [], [], []
    for f in items:
        start, end = parse_number(f["start"]), parse_number(f["end"])
        if start in seen:
            raise ValueError(f"duplicate PPU function entry: 0x{start:x}")
        seen.add(start)
        if start == 0 or start > 0xffffffff or end > 0x100000000:
            rejected.append({"start": hex(start), "reason": "invalid 32-bit entry"})
            continue
        try:
            words = image.words(start, end)
            c_src, counts = lift(words, start, f"ar_game_ppu_{start:08x}")
            if not c_src.startswith(PROLOGUE):
                raise ValueError("lifter prologue contract changed")
            bodies.append(c_src[len(PROLOGUE):])
            accepted.append({"start": hex(start), "end": hex(end),
                             "instructions": len(words), "opcodes": counts})
        except Unsupported as error:
            rejected.append({"start": hex(start), "reason": str(error)})
    if not accepted or len(accepted) > MAX_FUNCS:
        raise ValueError(f"no usable native PPU functions or >{MAX_FUNCS} functions")
    if require_entry is not None and require_entry not in {
            int(f["start"], 0) for f in accepted}:
        raise ValueError(f"required entry 0x{require_entry:x} was not translated")
    digest = hashlib.sha256(raw).digest()
    digest_c = ", ".join(f"0x{x:02x}" for x in digest)
    registrations = "\n".join(
        f"    if ((rc=ar_register(0x{int(f['start'],0):08x}u,"
        f" ar_game_ppu_{int(f['start'],0):08x})) != AR_OK) return rc;"
        for f in accepted
    )
    final = (
        "/* PRIVATE PPC64-to-ARM64 AOT translation, not an interpreter.\n"
        " * No commercial-derived output may be committed to a public repo.\n"
        " * Link before signing the iOS application.\n"
        " */\n"
        "#include <stddef.h>\n#include <string.h>\n"
        "#include \"ppu_bridge.h\"\n" + PROLOGUE + "\n".join(bodies) +
        "\nstatic const unsigned char ar_source_sha256[32] = {"
        + digest_c + "};\n"
        "int ar_private_aot_install_sha256(const unsigned char *digest, size_t size) {\n"
        "    if (!digest || size != 32 || memcmp(digest, ar_source_sha256, 32))"
        " return AR_BAD_ARGS;\n"
        "    int rc = AR_OK;\n" + registrations + "\n"
        "    return AR_OK;\n}\n"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "ascension_private_aot.c").write_text(final)
    report = {
        "schema": "ascension-recomp/private-aot-v1",
        "source_sha256": digest.hex(), "source_size": len(raw),
        "candidates": len(items), "generated_functions": len(accepted),
        "rejected_functions": len(rejected), "accepted": accepted,
        "rejected": rejected,
        "warning": "AOT candidates only. Coverage and correct gameplay NOT established."
    }
    (output_dir / "aot-manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    return report

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--elf", required=True, type=Path)
    p.add_argument("--functions", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--require-entry", type=lambda s: int(s,0), default=None)
    a = p.parse_args()
    report = build(a.elf, a.functions, a.output_dir, a.require_entry)
    print(f"private native AOT candidates: {report['generated_functions']}"
          f"/{report['candidates']}; rejected={report['rejected_functions']}")
if __name__ == "__main__":
    main()
