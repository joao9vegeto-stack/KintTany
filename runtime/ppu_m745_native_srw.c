/* M7.45: static C->Apple ARM64 owner PPC block 0x0052BA70.
 * Original words: SRW, CMPWI, ANDC, ADDI, STW, BC. Not an interpreter.
 * Register only AFTER signed GOWA.ELF SHA validation. */
#include <stdint.h>
#include <stddef.h>
#include "ppu_bridge.h"
extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);
#define PC745 UINT32_C(0x0052ba70)
static const uint32_t owner[6]={0x7d290430u,0x2f870000u,0x7d694878u,
                                  0x39430004u,0x91230000u,0x419e0030u};
int ar_m745_native_0052ba70(ppu_context *c){
 if(!c)return AR_BAD_ARGS;
 uint64_t *r=c->gpr;
 /* srw r9,r9,r0: shift low word, six-bit shift field. */
 const unsigned sh=(unsigned)r[0]&63u;
 const uint32_t rs=(uint32_t)r[9];
 r[9]=sh>=32u?0u:(uint64_t)(rs>>sh);
 /* cmpdi cr7,r7,0, CR7.SO follows sticky XER.SO. */
 const uint32_t nib=(int32_t)(uint32_t)r[7]<0?8u:(uint32_t)r[7]?4u:2u;
 c->cr=(c->cr&~UINT32_C(15))|nib|((c->xer>>31)&1u);
 /* andc r9,r11,r9; addi r10,r3,4; stw r9,0(r3) */
 r[9]=r[11]&~r[9];
 r[10]=r[3]+UINT64_C(4);
 ar_write32(r[3],(uint32_t)r[9]);
 if(ar_last_error()!=AR_OK)return AR_MEM_FAULT;
 /* beq cr7,+0x30: BO=12,BI=30; LR and CTR preserved. */
 c->cia=(c->cr&2u)?UINT32_C(0x0052bab4):UINT32_C(0x0052ba88);
 return AR_TAIL;
}
int ar_m745_register_owner(const uint8_t*elf,size_t len){
 if(!elf||len<64u)return AR_BAD_ARGS;
 for(unsigned offset=0;offset<6u;offset+=4u){
   uint32_t w[6]={0};
   const unsigned n=(6u-offset<4u)?6u-offset:4u;
   const uint32_t addr=PC745+offset*4u;
   if(ar_m712_exec_window(elf,len,addr,w)!=AR_OK||
      w[4]<n||!(w[5]&1u))return AR_BAD_ARGS;
   for(unsigned i=0;i<n;i++)
     if(w[i]!=owner[offset+i]||
        ar_read32(addr+i*4u)!=owner[offset+i]||
        ar_last_error()!=AR_OK)return AR_BAD_ARGS;
 }
 return ar_register(PC745,ar_m745_native_0052ba70);
}
