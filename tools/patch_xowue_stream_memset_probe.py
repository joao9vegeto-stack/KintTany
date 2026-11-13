#!/usr/bin/env python3
"""Instrument exact XOWUE stream-worker and chunk-entry AOT callsites."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

FUNCTION = re.compile(
    r"PPC_FUNC_IMPL\(__imp__(sub_[0-9A-Fa-f]{8})\)\s*\{"
)
MEMSET_FUNCTION = "sub_82573DE0"
CHUNK_FUNCTION = "sub_82575108"
MEMSET_DECLARATION = (
    "void xowue_trace_stream_memset(PPCContext &ctx, uint8_t *base, uint32_t phase);"
)
CHUNK_DECLARATION = (
    "void xowue_trace_chunk_entry(PPCContext &ctx, uint8_t *base);"
)
MEMSET_BEGIN = "xowue_trace_stream_memset(ctx, base, 0u);"
MEMSET_END = "xowue_trace_stream_memset(ctx, base, 1u);"
CHUNK_CALL = "xowue_trace_chunk_entry(ctx, base);"
EOF_FUNCTION = "sub_82575480"
EOF_DECLARATION = (
    "void xowue_trace_stream_eof_poll(PPCContext &ctx, uint8_t *base);"
)
EOF_CALL = "xowue_trace_stream_eof_poll(ctx, base);"
CHUNK_OOB_DECLARATION = (
    "void xowue_trace_chunk_idx_oob(PPCContext &ctx, uint8_t *base);"
)
CHUNK_OOB_LEGACY_GUARD = "if (xowue_trace_chunk_idx_oob(ctx, base)) return;"
CHUNK_OOB_GUARD = "xowue_trace_chunk_idx_oob(ctx, base);"
EOF_B149_DECLARATION = (
    "void xowue_trace_stream_eof_poll_b149(PPCContext &ctx, uint8_t *base);"
)
EOF_B149_CALL = "xowue_trace_stream_eof_poll_b149(ctx, base);"
EOF_ZERO_DECLARATION = (
    "bool xowue_exp_eof_zero_apply(PPCContext &ctx, uint8_t *base);"
)
EOF_ZERO_CALL = "if (xowue_exp_eof_zero_apply(ctx, base)) return;"
CALL_SITE = re.compile(
    r"(?P<prefix>"
    r"^\s*// li r4,0\s*\n"
    r"\s*ctx\.r4\.s64 = 0;\s*\n"
    r"\s*// lwz r5,40\(r29\)\s*\n"
    r"\s*ctx\.r5\.u64 = PPC_LOAD_U32\(ctx\.r29\.u32 \+ 40\);\s*\n"
    r"\s*// lwz r3,44\(r29\)\s*\n"
    r"\s*ctx\.r3\.u64 = PPC_LOAD_U32\(ctx\.r29\.u32 \+ 44\);\s*\n"
    r"\s*// bl 0x82c2a1f0\s*\n"
    r"\s*ctx\.lr = 0x82573E64;\s*\n"
    r")(?P<call>\s*sub_82C2A1F0\(ctx, base\);)",
    re.MULTILINE,
)


def _function_span(source: str, function_name: str):
    matches = list(FUNCTION.finditer(source))
    found = [i for i, match in enumerate(matches) if match.group(1) == function_name]
    if len(found) > 1:
        raise RuntimeError(f"{function_name} appears more than once in one AOT source")
    if not found:
        return None
    index = found[0]
    match = matches[index]
    end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
    return match.start(), end, match


def _ensure_declaration(source: str, marker: str, declaration: str) -> str:
    count = source.count(declaration)
    if count == 1:
        return source
    if count != 0:
        raise RuntimeError(f"duplicated declaration: {declaration}")
    if source.count(marker) != 1:
        raise RuntimeError(f"could not find unique declaration anchor: {marker}")
    return source.replace(marker, declaration + "\n\n" + marker, 1)


def _patch_memset_probe(source: str) -> tuple[str, bool, bool]:
    span = _function_span(source, MEMSET_FUNCTION)
    if span is None:
        return source, False, False
    start, end, _ = span
    body = source[start:end]
    existing_begin = body.count(MEMSET_BEGIN)
    existing_end = body.count(MEMSET_END)
    if existing_begin == 1 and existing_end == 1:
        patched = _ensure_declaration(
            source, f"PPC_FUNC_IMPL(__imp__{MEMSET_FUNCTION})", MEMSET_DECLARATION
        )
        return patched, True, False
    if existing_begin or existing_end:
        raise RuntimeError("partial/duplicated stream memset probe detected; refusing to patch")

    call_matches = list(CALL_SITE.finditer(body))
    if len(call_matches) != 1:
        raise RuntimeError(
            f"expected exactly one direct memset call at 0x82573E64, found {len(call_matches)}"
        )
    call = call_matches[0]
    injected = (
        call.group("prefix")
        + "        " + MEMSET_BEGIN + "\n"
        + call.group("call")
        + "\n        " + MEMSET_END
    )
    patched_body = body[:call.start()] + injected + body[call.end():]
    patched = source[:start] + patched_body + source[end:]
    patched = _ensure_declaration(
        patched, f"PPC_FUNC_IMPL(__imp__{MEMSET_FUNCTION})", MEMSET_DECLARATION
    )
    if patched.count(MEMSET_BEGIN) != 1 or patched.count(MEMSET_END) != 1:
        raise RuntimeError("stream memset probe call count is not exactly one")
    return patched, True, True


def _patch_eof_poll_probe(source: str) -> tuple[str, bool, bool]:
    span = _function_span(source, EOF_FUNCTION)
    if span is None:
        return source, False, False
    start, end, match = span
    body = source[start:end]
    existing_b148 = body.count(EOF_CALL)
    existing_b149 = body.count(EOF_B149_CALL)
    if existing_b148 > 1 or existing_b149 > 1:
        raise RuntimeError("duplicated B148/B149 stream EOF-poll probe detected; refusing to patch")

    inserted = False
    if existing_b148 == 0 and existing_b149 == 0:
        insertion = match.end()
        injected = "\n    " + EOF_CALL + "\n    " + EOF_B149_CALL
        patched = source[:insertion] + injected + source[insertion:]
        inserted = True
    elif existing_b148 == 1 and existing_b149 == 0:
        call_at = body.index(EOF_CALL) + len(EOF_CALL)
        patched_body = body[:call_at] + "\n    " + EOF_B149_CALL + body[call_at:]
        patched = source[:start] + patched_body + source[end:]
        inserted = True
    elif existing_b148 == 0 and existing_b149 == 1:
        call_at = body.index(EOF_B149_CALL)
        patched_body = body[:call_at] + EOF_CALL + "\n    " + body[call_at:]
        patched = source[:start] + patched_body + source[end:]
        inserted = True
    else:
        patched = source

    patched = _ensure_declaration(
        patched, f"PPC_FUNC_IMPL(__imp__{EOF_FUNCTION})", EOF_DECLARATION
    )
    patched = _ensure_declaration(
        patched, f"PPC_FUNC_IMPL(__imp__{EOF_FUNCTION})", EOF_B149_DECLARATION
    )
    if patched.count(EOF_CALL) != 1 or patched.count(EOF_B149_CALL) != 1:
        raise RuntimeError("B148/B149 stream EOF-poll probe call counts are not exactly one")
    return patched, True, inserted


def _patch_chunk_entry_probe(source: str) -> tuple[str, bool, bool, bool, bool]:
    span = _function_span(source, CHUNK_FUNCTION)
    if span is None:
        return source, False, False, False, False
    start, end, match = span
    body = source[start:end]
    existing_legacy_guard = body.count(CHUNK_OOB_LEGACY_GUARD)
    existing_oob_calls = body.count(CHUNK_OOB_GUARD) - existing_legacy_guard
    existing_chunk = body.count(CHUNK_CALL)
    if existing_legacy_guard > 1 or existing_oob_calls > 1 or existing_chunk > 1:
        raise RuntimeError("duplicated B148/B149/B147 chunk-entry probe detected; refusing to patch")

    if existing_legacy_guard == 1 and existing_oob_calls == 0 and existing_chunk == 1:
        # Upgrade the B148 early-return guard into a B149 log-only call.
        patched = source[:start] + body.replace(
            CHUNK_OOB_LEGACY_GUARD, CHUNK_OOB_GUARD, 1
        ) + source[end:]
        patched = _ensure_declaration(
            patched, f"PPC_FUNC_IMPL(__imp__{CHUNK_FUNCTION})", CHUNK_OOB_DECLARATION
        )
        patched = _ensure_declaration(
            patched, f"PPC_FUNC_IMPL(__imp__{CHUNK_FUNCTION})", CHUNK_DECLARATION
        )
        return patched, True, False, True, False

    if existing_oob_calls == 1 and existing_legacy_guard == 0 and existing_chunk == 1:
        patched = _ensure_declaration(
            source, f"PPC_FUNC_IMPL(__imp__{CHUNK_FUNCTION})", CHUNK_OOB_DECLARATION
        )
        patched = _ensure_declaration(
            patched, f"PPC_FUNC_IMPL(__imp__{CHUNK_FUNCTION})", CHUNK_DECLARATION
        )
        return patched, True, False, True, False

    if existing_legacy_guard or existing_oob_calls or existing_chunk:
        raise RuntimeError("partial B148/B149/B147 chunk-entry probe detected; refusing to patch")

    # Log out-of-range indexes but never return early or alter PPC execution.
    insertion = match.end()
    injected = "\n    " + CHUNK_OOB_GUARD + "\n    " + CHUNK_CALL
    patched = source[:insertion] + injected + source[insertion:]
    patched = _ensure_declaration(
        patched, f"PPC_FUNC_IMPL(__imp__{CHUNK_FUNCTION})", CHUNK_OOB_DECLARATION
    )
    patched = _ensure_declaration(
        patched, f"PPC_FUNC_IMPL(__imp__{CHUNK_FUNCTION})", CHUNK_DECLARATION
    )
    if patched.count(CHUNK_OOB_GUARD) != 1 or patched.count(CHUNK_CALL) != 1:
        raise RuntimeError("B148/B149/B147 chunk-entry probe call counts are not exactly one")
    return patched, True, True, True, True


def _patch_eof_zero_probe(source: str) -> tuple[str, bool, bool]:
    span = _function_span(source, CHUNK_FUNCTION)
    if span is None:
        return source, False, False
    start, end, _ = span
    body = source[start:end]
    existing = body.count(EOF_ZERO_CALL)
    if existing > 1:
        raise RuntimeError("duplicated B150 EOF-zero chunk hook detected; refusing to patch")
    prologue = "PPC_FUNC_PROLOGUE();"
    if body.count(prologue) != 1:
        raise RuntimeError(f"expected exactly one PPC_FUNC_PROLOGUE in {CHUNK_FUNCTION}")
    prologue_end = body.index(prologue) + len(prologue)
    if existing == 1:
        if body.index(EOF_ZERO_CALL) < prologue_end:
            raise RuntimeError("B150 EOF-zero hook must run after PPC_FUNC_PROLOGUE")
        patched = _ensure_declaration(
            source, f"PPC_FUNC_IMPL(__imp__{CHUNK_FUNCTION})", EOF_ZERO_DECLARATION
        )
        return patched, True, False
    patched_body = body[:prologue_end] + "\n    " + EOF_ZERO_CALL + body[prologue_end:]
    patched = source[:start] + patched_body + source[end:]
    patched = _ensure_declaration(
        patched, f"PPC_FUNC_IMPL(__imp__{CHUNK_FUNCTION})", EOF_ZERO_DECLARATION
    )
    if patched.count(EOF_ZERO_CALL) != 1:
        raise RuntimeError("B150 EOF-zero hook call count is not exactly one")
    return patched, True, True



def patch_source(source: str) -> tuple[str, dict[str, int]]:
    patched, has_memset, inserted_memset = _patch_memset_probe(source)
    patched, has_eof, inserted_eof = _patch_eof_poll_probe(patched)
    patched, has_chunk, inserted_chunk, has_chunk_oob, inserted_chunk_oob = _patch_chunk_entry_probe(patched)
    patched, has_eof_zero, inserted_eof_zero = _patch_eof_zero_probe(patched)
    return patched, {
        "memset_function": int(has_memset),
        "memset_inserted": int(inserted_memset),
        "eof_poll_function": int(has_eof),
        "eof_poll_inserted": int(inserted_eof),
        "chunk_function": int(has_chunk),
        "chunk_inserted": int(inserted_chunk),
        "chunk_oob_function": int(has_chunk_oob),
        "chunk_oob_inserted": int(inserted_chunk_oob),
        "eof_zero_function": int(has_eof_zero),
        "eof_zero_inserted": int(inserted_eof_zero),
    }


def self_test() -> None:
    fixture = """#include <cstdint>
