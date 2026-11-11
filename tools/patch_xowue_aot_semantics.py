#!/usr/bin/env python3
"""Restore Xbox PPC memory ordering and Xenon spin hints in native ARM64 AOT."""
from __future__ import annotations
import argparse
import collections
import json
import os
import re
from pathlib import Path

BARRIERS = ("sync", "lwsync", "eieio", "isync", "ptesync", "msync")
SPIN_HINTS = ("db8cyc", "db10cyc", "db12cyc", "db14cyc", "db16cyc")
MEDIA_WATCH_FUNCTIONS = {0x824ACBF8, 0x82575250}
MEDIA_WATCH_PCS = {0x824ACC1C, 0x82575510}

BARRIER_MARKER_RE = re.compile(
    r"(?m)^(?P<indent>[ \t]*)// (?P<mn>sync|lwsync|eieio|isync|ptesync|msync)"
    r"(?:[ \t]+(?P<ops>[^\r\n]*))?(?P<nl>\r?\n|\Z)"
)
SPIN_MARKER_RE = re.compile(
    r"(?m)^(?P<indent>[ \t]*)// (?P<mn>db8cyc|db10cyc|db12cyc|db14cyc|db16cyc)"
    r"(?:[ \t]+[^\r\n]*)?(?P<nl>\r?\n|\Z)"
)
FENCE_AHEAD_RE = re.compile(r"[ \t]*std::atomic_thread_fence\(")
PAUSE_AHEAD_RE = re.compile(
    r"(?:[ \t]*__builtin_arm_isb\(|"
    r"#if defined\(__aarch64__\)[ \t]+// XOWUE AOT SPINHINT "
    r"(?:db8cyc|db10cyc|db12cyc|db14cyc|db16cyc)[ \t]*\r?\n"
    r"[ \t]*__builtin_arm_isb\()"
)
SPIN_BLOCK_RE = re.compile(
    r"^#if defined\(__aarch64__\)[ \t]+// XOWUE AOT SPINHINT "
    r"(?:db8cyc|db10cyc|db12cyc|db14cyc|db16cyc)[ \t]*\r?\n"
    r"[ \t]*__builtin_arm_isb\(15\);[ \t]*\r?\n"
    r"#endif(?:\r?\n|\Z)", re.M
)
FENCE_LINE_RE = re.compile(
    r"^[ \t]*std::atomic_thread_fence\(std::memory_order_\w+\);"
    r"[ \t]*// XOWUE AOT BARRIER (?:sync|lwsync|eieio|isync|ptesync|msync)"
    r"(?:\r?\n|\Z)", re.M
)
LEFTOVER_UNIMPLEMENTED_RE = re.compile(
    r"// UNIMPLEMENTED: (?:sync|lwsync|eieio|isync|ptesync|msync)\b|"
    r"REX_UNIMPLEMENTED\([^\n]*\"(?:sync|lwsync|eieio|isync|ptesync|msync)\""
)
FUNCTION_RE = re.compile(r"PPC_FUNC_IMPL\(__imp__(sub_([0-9A-Fa-f]{8}))\)\s*\{")
COMMENT_LINE_RE = re.compile(r"(?m)^[ \t]*//\s+(.+?)\s*$")


def fence_order(mnemonic: str, operands: str) -> str:
    if mnemonic == "isync":
        return "acquire"
    if mnemonic == "lwsync" or (mnemonic == "sync" and operands.strip() == "1"):
        return "acq_rel"
    return "seq_cst"


def fence_line(mnemonic: str, order: str, newline: str) -> str:
    return (
        f"\tstd::atomic_thread_fence(std::memory_order_{order});"
        f"  // XOWUE AOT BARRIER {mnemonic}{newline}"
    )


def spin_block(mnemonic: str, newline: str) -> str:
    nl = newline or "\n"
    return (
        f"#if defined(__aarch64__)  // XOWUE AOT SPINHINT {mnemonic}{nl}"
        f"\t__builtin_arm_isb(15);{nl}"
        f"#endif{newline}"
    )


