#!/usr/bin/env python3
"""Lift the exact C8 WWS policy module captured by Ascension M7.88.

The input is an owner-supplied raw SPU local-store image, not a game ELF.
The generated C is kept separate from the unrelated NPUA WWS image. The four
known metadata slots are excluded only after exact-byte and reachability checks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile


EXPECTED_SIZE = 0x3000
EXPECTED_SHA256 = "2cdc171545c7874a12ec85646fe0456a9cb4f62c7576bcd571a705799be34e99"
EXPECTED_FNV = 0xC8D774963A96DCF2
EXPECTED_UPSTREAM = "39a36296511c445707adabcd312f0b740cfbd694"
BASE = 0xA00
CODE_END = BASE + EXPECTED_SIZE
METADATA_WORDS = {
    0x1640: (0x2C000000, 0x00000000),
    0x1650: (0x2D000000, 0x00000000),
    0x1660: (0x2C000000, 0x00000000),
    0x1670: (0x2D000000, 0x00000000),
}
EXPECTED_EXTERNAL_TARGETS = {0x3FEC0}  # runtime-generated SPURS kernel stub
PREFIX = "wws_pm_c8d774_"


def fnv1a64(data: bytes) -> int:
    # Match ps3recomp runtime's historical (non-standard) offset basis.
    value = 1469598103934665603
    for byte in data:
        value = ((value ^ byte) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return value


def run(command: list[str], log: pathlib.Path) -> None:
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    log.write_text(result.stdout)
    if result.returncode:
        raise SystemExit(f"command failed ({result.returncode}): {' '.join(map(str, command))}\n"
                         f"see {log}\n{result.stdout[-10000:]}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=pathlib.Path, required=True,
                        help="captured spupm_C8D774963A96DCF2_12288.bin")
    parser.add_argument("--upstream", type=pathlib.Path, required=True,
                        help="pinned ps3recomp checkout")
    parser.add_argument("--output", type=pathlib.Path, required=True,
                        help="directory for generated native C, header, and manifest")
    args = parser.parse_args()

    blob = args.input.read_bytes()
    sha = hashlib.sha256(blob).hexdigest()
    if len(blob) != EXPECTED_SIZE or sha != EXPECTED_SHA256:
        raise SystemExit(f"C8 source mismatch: size={len(blob)}, sha256={sha}")
    fnv = fnv1a64(blob)
    if fnv != EXPECTED_FNV:
        raise SystemExit(f"C8 runtime fingerprint mismatch: {fnv:016X}")

    lifter = args.upstream / "tools/spu_lifter.py"
    detector = args.upstream / "tools/find_spu_functions.py"
    if not lifter.is_file() or not detector.is_file():
        raise SystemExit("pinned ps3recomp SPU tools are missing")
    upstream_commit = subprocess.check_output(
        ["git", "-C", str(args.upstream), "rev-parse", "HEAD"], text=True).strip()
    if upstream_commit != EXPECTED_UPSTREAM:
        raise SystemExit(f"ps3recomp SPU lifter pin mismatch: {upstream_commit} != {EXPECTED_UPSTREAM}")

    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="m789-c8-lift-") as tmp_name:
        tmp = pathlib.Path(tmp_name)
        raw = tmp / "spupm_C8D774963A96DCF2_12288.bin"
        raw.write_bytes(blob)
        detected = tmp / "functions.json"
        run([sys.executable, str(detector), str(raw), "--raw", "--base", hex(BASE),
             "--out", str(detected)], tmp / "detect.log")
        functions = json.loads(detected.read_text())

        exact_ranges = {start: end for start, end in
                        ((int(row["start"]), int(row["end"])) for row in functions)}
        for address, words in METADATA_WORDS.items():
            offset = address - BASE
            actual = tuple(int.from_bytes(blob[offset + i:offset + i + 4], "big")
                           for i in (0, 4))
            if actual != words or exact_ranges.get(address) != address + 8:
                raise SystemExit(f"C8 metadata slot changed at 0x{address:X}: "
                                 f"words={actual}, detected_end={exact_ranges.get(address)}")

        # Lift once without filtering to prove the metadata slots are not
        # branch/call destinations, and to pin the decoder's unsupported set.
        preliminary = tmp / "preliminary"
        preliminary.mkdir()
        prelim_report = tmp / "preliminary.json"
        run([sys.executable, str(lifter), str(raw), "--base", hex(BASE),
             "--length", hex(EXPECTED_SIZE), "--functions", str(detected),
             "--output", str(preliminary), "--symbol-prefix", PREFIX,
             "--return-entries", "--code-end", hex(CODE_END),
             "--report", str(prelim_report)], tmp / "preliminary.log")
        prelim = json.loads(prelim_report.read_text())
        references = set(prelim["call_targets"]) | set(prelim["branch_targets"])
        touched = sorted(references.intersection(METADATA_WORDS))
        if touched:
            raise SystemExit("metadata slots are referenced as code targets: " +
                             ", ".join(f"0x{x:X}" for x in touched))
        if prelim["unsupported"] != {".word": 4}:
            raise SystemExit(f"unexpected unfiltered C8 decoder gaps: {prelim['unsupported']}")

        filtered = [row for row in functions if int(row["start"]) not in METADATA_WORDS]
        if len(filtered) != len(functions) - len(METADATA_WORDS):
            raise SystemExit("did not isolate exactly the four metadata function candidates")
        filtered_file = tmp / "functions-filtered.json"
        filtered_file.write_text(json.dumps(filtered, indent=2) + "\n")
        final_report = out / "spu_recomp.json"
        run([sys.executable, str(lifter), str(raw), "--base", hex(BASE),
             "--length", hex(EXPECTED_SIZE), "--functions", str(filtered_file),
             "--output", str(out), "--header-name", "spu_recomp.h",
             "--source-name", "spu_recomp.c", "--symbol-prefix", PREFIX,
             "--return-entries", "--code-end", hex(CODE_END),
             "--report", str(final_report)], out / "lift.log")
        # The ps3recomp lifter emits paths relative to its own source tree.
        # This generated directory is compiled with upstream/runtime/spu on
        # the include path, so use the same portable header names as the
        # existing in-repository NPUA lift.
        header = out / "spu_recomp.h"
        header.write_text(header.read_text().replace(
            '"../../runtime/spu/spu_context.h"', '"spu_context.h"'))
        source = out / "spu_recomp.c"
        source.write_text(source.read_text().replace(
            '"../../runtime/spu/spu_helpers.h"', '"spu_helpers.h"'))

    result = json.loads(final_report.read_text())
    definitions = {int(row[0]) for row in result["functions"]}
    external = (set(result["call_targets"]) | set(result["branch_targets"])) - definitions
    if result["unsupported"]:
        raise SystemExit(f"C8 lift has unsupported instructions: {result['unsupported']}")
    if BASE not in definitions or len(definitions) != 255:
        raise SystemExit(f"C8 entry/function count mismatch: entry={BASE in definitions}, "
                         f"functions={len(definitions)}")
    if external != EXPECTED_EXTERNAL_TARGETS:
        raise SystemExit("unexpected C8 external branch/call targets: " +
                         ", ".join(f"0x{x:X}" for x in sorted(external)))
    source = out / "spu_recomp.c"
    if "TODO spu:" in source.read_text(errors="replace"):
        raise SystemExit("C8 generated C contains TODO instruction fallbacks")

    manifest = {
        "schema": "ascension-m789-c8-wws-native-lift-v1",
        "upstream_commit": upstream_commit,
        "source_file": args.input.name,
        "source_size": len(blob),
        "source_sha256": sha,
        "runtime_fnv1a64": f"0x{fnv:016X}",
        "local_store_base": f"0x{BASE:X}",
        "entry": f"0x{BASE:X}",
        "detected_functions_before_return_splits": len(functions),
        "return_entry_splits": True,
        "metadata_slots_excluded": {
            f"0x{address:X}": [f"0x{word:08X}" for word in words]
            for address, words in METADATA_WORDS.items()
        },
        "metadata_slots_have_branch_or_call_references": False,
        "native_functions": len(definitions),
        "unsupported_instructions": result["unsupported"],
        "external_targets": [f"0x{x:X}" for x in sorted(external)],
        "external_target_resolution": "ps3recomp SPURS runtime-generated kernel stub",
        "generated_source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "generated_header_sha256": hashlib.sha256((out / "spu_recomp.h").read_bytes()).hexdigest(),
        "device_execution": "NOT_MEASURED",
        "guest_draws": "NOT_MEASURED",
        "guest_flips": "NOT_MEASURED",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
