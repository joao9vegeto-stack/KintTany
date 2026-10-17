/* M7.21 genuine Power ISA M/MD rotate+mask regression tests.
 * Synthetic ELF only; no owner game bytes or decrypted source embedded.
 */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
static void be16(uint8_t*p,uint16_t v){p[0]=(uint8_t)(v>>8);p[1]=(uint8_t)v;}
static void be32(uint8_t*p,uint32_t v){
 p[0]=(uint8_t)(v>>24);p[1]=(uint8_t)(v>>16);
 p[2]=(uint8_t)(v>>8);p[3]=(uint8_t)v;
}
static void be64(uint8_t*p,uint64_t v){
 be32(p,(uint32_t)(v>>32));be32(p+4,(uint32_t)v);
}
static uint32_t mform(unsigned op,unsigned rs,unsigned ra,unsigned sh,
                      unsigned mb,unsigned me,unsigned rc) {
 return (op<<26)|(rs<<21)|(ra<<16)|(sh<<11)|(mb<<6)|(me<<1)|rc;
}
static uint32_t mdform(unsigned rs,unsigned ra,unsigned sh,unsigned mb,
                       unsigned xo,unsigned rc){
 return (30u<<26)|(rs<<21)|(ra<<16)|((sh&31u)<<11)|
        ((mb&31u)<<6)|(mb&32u)|(xo<<2)|((sh&32u)>>4)|rc;
}
static int try_step(uint8_t *elf,uint32_t w,ppu_context *ctx) {
 be32(elf+0x200,w);
 if(ar_vm_load(0x1000,elf+0x200,4)!=AR_OK)return -99;
 uint32_t got=0;
 const int rc=ar_ppc_fallback_step(ctx,elf,1024,0x1000,&got);
 if(got!=w){
   uint32_t window[6]={0};
   extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);
   const int read_rc=ar_m712_exec_window(elf,1024,0x1000,window);
   fprintf(stderr,"M7.21 ELF-window mismatch: wanted=0x%08x observed=0x%08x read_rc=%d window_word=0x%08x flags=%u count=%u step_rc=%d e_phoff=%u e_phnum=%u\\n",
     w,got,read_rc,window[0],window[5],window[4],rc,
     (unsigned)elf[39],(unsigned)elf[57]);
   return -98;
 }
 return rc;
}
int main(void) {
 uint8_t elf[1024]={0};
 memcpy(elf,"\177ELF",4);elf[4]=2;elf[5]=2;elf[6]=1;
 be16(elf+16,2);be16(elf+18,21);be32(elf+20,1);
 be64(elf+32,64);be16(elf+54,56);be16(elf+56,1);
 uint8_t*ph=elf+64;be32(ph,1);be32(ph+4,5);
 be64(ph+8,0x200);be64(ph+16,0x100);be64(ph+32,0x100);
 if(ar_bridge_init(0x3000)!=AR_OK)return 1;
 ppu_context c={0};
 /* rlwimi: only the selected bits change, including preserving 64-bit
  * destination bits outside the word mask. */
 c.gpr[3]=UINT64_C(0xab);c.gpr[4]=UINT64_C(0xfeedface12345678);
 const int first_rc=try_step(elf,mform(20,3,4,24,1,5,0),&c);
 if(first_rc!=AR_TAIL || c.gpr[4]!=UINT64_C(0xfeedface2a345678) ||
    c.cia!=0x1004u){
    fprintf(stderr,"M7.21 RLWIMI mismatch: rc=%d r4=0x%016llx expected=0xfeedface2a345678 cia=0x%08llx vm_fault=%d\\n",
        first_rc,(unsigned long long)c.gpr[4],(unsigned long long)c.cia,
        ar_last_error());
    return 2;
 }
 /* Wrapped MASK32 on PPC64 also overwrites high 32 bits per Power ISA;
  * this catches accidental 32-bit-only rlwimi implementations. */
 memset(&c,0,sizeof(c));
 c.gpr[3]=UINT64_C(0x12345678);
 c.gpr[4]=UINT64_C(0xabcdef0100000000);
 if(try_step(elf,mform(20,3,4,0,28,3,0),&c)!=AR_TAIL ||
    c.gpr[4]!=UINT64_C(0x1234567810000008))return 3;
 /* rc=1 sets CR0.EQ and copies XER.SO without clearing rest of CR. */
 memset(&c,0,sizeof(c));c.xer=UINT32_C(0x80000000);
 c.cr=UINT32_C(0x000000f0);
 if(try_step(elf,mform(20,3,4,0,1,5,1),&c)!=AR_TAIL ||
    (c.cr&UINT32_C(0xf0000000))!=UINT32_C(0x30000000) ||
    (c.cr&UINT32_C(0x000000f0))!=UINT32_C(0x000000f0))return 4;
 /* rlwinm zero-extends nonwrapping 32-bit result. */
 memset(&c,0,sizeof(c));
 c.gpr[3]=UINT64_C(0xabcd000012345678);
 if(try_step(elf,mform(21,3,4,8,0,31,0),&c)!=AR_TAIL ||
    c.gpr[4]!=UINT64_C(0x34567812))return 5;
 /* rlwnm: shift comes from low five RB bits, not instruction SH field. */
 memset(&c,0,sizeof(c));c.gpr[3]=UINT64_C(0x12345678);c.gpr[5]=40u;
 if(try_step(elf,mform(23,3,4,5,0,31,0),&c)!=AR_TAIL ||
    c.gpr[4]!=UINT64_C(0x34567812))return 6;
 /* rlwinm with wrapping MB>ME repeats input word across 64 bits. */
 memset(&c,0,sizeof(c));c.gpr[3]=UINT64_C(0x12345678);
 if(try_step(elf,mform(21,3,4,0,28,3,0),&c)!=AR_TAIL ||
    c.gpr[4]!=UINT64_C(0x1234567810000008))return 7;
 /* rldimi inserts selected bits while preserving the remainder. */
 memset(&c,0,sizeof(c));c.gpr[3]=UINT64_C(0xdeadbeefcafefeed);
 c.gpr[4]=UINT64_C(0x1020304050607080);
 if(try_step(elf,mdform(3,4,0,32,3,0),&c)!=AR_TAIL ||
    c.gpr[4]!=UINT64_C(0x10203040cafefeed))return 8;
 /* rldic with immediate shift + mask(8,55). */
 memset(&c,0,sizeof(c));c.gpr[3]=UINT64_C(0xff);
 if(try_step(elf,mdform(3,4,8,8,2,0),&c)!=AR_TAIL ||
    c.gpr[4]!=UINT64_C(0xff00))return 9;
 /* Unknown 64-bit rotate family must still fail closed. */
 memset(&c,0,sizeof(c));c.gpr[4]=UINT64_C(0xdeadbeefcafefeed);
 if(try_step(elf,UINT32_C(0xffffffff),&c)!=AR_PPC_UNSUPPORTED ||
    c.gpr[4]!=UINT64_C(0xdeadbeefcafefeed))return 10;
 ar_bridge_shutdown();
 puts("M7.21 synthetic PPC64 rlwimi/rlwinm/rlwnm/rldic/rldimi masks, CR0 and fail-closed PASS");
 return 0;
}