def patch_barriers(source: str) -> tuple[str, collections.Counter]:
    counts: collections.Counter = collections.Counter()
    parts: list[str] = []
    cursor = 0
    for marker in BARRIER_MARKER_RE.finditer(source):
        parts.append(source[cursor:marker.end()])
        mnemonic = marker.group("mn")
        if FENCE_AHEAD_RE.match(source, marker.end()):
            counts[(mnemonic, "present")] += 1
            cursor = marker.end()
            continue
        parts.append(fence_line(
            mnemonic, fence_order(mnemonic, marker.group("ops") or ""), marker.group("nl")
        ))
        counts[(mnemonic, "insert")] += 1
        cursor = marker.end()
    parts.append(source[cursor:])
    return "".join(parts), counts


def patch_spin_hints(source: str) -> tuple[str, collections.Counter]:
    counts: collections.Counter = collections.Counter()
    parts: list[str] = []
    cursor = 0
    for marker in SPIN_MARKER_RE.finditer(source):
        parts.append(source[cursor:marker.end()])
        mnemonic = marker.group("mn")
        if PAUSE_AHEAD_RE.match(source, marker.end()):
            counts[(mnemonic, "present")] += 1
            cursor = marker.end()
            continue
        parts.append(spin_block(mnemonic, marker.group("nl")))
        counts[(mnemonic, "insert")] += 1
        cursor = marker.end()
    parts.append(source[cursor:])
    return "".join(parts), counts


def strip_our_patch(source: str) -> str:
    source = FENCE_LINE_RE.sub("", source)
    source = SPIN_BLOCK_RE.sub("", source)
    return re.sub(r"(?m)^#include <atomic>\r?\n", "", source, count=1)


def verify_source(original: str, patched: str) -> list[str]:
    problems: list[str] = []
    if strip_our_patch(original) != strip_our_patch(patched):
        problems.append("source changed outside the XOWUE barrier/spin-hint patch")
    for marker in BARRIER_MARKER_RE.finditer(patched):
        if not FENCE_AHEAD_RE.match(patched, marker.end()):
            problems.append(
                f"unfenced {marker.group('mn')} at line "
                f"{patched.count(chr(10), 0, marker.start()) + 1}"
            )
    for marker in SPIN_MARKER_RE.finditer(patched):
        if not PAUSE_AHEAD_RE.match(patched, marker.end()):
            problems.append(
                f"unpaused {marker.group('mn')} at line "
                f"{patched.count(chr(10), 0, marker.start()) + 1}"
            )
    for match in LEFTOVER_UNIMPLEMENTED_RE.finditer(patched):
        problems.append(f"unimplemented memory barrier remains near offset {match.start()}")
    return problems


def verify_fpscr_header(path: Path) -> None:
    header = path.read_text(encoding="utf-8")
    expected_x86 = (
        "HostToGuest[] = { PPC_ROUND_NEAREST, PPC_ROUND_DOWN, "
        "PPC_ROUND_UP, PPC_ROUND_TOWARD_ZERO }"
    )
    expected_arm = (
        "HostToGuest[] = { PPC_ROUND_NEAREST, PPC_ROUND_UP, "
        "PPC_ROUND_DOWN, PPC_ROUND_TOWARD_ZERO }"
    )
    if expected_x86 not in header:
        raise RuntimeError(f"x86 FPSCR HostToGuest mapping missing or changed in {path}")
    if expected_arm not in header:
        raise RuntimeError(f"ARM64 FPSCR HostToGuest mapping missing or changed in {path}")
    for guest_index in range(4):
        token = (
            f"static_assert(HostToGuest[(GuestToHost[{guest_index}] & RoundMask) "
            ">> RoundShift] =="
        )
        if token not in header:
            raise RuntimeError(
                f"FPSCR round-trip static_assert for guest mode {guest_index} missing in {path}"
            )