#include "ppc_recomp_shared.h"

PPC_FUNC_IMPL(__imp__sub_82573DE0) {
    // li r4,0
    ctx.r4.s64 = 0;
    // lwz r5,40(r29)
    ctx.r5.u64 = PPC_LOAD_U32(ctx.r29.u32 + 40);
    // lwz r3,44(r29)
    ctx.r3.u64 = PPC_LOAD_U32(ctx.r29.u32 + 44);
    // bl 0x82c2a1f0
    ctx.lr = 0x82573E64;
    sub_82C2A1F0(ctx, base);
}

PPC_FUNC_IMPL(__imp__sub_82575480) {
    // first translated EOF poll instruction
    ctx.r3.u64 = ctx.r3.u32;
}

PPC_FUNC_IMPL(__imp__sub_82575108) {
    PPC_FUNC_PROLOGUE();
    // first translated chunk instruction
    ctx.r3.u64 = ctx.r3.u32;
}
"""
    patched, result = patch_source(fixture)
    assert result == {
        "memset_function": 1, "memset_inserted": 1,
        "eof_poll_function": 1, "eof_poll_inserted": 1,
        "chunk_function": 1, "chunk_inserted": 1,
        "chunk_oob_function": 1, "chunk_oob_inserted": 1,
        "eof_zero_function": 1, "eof_zero_inserted": 1,
    }
    assert patched.index(MEMSET_BEGIN) < patched.index("sub_82C2A1F0(ctx, base);")
    assert patched.index("sub_82C2A1F0(ctx, base);") < patched.index(MEMSET_END)
    eof_marker = "PPC_FUNC_IMPL(__imp__sub_82575480) {"
    assert patched.index(EOF_CALL) == patched.index(eof_marker) + len(eof_marker) + 5
    assert patched.index(EOF_B149_CALL) > patched.index(EOF_CALL)
    assert patched.index(EOF_B149_CALL) < patched.index("ctx.r3.u64 = ctx.r3.u32;", patched.index(eof_marker))
    chunk_marker = "PPC_FUNC_IMPL(__imp__sub_82575108) {"
    assert patched.index(CHUNK_OOB_GUARD) == patched.index(chunk_marker) + len(chunk_marker) + 5
    assert patched.index(CHUNK_OOB_GUARD) < patched.index(CHUNK_CALL)
    prologue_pos = patched.index("PPC_FUNC_PROLOGUE();", patched.index(chunk_marker))
    zero_pos = patched.index(EOF_ZERO_CALL, prologue_pos)
    assert zero_pos > prologue_pos
    assert zero_pos < patched.index("// first translated chunk instruction", prologue_pos)
    assert "if (xowue_trace_chunk_idx_oob(ctx, base)) return;" not in patched
    repeated, repeated_result = patch_source(patched)
    assert repeated == patched
    assert repeated_result["memset_inserted"] == 0
    assert repeated_result["eof_poll_inserted"] == 0
    assert repeated_result["chunk_inserted"] == 0
    assert repeated_result["chunk_oob_inserted"] == 0
    assert repeated_result["eof_zero_inserted"] == 0
    assert patched.count(MEMSET_BEGIN) == 1 and patched.count(MEMSET_END) == 1
    assert patched.count(EOF_CALL) == 1 and patched.count(EOF_B149_CALL) == 1
    assert patched.count(CHUNK_OOB_GUARD) == 1 and patched.count(CHUNK_CALL) == 1
    assert patched.count(EOF_ZERO_CALL) == 1
    print("XOWUE_B146_B147_AOT_PROBE_SELF_TEST_OK B149 eof_poll=0x82575480 chunk_entry=0x82575108 B150 eof_zero=after-prologue log_only=1 idempotent=1")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ppc-dir", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        if args.ppc_dir:
            parser.error("--self-test cannot be combined with --ppc-dir")
        return 0
    if not args.ppc_dir:
        parser.error("--ppc-dir is required unless --self-test is selected")

    paths = sorted(args.ppc_dir.glob("ppc_recomp.*.cpp"))
    if not paths:
        raise SystemExit(f"no generated ppc_recomp.*.cpp files in {args.ppc_dir}")

    found = {
        "memset_function": 0,
        "eof_poll_function": 0,
        "chunk_function": 0,
        "chunk_oob_function": 0,
        "eof_zero_function": 0,
    }
    inserted = {
        "memset_inserted": 0,
        "eof_poll_inserted": 0,
        "chunk_inserted": 0,
        "chunk_oob_inserted": 0,
        "eof_zero_inserted": 0,
    }
    patched_files = []
    for path in paths:
        original = path.read_text(encoding="utf-8")
        patched, result = patch_source(original)
        for key in found:
            found[key] += result[key]
        for key in inserted:
            inserted[key] += result[key]
        if patched != original:
            temporary = path.with_suffix(path.suffix + ".b148-probe.tmp")
            temporary.write_text(patched, encoding="utf-8", newline="\n")
            temporary.replace(path)
            patched_files.append(path.name)

    expected = {
        "memset_function": 1,
        "eof_poll_function": 1,
        "chunk_function": 1,
        "chunk_oob_function": 1,
        "eof_zero_function": 1,
    }
    for key, value in expected.items():
        if found[key] != value:
            raise SystemExit(f"expected exactly {value} {key} in generated AOT, found {found[key]}")

    report = {
        "memset_guest_function": "0x82573DE0",
        "memset_guest_call_pc": "0x82573E64",
        "memset_callee": "0x82C2A1F0",
        "eof_poll_guest_function": "0x82575480",
        "chunk_entry_guest_function": "0x82575108",
        "probe": "B146 memset + B147 chunk entry + B148 EOF poll + B149 EOF history/log-only OOB + B150 guarded EOF zero window",
        "found": found,
        "inserted": inserted,
        "patched_files": patched_files,
    }
    print("XOWUE_B146_B147_AOT_PROBES " + json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
