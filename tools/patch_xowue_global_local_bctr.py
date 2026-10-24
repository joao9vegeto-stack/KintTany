#!/usr/bin/env python3
"""Lower validated local PPC CTR branches to native CFG throughout the AOT corpus.
Use only pre-existing PPC labels matching exact guest instruction indices.
Never invent instructions, stubs, JIT code or replace unknown cross-function targets.
"""
from __future__ import annotations
import argparse
import bisect
import json
import re
from pathlib import Path

FUNC = re.compile(r'PPC_FUNC_IMPL\(__imp__(sub_[0-9A-Fa-f]+)\) \{\n')
INSN = re.compile(r'(?m)^\t// (.+?)\s*$')
LABEL = re.compile(r'(?m)^loc_([0-9A-Fa-f]+):\s*$')
BCTR = re.compile(r'(?m)^\t// bctr\s*$')
CALL = '\tPPC_CALL_INDIRECT_FUNC(ctx.ctr.u32);\n\treturn;'

def rewrite_owner(body: str, owner: int) -> tuple[str, int, str]:
    if CALL not in body or not BCTR.search(body):
        return body, 0, 'no_direct_bctr'
    comments = list(INSN.finditer(body))
    starts = [x.start() for x in comments]
    if not comments:
        return body, 0, 'no_instruction_comments'
    labels = set()
    for label in LABEL.finditer(body):
        pc = int(label.group(1), 16)
        index = bisect.bisect_left(starts, label.end())
        if pc < owner or ((pc - owner) & 3) or index != (pc - owner) // 4:
            return body, 0, 'unsafe_label_instruction_mapping'
        labels.add(pc)
    if not labels or len(labels) > 512:
        return body, 0, 'no_or_too_many_validated_labels'
    edits = []
    for match in BCTR.finditer(body):
        following = next((x.start() for x in comments if x.start() > match.start()), len(body))
        between = body[match.end():following]
        if between.count(CALL) != 1:
            continue
        arms = ['\tswitch (ctx.ctr.u32) {']
        arms.extend(f'\tcase 0x{pc:08X}u: goto loc_{pc:X};' for pc in sorted(labels))
        arms += ['\tdefault:', '\t\tPPC_CALL_INDIRECT_FUNC(ctx.ctr.u32);',
                 '\t\treturn;', '\t}']
        edits.append((match.end(), following, between.replace(CALL, '\n'.join(arms))))
    if not edits:
        return body, 0, 'no_eligible_indirect_bctr'
    out = body
    for start, end, value in reversed(edits):
        out = out[:start] + value + out[end:]
    return out, len(edits), 'patched'

def rewrite_source(source: str) -> tuple[str, dict]:
    matches = list(FUNC.finditer(source))
    edits = []
    tally = dict(functions=len(matches), functions_patched=0, local_bctr_patched=0, skips={})
    for match in matches:
        end = source.find('\n}\n', match.end())
        if end < 0:
            raise RuntimeError('unterminated native PPC function ' + match.group(1))
        body = source[match.start():end + 3]
        changed, count, reason = rewrite_owner(body, int(match.group(1)[4:], 16))
        if count:
            edits.append((match.start(), end + 3, changed))
            tally['functions_patched'] += 1
            tally['local_bctr_patched'] += count
        elif reason != 'no_direct_bctr':
            tally['skips'][reason] = tally['skips'].get(reason, 0) + 1
    for start, end, changed in reversed(edits):
        source = source[:start] + changed + source[end:]
    return source, tally

def self_test() -> None:
    fixture = ('PPC_FUNC_IMPL(__imp__sub_82000000) {\n'
               '\tint temp = 0;\n'
               'loc_82000000:\n\t// li r3,1\n\tctx.r3.u32 = 1;\n'
               '\t// bctr \n\tPPC_CALL_INDIRECT_FUNC(ctx.ctr.u32);\n\treturn;\n'
               '\t// blr \n\treturn;\n}\n')
    changed, counter = rewrite_source(fixture)
    assert counter['local_bctr_patched'] == 1
    assert 'case 0x82000000u: goto loc_82000000;' in changed
    assert 'default:\n\t\tPPC_CALL_INDIRECT_FUNC(ctx.ctr.u32);' in changed
    again, count2 = rewrite_source(changed)
    assert changed == again and count2['local_bctr_patched'] == 0
    invalid = fixture.replace('loc_82000000:', 'loc_82000004:')
    assert rewrite_source(invalid)[0] == invalid
    print('PASS: safe native PPC CTR CFG, unknown-target guard, and idempotency')

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--ppc-dir', type=Path)
    ap.add_argument('--report', type=Path)
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.ppc_dir or not args.report:
        ap.error('--ppc-dir and --report are required')
    paths = sorted(args.ppc_dir.glob('ppc_recomp.*.cpp'))
    if len(paths) != 344:
        raise SystemExit('expected 344 native AOT units')
    summary = dict(units=len(paths), functions=0, functions_patched=0,
                   local_bctr_patched=0, skips={})
    for path in paths:
        original = path.read_text('utf-8')
        updated, counters = rewrite_source(original)
        for key in ('functions', 'functions_patched', 'local_bctr_patched'):
            summary[key] += counters[key]
        for key, value in counters['skips'].items():
            summary['skips'][key] = summary['skips'].get(key, 0) + value
        if updated != original:
            path.write_text(updated, encoding='utf-8')
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print('XOWUE_GLOBAL_NATIVE_LOCAL_CTR ' + json.dumps(summary))

if __name__ == '__main__':
    main()
