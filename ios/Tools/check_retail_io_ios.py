#!/usr/bin/env python3
"""Build18: fail CI if verified D3D8 x86 port I/O sites are unpatched."""
from pathlib import Path
import sys
root=Path(sys.argv[1])
h=(root/'source/xbox-retail/gen/recomp_types.h').read_text()
d=(root/'source/xbox-retail/gen/xdk/d3d8/d3d8_0000.c').read_text()
e=(Path(__file__).resolve().parents[1]/'Native/poptst_engine.c').read_text()
m=(root/'port/game/recomp_manual.c').read_text()
assert '#define RECOMP_UNIMPL(_text, _va) do {' in h
for opcode,vas in {
  'out dx, al':['00373580'],
  'in al, dx':['0037246C','0037266D'],
  'wbinvd':['00371224'],
}.items():
  for va in vas:
    assert d.count(f'RECOMP_UNIMPL("{opcode}", 0x{va}u)')==1
    assert f'case 0x{va}u:' in h
assert 'default: \\' in h and '__builtin_trap();' in h
for fn in ('poptst_guest_out8','poptst_guest_in8','poptst_guest_wbinvd'):
  assert f'{fn}(' in h and f'{fn}(' in e
assert 'FATAL: unsupported Xbox x86 opcode VA=' in m
assert '0x80C0u' in e and 'atomic_thread_fence(memory_order_seq_cst)' in e
print('PASS B18: exact retail video port I/O, cache fence and failclosed unknowns')
