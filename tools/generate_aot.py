#!/usr/bin/env python3
"""Patch generated XOWUE AOT sources for QPC correctness and 32-bit GPR state."""
from __future__ import annotations
import argparse
import re
from pathlib import Path

QPC_MARKER = "PPC_FUNC_IMPL(__imp__sub_82C3C4D8) {"
QPC_BODY = """PPC_FUNC_IMPL(__imp__sub_82C3C4D8) {
    xowue_thread_checkpoint(0x82C3C4D8u);
    const uint32_t outPtr = ctx.r3.u32;
    const uint64_t tb64 = xowue_qpc_write(outPtr, xowue_guest_timebase(), static_cast<uint32_t>(ctx.lr));
    ctx.r11.u64 = tb64;
    ctx.r10.u64 = static_cast<uint32_t>(tb64);
    ctx.cr0.compare<int32_t>(ctx.r10.s32, 0, ctx.xer);
    ctx.r3.u64 = 1ull;
    return;
}"""

def replace_function(source: str) -> tuple[str, int]:
    start = source.find(QPC_MARKER)
    if start < 0:
        return source, 0
    brace = source.find("{", start)
    depth = 0
    end = None
    for i in range(brace, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise RuntimeError("unterminated generated QPC function")
    old_body = source[start:end]
    if "xowue_thread_checkpoint(0x82C3C4D8u);" not in old_body and "xowue_thread_checkpoint();" in old_body:
        replacement = QPC_BODY.replace(
            "xowue_thread_checkpoint(0x82C3C4D8u);", "xowue_thread_checkpoint();")
    else:
        replacement = QPC_BODY
    return source[:start] + replacement + source[end:], 1

def normalize_32bit_writes(source: str) -> tuple[str, int]:
    lines = source.splitlines()
    output: list[str] = []
    count = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        output.append(line)
        m = re.match(r"^([ \t]*)ctx\.r(\d+)\.u32\s*=\s*[^;]+;\s*$", line)
        if m:
            clear = f"{m.group(1)}ctx.r{m.group(2)}.u64 = static_cast<uint32_t>(ctx.r{m.group(2)}.u32);"
            if i + 1 >= len(lines) or lines[i + 1].strip() != clear.strip():
                output.append(clear)
                count += 1
        i += 1
    normalized = "\n".join(output) + ("\n" if source.endswith("\n") else "")
    return normalized, count

def normalize_rlw_instructions(source: str) -> tuple[str, int]:
    count = 0
    # The pinned generator encodes rlwinm through a 64-bit rotation and can
    # accidentally consume a stale upper half of the source GPR.
    rlwinm = re.compile(
        r"(?m)^([ \t]*ctx\.r(\d+)\.u64\s*=\s*)__builtin_rotateleft64\("
        r"ctx\.r(\d+)\.u32\s*\|\s*\(ctx\.r\d+\.u64\s*<<\s*32\),\s*(\d+)\)"
        r"\s*&\s*(0x[0-9A-Fa-f]+);"
    )
    def fix_rlwinm(m: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return (f"{m.group(1)}static_cast<uint32_t>(__builtin_rotateleft32("
                f"ctx.r{m.group(3)}.u32, {m.group(4)}) & static_cast<uint32_t>({m.group(5)}));")
    source = rlwinm.sub(fix_rlwinm, source)

    # rlwimi merges only the destination's low 32 bits. Preserve that masked
    # portion, not old upper bits, then zero-extend the 32-bit result.
    rlwimi = re.compile(
        r"(?m)^([ \t]*ctx\.r(\d+)\.u64\s*=\s*)\(__builtin_rotateleft32\("
        r"ctx\.r(\d+)\.u32,\s*(\d+)\)\s*&\s*(0x[0-9A-Fa-f]+)\)\s*\|\s*"
        r"\(ctx\.r\d+\.u64\s*&\s*(0x[0-9A-Fa-f]+)\);"
    )
    def fix_rlwimi(m: re.Match[str]) -> str:
        nonlocal count
        count += 1
        d, src, shift, mask, old_mask = m.group(2), m.group(3), m.group(4), m.group(5), m.group(6)
        return (f"{m.group(1)}static_cast<uint32_t>((__builtin_rotateleft32(ctx.r{src}.u32, {shift}) "
                f"& static_cast<uint32_t>({mask})) | (ctx.r{d}.u32 & static_cast<uint32_t>({old_mask})));")
    source = rlwimi.sub(fix_rlwimi, source)
    return source, count

def normalize_32bit_arithmetic(source: str) -> tuple[str, int]:
    # LI/LIS/ADDI/ADDIS emitter output uses .s64 for the expression. The guest
    # destination in this port intentionally retains only the low 32 bits.
    pat = re.compile(r"(?m)^([ \t]*ctx\.r\d+)\.s64 = ((?:ctx\.r\d+\.s64 \+\s*)?-?\d+);[ \t]*$")
    normalized, count = pat.subn(r"\1.u64 = static_cast<uint32_t>(\2);", source)
    return normalized, count

def self_test() -> None:
    fixture = (
        'PPC_FUNC_IMPL(__imp__sub_82C3C4D8) {\n'
        '    xowue_thread_checkpoint(0x82C3C4D8u);\n'
        '    ctx.r11.u64 = __rdtsc();\n'
        '    ctx.r10.u32 = 1;\n'
        '    ctx.r3.u64 = 123;\n'
        '    return;\n}\n'
        'PPC_FUNC_IMPL(__imp__sub_82345678) {\n'
        '    ctx.r7.u32 = 0;\n'
        '    ctx.r8.s64 = ctx.r9.s64 + -1;\n'
        '    ctx.r3.u64 = __builtin_rotateleft64(ctx.r11.u32 | (ctx.r11.u64 << 32), 0) & 0xFFFFFFFF;\n'
        '    ctx.r10.u64 = (__builtin_rotateleft32(ctx.r11.u32, 0) & 0xFFFFFFFF) | (ctx.r10.u64 & 0xFFFFFFFF00000000);\n'
        '    return;\n}\n'
    )
    patched, n = replace_function(fixture)
    assert n == 1 and "const uint32_t outPtr = ctx.r3.u32;" in patched
    assert "xowue_qpc_write(outPtr, xowue_guest_timebase(), static_cast<uint32_t>(ctx.lr))" in patched
    assert "ctx.r3.u64 = 1ull;" in patched and "ctx.r3.u64 = 123;" not in patched
    patched, clears = normalize_32bit_writes(patched)
    assert clears >= 1 and "ctx.r7.u64 = static_cast<uint32_t>(ctx.r7.u32);" in patched
    patched, arithmetic = normalize_32bit_arithmetic(patched)
    assert arithmetic >= 1 and "ctx.r8.u64 = static_cast<uint32_t>(ctx.r9.s64 + -1);" in patched
    patched, rlw = normalize_rlw_instructions(patched)
    assert rlw == 2
    assert "static_cast<uint32_t>(__builtin_rotateleft32(ctx.r11.u32, 0)" in patched
    assert "(ctx.r10.u32 & static_cast<uint32_t>(0xFFFFFFFF00000000))" in patched
    patched2, _ = normalize_32bit_writes(patched)
    assert patched2 == patched, "32-bit GPR normalization must be idempotent"
    print("PASS: Build 64 QPC pointer preservation, RLW upper-half hygiene, and 32-bit GPR clearing")

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ppc-dir", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.ppc_dir:
        parser.error("--ppc-dir is required unless --self-test is selected")
    sources = sorted(args.ppc_dir.glob("ppc_recomp.*.cpp"))
    if not sources:
        raise SystemExit(f"no generated AOT sources found in {args.ppc_dir}")
    qpc_count = clear_count = arithmetic_count = rlw_count = 0
    for path in sources:
        source = path.read_text(encoding="utf-8")
        source, qpc = replace_function(source)
        source, arithmetic = normalize_32bit_arithmetic(source)
        source, rlw = normalize_rlw_instructions(source)
        source, clears = normalize_32bit_writes(source)
        qpc_count += qpc
        arithmetic_count += arithmetic
        rlw_count += rlw
        clear_count += clears
        if qpc or arithmetic or rlw or clears:
            path.write_text(source, encoding="utf-8")
    if qpc_count != 1:
        raise SystemExit(f"expected exactly one QPC helper at 0x82C3C4D8, found {qpc_count}")
    print(f"XOWUE_B64_AOT_PATCH qpc={qpc_count} arithmetic_zero_extend={arithmetic_count} "
          f"rlw_fixes={rlw_count} direct_u32_upper_clears={clear_count}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
