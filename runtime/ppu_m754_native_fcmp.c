/* M7.54: two real executable PPC words FCMPU+BC.
 * End-to-end guest branch: compare FPR1/FPR31 and respect CR0.GT,
 * taking 0x003B0668 or falling through to 0x003B0654. No fake jump.
 * Each word must match the authenticated PT_LOAD X and mapped guest VM. */
#include <stdint.h>
#include <stddef.h>
#include "ppu_bridge.h"
#include "ppu_fp_scalar.h"
extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);
int ar_m754_native_003b064c(ppu_context*c){
 if(!c)return AR_BAD_ARGS;
 const int rc=ar_fp_compare(c,0u,1u,31u,0);
 if(rc!=AR_OK){c->cia=UINT32_C(0x003b064c);return rc;}
 /* 0x41810018 = bgt cr0,+24; BO=12, BI=1, LK=0, AA=0. */
 c->cia=(c->cr & UINT32_C(0x40000000)) ?
     UINT32_C(0x003b0668) : UINT32_C(0x003b0654);
 return AR_TAIL;
}
int ar_m754_register_fcmp_branch(const uint8_t*elf,size_t len){
 if(!elf||len<64u)return AR_BAD_ARGS;
 const uint32_t pc=UINT32_C(0x003b064c);
 const uint32_t words[2]={UINT32_C(0xfc01f800),UINT32_C(0x41810018)};
 uint32_t code[6]={0};
 if(ar_m712_exec_window(elf,len,pc,code)!=AR_OK ||
    code[4]<2u || !(code[5]&1u))return AR_BAD_ARGS;
 uint64_t hash=UINT64_C(14695981039346656037);
 for(unsigned i=0;i<2u;i++){
  if(code[i]!=words[i]||ar_read32(pc+4u*i)!=words[i]||
     ar_last_error()!=AR_OK)return AR_BAD_ARGS;
  for(unsigned j=0;j<4u;j++){
   hash^=(uint8_t)(words[i]>>(24u-j*8u));
   hash*=UINT64_C(1099511628211);
  }
 }
 if(hash!=UINT64_C(0x81780420618041b4))return AR_BAD_ARGS;
 return ar_register(pc,ar_m754_native_003b064c);
}
