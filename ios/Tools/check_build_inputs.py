#!/usr/bin/env python3
from pathlib import Path
import hashlib,sys
root=Path(sys.argv[1])
expected='4ee36260e71d39fd8b02028fd614b1907a0d451b'
from subprocess import check_output
sha=check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
assert sha==expected,(sha,expected)
gen=root/'source/xbox-retail/gen'
cs=list(gen.rglob('*.c'))
assert len(cs)>=70, f'retail generation missing: {len(cs)} C units'
assert (gen/'recomp_dispatch.c').exists() and (gen/'recomp_funcs.h').exists()
assert (root/'source/xbox-retail/target_hooks.c').exists()
assert not any((root/q).exists() for q in ['Assets/xbox-demo/default.xbe','Assets/xbox-retail/default.xbe']), 'No game binary in Actions'
print('PoPTST: verified upstream commit, retail C:',len(cs),'and no XBE files')
