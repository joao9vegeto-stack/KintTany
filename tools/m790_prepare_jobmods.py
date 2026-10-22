#!/usr/bin/env python3
"""Safely extract the title's WWS overlays and lift them for the iOS archive.

The encrypted SELF and RAP are inspected in memory only. Only the already
provided ELF is written into RUNNER_TEMP, and it is removed after lifting.
Generated translated code stays in the temporary build directory; none of the
input binaries or raw SPU modules are copied into the repository or IPA bundle.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile


GOWA_PC_COMMIT = "45840d709a4e48a1d12d0803e323ba5c8568ab2a"
PS3RECOMP_COMMIT = "f6ab60baf37662bd712592b7ef9f66891972a5fc"
EXPECTED_TITLE = "UP9000-NPUA80918"
EXPECTED_MODULES = 31
MAX_ELF_BYTES = 32 * 1024 * 1024
NPUA_CODE_ENDS = {
    "jobmod_00749080_eC40": 0x4F20,
    "jobmod_0078B380_e7B40": 0xBF08,
    "jobmod_007AAE00_eAF80": 0x148F0,
    "jobmod_007BFC80_e16A80": 0x20570,
    "jobmod_007E1C00_e11A08": 0x1B770,
    "jobmod_007FF280_eE430": 0x17650,
    "jobmod_0084BE40_e9DA8": 0xE310,
}
NPUA_DATA_RANGES = {
    "jobmod_00818600_eA00": [(0x83A0, 0x8A48)],
}


def git_head(path: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
    ).strip()


def elf_dimensions(data: bytes) -> tuple[int, int, int, int, int]:
    if len(data) < 64 or data[:4] != b"\x7fELF":
        raise SystemExit("GOWA.ELF does not have an ELF64 header")
    if data[4:6] != b"\x02\x02":
        raise SystemExit("GOWA.ELF must be ELF64 big-endian")
    machine = struct.unpack_from(">H", data, 18)[0]
    if machine != 21:
        raise SystemExit(f"GOWA.ELF has unexpected e_machine {machine}")
    phoff, shoff = struct.unpack_from(">QQ", data, 32)
    phentsize, phnum, shentsize, shnum = struct.unpack_from(">4H", data, 54)
    if phentsize != 56 or phnum == 0 or shentsize != 64 or shnum == 0:
        raise SystemExit("GOWA.ELF has invalid PowerPC64 table dimensions")
    if phoff + phentsize * phnum > len(data) or shoff + shentsize * shnum > len(data):
        raise SystemExit("GOWA.ELF header tables extend beyond the file")
    return phoff, phnum, phentsize, shoff, shnum


def verify_self_pair(elf: bytes, self_data: bytes) -> None:
    if len(self_data) < 0x70 or self_data[:4] != b"SCE\x00":
        raise SystemExit("GOWA.SELF is missing the retail SELF header")
    _, _, key_revision, header_type, _, _, declared_elf_size = struct.unpack_from(
        ">4sIHHIQQ", self_data, 0
    )
    if header_type != 1 or key_revision != 0x1C:
        raise SystemExit("GOWA.SELF is not the expected retail SELF revision")
    (_, app_info_off, embedded_elf_off, phdr_off, shdr_off, _, _, control_off,
     control_size, _) = struct.unpack_from(">10Q", self_data, 0x20)
    if declared_elf_size != len(elf):
        raise SystemExit("GOWA.ELF length differs from the SELF-declared ELF size")
    if self_data[embedded_elf_off:embedded_elf_off + 64] != elf[:64]:
        raise SystemExit("GOWA.ELF header differs from the SELF's embedded ELF header")

    phoff, phnum, phentsize, shoff, shnum = elf_dimensions(elf)
    phbytes = phnum * phentsize
    shentsize = struct.unpack_from(">H", elf, 58)[0]
    shbytes = shnum * shentsize
    if (elf[phoff:phoff + phbytes] != self_data[phdr_off:phdr_off + phbytes] or
            elf[shoff:shoff + shbytes] != self_data[shdr_off:shdr_off + shbytes]):
        raise SystemExit("GOWA.ELF program/section headers differ from the SELF")

    control = self_data[control_off:control_off + control_size]
    npd = control.find(b"NPD\x00")
    if npd < 0:
        raise SystemExit("GOWA.SELF has no NPDRM title metadata")
    license_type = struct.unpack_from(">I", control, npd + 8)[0]
    title_id = control[npd + 0x10:npd + 0x20].decode("ascii", "replace")
    if title_id != EXPECTED_TITLE or license_type != 2:
        raise SystemExit("GOWA.SELF title/license metadata does not match the NPUA digital dump")
    if app_info_off + 0x18 > len(self_data):
        raise SystemExit("GOWA.SELF app-info block is out of bounds")
    print("SELF/ELF verification: title NPUA80918; ELF header and both ELF tables match")


def extract_elf_from_archive(archive: Path, target: Path) -> None:
    with ZipFile(archive) as zf:
        names = [item.filename for item in zf.infolist()]
        if names.count("GOWA.ELF") != 1 or names.count("GOWA.SELF") != 1:
            raise SystemExit("Arq.zip must contain one GOWA.ELF and one GOWA.SELF")
        elf_info = zf.getinfo("GOWA.ELF")
        self_info = zf.getinfo("GOWA.SELF")
        if elf_info.file_size > MAX_ELF_BYTES or self_info.file_size > MAX_ELF_BYTES:
            raise SystemExit("Arq.zip ELF/SELF member exceeds the 32 MiB safety limit")
        elf = zf.read(elf_info)
        self_data = zf.read(self_info)
    verify_self_pair(elf, self_data)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(elf)
    target.chmod(0o600)
    print("The RAP was left unread and was not extracted.")


def patch_pinned_lifter(ps3recomp: Path, raw_modules: Path) -> None:
    """Apply source-verified data boundaries to the pinned Ascension lifter."""
    sys.path.insert(0, str(ps3recomp / "tools"))
    from spu_disasm import disassemble_spu
    from find_spu_functions import detect_functions
    from wrap_spu_elf import wrap

    branch_mnemonics = {"br", "bra", "brz", "brnz", "brhz", "brhnz",
                        "brsl", "brasl", "bisl", "bisled"}

    verified: list[tuple[str, int]] = []
    for name, end_pc in NPUA_CODE_ENDS.items():
        raw_path = raw_modules / f"{name}.bin"
        if not raw_path.is_file():
            raise SystemExit(f"code-end evidence module is missing: {name}")
        raw = raw_path.read_bytes()
        end_off = end_pc - 0x4000
        if end_off < 4 or end_off + 16 > len(raw):
            raise SystemExit(f"code-end evidence address is out of range: {name}")
        instructions = {item.addr: item for item in disassemble_spu(raw, base_addr=0x4000)}
        previous = instructions.get(end_pc - 4)
        first_words = raw[end_off:end_off + 16]
        if name == "jobmod_0084BE40_e9DA8":
            marker = bytes.fromhex("00808080018080800280808003808080")
            if (previous is None or previous.mnemonic != "stop" or
                    previous.operands != "0x0" or raw[end_off:end_off + len(marker)] != marker):
                raise SystemExit(f"{name} constant-tail boundary evidence changed")
        elif name == "jobmod_00749080_eC40":
            recent = [instructions.get(pc) for pc in range(end_pc - 16, end_pc, 4)]
            bi_index = next((i for i, item in enumerate(recent)
                             if item is not None and item.mnemonic == "bi" and
                             item.operands == "$r0"), -1)
            if bi_index < 0 or any(item is None or item.mnemonic not in {"lnop", "stop"}
                                   for item in recent[bi_index + 1:]):
                raise SystemExit(f"{name} no longer returns before its ANSI debug-string tail")
            if not first_words.startswith(b"\x1b[41mASSERT: "):
                raise SystemExit(f"{name} no longer begins its ANSI debug-string tail")
        else:
            if previous is None or previous.mnemonic != "bi" or previous.operands != "$r0":
                raise SystemExit(f"{name} no longer ends executable code with bi $r0")
            if name == "jobmod_0078B380_e7B40":
                if first_words != bytes.fromhex("00000000000000000405060780808080"):
                    raise SystemExit(f"{name} constant-tail signature changed")
            elif not all(byte == 0 or byte in (9, 10, 13) or 32 <= byte < 127
                         for byte in first_words):
                raise SystemExit(f"{name} code-end no longer starts in embedded printable data")
        for instruction in instructions.values():
            if instruction.addr >= end_pc or instruction.mnemonic not in branch_mnemonics:
                continue
            for operand in instruction.operands.split(","):
                operand = operand.strip()
                if not operand.startswith("0x"):
                    continue
                try:
                    target = int(operand, 16)
                except ValueError:
                    continue
                if end_pc <= target < 0x4000 + len(raw):
                    raise SystemExit(
                        f"{name} branch at 0x{instruction.addr:X} targets data tail 0x{target:X}")
        verified.append((name, end_pc))

    verified_ranges: list[tuple[str, int, int]] = []
    for name, ranges in NPUA_DATA_RANGES.items():
        raw_path = raw_modules / f"{name}.bin"
        if not raw_path.is_file():
            raise SystemExit(f"code/data-island evidence module is missing: {name}")
        raw = raw_path.read_bytes()
        instructions = disassemble_spu(raw, base_addr=0x4000)
        for start, end in ranges:
            if not (0x4000 < start < end < 0x4000 + len(raw)):
                raise SystemExit(f"{name} code/data-island range is out of bounds")
            previous = next((item for item in instructions if item.addr == start - 4), None)
            if previous is None or previous.mnemonic != "bi" or previous.operands != "$r0":
                raise SystemExit(f"{name} string island no longer follows bi $r0")
            island = raw[start - 0x4000:end - 0x4000]
            if not all(byte == 0 or byte in (9, 10, 13) or 32 <= byte < 127 for byte in island):
                raise SystemExit(f"{name} embedded string-island bytes changed")
            for instruction in instructions:
                if start <= instruction.addr < end or instruction.mnemonic not in branch_mnemonics:
                    continue
                for operand in instruction.operands.split(","):
                    operand = operand.strip()
                    if operand.startswith("0x"):
                        try:
                            target = int(operand, 16)
                        except ValueError:
                            continue
                        if start <= target < end:
                            raise SystemExit(
                                f"{name} branch at 0x{instruction.addr:X} targets string data 0x{target:X}")
            elf = wrap(raw, base=0x4000,
                       entry=0x4000 + struct.unpack_from(">I", raw, 0x10)[0])
            functions, _ = detect_functions(elf)
            if any(function_start < start < function_end for function_start, function_end in functions):
                raise SystemExit(f"{name} detected function crosses into its embedded string island")
            verified_ranges.append((name, start, end))

    lifter = ps3recomp / "tools/lift_jobmods.py"
    source = lifter.read_text()
    marker = "# ASCENSION_M790_NPUA_DATA_TAILS_V1"
    if marker not in source:
        anchor = "CODE_END = {\n"
        if source.count(anchor) != 1:
            raise SystemExit("cannot anchor NPUA data-tail boundaries in the pinned job lifter")
        additions = [f"    {marker}"]
        additions.extend(f'    "{name}": 0x{end_pc:X},' for name, end_pc in verified)
        source = source.replace(anchor, anchor + "\n".join(additions) + "\n", 1)
        range_anchor = "\n# Extra function entries"
        if source.count(range_anchor) != 1:
            raise SystemExit("cannot anchor NPUA string-island map in the pinned job lifter")
        source = source.replace(
            range_anchor,
            "\n# ASCENSION_M790_NPUA_STRING_ISLANDS_V1\n"
            "DATA_RANGES = {\"jobmod_00818600_eA00\": [(0x83A0, 0x8A48)]}\n" + range_anchor,
            1)
        lift_anchor = '        if inside:\n            cmd += ["--extra-funcs", ",".join(inside)]\n        r = subprocess.run(cmd, capture_output=True, text=True)\n'
        if source.count(lift_anchor) != 1:
            raise SystemExit("cannot anchor NPUA string-island filtering in the pinned job lifter")
        lift_patch = '''        if name in DATA_RANGES:
            from find_spu_functions import detect_functions
            ranges = DATA_RANGES[name]
            functions, _ = detect_functions(elf)
            filtered = []
            for start, end in functions:
                overlaps_data = any(start < data_end and end > data_start
                                    for data_start, data_end in ranges)
                if overlaps_data and any(start >= data_start
                                         for data_start, _ in ranges):
                    continue
                if overlaps_data:
                    raise SystemExit(f"{name} detected function crosses string data")
                filtered.append({"start": start, "end": end})
            os.makedirs(outsub, exist_ok=True)
            functions_path = os.path.join(outsub, "_functions.json")
            with open(functions_path, "w") as f:
                json.dump(filtered, f)
            cmd = [sys.executable, LIFTER, path, "--base", hex(BASE),
                   "--functions", functions_path, "--symbol-prefix", prefix, "-o", outsub,
                   "--source-name", "spu_recomp.c", "--header-name", "spu_recomp.h"]
            inside = [a for a in inside if not any(
                data_start <= int(a, 0) < data_end for data_start, data_end in ranges)]
        if inside:
            cmd += ["--extra-funcs", ",".join(inside)]
        r = subprocess.run(cmd, capture_output=True, text=True)
'''
        source = source.replace(lift_anchor, lift_patch, 1)
        lifter.write_text(source)
    else:
        missing = [name for name, end_pc in verified
                   if f'"{name}": 0x{end_pc:X},' not in source]
        if missing:
            raise SystemExit(f"partial NPUA data-tail patch in pinned job lifter: {missing}")
        if ("ASCENSION_M790_NPUA_STRING_ISLANDS_V1" not in source or
                '"jobmod_00818600_eA00": [(0x83A0, 0x8A48)]' not in source):
            raise SystemExit("partial NPUA string-island patch in pinned job lifter")
    print(f"Verified {len(verified)} NPUA code/data tails and {len(verified_ranges)} internal string island.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--archive", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--gowa-pc", type=Path, required=True)
    ap.add_argument("--ps3recomp", type=Path, required=True)
    args = ap.parse_args()

    gowa_pc = args.gowa_pc.resolve()
    ps3recomp = args.ps3recomp.resolve()
    if git_head(gowa_pc) != GOWA_PC_COMMIT:
        raise SystemExit("gowa-pc extractor revision differs from the audited revision")
    if git_head(ps3recomp) != PS3RECOMP_COMMIT:
        raise SystemExit("ps3recomp gowa-fixes revision differs from the audited revision")

    out = args.out.resolve()
    work = out / "private-input"
    raw_modules = work / "jobmods"
    lifted = out / "lifted"
    elf_path = work / "GOWA.ELF"
    if out.exists():
        shutil.rmtree(out)
    work.mkdir(parents=True, exist_ok=True)
    extract_elf_from_archive(args.archive.resolve(), elf_path)

    extractor = gowa_pc / "scripts/extract_jobmods_elf.py"
    subprocess.run([sys.executable, str(extractor), str(elf_path),
                    "--out", str(raw_modules)], check=True)
    patch_pinned_lifter(ps3recomp, raw_modules)
    register = lifted / "jobmods_register.c"
    subprocess.run([sys.executable, str(ps3recomp / "tools/lift_jobmods.py"),
                    "--jobmods", str(raw_modules), "--out", str(lifted),
                    "--register", str(register), "--symbol-prefix", "ascension_npua"],
                   check=True)

    manifest_path = lifted / "jobmods_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if len(manifest) != EXPECTED_MODULES:
        raise SystemExit(f"expected {EXPECTED_MODULES} ELF job modules, found {len(manifest)}")
    if not any(item["name"] == "jobmod_00818600_eA00" for item in manifest):
        raise SystemExit("the expected NPUA ELF job module with entry 0xA00 was not lifted")
    if len({item["sig"] for item in manifest}) != len(manifest):
        raise SystemExit("duplicate WWS overlay signatures in the ELF extraction")

    # A generated `spu_unsupported()` call returns without emulating the
    # instruction. Never link one into a title job: boundaries above must
    # account for data islands, and any remaining site blocks this build.
    unsupported_kinds: dict[str, int] = {}
    for source in sorted(lifted.glob("jobmod_*/spu_recomp.c")):
        body = source.read_text(errors="replace")
        for mnemonic in re.findall(r'spu_unsupported\(0x[0-9A-Fa-f]+,\s*"([^"]+)"\)', body):
            unsupported_kinds[mnemonic] = unsupported_kinds.get(mnemonic, 0) + 1
    unsupported_reported = sum(int(item["unsupported"]) for item in manifest)
    if sum(unsupported_kinds.values()) != unsupported_reported:
        raise SystemExit("SPU unsupported-site report differs from translated source")
    if set(unsupported_kinds) - {".word"}:
        raise SystemExit(f"WWS job lifts contain unsupported executable mnemonics: {unsupported_kinds}")
    if unsupported_reported:
        raise SystemExit(
            f"refusing a partial native job lift: {unsupported_reported} unresolved SPU words remain"
        )

    # The caller explicitly registers overlays through m772_bridge.cpp. Remove
    # the lifter's constructor so a static-library constructor cannot register
    # every overlay a second time before the guest runtime initializes.
    register_text = register.read_text()
    ctor = ("\n__attribute__((constructor)) static void ascension_npua_jobmods_register_ctor(void)\n"
            "{\n    ascension_npua_jobmods_register_all();\n}\n")
    if register_text.count(ctor) != 1:
        raise SystemExit("cannot remove the generated overlay registration constructor safely")
    register.write_text(register_text.replace(ctor, "\n", 1))

    unsupported = unsupported_reported
    summary = {
        "schema": "ascension-m790-elf-jobmods-v1",
        "source_title": EXPECTED_TITLE,
        "source_elf_structurally_matches_self": True,
        "modules": len(manifest),
        "lifted_functions": sum(int(item["funcs"]) for item in manifest),
        "unclassified_words": unsupported,
        "unclassified_mnemonics": unsupported_kinds,
        "code_end_overrides": {name: f"0x{end_pc:X}"
                               for name, end_pc in NPUA_CODE_ENDS.items()},
        "data_islands": {
            name: [[f"0x{start:X}", f"0x{end:X}"] for start, end in ranges]
            for name, ranges in NPUA_DATA_RANGES.items()
        },
        "registered_overlay_image_ids": [200, 200 + len(manifest) - 1],
        "registration_symbol": "ascension_npua_jobmods_register_all",
        "source_elf_hash_or_bytes_logged": False,
        "license_extracted": False,
    }
    (lifted / "jobmods_attestation.json").write_text(json.dumps(summary, indent=2) + "\n")
    shutil.rmtree(work)
    (lifted / "_tmp.elf").unlink(missing_ok=True)
    print("Native WWS job lifts:", json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
