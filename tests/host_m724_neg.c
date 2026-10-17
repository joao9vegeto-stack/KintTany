/* M7.24 synthetic Power ISA NEG/NEGO verification with actual bounded fallback.
 * No PS3 game bytes, secrets or per-PC patches.
 */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
static void be16(uint8_t*p,uint16_t x){p[0]=(uint8_t)(x>>8);p[1]=(uint8_t)x;}
static void be32(uint8_t*p,uint32_t x){
 p[0]=(uint8_t)(x>>24);p[1]=(uint8_t)(x>>16);
 p[2]=(uint8_t)(x>>8);p[3]=(uint8_t)x;
}
static void be64(uint8_t*p,uint64_t x){be32(p,(uint32_t)(x>>32));be32(p+4,(uint32_t)x);}
static uint32_t neg_op(unsigned rt,unsigned ra,int oe,int rc,unsigned rb){
 return (31u<<26)|(rt<<21)|(ra<<16)|(rb<<11)|((104u+(oe?512u:0u))<<1)|(unsigned)rc;
}
static int step(uint8_t *elf,uint32_t word,ppu_context*c){
 uint32_t got=0;
 be32(elf+0x200,word);
 if(ar_vm_load(0x1000,elf+0x200,4)!=AR_OK)return -999;
 int rc=ar_ppc_fallback_step(c,elf,1024,0x1000,&got);
 return got==word?rc:-998;
}
int main(void){
 uint8_t elf[1024]={0};
 memcpy(elf,"\177ELF",4);elf[4]=2;elf[5]=2;elf[6]=1;
 be16(elf+16,2);be16(elf+18,21);be32(elf+20,1);
 be64(elf+32,64);be16(elf+54,56);be16(elf+56,1);
 uint8_t*ph=elf+64;be32(ph,1);be32(ph+4,5);
 be64(ph+8,0x200);be64(ph+16,0x1000);
 be64(ph+32,0x100);be64(ph+40,0x100);
 if(ar_bridge_init(0x3000)!=AR_OK)return 1;
 ppu_context c={0};
 c.gpr[4]=7;c.xer=UINT32_C(0xe0000000);c.cr=UINT32_C(0x12345678);
 if(step(elf,neg_op(3,4,0,0,0),&c)!=AR_TAIL||
    c.gpr[3]!=UINT64_C(0xfffffffffffffff9)||
    c.xer!=UINT32_C(0xe0000000)||
    c.cr!=UINT32_C(0x12345678)||c.cia!=0x1004u)return 2;
 memset(&c,0,sizeof(c));
 c.gpr[4]=UINT64_C(0x8000000000000000);
 c.xer=UINT32_C(0x20000000);c.cr=UINT32_C(0x000000ab);
 if(step(elf,neg_op(3,4,1,1,0),&c)!=AR_TAIL||
    c.gpr[3]!=UINT64_C(0x8000000000000000)||
    c.xer!=UINT32_C(0xe0000000)||
    c.cr!=UINT32_C(0x900000ab))return 3;
 c.gpr[4]=UINT64_C(0xfffffffffffffffd);
 if(step(elf,neg_op(4,4,1,1,0),&c)!=AR_TAIL||
    c.gpr[4]!=3u||
    c.xer!=UINT32_C(0xa0000000)||
    c.cr!=UINT32_C(0x500000ab))return 4;
 memset(&c,0,sizeof(c));c.gpr[4]=99;c.cia=0x777u;
 if(step(elf,neg_op(3,4,0,0,1),&c)!=AR_PPC_UNSUPPORTED||
    c.gpr[3]!=0||c.cia!=0x777u)return 5;
 ar_bridge_shutdown();
 puts("M7.24 NEG/NEGO PPC64 fallback: modulo, overflow, sticky SO, Rc and invalid RB PASS");
 return 0;
}
