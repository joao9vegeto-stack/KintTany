#!/usr/bin/env python3
"""Make verified internal PCs of ONE actual PPC AOT owner native callable entries.

This is an owner-wide native continuation table, NOT an interpreter/JIT/stub.
All entries share one cloned PPC function and jump into exact translated
instruction labels. Fail closed if the saved AOT instruction order, known
XEX instruction sequences, any existing label, or ownership cannot be proved.
"""
from __future__ import annotations
import argparse, bisect, json, re
from pathlib import Path

OWNER = 0x82C2E240
END = 0x82C2EBA0
KNOWN = {
    0x82C2E338: ("extsb r11,r10", "cmpwi cr6,r11,49",
                 "blt cr6,0x82c2e358"),
    0x82C2E4A8: ("extsb r11,r10", "li r30,1",
                 "b 0x82c2e4e8"),
}
FUNCTION = re.compile(r"PPC_FUNC_IMPL\(__imp__(sub_[0-9A-Fa-f]+)\) \{\n")
OPCODE = re.compile(r"(?m)^\t// (.+?)\s*$")
LABEL = re.compile(r"(?m)^loc_([0-9A-Fa-f]+):\s*$")
TERMINATOR = re.compile(r"(?m)^\s*\{\s*0\s*,\s*nullptr\s*\}\s*,?\s*$")