def locate_semantic_sites(source: str, filename: str) -> list[dict[str, object]]:
    sites: list[dict[str, object]] = []
    functions = list(FUNCTION_RE.finditer(source))
    for index, function in enumerate(functions):
        owner = int(function.group(2), 16)
        end = functions[index + 1].start() if index + 1 < len(functions) else len(source)
        body = source[function.end():end]
        comments = list(COMMENT_LINE_RE.finditer(body))
        for regex, kind in ((BARRIER_MARKER_RE, "barrier"), (SPIN_MARKER_RE, "spin_hint")):
            for marker in regex.finditer(body):
                instruction_index = sum(
                    1 for comment in comments if comment.start() < marker.start()
                )
                pc = owner + instruction_index * 4
                if (
                    owner in MEDIA_WATCH_FUNCTIONS
                    or pc in MEDIA_WATCH_PCS
                    or any(abs(pc - target) <= 0x40 for target in MEDIA_WATCH_PCS)
                ):
                    sites.append({
                        "file": filename,
                        "function": f"0x{owner:08X}",
                        "pc": f"0x{pc:08X}",
                        "kind": kind,
                        "instruction": marker.group("mn"),
                    })
    return sites


def patch_file(
    path: Path,
) -> tuple[bool, collections.Counter, collections.Counter, list[dict[str, object]]]:
    original = path.read_text(encoding="utf-8")
    sites = locate_semantic_sites(original, path.name)
    with_barriers, barrier_counts = patch_barriers(original)
    patched, spin_counts = patch_spin_hints(with_barriers)
    if barrier_counts and "#include <atomic>" not in patched:
        patched = "#include <atomic>\n" + patched
    problems = verify_source(original, patched)
    if problems:
        raise RuntimeError(f"{path}: " + "; ".join(problems[:12]))
    changed = patched != original
    if changed:
        temporary = path.with_suffix(path.suffix + ".xowue-aot.tmp")
        temporary.write_text(patched, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    return changed, barrier_counts, spin_counts, sites


def self_test() -> None:
    fixture = (
        "PPC_FUNC_IMPL(__imp__sub_82575250) {\n"
        "\t// sync\n\t// lwsync\n\t// sync 1\n\t// eieio\n"
        "\t// isync\n\t// db16cyc\n\t// db8cyc\n\treturn;\n}\n"
    )
    patched, barriers = patch_barriers(fixture)
    patched, spins = patch_spin_hints(patched)
    assert barriers[("sync", "insert")] == 2
    assert barriers[("lwsync", "insert")] == 1
    assert barriers[("eieio", "insert")] == 1
    assert barriers[("isync", "insert")] == 1
    assert "memory_order_seq_cst" in patched
    assert "memory_order_acq_rel" in patched
    assert "memory_order_acquire" in patched
    assert spins[("db16cyc", "insert")] == 1
    assert spins[("db8cyc", "insert")] == 1
    assert patched.count("__builtin_arm_isb(15);") == 2
    repeated_barriers, repeated_counts = patch_barriers(patched)
    repeated, repeated_spins = patch_spin_hints(repeated_barriers)
    assert repeated == patched
    assert sum(
        value for (mnemonic, action), value in repeated_counts.items()
        if action == "present"
    ) == 5
    assert sum(
        value for (mnemonic, action), value in repeated_spins.items()
        if action == "present"
    ) == 2

    # ARM FPCR encoding: nearest, +infinity, -infinity, toward-zero.
    arm_guest_to_host = (0, 3, 1, 2)
    arm_host_to_guest = (0, 2, 3, 1)
    assert all(
        arm_host_to_guest[host] == guest
        for guest, host in enumerate(arm_guest_to_host)
    )
    # x86 MXCSR encoding: nearest, -infinity, +infinity, toward-zero.
    x86_guest_to_host = (0, 3, 2, 1)
    x86_host_to_guest = (0, 3, 2, 1)
    assert all(
        x86_host_to_guest[host] == guest
        for guest, host in enumerate(x86_guest_to_host)
    )
    print(
        "XOWUE_AOT_ARM64_SEMANTICS_SELF_TEST_OK "
        "barriers=sync,lwsync,eieio,isync; spin=db8cyc,db16cyc; FPSCR=x86+arm64"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ppc-dir", type=Path)
    parser.add_argument("--fpscr-header", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        if args.ppc_dir or args.fpscr_header or args.report:
            parser.error("--self-test cannot be combined with patching arguments")
        return 0
    if not args.ppc_dir or not args.fpscr_header:
        parser.error(
            "--ppc-dir and --fpscr-header are required unless --self-test is selected"
        )

    verify_fpscr_header(args.fpscr_header)
    sources = sorted(args.ppc_dir.glob("ppc_recomp.*.cpp"))
    if len(sources) != 344:
        raise SystemExit(
            f"expected 344 generated AOT function units, found {len(sources)}"
        )

    total_barriers: collections.Counter = collections.Counter()
    total_spins: collections.Counter = collections.Counter()
    changed_files = 0
    media_sites: list[dict[str, object]] = []
    for path in sources:
        changed, barrier_counts, spin_counts, sites = patch_file(path)
        changed_files += int(changed)
        total_barriers.update({
            mnemonic: count
            for (mnemonic, action), count in barrier_counts.items()
            if action in ("insert", "present")
        })
        total_spins.update({
            mnemonic: count
            for (mnemonic, action), count in spin_counts.items()
            if action in ("insert", "present")
        })
        media_sites.extend(sites)

    barrier_total = sum(total_barriers.values())
    spin_total = sum(total_spins.values())
    if barrier_total == 0:
        raise SystemExit(
            "no PPC memory barriers found in generated AOT; refusing an unverified IPA"
        )

    report = {
        "target": "iOS arm64 native PPC AOT",
        "aot_function_units": len(sources),
        "changed_files": changed_files,
        "fpscr_header": str(args.fpscr_header),
        "fpscr_arm64_host_to_guest": [0, 2, 3, 1],
        "fpscr_x86_host_to_guest": [0, 3, 2, 1],
        "barriers": {name: total_barriers[name] for name in BARRIERS},
        "barrier_total": barrier_total,
        "spin_hints": {name: total_spins[name] for name in SPIN_HINTS},
        "spin_hint_total": spin_total,
        "media_watch_functions": [
            f"0x{address:08X}" for address in sorted(MEDIA_WATCH_FUNCTIONS)
        ],
        "media_watch_pcs": [
            f"0x{address:08X}" for address in sorted(MEDIA_WATCH_PCS)
        ],
        "media_loop_semantic_sites": media_sites,
        "menu_claim": False,
        "notes": [
            "Memory barriers and Xenon delay hints are restored in generated guest AOT code.",
            "The FPSCR FPCR read-back mapping is checked in the compiled PPC context header.",
            "These changes do not force Bink completion, skip media, synthesize a stream callback result, or claim that the menu is reached.",
            "Device acceptance requires the main PPC stream loop to advance and new genuine guest menu frames after the final movie."
        ],
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(
        "XOWUE_AOT_ARM64_SEMANTICS "
        f"units={len(sources)} changed_files={changed_files} barriers={barrier_total} "
        f"spin_hints={spin_total} fpscr=ARM64_ROUNDTRIP_OK media_sites={len(media_sites)}"
    )
    for mnemonic in BARRIERS:
        print(
            f"XOWUE_AOT_BARRIER_COUNT mnemonic={mnemonic} count={total_barriers[mnemonic]}"
        )
    for mnemonic in SPIN_HINTS:
        print(
            f"XOWUE_AOT_SPINHINT_COUNT mnemonic={mnemonic} count={total_spins[mnemonic]}"
        )
    for site in media_sites:
        print("XOWUE_MEDIA_LOOP_SEMANTIC_SITE " + json.dumps(site, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
