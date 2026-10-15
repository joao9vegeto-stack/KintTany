#!/usr/bin/env python3
"""Synthetic-only PowerPC branch to PS3 import stub. No game code."""
from pathlib import Path
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from ppu_cfg_lifter import lift
def make(out):
    # Save LR, li r3,0x800; linked call 0x10220; restore LR; return.
    words=[0x7c0802a6,0x38600800,0x48000019,0x7c0803a6,0x4e800020]
    src,_=lift(words,0x10200,'ppu_f_00010200')
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(src)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();make(a.out)
