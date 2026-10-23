#!/usr/bin/env python3
"""Verify and unpack the owner-provided PS3Recomp lift bundle for M7.72 CI."""
import argparse
import hashlib
import json
import pathlib
import re
import zipfile

PARTS = [
    ("AscensionRecomp-PS3Recomp-Lift.zip.part00", "5c150c6557cf639ccd583fd351e3425ac67781fb142ab7edec713e5a15a2158a"),
    ("AscensionRecomp-PS3Recomp-Lift.zip.part01", "f82ac92b11b542be41720d129377b6655586293be9d3d6ee05d382fdde317167"),
    ("AscensionRecomp-PS3Recomp-Lift.zip.part02", "36a922021e51140983bd057cb0320f685b2f530be05f0d11f0291384a5b4129e"),
]
ZIP_SHA256 = "0ff6e0a8ae608c23a5b66400813681c563b002d008f273feac324e4013e5865e"
ZIP_BYTES = 243404277
ROOT_NAME = "AscensionRecomp-PS3Recomp-Lift"
PPU_ENTRY = re.compile(
    r"^void\s+func_([0-9A-Fa-f]{8})\s*\(ppu_context\*\s*ctx\)\s*\{",
    re.MULTILINE,
)


def instrument_known_waitloop(source):
    """Sample the exact usleep(30) PPU wait loop identified by M7.96."""
    wait_entry = "void func_00419AC8(ppu_context* ctx) {"
    wait_matches = []
    for path in sorted((source / "ppu").glob("ppu_recomp_*.cpp")):
        text = path.read_text()
        if wait_entry in text:
            wait_matches.append((path, text))
    if len(wait_matches) != 1:
        raise SystemExit(
            f"M8.03 expected one AOT unit for func_00419AC8, found {len(wait_matches)}"
        )
    wait_unit, wait_text = wait_matches[0]
    wait_start = wait_text.find(wait_entry)
    wait_end = wait_text.find("\nvoid func_", wait_start + 1)
    if wait_start < 0 or wait_end < 0:
        raise SystemExit("M8.03 cannot isolate func_00419AC8")
    wait_body = wait_text[wait_start:wait_end]
    wait_anchor = "loc_00419D1C:\n"
    hook = "        ar_m772_note_hotloop(0x00419D1Cu, ctx);\n"
    if hook in wait_body:
        if wait_body.count(hook) != 1:
            raise SystemExit("M8.03 duplicated the func_00419AC8 wait-loop probe")
        return 1
    if wait_body.count(wait_anchor) != 1:
        raise SystemExit("M8.03 known usleep(30) wait-loop backedge changed")
    wait_body = wait_body.replace(wait_anchor, wait_anchor + hook, 1)
    wait_unit.write_text(wait_text[:wait_start] + wait_body + wait_text[wait_end:])
    return 1


