/* M7.2 comprehensive PowerPC condition-register and branch behavior.
 * All guest instructions below are synthetic; no Ascension game bytes. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
extern int ar_m71_private_continuous_probe(const uint8_t*,size_t,uint32_t,uint32_t,uint32_t[16]);
static void p16(uint8_t*d,unsigned i,uint16_t x){d[i]=x>>8;d[i+1]=(uint8_t)x;}
static void p32(uint8_t*d,unsigned i,uint32_t x){
 d[i]=(uint8_t)(x>>24);d[i+1]=(uint8_t)(x>>16);
 d[i+2]=(uint8_t)(x>>8);d[i+3]=(uint8_t)x;
}
static void p64(uint8_t*d,unsigned i,uint64_t x){p32(d,i,(uint32_t)(x>>32));p32(d,i+4,(uint32_t)x);}
static uint32_t cmpx(unsigned bf,unsigned wide,unsigned ra,unsigned rb,unsigned logical){
 return (31u<<26)|(bf<<23)|(wide<<21)|(ra<<16)|(rb<<11)|(logical?64u:0u);
}
static uint32_t cmpi(unsigned bf,unsigned wide,unsigned ra,int imm,unsigned logical){
 return ((logical?10u:11u)<<26)|(bf<<23)|(wide<<21)|(ra<<16)|((uint16_t)imm);
}
static uint32_t bc(unsigned bo,unsigned bi,int delta){
 return (16u<<26)|(bo<<21)|(bi<<16)|((uint16_t)delta&0xfffcu);
}
static void setup(uint8_t*d,size_t length){
 memset(d,0,length);
 memcpy(d,"\177ELF",4);d[4]=2;d[5]=2;d[6]=1;d[7]=0x66;
 p16(d,16,2);p16(d,18,21);p32(d,20,1);p64(d,24,0x20000u);
 p64(d,32,0x500u);p16(d,52,64);p16(d,54,56);p16(d,56,3);
 p32(d,0x500,1);p32(d,0x504,5);
 p64(d,0x508,0x100);p64(d,0x510,0x10000);
 p64(d,0x520,0xc0);p64(d,0x528,0xc0);
 p32(d,0x538,1);p32(d,0x53c,6);
 p64(d,0x540,0x240);p64(d,0x548,0x20000);
 p64(d,0x558,0x240);p64(d,0x560,0x240);
 p32(d,0x570,7);p32(d,0x574,4);
 p64(d,0x578,0x290);p64(d,0x580,0x20050);
 p64(d,0x590,4);p64(d,0x598,16);
 p32(d,0x240,0x10000);p32(d,0x244,0x20010);
}
static int run(const uint8_t*d,size_t len,uint32_t out[16]){
 return ar_m71_private_continuous_probe(d,len,0u,256u,out);
}
int main(void){
 uint8_t d[0x900]={0};uint32_t out[16]={0};
 setup(d,sizeof(d));
 /* r31=0, r8=PT_TLS address (nonzero): CR7 LT from real cmpld. */
 p32(d,0x100,cmpx(7,1,31,8,1));  /* physical Ascension 0x7FBF4040 */
 p32(d,0x104,cmpi(1,0,31,0,0)); /* cmpwi cr1,r31,0 => EQ */
 p32(d,0x108,bc(12,28,8));      /* blt cr7 => taken */
 p32(d,0x10c,0xffffffffu);
 p32(d,0x110,bc(12,6,8));       /* beq cr1 => taken; CR7 intact */
 p32(d,0x114,0xffffffffu);
 p32(d,0x118,cmpi(2,1,8,0x50,1)); /* cmpldi cr2,r8,0x50 => GT */
 p32(d,0x11c,bc(12,9,8));       /* bgt cr2 */
 p32(d,0x120,0xffffffffu);
 p32(d,0x124,cmpx(3,0,31,8,0)); /* cmpw cr3,r31,r8 => LT */
 p32(d,0x128,bc(4,14,8));       /* bne cr3 (EQ=false) */
 p32(d,0x12c,0xffffffffu);
 p32(d,0x130,0x3860ffffu);      /* li r3,-1, 64-bit sign extended */
 p32(d,0x134,cmpx(4,1,3,8,0)); /* cmpd signed -1 < +0x20050 */
 p32(d,0x138,bc(12,16,8));      /* blt cr4 */
 p32(d,0x13c,0xffffffffu);
 p32(d,0x140,cmpx(6,1,3,8,1)); /* cmpld unsigned -1 > +0x20050 */
 p32(d,0x144,bc(12,25,8));      /* bgt cr6 */
 p32(d,0x148,0xffffffffu);
 p32(d,0x14c,0xffffffffu);      /* final expected unsupported word */
 int rc=run(d,sizeof(d),out);
 if(rc || (int32_t)out[0]!=-1311 || out[1]!=13u ||
    out[2]!=0x1004cu || out[3]!=0xffffffffu ||
    out[5]!=0u || out[11]!=0u){
    fprintf(stderr,"M7.2 compare/branches rc=%d reason=%d steps=%u PC=%x opcode=%x\n",
            rc,(int32_t)out[0],out[1],out[2],out[3]);return 1;
 }
 /* Untaken CR7 EQ must fall into the first sentinel, not skip it. */
 p32(d,0x108,bc(12,30,8));
 rc=run(d,sizeof(d),out);
 if(rc || (int32_t)out[0]!=-1311 || out[1]!=3u ||
    out[2]!=0x1000cu)return 2;
 /* Width and signedness are semantically distinct: compare 0 vs 0x20050
  * without truncation, and compare -1 in 64-bit form. */
 setup(d,sizeof(d));
 p32(d,0x100,0x38600002u);     /* li r3,2 */
 p32(d,0x104,0x7c6903a6u);     /* mtctr r3 */
 p32(d,0x108,bc(16,0,8));      /* bdnz decrements CTR 2->1: taken */
 p32(d,0x10c,0xffffffffu);
 p32(d,0x110,bc(18,0,8));      /* bdz decrements CTR 1->0: taken */
 p32(d,0x114,0xffffffffu);
 p32(d,0x118,0xffffffffu);
 rc=run(d,sizeof(d),out);
 if(rc || (int32_t)out[0]!=-1311 || out[1]!=4u ||
    out[2]!=0x10018u || out[8]!=0u)return 3; /* out[8] is CTR */
 /* Exact cmpd decoded but reserved bit22 must be refused, not executed. */
 setup(d,sizeof(d));
 p32(d,0x100,0x7fbf4040u|0x00400000u);
 rc=run(d,sizeof(d),out);
 if(rc || (int32_t)out[0]!=-1311 || out[1]!=0u ||
    out[2]!=0x10000u)return 4;
 /* Conditional CR branch with invalid target fails only when taken. */
 setup(d,sizeof(d));
 p32(d,0x100,cmpx(7,1,31,8,1));
 p32(d,0x104,bc(12,28,-4)); /* target pc-4 remains executable; loop */
 rc=ar_m71_private_continuous_probe(d,sizeof(d),0u,9u,out);
 if(rc || (int32_t)out[0]!=-1310 || out[1]!=9u)return 5;
 p32(d,0x104,bc(12,28,0x200)); /* taken but outside file executable map */
 rc=run(d,sizeof(d),out);
 if(rc || (int32_t)out[0]!=-1312 || out[1]!=1u)return 6;
 /* CR-aware bclr: LR loaded from a guest GPR; only branch when CR7 LT. */
 setup(d,sizeof(d));
 p32(d,0x100,0x3c600001u); /* lis r3,1 */
 p32(d,0x104,0x60630018u); /* ori r3,r3,0x18 -> guest 0x10018 */
 p32(d,0x108,0x7c6803a6u); /* mtlr r3 */
 p32(d,0x10c,0x7fbf4040u); /* cmpld cr7,r31,r8: LT */
 p32(d,0x110,0x4d9c0020u); /* bclr BO12,BI28 -> guest LR */
 p32(d,0x114,0xffffffffu);
 p32(d,0x118,0xffffffffu);
 rc=run(d,sizeof(d),out);
 if(rc || (int32_t)out[0]!=-1311 || out[1]!=5u ||
    out[2]!=0x10018u)return 7;
 p32(d,0x110,0x4d9e0020u); /* bclr on CR7 EQ=false */
 rc=run(d,sizeof(d),out);
 if(rc || (int32_t)out[0]!=-1311 || out[1]!=5u ||
    out[2]!=0x10014u)return 8;
 /* CR-aware bcctr: CTR remains the branch target, not a loop counter. */
 setup(d,sizeof(d));
 p32(d,0x100,0x3c600001u); /* lis r3,1 */
 p32(d,0x104,0x60630018u); /* ori r3,r3,0x18 */
 p32(d,0x108,0x7c6903a6u); /* mtctr r3 */
 p32(d,0x10c,0x7fbf4040u); /* cmpld cr7,r31,r8 */
 p32(d,0x110,0x4d9c0420u); /* bcctr BO12,BI28 => target 0x10018 */
 p32(d,0x114,0xffffffffu);
 p32(d,0x118,0xffffffffu);
 rc=run(d,sizeof(d),out);
 if(rc || (int32_t)out[0]!=-1311 || out[1]!=5u ||
    out[2]!=0x10018u || out[8]!=0x10018u)return 9;
 p32(d,0x110,0x4e1c0420u); /* illegal bcctr with CTR decrement */
 rc=run(d,sizeof(d),out);
 if(rc || (int32_t)out[0]!=-1311 || out[1]!=4u ||
    out[2]!=0x10010u)return 10;
 puts("M7.2 CR7 cmpld, signed/unsigned compare and conditional branches PASS");
 return 0;
}
