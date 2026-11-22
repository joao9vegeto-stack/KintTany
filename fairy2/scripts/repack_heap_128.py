#!/usr/bin/env python3
"""Fairy Tail 2: guarded 20 MiB -> 128 MiB SetMemoryHeapSize patch on completed IPA.

One guest MOVZ change. Both the host and Metal shaders remain EXACTLY as built.
Hypothesis under test: the 20 MiB heap request is constraining a 32 MiB KTGL
allocation. Only an iPhone runtime test can establish that relationship.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from repack_region_cut import (
    TITLE, FRAMEWORK, APP, require, checksum, run, locate, macho_text_sha,
    embedded_main, validate_settings, SITES,
)

SOURCE_RUN = 44980090949
SOURCE_SHA = "42f2895219c938f40d3b26967abfa1ef4d685e6e694c87dbb95ae5f023e2bb74"
SOURCE_NAME = "Fairy2iOS-FairyTail2-3GiB-region-cut.ipa"
OUTPUT_NAME = "Fairy2iOS-FairyTail2-128MiB-heap-repack.ipa"
HEAP_SITE = 0x2295A88
OLD_HEAP_BYTES = 0x1400000
NEW_HEAP_BYTES = 0x8000000
OLD_MOV = bytes.fromhex("1328a052")
NEW_MOV = bytes.fromhex("1300a152")
FINGERPRINT = "9bcd054c6b3be4a714fab870db64ea895c5ff9f99cae0ddfa5b5b2763f526a91"
EXPECTED_METAL_SHA = "ab35b0ef89c907a38c8462da78ba6864153c86f8c203d613b321d45ce0aa262b"

def patch_heap_bytes(guest: bytes):
    """No heuristic search, no NOP of a failed allocator; fail closed."""
    require(HEAP_SITE + 40 <= len(guest), "guest main too short for requested patch")
    require(guest[HEAP_SITE:HEAP_SITE + 4] == OLD_MOV,
            "heap size instruction differs from v458752: refusing blind patch")
    require(hashlib.sha256(guest[HEAP_SITE - 24:HEAP_SITE + 40]).hexdigest() == FINGERPRINT,
            "heap startup function fingerprint mismatch: refusing blind patch")
    for site, before, after, fp in SITES:
        require(guest[site:site + 4] == bytes.fromhex(after),
                f"prior verified 3 GiB region patch missing at main+0x{site:x}")
    altered = bytearray(guest)
    altered[HEAP_SITE:HEAP_SITE + 4] = NEW_MOV
    require(sum(a != b for a, b in zip(guest, altered)) == 2,
            "guest code change exceeds permitted two bytes")
    return bytes(altered)

def patch_framework(framework: Path):
    offset, guest = embedded_main(framework)
    altered = patch_heap_bytes(guest)
    before = hashlib.sha256(guest).hexdigest()
    after = hashlib.sha256(altered).hexdigest()
    with framework.open("r+b") as fd:
        fd.seek(offset)
        require(fd.read(len(guest)) == guest, "embedded main changed while patching")
        fd.seek(offset)
        fd.write(altered)
    return {"original_section_sha256": before, "patched_section_sha256": after,
            "section_size": len(guest), "byte_changes": 2,
            "offset": f"main+0x{HEAP_SITE:x}", "old_opcode": OLD_MOV.hex(),
            "new_opcode": NEW_MOV.hex()}

def check_framework(framework: Path, proof: dict):
    _, guest = embedded_main(framework)
    require(len(guest) == proof["section_size"] and
            hashlib.sha256(guest).hexdigest() == proof["patched_section_sha256"],
            "guest code differs from the single approved heap patch")
    require(guest[HEAP_SITE:HEAP_SITE + 4] == NEW_MOV, "heap instruction reverted")
    for site, _, after, _ in SITES:
        require(guest[site:site + 4] == bytes.fromhex(after),
                "previous 3 GiB reservation cut lost")
    return True

def validate_source(ipa: Path):
    require(ipa.name == SOURCE_NAME and ipa.is_file(), "required 3 GiB IPA not selected")
    require(checksum(ipa) == SOURCE_SHA, "last successful region-cut IPA SHA mismatch")
    details = locate(ipa)
    require(sorted(details["manifest"].get("modules", [])) == ["main", "sdk", "subsdk1"],
            "unexpected guest module inventory")
    with zipfile.ZipFile(ipa) as z:
        path = "Payload/" + APP + "/Frameworks/" + FRAMEWORK + "/"
        cfg = json.loads(z.read(path + "dm/launcher.json"))
        validate_settings(cfg)
        profile = z.read(path + "profile.tsv").decode("utf-8")
        require("mem_reserve\t0x140000000" in profile and
                "mem_alias\t0xe0000000" in profile,
                "source IPA has unexpected host memory profile")
    return details

def make(source: Path, output: Path, report: Path):
    validate_source(source)
    require(source.resolve() != output.resolve(), "source and output collide")
    output.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="fairy2-heap-only-") as temp:
        stage = Path(temp)
        run("ditto", "-x", "-k", source, stage)
        app = stage / "Payload" / APP
        fw = app / "Frameworks" / FRAMEWORK
        game = fw / ("DmGame" + TITLE)
        shell = app / "DmShell"
        metal = fw / "msl" / "b-0724088d3779.img"
        shmap = fw / "dm" / "shader_map.tsv"
        launcher = fw / "dm" / "launcher.json"
        require(all(p.is_file() for p in [game, shell, metal, shmap, launcher]),
                "original IPA incompletely extracted")
        require(checksum(metal) == EXPECTED_METAL_SHA,
                "compiled Metal library differs from original")
        shader_map_sha = checksum(shmap)
        launcher_sha = checksum(launcher)
        shell_text_sha = macho_text_sha(shell)
        host_text_sha = macho_text_sha(game)
        proof = patch_framework(game)
        run("xattr", "-cr", fw)
        run("codesign", "--force", "--sign", "-", "--timestamp=none", fw)
        run("xattr", "-cr", app)
        run("codesign", "--force", "--sign", "-", "--preserve-metadata=entitlements",
            "--timestamp=none", app)
        run("codesign", "--verify", "--deep", "--strict", app)
        check_framework(game, proof)
        require(macho_text_sha(game) == host_text_sha,
                "host __TEXT,__text changed beyond its separately embedded guest")
        require(macho_text_sha(shell) == shell_text_sha,
                "re-signing changed shell executable code")
        require(checksum(metal) == EXPECTED_METAL_SHA and checksum(shmap) == shader_map_sha,
                "shaders or shader map changed")
        require(checksum(launcher) == launcher_sha,
                "30/60 FPS or A/B launcher configuration changed")

        # Keep the proven outer IPA packing method from region-cut / HookLink.
        run("ditto", "-c", "-k", "--keepParent", stage / "Payload", output)
        with zipfile.ZipFile(output) as z:
            path = "Payload/" + APP + "/Frameworks/" + FRAMEWORK + "/"
            require(z.testzip() is None, "new IPA ZIP CRC error")
            validate_settings(json.loads(z.read(path + "dm/launcher.json")))
            tmp_game = stage / "verification-embedded-game"
            with z.open(path + "DmGame" + TITLE) as inp, tmp_game.open("wb") as out:
                shutil.copyfileobj(inp, out, 8 * 1024 * 1024)
            check_framework(tmp_game, proof)
            require(z.getinfo(path + "msl/b-0724088d3779.img").file_size == metal.stat().st_size,
                    "new IPA Metal library length mismatch")
        result = {
            "project": "Fairy2iOS", "title_id": TITLE,
            "source_run_id": SOURCE_RUN, "source_ipa_sha256": SOURCE_SHA,
            "output_ipa": output.name, "output_size_bytes": output.stat().st_size,
            "output_sha256": checksum(output),
            "method": "existing IPA: one fingerprinted SetMemoryHeapSize MOVZ change",
            "heap_before_bytes": OLD_HEAP_BYTES, "heap_after_bytes": NEW_HEAP_BYTES,
            "heap_instruction_audit": proof,
            "five_region_cut_movs_preserved": True,
            "native_host_recompiled": False, "guest_modules_rewritten": False,
            "game_shaders_recompiled": False,
            "game_shader_sha256": EXPECTED_METAL_SHA, "shader_map_sha256": shader_map_sha,
            "original_launcher_sha256": launcher_sha,
            "romfs_aoc_external_unchanged": True,
            "fps_options": [30, 60], "pad_ab_swap_preserved": True,
            "runtime_32mib_allocator_fix_verified": False,
            "crash_fixed_on_iphone_verified": False,
        }
        report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print("[Fairy2iOS] Signed single-instruction heap repack:", result["output_sha256"],
              "IPA bytes", result["output_size_bytes"], flush=True)
        return result

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    a = p.parse_args()
    make(a.source, a.output, a.report)
