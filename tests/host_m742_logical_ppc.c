/* M7.42: comprehensive synthetic PPC64 owner-path bitwise-family tests.
 * Covers the physical iPhone's current NOR + CNTLZD instructions and
 * five more architectural X-form operations. NOT a claimed AOT translation.
 */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
extern int ar_ppc_fallback_step(ppu_context*,const uint8_t*,size_t,
                                uint32_t,uint32_t*);
static void w16(uint8_t*p,uint16_t v){p[0]=(uint8_t)(v>>8);p[1]=(uint8_t)v;}
static void w32(uint8_t*p,uint32_t v){
 p[0]=(uint8_t)(v>>24);p[1]=(uint8_t)(v>>16);
 p[2]=(uint8_t)(v>>8);p[3]=(uint8_t)v;
}
static void w64(uint8_t*p,uint64_t v){w32(p,(uint32_t)(v>>32));w32(p+4,(uint32_t)v);}
static uint32_t encode(unsigned rs,unsigned ra,unsigned rb,unsigned xo,unsigned rc){
 return (31u<<26)|(rs<<21)|(ra<<16)|(rb<<11)|(xo<<1)|rc;
}
typedef struct {
 const char*name;uint32_t word;
 unsigned rs,ra,rb;uint64_t vs, vb, expected;
 int cr0; /* -1 unchanged, else expected exact CR0 nibble */
 int unsupported;
} testcase;
#define MASK UINT64_C(0xffffffffffffffff)
static const testcase cases[]={
 {"owner 0x00525F10 NOR",UINT32_C(0x7d2b50f8),9,11,10,
    UINT64_C(0x00ff00ff00ff00ff),UINT64_C(0xf000f000f000f000),
    UINT64_C(0x0f000f000f000f00),-1,0},
 {"owner 0x00525F14 CNTLZD",UINT32_C(0x7d600074),11,0,0,
    UINT64_C(0x0000800000000000),UINT64_C(0),16,-1,0},
 {"NOR Rc=1 negative",0,3,4,5,0,0,MASK,9,0},
 {"NAND",0,3,4,5,UINT64_C(0xf0),UINT64_C(0x0f),UINT64_C(0xffffffffffffff00),-1,0},
 {"EQV",0,3,4,5,UINT64_C(0x0f),UINT64_C(0xff),UINT64_C(0xffffffffffffff0f),-1,0},
 {"ORC",0,3,4,5,0,UINT64_C(0xff),UINT64_C(0xffffffffffffff00),-1,0},
 {"ANDC",0,3,4,5,UINT64_C(0xf0),UINT64_C(0x0f),UINT64_C(0xf0),-1,0},
 {"CNTLZD 0",0,11,0,0,0,0,64,-1,0},
 {"CNTLZD high",0,11,0,0,UINT64_C(0x8000000000000000),0,0,-1,0},
 {"CNTLZD mid",0,11,0,0,UINT64_C(0x0100000000000000),0,7,-1,0},
 {"CNTLZD word",0,11,0,0,UINT64_C(0x0000000100000000),0,31,-1,0},
 {"CNTLZD alias RA=RS",0,11,11,0,UINT64_C(0x100),0,55,5,0},
 {"NOR alias RA=RS",0,9,9,10,UINT64_C(0xf0),UINT64_C(0x0f),UINT64_C(0xffffffffffffff00),9,0},
 {"NOR alias RA=RB",0,9,10,10,UINT64_C(0xf0),UINT64_C(0x0f),UINT64_C(0xffffffffffffff00),-1,0},
 {"CNTLZD reserved RB",0,11,0,1,UINT64_C(0x100),0,0,-1,1},
};
int main(void){
 uint8_t elf[1024]={0};memcpy(elf,"\177ELF",4);
 elf[4]=2;elf[5]=2;elf[6]=1;w16(elf+16,2);w16(elf+18,21);
 w32(elf+20,1);w64(elf+32,64);w16(elf+54,56);w16(elf+56,1);
 uint8_t *ph=elf+64;w32(ph,1);w32(ph+4,5);
 w64(ph+8,0x200);w64(ph+16,0x1000);w64(ph+32,4);w64(ph+40,4);
 if(ar_bridge_init(0x10000u)!=AR_OK)return 1;
 for(size_t i=0;i<sizeof(cases)/sizeof(cases[0]);i++){
   const testcase *t=&cases[i];
   uint32_t w=t->word;
   if(i>=2){
     unsigned xo=0u,rc=0u;
     if(i==2){xo=124;rc=1;} /* NOR. */
     else if(i==3)xo=476; /* NAND */
     else if(i==4)xo=284; /* EQV */
     else if(i==5)xo=412; /* ORC */
     else if(i==6)xo=60;  /* ANDC */
     else xo=(t->name[0]=='N' && t->name[1]=='O')?124:58;
     if(i==11)rc=1; /* CNTLZD. sets CR0 GT|SO */
     if(i==12)xo=124,rc=1;
     if(i==13)xo=124;
     if(i==14)xo=58;
     w=encode(t->rs,t->ra,t->rb,xo,rc);
   }
   w32(elf+0x200,w);
   if(ar_vm_load(0x1000u,elf+0x200,4u)!=AR_OK)return 2;
   ppu_context cpu={0};
   for(unsigned j=0;j<32;j++)cpu.gpr[j]=UINT64_C(0x0101010101010101)+j;
   cpu.gpr[t->rs]=t->vs;
   if(t->rb!=t->rs)cpu.gpr[t->rb]=t->vb;
   cpu.xer=UINT32_C(0x80000000); /* sticky SO */
   cpu.cr=UINT32_C(0x12345678);
   cpu.lr=UINT64_C(0x1234567890abcdef);
   cpu.ctr=UINT64_C(0xffffffffffffffff);
   cpu.cia=0x1000;
   ppu_context before=cpu;
   uint32_t observed=0u;
   const int res=ar_ppc_fallback_step(&cpu,elf,sizeof(elf),0x1000u,&observed);
   const int wanted=t->unsupported?AR_PPC_UNSUPPORTED:AR_TAIL;
   if(res!=wanted||observed!=w){
     printf("M7.42 failure %zu (%s) rc=%d wanted=%d opcode=%08x got=%08x\n",
            i,t->name,res,wanted,w,observed);
     return (int)(10+i);
   }
   if(t->unsupported){
     if(memcmp(&before,&cpu,sizeof(cpu))!=0)return 29;
     continue;
   }
   for(unsigned j=0;j<32;j++){
     uint64_t expected=(j==t->ra)?t->expected:before.gpr[j];
     if(cpu.gpr[j]!=expected){
       printf("M7.42 failure %zu (%s) r%u=%016llx expected=%016llx\n",
          i,t->name,j,(unsigned long long)cpu.gpr[j],
          (unsigned long long)expected);
       return (int)(30+i);
     }
   }
   if(cpu.lr!=before.lr||cpu.ctr!=before.ctr||
      cpu.xer!=before.xer||cpu.cia!=0x1004u)return 70;
   const uint32_t expectedCr=t->cr0<0?before.cr:
                  ((before.cr&UINT32_C(0x0fffffff))|((uint32_t)t->cr0<<28));
   if(cpu.cr!=expectedCr)return 71;
 }
 ar_bridge_shutdown();
 puts("M7.42 PPC logical family: 15 synthetic owner-pattern vectors, NOR/CNTLZD/NAND/EQV/ORC/ANDC, CR0/SO and alias-safe GPR preservation PASS");
 return 0;
}
