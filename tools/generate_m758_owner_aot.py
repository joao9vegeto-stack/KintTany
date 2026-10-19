#!/usr/bin/env python3
"""Emit one authenticated owner PPC64->C->Apple ARM64 AOT span.

GOWA NPUA80918, original ELF SHA-256:
4bf75c897b82d1beb25514cbadaff3d03e1b0c7bf849fa5d289be4f9183462b5
Owner raw 28 PPC64 words SHA-256 (BE):
891703e2b7c9a7ea6b108e93b7f257b80bb1bff141da0aea1536fe76d3623ee7
Ghidra classifies PC 0x003C5110 inside FUN_003C500C (0x003C500C..0x003C5217).
No CELl FS invocation is inferred by this span; sys_fs awaits physical evidence.
"""
from __future__ import annotations
import argparse
import hashlib
import re
import struct
from pathlib import Path
from ppu_cfg_lifter import lift, PPUImage, Unsupported

PC = 0x003C5110
END = 0x003C5180
OWNER_SHA = "4bf75c897b82d1beb25514cbadaff3d03e1b0c7bf849fa5d289be4f9183462b5"
BE_SHA = "891703e2b7c9a7ea6b108e93b7f257b80bb1bff141da0aea1536fe76d3623ee7"
WORDS = (
    0x7c7ff014,0x3c808000,0x7c7b1810,0x5384c04a,
    0x5465013a,0x5463f1be,0x7cbb2814,0x5484000a,
    0x30a5fffc,0x53a4f1be,0x78a50020,0x907b0000,
    0x5486467a,0x90650000,0x7c7f3014,0x909f0000,
    0x7cbfe014,0x78630020,0x90830000,0x809f0000,
    0x30650004,0x5485113a,0x78630020,0x7cbf2814,
    0x30a5fffc,0x78a50020,0x90850000,0x48000078
)
assert len(WORDS) == 28 and PC+len(WORDS)*4 == END
assert hashlib.sha256(struct.pack('>28I',*WORDS)).hexdigest() == BE_SHA

OWNER_CPP = r"""
/* Verifies the SAME executable PT_LOAD and actual mapped guest instruction
 * bytes. Runtime never decodes/executes PPC. Registers one compiled C
 * function on the real iOS dispatch table (the C is compiled to ARM64).
 */
#include "ppu_bridge.h"
#include <stddef.h>
#include <stdint.h>
extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);
static const uint32_t ar_m758_expected[28] = {
__WORDS__
};
int ar_m758_register_owner(const uint8_t*elf,size_t len){
 if(!elf||len<64u)return AR_BAD_ARGS;
 for(unsigned off=0u;off<28u;off+=4u){
  uint32_t window[6]={0};
  const uint32_t base=UINT32_C(0x003c5110)+off*4u;
  if(ar_m712_exec_window(elf,len,base,window)!=AR_OK||
     window[4]<4u||!(window[5]&1u))return AR_BAD_ARGS;
  for(unsigned j=0;j<4u;j++){
   const uint32_t addr=base+j*4u;
   const uint32_t source=ar_m758_expected[off+j];
   if(window[j]!=source||ar_read32(addr)!=source||
      ar_last_error()!=AR_OK)return AR_BAD_ARGS;
  }
 }
 return ar_register(UINT32_C(0x003c5110),ar_m758_native_003c5110);
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
    source,hist=lift(WORDS,PC,'ar_m758_native_003c5110')
    if hist.get('b/bl',0)!=1 or not source.endswith('\n}\n'):
        raise RuntimeError('Unexpected control-flow shape in owner compiler.')
    if 'c->cia=0x3c51f4ULL; return 1;' not in source:
        raise RuntimeError('The unconditional PPC branch destination changed.')
    # Fail-closed on guest RAM faults; the generic prototype currently emits
    # load/store statements without checking guest VM status after each one.
    if re.search(r'\bgoto\s+L_',source):
        raise RuntimeError('Unexpected internal goto in linear 28-PPC segment')
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
    if memory_ops<4:
        raise RuntimeError('Expected real guest loads/stores in 28-word span.')
    code='\n'.join(lines)+'\n'
    code='#include "ppu_bridge.h"\n'+code
    generated_words=','.join(f'UINT32_C(0x{w:08x})' for w in WORDS)
    code+='\n'+OWNER_CPP.replace('__WORDS__',generated_words)
    return code,{'number_words':len(WORDS),'guest_memory_ops':memory_ops,
                 'isa_histogram':hist,'pc':f'0x{PC:08x}','next_pc':'0x003c51f4',
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
    print('M7.58 PPC64->ARM64 offline AOT owner span:',details)

if __name__=='__main__':
    main()
