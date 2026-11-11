#!/usr/bin/env python3
"""Instrument the direct stream-worker memset call in generated native PPC AOT."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

FUNCTION = re.compile(
    r"PPC_FUNC_IMPL\(__imp__(sub_[0-9A-Fa-f]{8})\)\s*\{"
)
FUNCTION_NAME = "sub_82573DE0"
DECLARATION = (
    "void xowue_trace_stream_memset(PPCContext &ctx, uint8_t *base, uint32_t phase);"
)
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


def patch_source(source: str) -> tuple[str, dict[str, int]]:
    matches = list(FUNCTION.finditer(source))
    target = None
    for index, match in enumerate(matches):
        if match.group(1) != FUNCTION_NAME:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        target = (match.start(), end)
        break
    if target is None:
        raise RuntimeError(f"{FUNCTION_NAME} missing from generated AOT source")

    start, end = target
    body = source[start:end]
    existing_begin = body.count("xowue_trace_stream_memset(ctx, base, 0u);")
    existing_end = body.count("xowue_trace_stream_memset(ctx, base, 1u);")
    if existing_begin == 1 and existing_end == 1:
        if source.count(DECLARATION) != 1:
            raise RuntimeError("probe call exists but its declaration is missing or duplicated")
        return source, {"declaration": 1, "begin": 1, "end": 1, "inserted": 0}
    if existing_begin or existing_end:
        raise RuntimeError("partial/duplicated stream memset probe detected; refusing to patch")

    call_matches = list(CALL_SITE.finditer(body))
    if len(call_matches) != 1:
        raise RuntimeError(
            f"expected exactly one direct memset call at 0x82573E64, found {len(call_matches)}"
        )

    call = call_matches[0]
    prefix = call.group("prefix")
    direct_call = call.group("call")
    injected = (
        prefix
        + "        xowue_trace_stream_memset(ctx, base, 0u);\n"
        + direct_call
        + "\n        xowue_trace_stream_memset(ctx, base, 1u);"
    )
    patched_body = body[:call.start()] + injected + body[call.end():]
    patched = source[:start] + patched_body + source[end:]

    if patched.count(DECLARATION) == 0:
        marker = "PPC_FUNC_IMPL(__imp__sub_82573DE0)"
        if patched.count(marker) != 1:
            raise RuntimeError("could not find unique target function marker for probe declaration")
        patched = patched.replace(marker, DECLARATION + "\n\n" + marker, 1)
    if patched.count(DECLARATION) != 1:
        raise RuntimeError("stream memset probe declaration is duplicated")
    if patched.count("xowue_trace_stream_memset(ctx, base, 0u);") != 1:
        raise RuntimeError("stream memset begin probe count is not exactly one")
    if patched.count("xowue_trace_stream_memset(ctx, base, 1u);") != 1:
        raise RuntimeError("stream memset end probe count is not exactly one")
    return patched, {"declaration": 1, "begin": 1, "end": 1, "inserted": 1}


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
"""
    patched, result = patch_source(fixture)
    assert result == {"declaration": 1, "begin": 1, "end": 1, "inserted": 1}
    assert patched.index("xowue_trace_stream_memset(ctx, base, 0u);") < patched.index(
        "sub_82C2A1F0(ctx, base);"
    )
    assert patched.index("sub_82C2A1F0(ctx, base);") < patched.index(
        "xowue_trace_stream_memset(ctx, base, 1u);"
    )
    repeated, repeated_result = patch_source(patched)
    assert repeated == patched
    assert repeated_result["inserted"] == 0
    print("XOWUE_STREAM_MEMSET_AOT_PROBE_SELF_TEST_OK pc=0x82573E64 direct_call=1 idempotent=1")


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

    path = args.ppc_dir / "ppc_recomp.64.cpp"
    if not path.is_file():
        raise SystemExit(f"missing generated AOT source: {path}")
    original = path.read_text(encoding="utf-8")
    patched, result = patch_source(original)
    if patched != original:
        temporary = path.with_suffix(path.suffix + ".stream-probe.tmp")
        temporary.write_text(patched, encoding="utf-8", newline="\n")
        temporary.replace(path)
    report = {"source": path.name, "guest_function": "0x82573DE0",
              "guest_call_pc": "0x82573E64", "callee": "0x82C2A1F0",
              "probe": "read-only begin/end around direct AOT call",
              **result}
    print("XOWUE_STREAM_MEMSET_AOT_PROBE " + json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