def norm(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()

def generate(ppc_dir: Path):
    owners = []
    for path in sorted(ppc_dir.glob("ppc_recomp.*.cpp")):
        text = path.read_text("utf-8")
        for match in FUNCTION.finditer(text):
            if match.group(1) != f"sub_{OWNER:X}":
                continue
            finish = text.find("\n}\n", match.end())
            if finish < 0: raise ValueError("native owner is not terminated")
            owners.append((path, text, match.start(), finish + 3,
                           text[match.start():finish + 3]))
    if len(owners) != 1:
        raise ValueError(f"expected one native owner, got {len(owners)}")
    path, text, start, end, body = owners[0]
    comments = list(OPCODE.finditer(body))
    required = (END - OWNER) // 4
    # The final 0x82C2EB9C word in the supplied XEX is zero/data.
    # Original native AOT therefore contains 599 translated PPC opcodes.
    if END and len(comments) != required - 1:
        raise ValueError(f"owner instruction order incomplete: {len(comments)} != {required - 1}")
    if not END and not (OWNER + len(comments) * 4 > max(KNOWN)):
        raise ValueError(f"owner 0x{OWNER:X} translated_count={len(comments)} "
                         f"does not cover target=0x{max(KNOWN):X}")
    labels = {}
    starts = [match.start() for match in comments]
    for found in LABEL.finditer(body):
        pc = int(found.group(1), 16)
        index = bisect.bisect_left(starts, found.end())
        if pc != OWNER + index * 4:
            raise ValueError(f"native owner label out of alignment: 0x{pc:X} at index {index}")
        if pc in labels: raise ValueError(f"duplicate label 0x{pc:X}")
        labels[pc] = True
    for pc, original in KNOWN.items():
        i = (pc - OWNER) // 4
        segment = tuple(norm(x.group(1)) for x in comments[i:i + len(original)])
        if segment != tuple(map(norm, original)):
            raise ValueError(f"original XEX/AOT opcode sequence mismatch at 0x{pc:X}: {segment}")
    mapping = (ppc_dir / "ppc_func_mapping.cpp")
    map_source = mapping.read_text("utf-8")
    recorded = set(int(pc, 16) for pc in
                   re.findall(r"\{\s*0x([0-9A-Fa-f]+)\s*,", map_source))
    candidate_pcs = [OWNER + i * 4 for i in range(1, len(comments))
                     if OWNER + i * 4 not in recorded]
    if any(pc < OWNER or pc >= (END or OWNER + 4 * len(comments)) for pc in candidate_pcs) or len(candidate_pcs) < (500 if END else 8):
        raise ValueError("native owner PC coverage not internally consistent")
    renamed = body.replace(f"PPC_FUNC_IMPL(__imp__sub_{OWNER:X})",
                           f"static void xowue_resume_{OWNER:X}(PPCContext &ctx, uint8_t *base, uint32_t entryPc)", 1)
    # Re-scan after rewriting the header. The new function signature is
    # longer than PPC_FUNC_IMPL(...), so offsets from 'body' are invalid.
    # Using those old positions would splice labels into C++ instructions.
    new_comments = list(OPCODE.finditer(renamed))
    if len(new_comments) != len(comments):
        raise ValueError("owner instruction count changed after renaming")
    for i in reversed(range(1, len(new_comments))):
        pc = OWNER + 4 * i
        if pc not in labels:
            at = new_comments[i].start()
            renamed = renamed[:at] + f"loc_{pc:X}:\n" + renamed[at:]
    first = OPCODE.search(renamed)
    if first is None: raise ValueError("no native instruction to resume")
    switch = "\tswitch (entryPc) {\n"
    for pc in candidate_pcs:
        switch += f"\tcase 0x{pc:08X}u: goto loc_{pc:X};\n"
    switch += "\tdefault: return;\n\t}\n"
    renamed = renamed[:first.start()] + switch + renamed[first.start():]
    wrappers = ""
    for pc in candidate_pcs:
        wrappers += (f"\nPPC_FUNC_IMPL(__imp__sub_{pc:X}) {{\n"
                     f"\txowue_resume_{OWNER:X}(ctx,base,0x{pc:08X}u);\n}}\n"
                     f"PPC_WEAK_FUNC(sub_{pc:X}) {{\n"
                     f"\t__imp__sub_{pc:X}(ctx,base);\n}}\n")
    path.write_text(text[:end] + "\n" + renamed + "\n" + wrappers + text[end:],
                    encoding="utf-8")
    header = ppc_dir / "ppc_recomp_shared.h"
    header_text = header.read_text("utf-8")
    for pc in candidate_pcs:
        symbol = f"PPC_EXTERN_FUNC(sub_{pc:X});"
        if symbol in header_text: raise ValueError("entry already declared " + symbol)
        header_text += "\n" + symbol
    header.write_text(header_text, encoding="utf-8")
    terminators = list(TERMINATOR.finditer(map_source))
    if len(terminators) != 1: raise ValueError("ambiguous PPC mapping terminator")
    new_entries = "".join(f"\t{{ 0x{pc:X}, sub_{pc:X} }},\n" for pc in candidate_pcs)
    pos = terminators[0].start()
    mapping.write_text(map_source[:pos] + new_entries + map_source[pos:], encoding="utf-8")
    return dict(owner=f"0x{OWNER:08X}",
                exclusive_end=f"0x{(END or OWNER + 4 * len(comments)):08X}",
                aligned_guest_instructions=len(comments),
                preexisting_internal_entries=len(comments)-1-len(candidate_pcs),
                new_native_entries=len(candidate_pcs),
                validated_known_target=[f"0x{pc:X}" for pc in KNOWN],
                local_labels=len(labels),
                single_shared_resume_body=True,
                interpreter=False, jit=False)

def discover_owner(ppc_dir: Path, target: int,
                   context: tuple[str, ...]) -> int:
    """Find owner using exact AOT opcode sequence at the XEX guest PC, not
    the last executed AOT entry (which may be a different function)."""
    matches = []
    nearby = []
    for path in sorted(ppc_dir.glob("ppc_recomp.*.cpp")):
        source = path.read_text("utf-8")
        for match in FUNCTION.finditer(source):
            base = int(match.group(1)[4:], 16)
            if base > target or target-base > 0x4000:
                continue
            stop = source.find("\n}\n", match.end())
            if stop < 0: continue
            insns = list(OPCODE.finditer(source[match.start():stop+3]))
            index = (target - base) // 4
            if index + len(context) <= len(insns) and all(
                norm(insns[index+i].group(1)) == norm(ctx)
                for i,ctx in enumerate(context)):
                matches.append((base,path.name,index,len(insns)))
            if 0 <= target-base <= 0x180 and len(nearby)<200:
                probe=(insns[index].group(1) if index < len(insns) else "OUTSIDE")
                nearby.append((base,len(insns),index,probe,path.name))
    for base,n,index,probe,file in sorted(nearby,reverse=True)[:25]:
        print("XOWUE_OWNER_SEARCH base=%08X instr=%d index=%d opcode=%s file=%s" %
              (base,n,index,probe,file))
    if len(matches)!=1:
        raise ValueError("target 0x%08X owner matches=%s" %
                         (target,matches[:12]))
    base,file,index,count=matches[0]
    print("XOWUE_EXACT_OWNER_FOUND target=%08X owner=%08X index=%d "
          "opcodes=%d unit=%s" % (target,base,index,count,file))
    return base

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ppc-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = generate(args.ppc_dir)
        # The Build 23 runtime confirmed a second, independent internal-branch
        # owner: lastAotEntry=0x830EBDF8, guestTarget=0x830EBE74.
        # Verify *both* source AOT opcodes against the supplied XEX; reject
        # wrong ownership/data PC rather than fabricating a callable target.
        global OWNER, END, KNOWN
        KNOWN = {
            0x830EBE74: ("bne cr6,0x830ebe14", "cmplwi cr6,r27,0"),
        }
        OWNER = discover_owner(args.ppc_dir, 0x830EBE74, KNOWN[0x830EBE74])
        END = 0
        additional = generate(args.ppc_dir)
        report = {"owners": [report, additional],
                  "new_native_entries": report["new_native_entries"] +
                                        additional["new_native_entries"],
                  "interpreter": False, "jit": False}
    except ValueError as error:
        raise SystemExit(f"REFUSING_UNVERIFIED_GLOBAL_OWNER_CONTINUATION: {error}")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+"\n")
    print("XOWUE_VERIFIED_OWNER_WIDE_AOT " + json.dumps(report))
if __name__ == "__main__": main()
