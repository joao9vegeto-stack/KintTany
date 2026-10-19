#!/usr/bin/env python3
"""Original NPUA80918 PPC64 42-word 0x002C1378..0x002C141C span.

The nested BL at PC 0x002C13D0 targets existing AOT 0x0052B840.
The PPC BC at 0x002C141C branches to 0x002C14A4 or 0x002C1420.
Authenticates source words and guest RAM; never interprets PPC in production.
"""
from __future__ import annotations
import argparse
import hashlib
import re
import struct
from pathlib import Path
from ppu_cfg_lifter import lift, PPUImage, Unsupported

PC = 0x002C1378
END = 0x002C1420
OWNER_SHA = "4bf75c897b82d1beb25514cbadaff3d03e1b0c7bf849fa5d429be4f9183462b5"
BE_SHA = "c774d62f601ddcae1dc2582840cd3f9c5ec3315ddaf45346c82092775e4c05ea"
WORDS = (
    0x60000000,0x3c800084,0x607e0000,0x3ca00002,
    0x30de0020,0x60a5d1e4,0x8064b0a8,0x3b200000,
    0x80630008,0x907e1c4c,0x8064b0a8,0x63840000,
    0x80e3000c,0x81030004,0x7ce700d0,0x78c30020,
    0x90be0000,0x7cc83810,0x933e001c,0x38a0001f,
    0x30c60200,0x90de1c50,0x4826a471,0x60000000,
    0x3c600085,0x9b3e003f,0x7c9fd014,0x5766053e,
    0x3084fffc,0x2c060000,0x80a3ae5c,0x90be000c,
    0x93c3ae5c,0x93fe0010,0x909e0018,0x93fe0014,
    0x93fe0004,0x93fe0008,0x83bdb0ac,0x90de1c44,
    0x7fbdf810,0x41820088,
)
assert len(WORDS) == 42 and PC+len(WORDS)*4 == END
assert hashlib.sha256(struct.pack('>42I',*WORDS)).hexdigest() == BE_SHA

OWNER_CPP = r"""
/* Verifies the SAME executable PT_LOAD and actual mapped guest instruction
 * bytes. Runtime never decodes/executes PPC. Registers one compiled C
 * function on the real iOS dispatch table (the C is compiled to ARM64).
 */
#include "ppu_bridge.h"
#include <stddef.h>
#include <stdint.h>
extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);
static const uint32_t ar_m759_expected[42] = {
__WORDS__
};
int ar_m759_register_owner(const uint8_t*elf,size_t len){
 if(!elf||len<64u)return AR_BAD_ARGS;
 for(unsigned off=0u;off<42u;off+=4u){
  uint32_t window[6]={0};
  const uint32_t base=UINT32_C(0x002c1378)+off*4u;
  if(ar_m712_exec_window(elf,len,base,window)!=AR_OK||
     window[4]<(42u-off<4u?42u-off:4u)||!(window[5]&1u))return AR_BAD_ARGS;
  for(unsigned j=0;j<(42u-off<4u?42u-off:4u);j++){
   const uint32_t addr=base+j*4u;
   const uint32_t source=ar_m759_expected[off+j];
   if(window[j]!=source||ar_read32(addr)!=source||
      ar_last_error()!=AR_OK)return AR_BAD_ARGS;
  }
 }
 return ar_register(UINT32_C(0x002c1378),ar_m759_native_002c1378);
}
"""

def check_original_elf(path:Path)->None:
    data=path.read_bytes()
    digest=hashlib.sha256(data).hexdigest()
    if digest!=OWNER_SHA:
        raise RuntimeError(f'Owner ELF SHA mismatch; expected={OWNER_SHA} got={digest}')
    image=PPUImage(path)
    if tuple(image.words(PC,END))!=WORDS:
        raise RuntimeError('The owner PPC executable PT_LOAD bytes do not match.')

def generate()->tuple[str,dict]:
    source,hist=lift(WORDS,PC,'ar_m759_native_002c1378',allow_terminal_conditional=True)
    if hist.get('b/bl',0)!=1 or hist.get('bc',0)!=1 or not source.endswith('\n}\n'):
        raise RuntimeError('Unexpected control-flow shape in owner compiler.')
    if ('c->cia=0x2c14a4ULL; return 1;' not in source or
            'c->cia=0x2c1420ULL; return 1;' not in source):
        raise RuntimeError('The unconditional PPC branch destination changed.')
    # Fail-closed on guest RAM faults; the generic prototype currently emits
    # load/store statements without checking guest VM status after each one.
    if re.search(r'\bgoto\s+L_',source):
        raise RuntimeError('Unexpected internal goto in linear 42-PPC segment')
    lines=[]
    memory_ops=0
    for line in source.splitlines():
        if re.match(r'\s*L_[0-9a-f]+:\s*;\s*$',line):
            continue  # No local GOTOs: unused PPC labels can trigger -Werror.
        lines.append(line)
        if (re.search(r'\bar_(?:write(?:8|16|32|64)|read(?:8|16|32|64))\(',line)
                and not line.startswith('extern ')):
            # Only emitted CALL statements should reach this point.
            if not line.strip().endswith(';'):
                raise RuntimeError('Unexpected lift memory op syntax.')
            lines.append('    if(ar_last_error()!=AR_OK) return AR_MEM_FAULT;')
            memory_ops+=1
    if memory_ops<10:
        raise RuntimeError('Expected real guest loads/stores in 42-word span.')
    code='\n'.join(lines)+'\n'
    code='#include "ppu_bridge.h"\n'+code
    generated_words=','.join(f'UINT32_C(0x{w:08x})' for w in WORDS)
    code+='\n'+OWNER_CPP.replace('__WORDS__',generated_words)
    return code,{'number_words':len(WORDS),'guest_memory_ops':memory_ops,
                 'isa_histogram':hist,'pc':f'0x{PC:08x}','next_pc':'0x002c14a4',
                 'word_sha256':BE_SHA}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--verify-elf',type=Path)
    a=p.parse_args()
    if a.verify_elf:check_original_elf(a.verify_elf)
    code,details=generate()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(code)
    print('M7.59 PPC64->ARM64 offline AOT owner span:',details)

if __name__=='__main__':
    main()
