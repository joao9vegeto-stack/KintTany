/* M7.36 synthetic/independent signed PPC32-high-multiply test oracles.
 * No game ELF, license or commercial instruction stream in these fixtures.
 */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
extern int ar_m736_native_00524b8c(ppu_context*);
extern int ar_m736_register_owner(const uint8_t*,size_t);
extern int ar_ppc_fallback_step(ppu_context*,const uint8_t*,size_t,uint32_t,uint32_t*);
#define START UINT32_C(0x00524b8c)
#define FALL UINT32_C(0x00524bb0)
#define TAKE UINT32_C(0x00524d1c)
typedef struct{
 uint64_t src,mult,r9,r11;uint32_t xer;
 uint64_t expected_r0,expected_r4,expected_r9,expected_r10;
 uint32_t expected_carry,expected_cr0,expected_pc;
} oracle;
static const oracle cases[]={
 {0x0000000000000000ULL,0x0000000000000000ULL,0x0000000000000000ULL,0x0000000000000000ULL,0x00000000U,0x0000000000000000ULL,0x0000000000000000ULL,0x0000000000000000ULL,0x0000000000000000ULL,0U,2U,FALL},
 {0x00000000ffffffffULL,0x000000007fffffffULL,0x0000000000000000ULL,0x0000000000000000ULL,0x00000000U,0xfffffffffffffff4ULL,0x000000000000000cULL,0xfffffffffffffffcULL,0xffffffffffffffffULL,1U,4U,FALL},
 {0x0000000080000000ULL,0x000000007fffffffULL,0x0000000000000003ULL,0x0000000000000000ULL,0x80000000U,0xfffffffe7fffffdcULL,0x0000000180000024ULL,0xffffffff7ffffff4ULL,0xffffffffdffffffdULL,0U,5U,FALL},
 {0x0000000080000000ULL,0x0000000080000000ULL,0x0000000000000064ULL,0x0000000000000005ULL,0x20000000U,0x000000017ffffb50ULL,0xfffffffe800004b5ULL,0x000000007ffffe70ULL,0x000000001fffff9cULL,0U,8U,TAKE},
 {0x000000007fffffffULL,0x000000007fffffffULL,0x0000000000000000ULL,0x0000000000000000ULL,0x00000000U,0x000000017ffffff4ULL,0xfffffffe8000000cULL,0x000000007ffffffcULL,0x000000001fffffffULL,0U,8U,TAKE},
 {0x7fffffffffffffffULL,0x00000000fffffff0ULL,0x0000000000000000ULL,0x0000000000000000ULL,0x80000000U,0x0000000000000000ULL,0x0000000000000000ULL,0x0000000000000000ULL,0x0000000000000000ULL,0U,3U,FALL},
 {0x0000000100000000ULL,0x0000000080000000ULL,0x0000000000000005ULL,0xffffffffffffffffULL,0x00000000U,0xffffffffffffffc4ULL,0x000000000000003bULL,0xffffffffffffffecULL,0xfffffffffffffffbULL,0U,4U,FALL},
 {0xffffffff80000000ULL,0x0000000012345678ULL,0xffffffffffffffe0ULL,0xfffffffffffffffdULL,0x00000000U,0xffffffffc962fe18ULL,0x00000000369d01e5ULL,0xffffffffedcbaa08ULL,0xfffffffffb72ea82ULL,0U,4U,FALL},
 {0x0000000012345678ULL,0x0000000087654321ULL,0x0000000123456789ULL,0x7fffffffffffffffULL,0x80000000U,0xfffffffe2549ecdcULL,0x80000001dab61323ULL,0xffffffff61c34ef4ULL,0xffffffffd870d3bdULL,1U,9U,TAKE},
 {0xffffffffffffffffULL,0x0000000080000000ULL,0x0000000000000000ULL,0xfffffffffffffff0ULL,0x80000000U,0x0000000000000000ULL,0xfffffffffffffff0ULL,0x0000000000000000ULL,0x0000000000000000ULL,0U,9U,TAKE}
};
static int stop(ppu_context*c){(void)c;return AR_OK;}
static void be16(uint8_t*p,uint16_t v){p[0]=(uint8_t)(v>>8);p[1]=(uint8_t)v;}
static void be32(uint8_t*p,uint32_t v){
 p[0]=(uint8_t)(v>>24);p[1]=(uint8_t)(v>>16);
 p[2]=(uint8_t)(v>>8);p[3]=(uint8_t)v;
}
static void be64(uint8_t*p,uint64_t v){
 be32(p,(uint32_t)(v>>32));be32(p+4,(uint32_t)v);
}
int main(void){
 if(ar_bridge_init(0x600000u)!=AR_OK)return 1;
 if(ar_register(START,ar_m736_native_00524b8c)!=AR_OK||
    ar_register(FALL,stop)!=AR_OK||ar_register(TAKE,stop)!=AR_OK)return 2;
 for(size_t k=0;k<sizeof(cases)/sizeof(cases[0]);k++){
  const oracle*o=&cases[k];ppu_context c={0};
  c.gpr[0]=o->src;c.gpr[29]=o->mult;c.gpr[9]=o->r9;
  c.gpr[11]=o->r11;c.gpr[2]=0x87654321u;c.gpr[1]=0x6000u;
  c.lr=0x12345678u;c.ctr=0xfeedfaceu;c.xer=o->xer;
  c.cr=UINT32_C(0x01234567);
  if(ar_run(&c,START,16u)!=AR_OK)return (int)(10+k);
  if(c.gpr[0]!=o->expected_r0||c.gpr[4]!=o->expected_r4||
     c.gpr[9]!=o->expected_r9||c.gpr[10]!=o->expected_r10||
     c.gpr[29]!=o->mult||c.gpr[11]!=o->r11||
     c.gpr[2]!=0x87654321u||c.gpr[1]!=0x6000u||
     c.ctr!=0xfeedfaceu||c.lr!=0x12345678u||
     c.cr!=(UINT32_C(0x01234567)|(o->expected_cr0<<28))||
     c.cia!=o->expected_pc||
     ((c.xer&UINT32_C(0x20000000))!=0)!=o->expected_carry||
     (c.xer&~UINT32_C(0x20000000))!=(o->xer&~UINT32_C(0x20000000)))
      return (int)(30+k);
  ar_aot_trace t={0};ar_trace_snapshot(&t);
  if(t.aot_dispatches!=2||t.unique_aot!=2||
     t.fallback_steps||t.trace_count!=2||
     t.trace_pcs[0]!=START||t.trace_pcs[1]!=o->expected_pc)
       return (int)(50+k);
 }
 /* Full ELF-shaped *synthetic* data still fails fingerprint authentication. */
 uint8_t fake[1024]={0};
 memcpy(fake,"\177ELF",4);fake[4]=2;fake[5]=2;fake[6]=1;
 be16(fake+16,2);be16(fake+18,21);be32(fake+20,1);
 be64(fake+32,64);be16(fake+54,56);be16(fake+56,1);
 uint8_t *ph=fake+64;be32(ph,1);be32(ph+4,5);
 be64(ph+8,0x200);be64(ph+16,START);
 be64(ph+32,9u*4u);be64(ph+40,9u*4u);
 for(unsigned i=0;i<9;i++)be32(fake+0x200+4*i,UINT32_C(0x60000000));
 if(ar_vm_load(START,fake+0x200,36u)!=AR_OK)return 71;
 if(ar_m736_register_owner(fake,sizeof(fake))!=AR_BAD_ARGS ||
    ar_registered_count()!=3u)return 72;
 be32(ph+4,4); /* no execute permission: must fail closed */
 if(ar_m736_register_owner(fake,sizeof(fake))!=AR_BAD_ARGS)return 73;
 /* Generic mulhw fallback from a different synthetic instruction:
  * r6/r7 inputs, r5 output, flag bit Rc; no game ELF involved. */
 ar_bridge_shutdown();
 if(ar_bridge_init(0x400000u)!=AR_OK)return 74;
 const uint32_t synpc=0x1000u;
 const uint32_t syn=(31u<<26)|(5u<<21)|(6u<<16)|(7u<<11)|(75u<<1)|1u;
 memset(fake,0,sizeof(fake));
 memcpy(fake,"\177ELF",4);fake[4]=2;fake[5]=2;fake[6]=1;
 be16(fake+16,2);be16(fake+18,21);be32(fake+20,1);
 be64(fake+32,64);be16(fake+54,56);be16(fake+56,1);
 ph=fake+64;be32(ph,1);be32(ph+4,5);
 be64(ph+8,0x200);be64(ph+16,synpc);
 be64(ph+32,4);be64(ph+40,4);be32(fake+0x200,syn);
 if(ar_vm_load(synpc,fake+0x200,4u)!=AR_OK)return 75;
 ppu_context f={0};f.gpr[6]=UINT32_C(0xffffffff);
 f.gpr[7]=UINT32_C(0x7fffffff);f.xer=UINT32_C(0x80000000);
 uint32_t seen=0;
 if(ar_ppc_fallback_step(&f,fake,sizeof(fake),synpc,&seen)!=AR_TAIL||
    seen!=syn||f.gpr[5]!=UINT64_MAX||f.cia!=synpc+4u||
    (f.cr>>28)!=9u)return 76;
 ar_bridge_shutdown();
 puts("M7.36 signed MULHW native nine-op branch: 10 independent numeric oracles, both CR0 paths, XER.CA, preserved LR/CTR/TOC, strict ELF gate, generic fallback MULHW Rc PASS");
 return 0;
}
