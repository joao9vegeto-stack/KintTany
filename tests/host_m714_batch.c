#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
extern int ar_m714_register_fragment(const uint8_t*,size_t);
extern int ar_m714_aot_003c4da4(ppu_context*);
extern int ar_m714_frontier_inventory(const uint8_t*,size_t,uint32_t,uint32_t[32],uint32_t*,uint32_t*);
static void be16(uint8_t*p,uint16_t n){p[0]=(uint8_t)(n>>8);p[1]=(uint8_t)n;}
static void be32(uint8_t*p,uint32_t n){p[0]=(uint8_t)(n>>24);p[1]=(uint8_t)(n>>16);p[2]=(uint8_t)(n>>8);p[3]=(uint8_t)n;}
static void be64(uint8_t*p,uint64_t n){be32(p,(uint32_t)(n>>32));be32(p+4,(uint32_t)n);}
int main(void) {
 uint8_t elf[768]={0}; memcpy(elf,"\177ELF",4);elf[4]=2;elf[5]=2;elf[6]=1;
 be16(elf+16,2);be16(elf+18,21);be32(elf+20,1);be64(elf+32,64);be16(elf+54,56);be16(elf+56,1);
 uint8_t*ph=elf+64;be32(ph,1);be32(ph+4,5);be64(ph+8,0x200);be64(ph+16,0x003c4da4);be64(ph+32,60);be64(ph+40,60);
 const uint32_t op[4]={0x78840020u,0x907d0018u,0x3c608000u,0x93dd0010u};
 for(unsigned i=0;i<4;i++)be32(elf+0x200+4*i,op[i]);
 for(unsigned i=4;i<14;i++)be32(elf+0x200+4*i,0x60000000u);
 be32(elf+0x200+4*14,0x4e800020u);
 if(ar_bridge_init(0x1000)!=AR_OK)return 1;
 /* Verify original ELF signature and reject a modified executable word. */
 elf[0x201]^=1;
 if(ar_m714_register_fragment(elf,sizeof(elf))!=AR_BAD_ARGS||ar_registered_count()) return 2;
 elf[0x201]^=1;
 if(ar_m714_register_fragment(elf,sizeof(elf))!=AR_OK||ar_registered_count()!=1) return 3;
 if(ar_m714_register_fragment(elf,sizeof(elf))!=AR_DUPLICATE)return 4;
 ppu_context c={0};
 c.gpr[29]=0x180;c.gpr[4]=UINT64_C(0xbeef000012345678);
 c.gpr[3]=UINT64_C(0xdeadbeefbabacafe);c.gpr[30]=UINT64_C(0x1011223344);
 c.xer=0x1234u;c.cr=0xabab1234u;c.lr=0x1177u;c.ctr=0x88u;
 int rc=ar_run(&c,0x003c4da4u,4);
 if(rc!=AR_UNRESOLVED || ar_last_unresolved()!=0x003c4db4u) return 5;
 if(c.gpr[4]!=0x12345678u||c.gpr[3]!=UINT64_C(0xffffffff80000000)||c.xer!=0x1234u || c.cr!=0xabab1234u || c.lr!=0x1177u || c.ctr!=0x88u) return 6;
 if(ar_read32(0x180u+24u)!=0xbabacafeu||ar_read32(0x180u+16u)!=0x11223344u) return 7;
 uint32_t out[32]={0},count=0,terminal=0;
 if(ar_m714_frontier_inventory(elf,sizeof(elf),0x003c4db4u,out,&count,&terminal)!=AR_OK||count!=11u||terminal!=0x003c4ddcu) return 8;
 if(out[0]!=0x60000000u||out[10]!=0x4e800020u)return 9;
 be32(ph+4,4);
 if(ar_m714_frontier_inventory(elf,sizeof(elf),0x003c4db4u,out,&count,&terminal)!=AR_UNRESOLVED||count!=0u) return 10;
 be32(ph+4,5);
 ar_bridge_shutdown();
 if(ar_bridge_init(0x1000)!=AR_OK||ar_m714_register_fragment(elf,sizeof(elf))!=AR_OK)return 11;
 memset(&c,0,sizeof(c));c.gpr[29]=UINT64_C(0xffffff00);c.gpr[4]=UINT64_MAX;c.cr=0xaau;
 rc=ar_run(&c,0x003c4da4u,4);
 if(rc!=AR_MEM_FAULT||c.cia==0x003c4db4u||c.gpr[3]!=0u||c.cr!=0xaau) return 12;
 ar_bridge_shutdown();
 puts("M7.14 authenticated native stores and bounded 32-word frontier batch PASS");return 0;
}
