#!/usr/bin/env python3
"""Synthetic PPU nested call smoke: no Sony/game bytes."""
from pathlib import Path
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from ppu_cfg_lifter import lift
def generate(dest):
  main=[0x7c0802a6,0x38600005,0x4800001d,0x38630002,0x7c0803a6,0x4e800020]
  assert main[2]&0x3fffffc==0x1c
  sources=[lift(words,addr,f'ppu_f_{addr:08x}')[0] for addr,words in
      [(0x10000,main),(0x10024,[0x38630007,0x4e800020]),(0x10100,[0x48000100])]]
  prefix=sources[0].split('int ppu_f_',1)[0]
  dest.parent.mkdir(parents=True,exist_ok=True)
  dest.write_text(prefix+'\n'.join('int ppu_f_'+s.split('int ppu_f_',1)[1] for s in sources))
  return len(sources)
if __name__=='__main__':
  p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path)
  a=p.parse_args();print('Synthetic functions:',generate(a.out))
