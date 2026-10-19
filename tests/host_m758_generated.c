/* Synthetic host-only tests of owner-ELF validation and generated 28-PPC AOT.
 * Interpreter and RPCS3 are not linked into iOS. Guest-FS calls not faked.
 */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
extern int ar_m758_register_owner(const uint8_t*,size_t);
extern int ar_m758_native_003c5110(ppu_context*);
static const uint32_t expected[28]={
 0x7c7ff014,0x3c808000,0x7c7b1810,0x5384c04a,
 0x5465013a,0x5463f1be,0x7cbb2814,0x5484000a,
 0x30a5fffc,0x53a4f1be,0x78a50020,0x907b0000,
 0x5486467a,0x90650000,0x7c7f3014,0x909f0000,
 0x7cbfe014,0x78630020,0x90830000,0x809f0000,
 0x30650004,0x5485113a,0x78630020,0x7cbf2814,
 0x30a5fffc,0x78a50020,0x90850000,0x48000078
};
static uint32_t vm[28]={
 0x7c7ff014,0x3c808000,0x7c7b1810,0x5384c04a,
 0x5465013a,0x5463f1be,0x7cbb2814,0x5484000a,
 0x30a5fffc,0x53a4f1be,0x78a50020,0x907b0000,
 0x5486467a,0x90650000,0x7c7f3014,0x909f0000,
 0x7cbfe014,0x78630020,0x90830000,0x809f0000,
 0x30650004,0x5485113a,0x78630020,0x7cbf2814,
 0x30a5fffc,0x78a50020,0x90850000,0x48000078
};
struct pair { uint64_t key; uint32_t value; } mem[64];
static unsigned count, writes;
static ar_ppu_fn fn;
int ar_m712_exec_window(const uint8_t*image,size_t len,uint32_t pc,uint32_t out[6]){
 if(!image||len<64u||pc<0x003c5110u||pc>=0x003c5180u||
    ((pc-0x003c5110u)&3u))return AR_BAD_ARGS;
 const unsigned start=(pc-0x003c5110u)/4u;
 memset(out,0,6u*sizeof(*out));
 for(unsigned i=0;i<4u&&start+i<28u;i++)out[i]=expected[start+i];
 out[4]=4u;out[5]=5u;return AR_OK;
}
uint32_t ar_read32(uint64_t pc){
 if(pc>=0x003c5110u&&pc<0x003c5180u &&
    !((pc-0x003c5110u)&3u))
    return vm[(pc-0x003c5110u)/4u];
 for(unsigned i=0;i<count;i++)if(mem[i].key==pc)return mem[i].value;
 return 0;
}
void ar_write32(uint64_t pc,uint32_t val){
 writes++;
 for(unsigned i=0;i<count;i++)if(mem[i].key==pc){
  mem[i].value=val;return;
 }
 if(count<64u)mem[count++]=(struct pair){pc,val};
}
int ar_last_error(void){return AR_OK;}
int ar_register(uint32_t pc,ar_ppu_fn f){
 if(pc!=0x003c5110u||fn)return AR_DUPLICATE;
 fn=f;return AR_OK;
}
int main(void){
 uint8_t elf[64]={0};
 vm[13]^=1u;
 if(ar_m758_register_owner(elf,sizeof(elf))==AR_OK||fn)return 1;
 vm[13]^=1u;
 if(ar_m758_register_owner(elf,sizeof(elf))!=AR_OK||!fn)return 2;
 ppu_context c={0};c.gpr[31]=0x1000;c.gpr[30]=8;
 c.gpr[27]=0x1000;c.gpr[28]=0x2000;c.gpr[29]=0x1000;
 c.gpr[3]=12;c.gpr[4]=4;c.gpr[5]=32;c.gpr[6]=20;
 c.lr=0x1234;c.ctr=11;
 if(fn(&c)!=AR_TAIL||c.cia!=0x003c51f4u||
    c.lr!=0x1234||c.ctr!=11||writes<4u||count==0)
     return 3;
 puts("M7.58: 28 original owner PPC words -> C AOT, native dispatch, guest memory stores and unconditional branch PASS");
 return 0;
}
