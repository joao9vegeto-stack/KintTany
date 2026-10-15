#!/usr/bin/env python3
"""Original synthetic PPC64 code: LI r11,352; LI r3,0x1000; SC; BLR."""
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from ppu_cfg_lifter import lift
def make(out):
 src,_=lift([0x39600160,0x38601000,0x44000002,0x4e800020],0x18000,'ppu_f_00018000')
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(src)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
 a=p.parse_args();make(a.out)
