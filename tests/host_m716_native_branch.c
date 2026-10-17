/* M7.16 host-only synthetic ELF & guest memory: no commercial code. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
extern int ar_m716_register_block(const uint8_t*,size_t);
extern int ar_m716_verified_successors(const uint8_t*,size_t,uint32_t[2]);
static void be16(uint8_t*p,uint16_t n){p[0]=(uint8_t)(n>>8);p[1]=(uint8_t)n;}
static void be32(uint8_t*p,uint32_t n){p[0]=(uint8_t)(n>>24);p[1]=(uint8_t)(n>>16);p[2]=(uint8_t)(n>>8);p[3]=(uint8_t)n;}
static void be64(uint8_t*p,uint64_t n){be32(p,(uint32_t)(n>>32));be32(p+4,(uint32_t)n);}
#define BASE 0x003c4dc4u
#define MEM_SIZE 0x009d2000u
static void init_ppu(ppu_context*c,uint8_t payload){
  memset(c,0,sizeof(*c));
  c->gpr[29]=0x2000u;
  c->gpr[31]=UINT64_C(0xabcdffff00000100);
  c->gpr[6]=UINT64_C(0xfedcba9812345678);
  c->gpr[4]=0x1800u;
  c->gpr[3]=0xdeadbeefu;
  c->xer=0x80000000u;
  c->cr=0x0abcdef0u;
  c->lr=0x3456u;c->ctr=0x7890u;
  ar_write32(0x2018u,0x3000u);
  ar_write8(0x009c1780u,payload);
}
static int test_branch(const uint8_t *elf,size_t size,uint8_t payload,uint32_t want_pc){
  ar_bridge_shutdown();
  if(ar_bridge_init(MEM_SIZE)!=AR_OK)return 1;
  if(ar_m716_register_block(elf,size)!=AR_OK||ar_registered_count()!=1u)return 2;
  ppu_context c;
  init_ppu(&c,payload);
  if(ar_last_error()!=AR_OK)return 3;
  const int status=ar_run(&c,BASE,64u);
  if(status!=AR_UNRESOLVED||ar_last_unresolved()!=want_pc||c.cia!=want_pc)return 4;
  if(c.gpr[31]!=0x100u||c.gpr[5]!=0x3000u||c.gpr[4]!=0x9c0000u)return 5;
  if(c.gpr[30]!=0x2f00u||c.gpr[3]!=payload)return 6;
  if(ar_read32(0x200cu)!=0x12345678u||ar_read32(0x2014u)!=0x1800u
      ||ar_read32(0x1800u)!=0xdeadbeefu||ar_read32(0x3000u)!=0xdeadbeefu
      ||ar_read32(0x2004u)!=0x100u||ar_read32(0x2008u)!=0x100u)return 7;
  if(c.xer!=0xa0000000u||c.lr!=0x3456u||c.ctr!=0x7890u)return 8;
  const uint32_t expected_cr=(payload?0x40000000u:0x20000000u)|0x10000000u|0x0abcdef0u;
  if(c.cr!=expected_cr)return 9;
  return 0;
}
int main(void){
  uint8_t elf[1024]={0};
  memcpy(elf,"\177ELF",4);elf[4]=2;elf[5]=2;elf[6]=1;
  be16(elf+16,2);be16(elf+18,21);be32(elf+20,1);
  be64(elf+32,64);be16(elf+54,56);be16(elf+56,1);
  uint8_t*ph=elf+64;
  be32(ph,1);be32(ph+4,5);be64(ph+8,0x200u);
  be64(ph+16,BASE);be64(ph+32,80u);be64(ph+40,80u);
  const uint32_t ops[15]={
    0x7bff0020u,0x90dd000cu,0x909d0014u,0x90640000u,
    0x80bd0018u,0x3c80009cu,0x90650000u,0x807d0018u,
    0x93fd0004u,0x93fd0008u,0x7fdf1810u,0x88641780u,
    0x7bde0020u,0x2c030000u,0x41820018u
  };
  for(unsigned i=0;i<15u;i++)be32(elf+0x200u+4u*i,ops[i]);
  if(ar_bridge_init(0x1000u)!=AR_OK)return 1;
  elf[0x200u+4u*10u]^=1u;
  if(ar_m716_register_block(elf,sizeof(elf))!=AR_BAD_ARGS||ar_registered_count())return 2;
  elf[0x200u+4u*10u]^=1u;
  be32(ph+4,4);
  if(ar_m716_register_block(elf,sizeof(elf))!=AR_BAD_ARGS)return 3;
  be32(ph+4,5);
  uint32_t next[2]={0};
  if(ar_m716_verified_successors(elf,sizeof(elf),next)!=AR_OK ||
     next[0]!=0x003c4e00u||next[1]!=0x003c4e14u)return 4;
  elf[0x200u+4u*14u+3u]^=1u;
  if(ar_m716_verified_successors(elf,sizeof(elf),next)!=AR_BAD_ARGS ||
     ar_m716_register_block(elf,sizeof(elf))!=AR_BAD_ARGS)return 5;
  elf[0x200u+4u*14u+3u]^=1u;
  if(test_branch(elf,sizeof(elf),0u,0x003c4e14u)!=0)return 6;
  if(test_branch(elf,sizeof(elf),0x7fu,0x003c4e00u)!=0)return 7;
  ar_bridge_shutdown();
  if(ar_bridge_init(0x4000)!=AR_OK ||
     ar_m716_register_block(elf,sizeof(elf))!=AR_OK)return 8;
  ppu_context c={0};
  c.gpr[29]=0x2000u;c.gpr[4]=UINT64_MAX;c.gpr[31]=UINT64_MAX;
  c.xer=0xa0000000u;c.cr=0x87654321u;
  if(ar_run(&c,BASE,32u)!=AR_MEM_FAULT||
     c.cia==0x003c4e14u||c.cr!=0x87654321u)return 9;
  ar_bridge_shutdown();
  puts("M7.16 authentic 15-word ARM64 PPC branch, memory, CR0 and XER tests PASS");
  return 0;
}
