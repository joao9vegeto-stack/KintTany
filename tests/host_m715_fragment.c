/* Synthetic-only regression for the four authenticated PPC instructions. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
extern int ar_m715_register_fragment(const uint8_t*,size_t);
static void be16(uint8_t*p,uint16_t n){p[0]=(uint8_t)(n>>8);p[1]=(uint8_t)n;}
static void be32(uint8_t*p,uint32_t n){p[0]=(uint8_t)(n>>24);p[1]=(uint8_t)(n>>16);p[2]=(uint8_t)(n>>8);p[3]=(uint8_t)n;}
static void be64(uint8_t*p,uint64_t n){be32(p,(uint32_t)(n>>32));be32(p+4,(uint32_t)n);}
int main(void){
 uint8_t elf[1024]={0};
 memcpy(elf,"\177ELF",4);elf[4]=2;elf[5]=2;elf[6]=1;
 be16(elf+16,2);be16(elf+18,21);be32(elf+20,1);
 be64(elf+32,64);be16(elf+54,56);be16(elf+56,1);
 uint8_t*ph=elf+64;
 be32(ph,1);be32(ph+4,5);be64(ph+8,0x300);
 be64(ph+16,0x003c4db4);be64(ph+32,16);be64(ph+40,16);
 const uint32_t words[4]={0x33e40004,0x60630001,0x80c5ae5c,0x93a5ae5c};
 for(unsigned i=0;i<4;i++)be32(elf+0x300+4*i,words[i]);
 if(ar_bridge_init(0x9000)!=AR_OK)return 1;
 elf[0x300+7]^=1;
 if(ar_m715_register_fragment(elf,sizeof(elf))!=AR_BAD_ARGS||ar_registered_count())return 2;
 elf[0x300+7]^=1;
 be32(ph+4,4);
 if(ar_m715_register_fragment(elf,sizeof(elf))!=AR_BAD_ARGS||ar_registered_count())return 3;
 be32(ph+4,5);
 if(ar_m715_register_fragment(elf,sizeof(elf))!=AR_OK||ar_registered_count()!=1)return 4;
 if(ar_m715_register_fragment(elf,sizeof(elf))!=AR_DUPLICATE)return 5;
 const uint32_t ea=0x6000-0x51a4;
 ar_write32(ea,0x80000080u);
 if(ar_last_error()!=AR_OK)return 6;
 ppu_context c={0};
 c.gpr[4]=UINT64_MAX-2u;c.gpr[3]=UINT64_C(0x1234000000000000);
 c.gpr[5]=0x6000;c.gpr[29]=UINT64_C(0xabcdef00deadbeef);
 c.gpr[6]=UINT64_MAX;c.xer=0x80000000u;c.cr=0xa1b2c3d4u;c.lr=0x1577;c.ctr=0x1666;
 int rc=ar_run(&c,0x003c4db4u,8);
 if(rc!=AR_UNRESOLVED||ar_last_unresolved()!=0x003c4dc4u||c.cia!=0x003c4dc4u)return 7;
 if(c.gpr[31]!=1u||c.gpr[3]!=UINT64_C(0x1234000000000001)||
    c.gpr[6]!=0x80000080u||ar_read32(ea)!=0xdeadbeefu)return 8;
 if(c.xer!=0xa0000000u||c.cr!=0xa1b2c3d4u||c.lr!=0x1577u||c.ctr!=0x1666u)return 9;
 ar_bridge_shutdown();
 if(ar_bridge_init(0x9000)!=AR_OK || ar_m715_register_fragment(elf,sizeof(elf))!=AR_OK)return 10;
 memset(&c,0,sizeof(c));
 c.gpr[4]=1;c.gpr[3]=2;c.gpr[5]=0x51a0;c.gpr[29]=0xff00;
 c.xer=0x20000000u;
 rc=ar_run(&c,0x003c4db4u,8);
 if(rc!=AR_MEM_FAULT||c.cia==0x003c4dc4u||c.gpr[6]!=0||
    (c.xer & 0x20000000u)!=0u)return 11;
 ar_bridge_shutdown();
 puts("M7.15 authentic PPC load-store AOT, CA, BE guest memory and fail-closed PASS");
 return 0;
}
