#!/usr/bin/env python3
"""Turn remaining silent stubs/no-op sites into fatal diagnostics in private C lift.
Does NOT implement their semantics. The correct application stays non-playable
until these traps are removed by proven translations/runtime fixes.
"""
import argparse, pathlib, re, json
ap=argparse.ArgumentParser()
ap.add_argument('--gen',type=pathlib.Path,required=True)
ap.add_argument('--output-json',type=pathlib.Path,required=True)
a=ap.parse_args()
stub=a.gen/'recomp_stubs_unresolved.c'
header=a.gen/'recomp_types.h'
s=stub.read_text('utf-8');h=header.read_text('utf-8')
pattern=re.compile(r'(?m)^(void sub_([0-9A-F]{8})\(void\)) \{ g_esp \+= (\d+); /\* 0x[0-9A-F]{8}: (?:not detected|ret \d+) \*/ \}$')
def guard(m):return f'{m[1]} {{ fprintf(stderr, "PoPTST FATAL: unimplemented guest target 0x{m[2]}\\n"); abort(); }}'
s,count=pattern.subn(guard,s)
if count!=39:raise SystemExit(f'FAIL: expected 39 remaining stubs, found {count}')
if '#include <stdio.h>' not in s:
 s=s.replace('#include "recomp_funcs.h"','#include "recomp_funcs.h"\n#include <stdio.h>\n#include <stdlib.h>',1)
needle='#define RECOMP_UNIMPL(_text, _va) recomp_unimpl((_text), (_va))'
assert h.count(needle)==1
h=h.replace(needle,needle+'''

/* PoPTST fail-closed mode: a recorded-but-ignored opcode may never silently
 * allow game execution to continue. Activate with -DPOPTST_FAIL_CLOSED_LIFT.
 * This is an audit guard, not an implementation of that x86 instruction. */
#ifndef POPTST_FAIL_CLOSED_LIFT
#error "PoPTST audited lift requires -DPOPTST_FAIL_CLOSED_LIFT (unimplemented x86 instructions must trap)"
#endif
#undef RECOMP_UNIMPL
#define RECOMP_UNIMPL(_text, _va) do { \\
    recomp_unimpl((_text), (_va)); \\
    __builtin_trap(); \\
} while (0)''',1)
stub.write_text(s,'utf-8');header.write_text(h,'utf-8')
result={'silent_stubs_replaced_by_fatal_diagnostics':count,'unimplemented_opcode_sites':725,'compile_flag':'-DPOPTST_FAIL_CLOSED_LIFT','note':'Fatal traps are guards; these are not x86 opcode implementations.'}
a.output_json.write_text(json.dumps(result,indent=2)+'\n','utf-8')
print(json.dumps(result))
