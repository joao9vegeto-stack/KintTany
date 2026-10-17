/* AscensionRecomp M7.36: verified owner-ELF PowerPC64 time conversion
 * continuation at guest 0x00524B8C. One nine-instruction basic block.
 * Registration follows whole-private-ELF SHA gate and validates all words
 * against executable PT_LOAD + live guest BE VM. No original game bytes.
 * This file is compiled as native ARM64; PPC interpreter is distinct.
 */
#include <stdint.h>
#include <stddef.h>
#include "ppu_bridge.h"
extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);
#define PC_START UINT32_C(0x00524b8c)
#define PC_NEXT  UINT32_C(0x00524bb0)
#define PC_TRUE  UINT32_C(0x00524d1c)
#define XER_CA UINT32_C(0x20000000)
static uint64_t sext_word(uint32_t bits){
  return (uint64_t)(int64_t)(int32_t)bits;
}
static uint64_t signed_mulhw(uint64_t a,uint64_t b){
  const int64_t p=(int64_t)(int32_t)(uint32_t)a *
                  (int64_t)(int32_t)(uint32_t)b;
  return sext_word((uint32_t)((uint64_t)p>>32));
}
static uint64_t srawi_one(ppu_context *cpu,uint64_t value){
  const uint32_t v=(uint32_t)value;
  const uint32_t shifted=(v>>1) | (v&UINT32_C(0x80000000));
  const uint32_t carry=((v&UINT32_C(0x80000001))==
                        UINT32_C(0x80000001))?XER_CA:0u;
  cpu->xer=(cpu->xer&~XER_CA)|carry;
  return sext_word(shifted);
}
static void update_cr0(ppu_context *cpu,uint64_t value){
  const uint32_t flag=((int64_t)value<0)?8u:(value?4u:2u);
  const uint32_t bits=flag|((cpu->xer>>31u)&1u);
  cpu->cr=(cpu->cr&UINT32_C(0x0fffffff))|(bits<<28u);
}
int ar_m736_native_00524b8c(ppu_context *cpu){
  if(!cpu)return AR_BAD_ARGS;
  uint64_t *r=cpu->gpr;
  /* PPC mulhw r0,r0,r29: signed 32x32 high 32, sign-extend. */
  r[0]=signed_mulhw(r[0],r[29]);
  /* PPC srawi r0,r0,1 also updates XER.CA, but does not update CR0. */
  r[0]=srawi_one(cpu,r[0]);
  r[0]-=r[9];                         /* sub r0,r0,r9 */
  r[10]=sext_word((uint32_t)r[0]);    /* extsw r10,r0 */
  r[9]=r[10]<<2u;                    /* sldi r9,r10,2 */
  r[0]=r[10]<<4u;                    /* sldi r0,r10,4 */
  r[0]-=r[9];                        /* sub r0,r0,r9 */
  r[4]=r[11]-r[0];                   /* sub. r4,r11,r0 */
  update_cr0(cpu,r[4]);              /* CR0=LT/GT/EQ plus XER.SO */
  /* bt CR0.LT: no LR write and no CTR decrement (BO=12, BI=0). */
  cpu->cia=(cpu->cr&UINT32_C(0x80000000))?PC_TRUE:PC_NEXT;
  return AR_TAIL;
}
int ar_m736_register_owner(const uint8_t *elf,size_t size){
  if(!elf||size<64u)return AR_BAD_ARGS;
  uint64_t h=UINT64_C(14695981039346656037);
  for(uint32_t j=0;j<9u;j+=4u){
    uint32_t window[6]={0};
    const unsigned count=9u-j<4u?9u-j:4u;
    if(ar_m712_exec_window(elf,size,PC_START+j*4u,window)!=AR_OK ||
       window[4]<count || !(window[5]&1u))return AR_BAD_ARGS;
    for(unsigned k=0;k<count;k++){
      const uint32_t w=window[k],pc=PC_START+4u*(j+k);
      if(ar_read32(pc)!=w || ar_last_error()!=AR_OK)return AR_BAD_ARGS;
      for(unsigned q=0;q<4u;q++){
        h^=(uint8_t)(w>>(24u-8u*q));
        h*=UINT64_C(1099511628211);
      }
    }
  }
  if(h!=UINT64_C(0xcb09c1e7aab58409))return AR_BAD_ARGS;
  return ar_register(PC_START,ar_m736_native_00524b8c);
}
