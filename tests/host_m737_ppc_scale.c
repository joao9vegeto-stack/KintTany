/* M7.37: generic PPC64 multiply/subtract family on synthetic guest ELF.
 * All results are PPC ABI-level oracles; interpreter is NEVER counted AOT.
 */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
extern int ar_ppc_fallback_step(ppu_context *,const uint8_t*,size_t,
                                uint32_t,uint32_t*);
static void wr16(uint8_t*p,uint16_t v){p[0]=(uint8_t)(v>>8);p[1]=(uint8_t)v;}
static void wr32(uint8_t*p,uint32_t v){
 p[0]=(uint8_t)(v>>24);p[1]=(uint8_t)(v>>16);
 p[2]=(uint8_t)(v>>8);p[3]=(uint8_t)v;
}
static void wr64(uint8_t*p,uint64_t v){
 wr32(p,(uint32_t)(v>>32));wr32(p+4,(uint32_t)v);
}
typedef struct {
 unsigned op,xo,d,a,b,record;
 uint64_t ra,rb,rd,expected;
 int ca; /* -1 means preserve CA */
 int cr0; /* -1 means preserve CR0 */
} sample;
static const sample vectors[]={
 {7,0,3,4,0,0,5,0,0,UINT64_C(18000),-1,-1}, /* 3600 */
 {7,0,3,4,0,0,UINT64_MAX,0,0,UINT64_C(0xfffffffffffff1f0),-1,-1},
 {8,0,3,4,0,0,5,0,0,UINT64_MAX,0,-1},   /* 4 - 5 */
 {8,0,3,4,0,0,2,0,0,UINT64_C(2),1,-1},  /* 4 - 2 */
 {31,233,3,4,5,0,UINT64_MAX,3,0,UINT64_C(0xfffffffffffffffd),-1,-1},
 {31,9,3,4,5,0,UINT64_MAX,2,0,UINT64_C(1),-1,-1},
 {31,73,3,4,5,0,UINT64_MAX,2,0,UINT64_MAX,-1,-1},
 {31,73,4,4,5,0,UINT64_MAX,2,0,UINT64_MAX,-1,-1}, /* alias */
 {31,233,3,4,5,1,UINT64_MAX,3,0,UINT64_C(0xfffffffffffffffd),-1,9}
};
int main(void){
 uint8_t elf[1024]={0};memcpy(elf,"\177ELF",4);
 elf[4]=2;elf[5]=2;elf[6]=1;wr16(elf+16,2);
 wr16(elf+18,21);wr32(elf+20,1);wr64(elf+32,64);
 wr16(elf+54,56);wr16(elf+56,1);
 uint8_t *ph=elf+64;wr32(ph,1);wr32(ph+4,5);
 wr64(ph+8,0x200);wr64(ph+16,0x1000);
 wr64(ph+32,4);wr64(ph+40,4);
 if(ar_bridge_init(0x10000u)!=AR_OK)return 1;
 for(size_t i=0;i<sizeof(vectors)/sizeof(vectors[0]);i++){
   const sample *t=&vectors[i];
   const uint32_t instruction=t->op==7u || t->op==8u
    ? (t->op<<26)|(t->d<<21)|(t->a<<16)|
      (t->op==7u?UINT32_C(0x0e10):UINT32_C(4))
    : (31u<<26)|(t->d<<21)|(t->a<<16)|(t->b<<11)|
      (t->xo<<1)|t->record;
   wr32(elf+0x200,instruction);
   if(ar_vm_load(0x1000u,elf+0x200,4u)!=AR_OK)return 2;
   ppu_context c={0};c.gpr[t->a]=t->ra;
   c.gpr[t->b]=t->rb;c.gpr[t->d]=t->rd;
   /* rD aliases RA: preserve RA input for alias cases. */
   if(t->d==t->a)c.gpr[t->a]=t->ra;
   c.xer=UINT32_C(0x80000000)|UINT32_C(0x20000000);
   c.cr=UINT32_C(0x01234567);
   uint32_t observed=0;
   const int result=ar_ppc_fallback_step(&c,elf,sizeof(elf),0x1000,&observed);
   if(result!=AR_TAIL||observed!=instruction||
      c.gpr[t->d]!=t->expected||c.cia!=0x1004u){
     printf("M7.37 PPC vector %zu failed rc=%d got=%016llx want=%016llx\n",
             i,result,(unsigned long long)c.gpr[t->d],
             (unsigned long long)t->expected);
     return (int)(10+i);
   }
   if(t->ca>=0&&((c.xer>>29u)&1u)!=(unsigned)t->ca)return 30;
   if(t->ca<0&&((c.xer>>29u)&1u)!=1u)return 31;
   if(t->cr0>=0&&(c.cr>>28u)!=(unsigned)t->cr0)return 32;
   if(t->cr0<0&&c.cr!=UINT32_C(0x01234567))return 33;
 }
 ar_bridge_shutdown();
 puts("M7.37 PPC scalar multiply batch: 9 synthetic ISA vectors mulli/subfic/mulld/mulhdu/mulhd aliases, XER/CR preserved PASS");
 return 0;
}
