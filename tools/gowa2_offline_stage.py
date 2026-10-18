#!/usr/bin/env python3
"""Restore, authenticate and inventory the nine owner-derived AOT C sources.

Only C translation output is stored in GitHub, as deterministic gzip/base64.
The original GOWA.ELF is never uploaded, reconstructed or included in IPA.
"""
import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path
import re

SOURCE_SHA256 = '4bf75c897b82d1beb25514cbadaff3d03e1b0c7bf849fa5d289be4f9183462b5'
MANIFEST_SHA = {
 '00':'8f45ba5a8885ad82016ef5ab4bd283038381041c2d7404debf7c6737b0223baf',
 '01':'444c87023f3f64ea6114f93e9ce77fac267fd105d107fec3e0a28a1cd1555ab4',
 '02':'18958deb810ee064118406646981eadbc21680fcacd07ba575952c8de4e5c7f6',
 '03':'9e8e1ae8fe1e5515253010a8652a738a438f3bab43c6528a5660d4abd3bdb3dd',
 '04':'4368c44f87e27c34926e349f61c7c8f1cfe2b16a165a3bda71c3bf634e34601b',
 '05':'f5e7b3df17db9b4c4d540c88a84124b672360b8dfd0dfe4af67bb755d96885e1',
 '06':'385b9d2b2b113b402aae85a529843f320a32405753278180acf3cceca1ca8b51',
 '07':'2c5f573840c3f888d9b562ce4a542939bb534ef785e9404f4b00e352a504c931',
 '08':'49004a98ceffd7a9be33fef0a06489f929958bd3d79690f3a9b5efa16fa6aabc',
}
SYM = re.compile(rb'\bint\s+(ar_gowa2_game_ppu_[0-9a-f]{8})\s*\(ppu_ctx\s*\*c\s*\)')
REG = re.compile(rb'ar_register\s*\(\s*UINT32_C\s*\(0x[0-9a-fA-F]+\)\s*,\s*(ar_gowa2_game_ppu_[0-9a-f]{8})\)')

def decode(blob):
 return gzip.decompress(base64.b64decode(blob,validate=False))

def stage(source, dest):
 dest.mkdir(parents=True, exist_ok=True)
 expected_syms=decode((source/'symbols.txt.gz.b64').read_bytes()).decode().splitlines()
 assert len(expected_syms)==6251 and len(set(expected_syms))==6251, 'bad symbol manifest'
 seen=[]
 report=[]
 for n, sha in MANIFEST_SHA.items():
  name=f'ppu_gowa2_offline_aot_{n}.c'
  raw=decode((source/(name+'.gz.b64')).read_bytes())
  digest=hashlib.sha256(raw).hexdigest()
  assert digest==sha, f'{name} SHA-256 mismatch: {digest} != {sha}'
  funcs=[s.decode() for s in SYM.findall(raw)]
  regs=[s.decode() for s in REG.findall(raw)]
  assert set(funcs)==set(regs) and len(funcs)==len(regs) and len(funcs)==len(set(funcs)), f'{name} functions and registrations differ'
  (dest/name).write_bytes(raw)
  seen+=funcs
  report.append({'file':name,'sha256':sha,'functions':len(funcs),'size':len(raw)})
 assert len(seen)==6251 and len(set(seen))==6251, 'duplicate/missing functions across chunks'
 assert set(seen)==set(expected_syms), 'symbols.txt differs from decoded C definitions'
 (dest/'symbols.txt').write_text('\n'.join(expected_syms)+'\n')
 summary={'schema':'gowa2-aot-ios-staging-v1','source_elf_sha256':SOURCE_SHA256,'generated_modules':9,'generated_functions':len(seen),'translated_ppc_instructions':221061,'rejected_candidates':1237,'files':report}
 (dest/'stage-report.json').write_text(json.dumps(summary,indent=2)+'\n')
 print('GOWA2 AOT STAGE OK: 9 SHA-256-valid modules; 6251 unique functions and registrations; 221061 translated PPC instructions; no ELF bundled')

if __name__=='__main__':
 ap=argparse.ArgumentParser()
 ap.add_argument('--source',type=Path,default=Path('runtime/gowa2-offline'))
 ap.add_argument('--dest',type=Path,default=Path('ios-probe/gowa2-staged'))
 args=ap.parse_args()
 stage(args.source,args.dest)