/* M7.32: authenticated nine-instruction PowerPC64 guest routine compiled
 * as a genuine iOS ARM64 function. Observed in the user's M7.31 trace:
 * 0x005230e0..0x00523100, ending at the LV2 #144 call instruction
 * 0x00523104. No interpreter and NO game ELF bytes in this source.
 *
 * Only register this entry after the existing private SHA-256 identity gate
 * passed, then verify every executable PPC word against the original ELF
 * file and loaded guest instructions. A mismatch fails closed.
 */
#include <stdint.h>
#include <stddef.h>
#include "ppu_bridge.h"
extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);
#define FIRST UINT32_C(0x005230e0)
#define SYSCALL_PC UINT32_C(0x00523104)
int ar_m732_native_005230e0(ppu_context *c){
 if(!c)return AR_BAD_ARGS;
 /* stdu r1,-160(r1): store the OLD SP then update it iff store succeeds. */
 const uint64_t new_sp=c->gpr[1]-UINT64_C(160);
 ar_write64(new_sp,c->gpr[1]);
 if(ar_last_error()!=AR_OK)return AR_MEM_FAULT;
 c->gpr[1]=new_sp;
 /* mflr r0; std r28,128(r1); std r29,136(r1); mr r28,r3 */
 c->gpr[0]=c->lr;
 ar_write64(new_sp+UINT64_C(128),c->gpr[28]);
 if(ar_last_error()!=AR_OK)return AR_MEM_FAULT;
 ar_write64(new_sp+UINT64_C(136),c->gpr[29]);
 if(ar_last_error()!=AR_OK)return AR_MEM_FAULT;
 c->gpr[28]=c->gpr[3];
 /* std r0,176(r1); addi r4,r1,116; addi r3,r1,112 */
 ar_write64(new_sp+UINT64_C(176),c->gpr[0]);
 if(ar_last_error()!=AR_OK)return AR_MEM_FAULT;
 c->gpr[4]=new_sp+UINT64_C(116);
 c->gpr[3]=new_sp+UINT64_C(112);
 /* li r11,144. Dispatch real LV2 handler on next guest step. */
 c->gpr[11]=UINT64_C(144);
 c->cia=SYSCALL_PC;
 return AR_TAIL;
}
int ar_m732_register_block(const uint8_t *elf,size_t size){
 if(!elf)return AR_BAD_ARGS;
 static const uint32_t expected[9]={
  UINT32_C(0xf821ff61),UINT32_C(0x7c0802a6),
  UINT32_C(0xfb810080),UINT32_C(0xfba10088),
  UINT32_C(0x7c7c1b78),UINT32_C(0xf80100b0),
  UINT32_C(0x38810074),UINT32_C(0x38610070),
  UINT32_C(0x39600090)
 };
 for(unsigned i=0;i<9u;i+=4u){
   uint32_t got[6]={0};
   if(ar_m712_exec_window(elf,size,FIRST+4u*i,got)!=AR_OK ||
      !(got[5]&1u)||got[4]<(9u-i<4u?9u-i:4u))
       return AR_BAD_ARGS;
   for(unsigned j=0;j<got[4]&&j<9u-i;j++){
     if(got[j]!=expected[i+j])return AR_BAD_ARGS;
     if(ar_read32(FIRST+4u*(i+j))!=expected[i+j] ||
        ar_last_error()!=AR_OK)return AR_BAD_ARGS;
   }
 }
 /* Verify the next instruction is truly the LV2 syscall. */
 uint32_t sc[6]={0};
 if(ar_m712_exec_window(elf,size,SYSCALL_PC,sc)!=AR_OK ||
    !(sc[5]&1u)||sc[4]<1u||sc[0]!=UINT32_C(0x44000002)||
    ar_read32(SYSCALL_PC)!=UINT32_C(0x44000002)||
    ar_last_error()!=AR_OK)return AR_BAD_ARGS;
 return ar_register(FIRST,ar_m732_native_005230e0);
}
