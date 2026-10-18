#!/usr/bin/env python3
"""Require every GOWA2 native game AOT symbol in the final Apple Mach-O."""
import argparse
from pathlib import Path
import re

PAT = re.compile(r'^\s*[0-9a-fA-F]*\s+[Tt]\s+(_?ar_gowa2_game_ppu_[0-9a-f]{8})$',re.M)

def verify(symbols_txt, nm_txt):
 required=symbols_txt.read_text().splitlines()
 if len(required)!=6251 or len(set(required))!=6251:raise ValueError('expected 6251 unique GOWA2 functions in symbols.txt')
 found={m.lstrip('_') for m in PAT.findall(nm_txt.read_text())}
 missing=sorted(set(required)-found)
 if missing:raise ValueError(f'{len(missing)} GOWA2 ARM64 functions missing from final Mach-O: {missing[:8]}')
 print(f'GOWA2 ARM64 FINAL MACH-O: {len(required)} / {len(required)} required native functions present; no iPhone execution implied')

if __name__=='__main__':
 ap=argparse.ArgumentParser()
 ap.add_argument('manifest',type=Path)
 ap.add_argument('nm',type=Path)
 args=ap.parse_args()
 verify(args.manifest,args.nm)