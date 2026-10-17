/* M7.35 synthetic hardware-independent regression: four native AOT
 * entrypoints compiled from authenticated time/date PPC64, no game files.
 * All expected values were derived separately from PPC 64-bit arithmetic.
 */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
extern int ar_m735_native_0052aab0(ppu_context *);
extern int ar_m735_native_0052abe8(ppu_context *);
extern int ar_m735_native_0052aad8(ppu_context *);
extern int ar_m735_native_0052aad0(ppu_context *);
extern int ar_m735_native_0052aae0(ppu_context *);
extern int ar_m735_native_0052aafc(ppu_context *);
extern int ar_m735_native_0052ab58(ppu_context *);
extern int ar_m735_register_owner(const uint8_t *,size_t);
static int ending(ppu_context *c) {c->cia=c->lr;return AR_OK;}
static void be16(uint8_t *p,uint16_t x){p[0]=(uint8_t)(x>>8);p[1]=(uint8_t)x;}
static void be32(uint8_t *p,uint32_t x){p[0]=x>>24;p[1]=x>>16;p[2]=x>>8;p[3]=x;}
static void be64(uint8_t *p,uint64_t x){be32(p,(uint32_t)(x>>32));be32(p+4,(uint32_t)x);}
struct oracle {uint64_t date,sign;uint32_t output[5];};
static const struct oracle oracles[]={
 {UINT64_C(123456789),0,{9,33,21,99,4}},
 {UINT64_C(0xfffffffff8a432eb),UINT64_MAX,
  {UINT32_C(0xfffffff7),UINT32_C(0xffffffdf),UINT32_C(0xffffffeb),99,4}},
 {UINT64_C(0x8000000000000000),UINT64_MAX,
  {UINT32_C(0xfffffff8),UINT32_C(0xffffffe2),UINT32_C(0xfffffff1),99,4}},
 {UINT64_C(0x7fffffffffffffff),0,{7,30,15,99,4}},
 {0,0,{0,0,0,99,4}}
};
int main(void){
 if(ar_bridge_init(0x600000u)!=AR_OK)return 1;
 if(ar_register(0x0052aafc,ar_m735_native_0052aafc)!=AR_OK ||
    ar_register(0x0052ab58,ar_m735_native_0052ab58)!=AR_OK)return 2;
 for(size_t k=0;k<sizeof(oracles)/sizeof(oracles[0]);k++){
  const struct oracle *a=&oracles[k];
  ppu_context c={0};
  const uint64_t savedlr=UINT64_C(0x12345678);
  const uint64_t sp=0x7000u;
  c.gpr[1]=sp;c.gpr[2]=UINT64_C(0x9aabbccddeeff009);
  c.gpr[28]=0x5000u;c.gpr[26]=a->sign;c.gpr[27]=a->date;
  c.gpr[3]=2u;c.gpr[6]=100u;c.gpr[7]=4u;
  c.lr=UINT64_C(0xaaaaaaaa);c.ctr=UINT64_C(0x11223344);
  c.cr=UINT32_C(0xabcdef12);c.xer=UINT32_C(0xd0000000);
  ar_write64(sp+128,UINT64_C(0x22222222));
  ar_write64(sp+136,UINT64_C(0x55555555));
  ar_write64(sp+144,UINT64_C(0x66666666));
  ar_write64(sp+152,UINT64_C(0x77777777));
  ar_write64(sp+160,UINT64_C(0x88888888));
  ar_write64(sp+168,UINT64_C(0x99999999));
  ar_write64(sp+192,savedlr);
  if(ar_last_error()!=AR_OK)return (int)(10+k);
  if(ar_run(&c,0x0052aafc,80)!=AR_OK)return (int)(20+k);
  for(unsigned i=0;i<5;i++){
     if(ar_read32(0x5000+4u*i)!=a->output[i])return (int)(30+k);
  }
  if(c.lr!=savedlr||c.cia!=(savedlr&~UINT64_C(3)) ||
     c.gpr[1]!=sp+176u||c.cr!=UINT32_C(0xabcdef12)||
     c.ctr!=UINT64_C(0x11223344)||
     c.gpr[2]!=UINT64_C(0x9aabbccddeeff009)||
     c.gpr[26]!=UINT64_C(0x22222222)||
     c.gpr[27]!=UINT64_C(0x55555555)||
     c.gpr[28]!=UINT64_C(0x66666666)||
     c.gpr[29]!=UINT64_C(0x77777777)||
     c.gpr[30]!=UINT64_C(0x88888888)||
     c.gpr[31]!=UINT64_C(0x99999999)||
     (c.xer&UINT32_C(0xd0000000))!=UINT32_C(0xd0000000))
       return (int)(40+k);
  ar_aot_trace t={0};ar_trace_snapshot(&t);
  if(t.aot_dispatches!=2||t.unique_aot!=2||
     t.trace_count!=2||t.fallback_steps!=0||
     t.trace_pcs[0]!=0x0052aafc||t.trace_pcs[1]!=0x0052ab58)
       return (int)(50+k);
 }
 ar_bridge_shutdown();
 if(ar_bridge_init(0x600000u)!=AR_OK)return 70;
 if(ar_register(0x0052aad0,ar_m735_native_0052aad0)!=AR_OK ||
    ar_register(0x0052aae0,ar_m735_native_0052aae0)!=AR_OK ||
    ar_register(0x0052aafc,ending)!=AR_OK)return 71;
 ar_write32(0x7000u-22952u,0x1800u); /* guest r2 TOC pointer */
 ar_write16(0x182eu,5u);
 ar_write16(0x182cu,UINT16_C(0xfffe));
 ppu_context loop={0};loop.gpr[2]=0x7000u;loop.gpr[6]=0;
 loop.cr=UINT32_C(0x12345670);loop.xer=UINT32_C(0x80000000);
 if(ar_run(&loop,0x0052aad0,80)!=AR_OK)return 72;
 if(loop.gpr[7]!=10u||loop.gpr[3]!=UINT64_C(0xfffffffffffffffe)||
    loop.gpr[9]!=0x182cu||loop.gpr[11]!=0x182au||
    (loop.cr&0xfu)!=5u)return 73;
 ar_aot_trace tr={0};ar_trace_snapshot(&tr);
 if(tr.aot_dispatches!=4||tr.unique_aot!=3||
    tr.fallback_steps!=0||tr.trace_count!=4||
    tr.trace_pcs[0]!=0x0052aad0||tr.trace_pcs[1]!=0x0052aae0||
    tr.trace_pcs[2]!=0x0052aae0||tr.trace_pcs[3]!=0x0052aafc)return 74;
 /* The same guest loop is entered by the original alternative CR7 branch.
  * Register *native* entries at 0x52AAB0, 0x52ABE8 and 0x52AAD8. */
 if(ar_register(0x0052aab0,ar_m735_native_0052aab0)!=AR_OK||
    ar_register(0x0052abe8,ar_m735_native_0052abe8)!=AR_OK||
    ar_register(0x0052aad8,ar_m735_native_0052aad8)!=AR_OK)return 77;
 ar_write16(0x1816u,5u);ar_write16(0x1814u,UINT16_C(0xfffe));
 for(unsigned mode=0;mode<3;mode++){
   ppu_context branch={0};
   branch.gpr[31]=(mode==2?4u:mode);
   branch.gpr[28]=UINT64_C(0x5000);
   branch.gpr[2]=UINT64_C(0x7000);
   branch.gpr[3]=0;branch.gpr[30]=0;
   branch.xer=UINT32_C(0x80000000);
   const unsigned expected=(mode==2?6u:5u);
   if(ar_run(&branch,0x0052aab0,100)!=AR_OK)return 78;
   if(ar_read32(0x5014)!=branch.gpr[31]||ar_read32(0x501c)!=0||
      branch.gpr[7]!=10u||branch.gpr[3]!=UINT64_C(0xfffffffffffffffe)||
      (branch.cr&0xfu)!=5u)return 79;
   ar_trace_snapshot(&tr);
   if(tr.fallback_steps!=0||tr.aot_dispatches!=expected||
      tr.trace_pcs[0]!=0x0052aab0||
      tr.trace_pcs[expected-1]!=0x0052aafc)return 80;
   if(mode==2 && (tr.trace_pcs[1]!=0x0052abe8||
                  tr.trace_pcs[2]!=0x0052aad8))return 81;
   if(mode!=2 && tr.trace_pcs[1]!=0x0052aad0)return 82;
 }
 /* A fake ELF with only NOPs cannot register private native code. */
 uint8_t elf[1024]={0};
 memcpy(elf,"\177ELF",4);elf[4]=2;elf[5]=2;elf[6]=1;
 be16(elf+16,2);be16(elf+18,21);be32(elf+20,1);
 be64(elf+32,64);be16(elf+54,56);be16(elf+56,1);
 uint8_t *ph=elf+64;be32(ph,1);be32(ph+4,5);
 be64(ph+8,0x200);be64(ph+16,0x0052aad0);
 be64(ph+32,100);be64(ph+40,100);
 for(unsigned i=0;i<25;i++)be32(elf+0x200+4u*i,0x60000000u);
 if(ar_vm_load(0x0052aad0,elf+0x200,100)!=AR_OK)return 75;
 if(ar_m735_register_owner(elf,sizeof(elf))!=AR_BAD_ARGS)return 76;
 ar_bridge_shutdown();
 puts("M7.35 82 guest PPC instructions: native AOT 2-entry integer date chain, 4-entry looping chain + three alternate entry cases, 0 fallback, 5 numeric oracles, fake ELF rejected PASS");
 return 0;
}
