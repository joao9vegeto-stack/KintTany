/* M7.56: 7 REAL original NPUA80918 PPC instructions, AOT-only ARM64.
 * PC 0x003C4FC4..0x003C4FDC inclusive. Both BEQ successors preserved.
 * Authenticate TWO PT_LOAD X windows plus exact mapped guest bytes.
 */
#include <stdint.h>
#include <stddef.h>
#include "ppu_bridge.h"
extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);
#define CA UINT32_C(0x20000000)
int ar_m756_aot_003c4fc4(ppu_context*c){
 if(!c)return AR_BAD_ARGS;
 const uint64_t r9=c->gpr[9],r7=c->gpr[7];
 /* 30C90004  addic r6,r9,4 -- PPC64 carry, no CR0 modification. */
 c->gpr[6]=r9+UINT64_C(4);
 c->xer=(c->xer&~CA)|((c->gpr[6]<r9)?CA:0u);
 /* 7CC63B96 divwu r6,r6,r7; unsigned 32-bit quotient. */
 const uint32_t divisor=(uint32_t)r7;
 if(!divisor){c->cia=UINT32_C(0x003c4fc8);return AR_PPC_UNSUPPORTED;}
 c->gpr[6]=(uint64_t)((uint32_t)c->gpr[6]/divisor);
 /* 7CC639D6 mullw r6,r6,r7; signed word result sign extended. */
 const uint32_t word=(uint32_t)((uint64_t)(uint32_t)c->gpr[6]*(uint32_t)r7);
 c->gpr[6]=(uint64_t)(int64_t)(int32_t)word;
 /* 7CC64810 subfc r6,r6,r9 = r9-r6; XER.CA reflects no borrow. */
 const uint64_t r6=c->gpr[6],diff=r9-r6;
 c->gpr[6]=diff;
 c->xer=(c->xer&~CA)|((r9>=r6)?CA:0u);
 /* 30C60004 addic r6,r6,4, recomputing XER.CA. */
 c->gpr[6]=diff+UINT64_C(4);
 c->xer=(c->xer&~CA)|((c->gpr[6]<diff)?CA:0u);
 /* 2C060000 cmpwi cr0,r6,0 (SIGNED low word; XER.SO sticky). */
 const int32_t cmp=(int32_t)(uint32_t)c->gpr[6];
 const uint32_t nibble=(cmp<0?8u:cmp>0?4u:2u)|((c->xer>>31)&1u);
 c->cr=(c->cr&UINT32_C(0x0fffffff))|(nibble<<28);
 /* 41820008 beq cr0,+8 ; target 4FE4, fallthrough 4FE0. */
 c->cia=(c->cr & UINT32_C(0x20000000)) ?
         UINT32_C(0x003c4fe4) : UINT32_C(0x003c4fe0);
 return AR_TAIL;
}
int ar_m756_register_divloop(const uint8_t*elf,size_t len){
 if(!elf||len<64u)return AR_BAD_ARGS;
 static const uint32_t expected[7]={
  UINT32_C(0x30c90004),UINT32_C(0x7cc63b96),
  UINT32_C(0x7cc639d6),UINT32_C(0x7cc64810),
  UINT32_C(0x30c60004),UINT32_C(0x2c060000),
  UINT32_C(0x41820008)
 };
 for(unsigned group=0;group<2u;group++){
  const uint32_t at=UINT32_C(0x003c4fc4)+16u*group;
  uint32_t win[6]={0};
  const unsigned available=group?3u:4u;
  if(ar_m712_exec_window(elf,len,at,win)!=AR_OK||
     win[4]<available||!(win[5]&1u))return AR_BAD_ARGS;
  for(unsigned i=0;i<available;i++){
   const uint32_t pc=at+4u*i,expected_word=expected[group*4u+i];
   if(win[i]!=expected_word||ar_read32(pc)!=expected_word||
      ar_last_error()!=AR_OK)return AR_BAD_ARGS;
  }
 }
 return ar_register(UINT32_C(0x003c4fc4),ar_m756_aot_003c4fc4);
}
