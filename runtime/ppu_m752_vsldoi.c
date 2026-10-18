/* M7.52: native owner PPC VMX VSLDOI at actual iPhone M7.51 frontier.
 * Guest PC 0x003B0608, owner word 0x105FF82C = vsldoi v2,v31,v31,0.
 * Refuse registration unless executable ELF and mapped guest VM agree.
 * Pure signed static PPC->C->ARM64 entry, no JIT or fabricated file I/O.
 */
#include <stddef.h>
#include <stdint.h>
#include "ppu_bridge.h"
#include "ppu_vmx_cell.h"
extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);
int ar_m752_native_003b0608(ppu_context *c){
 if(!c)return AR_BAD_ARGS;
 int rc=ar_vmx_vsldoi(c,2u,31u,31u,0u);
 if(rc!=AR_OK){c->cia=UINT32_C(0x003b0608);return rc;}
 c->cia=UINT32_C(0x003b060c);
 return AR_TAIL;
}
int ar_m752_register_vsldoi(const uint8_t *elf,size_t len){
 if(!elf||len<64u)return AR_BAD_ARGS;
 const uint32_t pc=UINT32_C(0x003b0608),insn=UINT32_C(0x105ff82c);
 uint32_t words[6]={0};
 if(ar_m712_exec_window(elf,len,pc,words)!=AR_OK ||
    words[4]<1u || !(words[5]&1u) || words[0]!=insn ||
    ar_read32(pc)!=insn || ar_last_error()!=AR_OK)return AR_BAD_ARGS;
 uint64_t fnv=UINT64_C(14695981039346656037);
 for(unsigned b=0;b<4u;b++){
  fnv^=(uint8_t)(insn>>(24u-8u*b));
  fnv*=UINT64_C(1099511628211);
 }
 if(fnv!=UINT64_C(0x7cc41e063d73d8dc))return AR_BAD_ARGS;
 return ar_register(pc,ar_m752_native_003b0608);
}