def instrument_aot_entries(source):
    """Add a cheap, truthful entry hook to every complete lifted PPU function."""
    header = source / "ppu" / "ppu_recomp.h"
    text = header.read_text()
    anchor = "} ppu_context;\n"
    declaration = anchor + (
        "#ifdef __cplusplus\n"
        'extern "C" void ar_m772_note_function(uint32_t guest_pc, ppu_context* ctx);\n'
        'extern "C" void ar_m772_note_hotloop(uint32_t guest_pc, ppu_context* ctx);\n'
        "#endif\n"
    )
    if text.count(anchor) != 1:
        raise SystemExit("M7.75 cannot place the native AOT context telemetry declaration")
    header.write_text(text.replace(anchor, declaration, 1))

    count = 0
    for path in sorted((source / "ppu").glob("ppu_recomp_*.cpp")):
        if path.name == "ppu_recomp_table.cpp":
            continue
        text = path.read_text()

        def add_hook(match):
            nonlocal count
            count += 1
            pc = match.group(1).upper()
            return match.group(0) + f"\n    ar_m772_note_function(0x{pc}u, ctx);"

        path.write_text(PPU_ENTRY.sub(add_hook, text))
    if count != 29849:
        raise SystemExit(f"M7.75 native AOT telemetry count mismatch: {count} != 29849")

    # The M7.74 device capture remained inside this title's tree-search loop.
    # Record its changing pointers without changing guest registers or control flow.
    loop_unit = source / "ppu" / "ppu_recomp_058.cpp"
    loop_text = loop_unit.read_text()
    start = loop_text.find("void func_003C4F98(ppu_context* ctx) {")
    end = loop_text.find("\nvoid func_", start + 1)
    if start < 0 or end < 0:
        raise SystemExit("M7.75 could not locate the observed 0x003C4F98 guest loop")
    loop_body = loop_text[start:end]
    loop_anchor = "loc_003C4FA4:\n"
    if loop_body.count(loop_anchor) != 1:
        raise SystemExit("M7.75 observed guest loop header changed")
    loop_body = loop_body.replace(
        loop_anchor,
        loop_anchor + "        ar_m772_note_hotloop(0x003C4FA4u, ctx);\n",
        1,
    )
    loop_unit.write_text(loop_text[:start] + loop_body + loop_text[end:])

    # M8.03: sample the known PPU wait loop from M7.96 at its exact backedge.
    # The last HLE/LV2 event showed sys_timer_usleep(30), but earlier reports
    # could not tell whether this loop still dominated execution afterward.
    instrument_known_waitloop(source)
    return count


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parts", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--upstream", type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    archive = args.output / "lift.zip"
    with archive.open("wb") as dest:
        for name, expected in PARTS:
            part = args.parts / name
            if sha256(part) != expected:
                raise SystemExit(f"M7.72 source shard SHA-256 mismatch: {name}")
            with part.open("rb") as src:
                for block in iter(lambda: src.read(8 << 20), b""):
                    dest.write(block)
    if archive.stat().st_size != ZIP_BYTES or sha256(archive) != ZIP_SHA256:
        raise SystemExit("M7.72 source archive size/SHA-256 mismatch")

    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        if len(names) != 680 or len(set(names)) != len(names):
            raise SystemExit("M7.72 source ZIP inventory count mismatch")
        root = pathlib.PurePosixPath(ROOT_NAME)
        for name in names:
            path = pathlib.PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or path.parts[0] != ROOT_NAME:
                raise SystemExit(f"unsafe M7.72 source path: {name}")
            if name.lower().endswith((".elf", ".self", ".sprx", ".rap", ".pkg")):
                raise SystemExit(f"original game executable/content must not be staged: {name}")
        if bundle.testzip() is not None:
            raise SystemExit("M7.72 source ZIP CRC failed")
        bundle.extractall(args.output)

    source = args.output / ROOT_NAME
    ppu = sorted(source.joinpath("ppu").glob("ppu_recomp_*.cpp"))
    spu = sorted(source.joinpath("spu").glob("*/spu_recomp.c"))
    table = source / "ppu" / "ppu_recomp_table.cpp"
    if len(ppu) != 651 or not table.is_file() or len(spu) != 4:
        raise SystemExit(f"M7.72 source inventory mismatch: PPU={len(ppu)} SPU={len(spu)}")
    text = table.read_text(errors="replace")
    if ("function_table_count = 29849" not in text or
            "func_00010410" not in text or "func_0052A740" not in text or
            "func_0052E3F4" not in text):
        raise SystemExit("M7.72 PPU frontier/table checks failed")
    instrumented = instrument_aot_entries(source)
    (source / "runtime").symlink_to((args.upstream / "runtime").resolve())
    result = {
        "schema": "ascension-m772-source-preflight-v1",
        "zip_sha256": ZIP_SHA256,
        "zip_bytes": ZIP_BYTES,
        "ppu_translation_units_including_table": len(ppu),
        "ppu_function_table_entries": 29849,
        "native_aot_function_entry_hooks": instrumented,
        "native_observed_hotloop_hooks": 2,
        "frontier_0052a740_present": True,
        "frontier_callee_0052e3f4_present": True,
        "spu_translation_units": len(spu),
        "original_elf_in_repo": False,
        "ios_compiled": False,
        "ipa_linked": False,
        "device_executed": "NOT_MEASURED",
    }
    (args.output / "m772-source-preflight.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
