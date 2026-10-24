#!/usr/bin/env python3
"""Materialize validated *internal* AOT entry points as compiled PPC continuations.

XenonRecomp emits one C++ function per recognized guest entry. When a title
takes a legitimate branch into the middle of that function, the AOT lookup table
has no entry. Instead of interpreting PPC instructions or creating an empty
stub, duplicate the *already generated native C++ implementation* with an
initial direct goto to the verified instruction boundary. All subsequent
instructions execute as real translated native code.

This must fail closed if any target is not exactly present in the archived
translation, including the original opcode spelling and instruction index.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

# Extracted from the same default.xex as the archived XOWUE AOT source.
# The expected opcode guards against an unrelated instruction at this address.
VALIDATED = {
    0x82B47458: "addi r8,r8,-1",
}
# Following PPC instructions from the user's exact XEX, not guessed offsets.
CONTEXT_82B47458 = (
    "addi r8,r8,-1",
    "stw r11,14936(r31)",
    "stw r26,14896(r31)",
    "addi r9,r30,-4",
    "stw r30,14904(r31)",
)
FUNC_RE = re.compile(r"PPC_FUNC_IMPL\(__imp__(sub_[0-9A-Fa-f]+)\) \{\n")
ASM_LINE = re.compile(r"(?m)^\t// (.+?)\s*$")


def parse_functions(text: str):
    for match in FUNC_RE.finditer(text):
        end = text.find("\n}\n", match.end())
        if end < 0:
            raise ValueError(f"unterminated AOT function: {match.group(1)}")
        yield match.group(1), int(match.group(1)[4:], 16), match.start(), end + 3, text[match.start():end + 3]


def recover_entry(ppc_dir: Path, target: int, expected_opcode: str):
    found = []
    for path in sorted(ppc_dir.glob("ppc_recomp.*.cpp")):
        text = path.read_text("utf-8")
        if f"__imp__sub_{target:X}" in text:
            raise ValueError(f"0x{target:X} already has an AOT function: refusing duplicate")
        for symbol, base, start, end, body in parse_functions(text):
            if base > target:
                continue
            asm = list(ASM_LINE.finditer(body))
            if (target - base) % 4:
                continue
            # XenonRecomp may insert extra codegen comments between original
            # instruction comments. Match the complete original PPC context
            # rather than assuming every comment advances the guest PC.
            for index in range(len(asm) - len(CONTEXT_82B47458) + 1):
                window = tuple(match.group(1).strip().replace(" ", "")
                               for match in asm[index:index + len(CONTEXT_82B47458)])
                if window != tuple(op.replace(" ", "") for op in CONTEXT_82B47458):
                    continue
                found.append((path, text, symbol, start, end, body, asm[index], index))
    if len(found) != 1:
        print("AOT_MISSING_PC_DIAGNOSTIC: source candidates")
        nearest = []
        for path in sorted(ppc_dir.glob("ppc_recomp.*.cpp")):
            text = path.read_text("utf-8")
            for symbol, base, start, end, body in parse_functions(text):
                if base > target or target - base > 0x2000:
                    continue
                comments = list(ASM_LINE.finditer(body))
                offset = (target - base) // 4
                probable = comments[offset].group(1).strip() if offset < len(comments) else "OUTSIDE_FUNCTION"
                matching = [i for i, v in enumerate(comments) if expected_opcode.replace(" ", "") in v.group(1).replace(" ", "")]
                nearest.append((base, symbol, len(comments), probable, matching[:8], path.name))
        for base, symbol, size, probable, matches, path in sorted(nearest, reverse=True)[:24]:
            print(f"AOT_CANDIDATE {path} {symbol} base=0x{base:08X} comments={size} indexInstruction={probable} expectedPositions={matches}")
        raise ValueError(f"0x{target:08X}: expected exactly one verified native C++ owner, found {len(found)}")
    path, text, symbol, start, end, body, hit, index = found[0]
    marker = FUNC_RE.match(body)
    if not marker:
        raise ValueError("AOT generated function marker changed")
    first_instruction = ASM_LINE.search(body)
    if not first_instruction or first_instruction.start() >= hit.start():
        raise ValueError("AOT instruction sequence malformed")
    target_label = f"loc_{target:X}:"
    lifted = body.replace(f"__imp__{symbol}", f"__imp__sub_{target:X}", 1)
    # Every local temporary is declared above the first original PPC comment.
    # Branching after these declarations avoids crossing initializations.
    first_comment = ASM_LINE.search(lifted)
    lifted = lifted[:first_comment.start()] + f"\tgoto {target_label[:-1]};\n" + lifted[first_comment.start():]
    comments = list(ASM_LINE.finditer(lifted))
    anchor = comments[index]
    if anchor.group(1).strip().replace(" ", "") != expected_opcode.replace(" ", ""):
        raise ValueError("Target instruction moved while constructing continuation")
    if target_label not in lifted:
        raise AssertionError("internal error: goto disappeared")
    # If a label already exists, use it; otherwise make this PPC PC a label.
    if f"\n{target_label}\n" not in lifted and f"\n{target_label}:\n" not in lifted:
        lifted = lifted[:anchor.start()] + f"{target_label}\n" + lifted[anchor.start():]
    # Clone the public entry point and let the linker bind the function to
    # its original guest address. The implementation remains a normal AOT body.
    public = f"\nPPC_WEAK_FUNC(sub_{target:X}) {{\n\t__imp__sub_{target:X}(ctx, base);\n}}\n"
    updated = text[:end] + "\n" + lifted + public + text[end:]
    path.write_text(updated, encoding="utf-8")
    return path.name, symbol, len(comments)


def patch_mappings(ppc_dir: Path, targets):
    header = ppc_dir / "ppc_recomp_shared.h"
    header_text = header.read_text("utf-8")
    for target in targets:
        name = f"sub_{target:X}"
        marker = f"PPC_EXTERN_FUNC({name});"
        if marker in header_text:
            raise ValueError(f"{name} already declared")
        header_text += "\n" + marker
    header.write_text(header_text, encoding="utf-8")

    mappings = ppc_dir / "ppc_func_mapping.cpp"
    source = mappings.read_text("utf-8")
    terminators = list(re.finditer(r"(?m)^\s*\{\s*0\s*,\s*nullptr\s*\}\s*,?\s*$", source))
    if len(terminators) != 1:
        raise ValueError("AOT function mapping has no unique terminator")
    pos = terminators[0].start()
    entries = ""
    for target in targets:
        if re.search(r"\{\s*0x" + f"{target:X}" + r"\s*,", source, re.IGNORECASE):
            raise ValueError(f"0x{target:X} already in AOT function mapping")
        entries += f"\t{{ 0x{target:X}, sub_{target:X} }},\n"
    mappings.write_text(source[:pos] + entries + source[pos:], encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ppc-dir", required=True, type=Path)
    args = ap.parse_args()
    ppc_dir = args.ppc_dir
    if len(list(ppc_dir.glob("ppc_recomp.*.cpp"))) < 300:
        raise SystemExit("Unexpected XOWUE AOT file count")
    try:
        for address, opcode in VALIDATED.items():
            file, parent, length = recover_entry(ppc_dir, address, opcode)
            print(f"AOT_NATIVE_CONTINUATION target=0x{address:08X} original={parent} file={file} instructions={length}")
        patch_mappings(ppc_dir, VALIDATED)
    except ValueError as error:
        raise SystemExit(f"REFUSING_UNVALIDATED_AOT_PATCH: {error}")
    print(f"PASS: {len(VALIDATED)} direct native PPC continuation(s); no interpreter or JIT")


if __name__ == "__main__":
    main()
