#!/usr/bin/env python3
"""Audit all AOT PPC BCTR paths, without inventing interpreter fallbacks."""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

FUNC = re.compile(r'PPC_FUNC_IMPL\\(__imp__(sub_[0-9A-Fa-f]+)\\) \\{\\n')
BCTR = re.compile(r'(?m)^\\s*// bctr\\s*$')
NATIVE = 'switch (ctx.ctr.u32) {'
UNRESOLVED = 'PPC_CALL_INDIRECT_FUNC(ctx.ctr.u32);'
REQUIRED = {
    'sub_82B47360': 1,
    'sub_82D2D0A8': 2,
    'sub_82D34268': 1,
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ppc-dir', required=True, type=Path)
    parser.add_argument('--json-out', required=True, type=Path)
    args = parser.parse_args()
    units = sorted(args.ppc_dir.glob('ppc_recomp.*.cpp'))
    if len(units) != 344:
        raise SystemExit('Unexpected native PPC AOT unit count')
    totals = Counter()
    records = []
    for file in units:
        source = file.read_text('utf-8')
        funcs = list(FUNC.finditer(source))
        totals['native_functions'] += len(funcs)
        for i, match in enumerate(funcs):
            end = funcs[i+1].start() if i+1 < len(funcs) else len(source)
            body = source[match.end():end]
            bctr = len(BCTR.findall(body))
            indirect = body.count(UNRESOLVED)
            native = body.count(NATIVE)
            totals['bctr_instruction_comments'] += bctr
            totals['indirect_call_sites_still_present'] += indirect
            totals['native_local_switches'] += native
            if native or indirect:
                records.append(dict(owner=match[1], unit=file.name,
                                    bctr=bctr, indirect=indirect, native=native))
    for owner, count in REQUIRED.items():
        matched = [r for r in records if r['owner'].lower() == owner.lower()]
        if len(matched) != 1 or matched[0]['native'] < count:
            raise SystemExit(f'REQUIRED_NATIVE_SWITCH_MISSING {owner}: {matched}')
    result = dict(scope='all 344 native PPC units', totals=dict(totals),
                  caveat='Remaining indirect calls may be valid cross-function branches',
                  all_indirect=records)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(result,indent=2))
    print('PPC_GLOBAL_DISPATCH_AUDIT ' + json.dumps(totals))

if __name__ == '__main__':
    main()
