/* M7.46 native regression of authentic owner PPC words; synthetic guest RAM. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
extern int ar_m746_register_hotloop(const uint8_t*,size_t);
extern int ar_m746_native_003ef6cc(ppu_context*);
extern int ar_m746_native_003ef744(ppu_context*);
extern int ar_m746_native_003ef7ac(ppu_context*);
extern int ar_m746_native_003ef7b4(ppu_context*);
static uint32_t words[69]={
UINT32_C(0xf821ffc1),UINT32_C(0x38e00000),UINT32_C(0x3880ffff),UINT32_C(0x38c00000),UINT32_C(0x39000020),UINT32_C(0x98e30000),UINT32_C(0x60650000),UINT32_C(0x90e30340),UINT32_C(0x7d0903a6),UINT32_C(0x90e30344),UINT32_C(0x90830348),UINT32_C(0xf8c30350),UINT32_C(0x90e30358),UINT32_C(0x90e3035c),UINT32_C(0x90e309b0),UINT32_C(0x90e3033c),UINT32_C(0x90e30338),UINT32_C(0x90e30360),UINT32_C(0x98e30379),UINT32_C(0x90e309b4),UINT32_C(0x90e30364),UINT32_C(0x90e30370),UINT32_C(0x90e30374),UINT32_C(0x90e3036c),UINT32_C(0x90e30368),UINT32_C(0x98e30378),UINT32_C(0x98e3037a),UINT32_C(0xfbe10038),UINT32_C(0x90e3037c),UINT32_C(0x90e30380),UINT32_C(0x31050398),UINT32_C(0x31250390),UINT32_C(0x79080020),UINT32_C(0x3145039c),UINT32_C(0x79290020),UINT32_C(0x316503b0),UINT32_C(0x31850388),UINT32_C(0x794a0020),UINT32_C(0x796b0020),UINT32_C(0x90e80000),UINT32_C(0x79880020),UINT32_C(0xf8c90000),UINT32_C(0x33e503b4),UINT32_C(0x312503a0),UINT32_C(0x98ea0000),UINT32_C(0x90eb0000),UINT32_C(0x7bea0020),UINT32_C(0x90e80000),UINT32_C(0x316503a8),UINT32_C(0x79280020),UINT32_C(0x79690020),UINT32_C(0x30a50030),UINT32_C(0x98ea0000),UINT32_C(0x90e80000),UINT32_C(0xf8c90000),UINT32_C(0x4200ff9c),UINT32_C(0x38a00005),UINT32_C(0x7ca903a6),UINT32_C(0x30a30988),UINT32_C(0x30c3098c),UINT32_C(0x78a50020),UINT32_C(0x78c60020),UINT32_C(0x30630008),UINT32_C(0x90850000),UINT32_C(0x90860000),UINT32_C(0x4200ffe4),UINT32_C(0xebe10038),UINT32_C(0x38210040),UINT32_C(0x4e800020)
};
static uint32_t loaded[69];
static uint8_t ram[0x9000];
static int fault,registered;
static ar_ppu_fn fns[4];
int ar_m712_exec_window(const uint8_t*elf,size_t len,uint32_t pc,uint32_t out[6]){
 if(!elf||len<64||!out||pc<0x003ef6ccu||pc>=0x003ef7e0u||(pc&3u))return AR_BAD_ARGS;
 const unsigned ix=(pc-0x003ef6ccu)/4u;
 const unsigned n=(69u-ix<4u)?69u-ix:4u;
 memset(out,0,6u*sizeof(uint32_t));
 for(unsigned i=0;i<n;i++)out[i]=words[ix+i];
 out[4]=n;out[5]=5u;return AR_OK;
}
static uint64_t rd(uint64_t p,unsigned size){
 if(p>sizeof(ram)||size>sizeof(ram)-p){fault=AR_MEM_FAULT;return 0;}
 uint64_t v=0;for(unsigned i=0;i<size;i++)v=(v<<8)|ram[(size_t)p+i];return v;
}
static void wr(uint64_t p,uint64_t v,unsigned size){
 if(p>sizeof(ram)||size>sizeof(ram)-p){fault=AR_MEM_FAULT;return;}
 for(unsigned i=0;i<size;i++){ram[(size_t)p+size-1u-i]=(uint8_t)v;v>>=8;}
}
uint32_t ar_read32(uint64_t p){
 if(p>=0x003ef6ccu&&p<0x003ef7e0u&&!(p&3u))return loaded[(p-0x003ef6ccu)/4u];
 return (uint32_t)rd(p,4u);
}
uint64_t ar_read64(uint64_t p){return rd(p,8u);}
void ar_write8(uint64_t p,uint8_t v){wr(p,v,1u);}
void ar_write32(uint64_t p,uint32_t v){wr(p,v,4u);}
void ar_write64(uint64_t p,uint64_t v){wr(p,v,8u);}
int ar_last_error(void){return fault;}
int ar_register(uint32_t pc,ar_ppu_fn fn){
 static const uint32_t addr[]={0x003ef6ccu,0x003ef744u,0x003ef7acu,0x003ef7b4u};
 if(registered>=4||pc!=addr[registered])return AR_DUPLICATE;
 fns[registered++]=fn;return AR_OK;
}
int main(void){
 uint8_t fake[64]={0};
 memcpy(loaded,words,sizeof(words));
 if(ar_m746_register_hotloop(NULL,64)!=AR_BAD_ARGS)return 1;
 words[0]^=1u;
 if(ar_m746_register_hotloop(fake,64)!=AR_BAD_ARGS||registered)return 2;
 words[0]^=1u;loaded[68]^=1u;
 if(ar_m746_register_hotloop(fake,64)!=AR_BAD_ARGS||registered)return 3;
 loaded[68]^=1u;
 if(ar_m746_register_hotloop(fake,64)!=AR_OK||registered!=4)return 4;
 ppu_context c={0};
 c.gpr[1]=0x6000u;c.gpr[3]=0x1000u;
 c.gpr[31]=UINT64_C(0x12345678abcdef);
 c.lr=UINT64_C(0x234567890);c.xer=UINT32_C(0x80000000);c.cr=UINT32_C(0x12345678);
 if(fns[0](&c)!=AR_OK)return 5;
 if(c.gpr[1]!=0x6000u||c.gpr[3]!=0x1028u||
    c.gpr[31]!=UINT64_C(0x12345678abcdef)||
    c.ctr!=0||c.lr!=UINT64_C(0x234567890)||
    c.cr!=UINT32_C(0x12345678)||
    ar_read32(0x1000u+840u)!=UINT32_MAX||
    ar_read32(0x1000u+896u)!=0u||
    ar_read32(0x1000u+2440u)!=UINT32_MAX||
    ar_read32(0x1000u+2444u)!=UINT32_MAX)return 6;
 memset(&c,0,sizeof(c));memset(ram,0,sizeof(ram));fault=0;
 c.gpr[1]=0x6000u;c.gpr[3]=c.gpr[5]=0x1000u;
 c.gpr[4]=UINT64_MAX;c.ctr=32u;wr(0x6000u+56u,0x10101010u,8u);
 if(fns[1](&c)!=AR_OK||c.gpr[3]!=0x1028u||c.ctr!=0||
    c.gpr[31]!=0x10101010u)return 7;
 memset(&c,0,sizeof(c));memset(ram,0,sizeof(ram));fault=0;
 c.gpr[1]=0x6000u;c.gpr[3]=0x1000u;c.gpr[4]=UINT64_MAX;
 wr(0x6000u+56u,0x2030u,8u);
 if(fns[2](&c)!=AR_OK||c.gpr[3]!=0x1028u||c.ctr!=0||
    c.gpr[31]!=0x2030u)return 8;
 memset(&c,0,sizeof(c));memset(ram,0,sizeof(ram));fault=0;
 c.gpr[1]=0x6000u;c.gpr[3]=0x1000u;c.gpr[4]=UINT64_MAX;c.ctr=5u;
 wr(0x6000u+56u,0x4050u,8u);
 if(fns[3](&c)!=AR_OK||c.gpr[3]!=0x1028u||c.ctr!=0||
    c.gpr[31]!=0x4050u)return 9;
 memset(&c,0,sizeof(c));memset(ram,0,sizeof(ram));fault=0;
 c.gpr[1]=0x6000u;c.gpr[3]=c.gpr[5]=0x1000u;
 c.gpr[4]=UINT64_MAX;c.ctr=100u;
 if(fns[1](&c)!=AR_PPC_LIMIT||c.cia!=0x003ef744u)return 10;
 memset(&c,0,sizeof(c));memset(ram,0,sizeof(ram));fault=0;
 c.gpr[1]=0x6000u;c.gpr[3]=0x8ff0u;
 if(fns[0](&c)!=AR_MEM_FAULT)return 11;
 puts("M7.46 owner 69 PPC words: 4 native entries, 32+5 real CTR loops, 64 iteration cap, original ELF/VM mismatches blocked, memory faults PASS");
 return 0;
}
