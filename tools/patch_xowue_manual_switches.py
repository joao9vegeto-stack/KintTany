#!/usr/bin/env python3
"""Materialize manually verified XOWUE switch targets in archived AOT C++."""
from __future__ import annotations

import argparse
import tomllib
from pathlib import Path

TABLE_BASE = 0x8237CA50
TABLE_REGISTER = 11
TABLE_DEFAULT = 0x8237CB40
TABLE_LABELS = (
    0x8237CAD0,
    0x8237CADC,
    0x8237CAE8,
    0x8237CAF4,
    0x8237CB00,
    0x8237CB00,
    0x8237CB08,
    0x8237CB14,
    0x8237CB20,
    0x8237CB2C,
    0x8237CB38,
)

FUNCTION_MARKER = "PPC_FUNC_IMPL(__imp__sub_8237CA18) {"
INDIRECT_DISPATCH = "\t// bctr \n\tPPC_CALL_INDIRECT_FUNC(ctx.ctr.u32);\n\treturn;"

LABEL_ANCHORS = (
    ("loc_8237CAD0", "\t// lis r9,44\n\tctx.r9.s64 = 2883584;\n\t// ori r9,r9,33700"),
    ("loc_8237CADC", "\t// lis r9,44\n\tctx.r9.s64 = 2883584;\n\t// ori r9,r9,9125"),
    ("loc_8237CAE8", "\t// lis r9,42\n\tctx.r9.s64 = 2752512;\n\t// ori r9,r9,9145"),
    ("loc_8237CAF4", "\t// lis r9,26\n\tctx.r9.s64 = 1703936;\n\t// ori r9,r9,9126"),
    ("loc_8237CB00", "\t// mr r9,r6\n\tctx.r9.u64 = ctx.r6.u64;"),
    ("loc_8237CB08", "\t// lis r9,26\n\tctx.r9.s64 = 1703936;\n\t// ori r9,r9,8326"),
    ("loc_8237CB14", "\t// lis r9,24\n\tctx.r9.s64 = 1572864;\n\t// ori r9,r9,10374"),
    ("loc_8237CB20", "\t// lis r9,44\n\tctx.r9.s64 = 2883584;\n\t// ori r9,r9,9049"),
    ("loc_8237CB2C", "\t// lis r9,44\n\tctx.r9.s64 = 2883584;\n\t// ori r9,r9,8537"),
    ("loc_8237CB38", "\t// lis r9,44\n\tctx.r9.s64 = 2883584;\n\t// ori r9,r9,9055"),
)


def validate_table(path: Path) -> None:
    parsed = tomllib.loads(path.read_text(encoding="utf-8"))
    matches = [item for item in parsed.get("switch", []) if item.get("base") == TABLE_BASE]
    expected = {
        "base": TABLE_BASE,
        "r": TABLE_REGISTER,
        "default": TABLE_DEFAULT,
        "labels": list(TABLE_LABELS),
    }
    if matches != [expected]:
        raise SystemExit(
            f"{path} must contain exactly the validated switch table at 0x{TABLE_BASE:08X}"
        )


def function_span(source: str) -> tuple[int, int]:
    start = source.find(FUNCTION_MARKER)
    if start < 0 or source.find(FUNCTION_MARKER, start + len(FUNCTION_MARKER)) >= 0:
        raise SystemExit("expected exactly one AOT function sub_8237CA18")
    end = source.find("\n}\n", start)
    if end < 0:
        raise SystemExit("unterminated AOT function sub_8237CA18")
    return start, end + 2


def switch_body() -> str:
    lines = ["\tswitch (ctx.r11.u64) {"]
    for index, target in enumerate(TABLE_LABELS):
        lines.extend((f"\tcase {index}:", f"\t\tgoto loc_{target:08X};"))
    lines.extend(("\tdefault:", "\t\t__builtin_unreachable();", "\t}"))
    return "\n".join(lines)


def validate_function(body: str) -> None:
    if "ctx.r11.s64 = ctx.r11.s64 + -1;" not in body:
        raise SystemExit("switch selector decrement is missing from sub_8237CA18")
    if "if (ctx.cr6.gt) goto loc_8237CB40;" not in body:
        raise SystemExit("switch default guard is missing from sub_8237CA18")
    if switch_body() not in body:
        raise SystemExit("switch dispatch does not match the XEX target table")
    for label, _anchor in LABEL_ANCHORS:
        if body.count(label + ":") != 1:
            raise SystemExit(f"expected one target label {label}")
    if "PPC_CALL_INDIRECT_FUNC(ctx.ctr.u32);" in body:
        raise SystemExit("sub_8237CA18 still dispatches this internal switch through AOT")


def patch_file(path: Path, table_path: Path) -> bool:
    validate_table(table_path)
    source = path.read_text(encoding="utf-8")
    start, end = function_span(source)
    body = source[start:end]

    if switch_body() in body:
        validate_function(body)
        return False

    if body.count(INDIRECT_DISPATCH) != 1:
        raise SystemExit("expected exactly one indirect dispatch for the XOWUE switch")
    body = body.replace(INDIRECT_DISPATCH, "\t// bctr \n" + switch_body(), 1)
    for label, anchor in LABEL_ANCHORS:
        if body.count(anchor) != 1:
            raise SystemExit(f"expected exactly one validated code anchor for {label}")
        body = body.replace(anchor, label + ":\n" + anchor, 1)

    validate_function(body)
    path.write_text(source[:start] + body + source[end:], encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ppc-dir", type=Path, required=True)
    parser.add_argument("--switch-table", type=Path, required=True)
    args = parser.parse_args()
    source = args.ppc_dir / "ppc_recomp.24.cpp"
    changed = patch_file(source, args.switch_table)
    print(f"validated internal XOWUE switch targets in {source} (patched={changed})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())