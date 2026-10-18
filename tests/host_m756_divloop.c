/* Synthetic register/CR/XER tests; no game assets embedded. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
extern int ar_m756_register_divloop(const uint8_t*,size_t);
static const uint32_t real[7]={
 0x30c90004,0x7cc63b96,0x7cc639d6,0x7cc64810,
 0x30c60004,0x2c060000,0x41820008
};
static uint32_t vm[7]={
 0x30c90004,0x7cc63b96,0x7cc639d6,0x7cc64810,
 0x30c60004,0x2c060000,0x41820008
};
static ar_ppu_fn fn;
int ar_m712_exec_window(const uint8_t*d,size_t len,uint32_t pc,uint32_t out[6]){
 if(!d||len<64||!(pc==0x003c4fc4||pc==0x003c4fd4))return AR_BAD_ARGS;
 memset(out,0,sizeof(uint32_t)*6u);
 const unsigned start=(pc-0x003c4fc4)/4u;
 for(unsigned i=0;i<4u&&start+i<7u;i++)out[i]=real[start+i];
 out[4]=start?3u:4u;out[5]=5u;return AR_OK;
}
uint32_t ar_read32(uint64_t pc){
 if(pc<0x003c4fc4||pc>0x003c4fdc||((pc-0x003c4fc4)&3u))return 0;
 return vm[(pc-0x003c4fc4)/4u];
}
int ar_last_error(void){return AR_OK;}
int ar_register(uint32_t pc,ar_ppu_fn f){
 if(pc!=0x003c4fc4||fn)return AR_BAD_ARGS;
 fn=f;return AR_OK;
}
static int run(uint64_t r9,uint64_t r7,uint64_t to,uint32_t nibble){
 ppu_context c={0};
 c.gpr[9]=r9;c.gpr[7]=r7;c.xer=0x80000000;
 c.cr=0x0abcdef0;c.lr=0x11223344;c.ctr=0x55667788;
 const int rc=fn(&c);
 if(rc!=AR_TAIL||c.cia!=to||(c.cr>>28)!=nibble||
    (c.cr&0x0fffffffu)!=0x0abcdef0||
    c.gpr[9]!=r9||c.gpr[7]!=r7||
    c.lr!=0x11223344||c.ctr!=0x55667788||
    !(c.xer&0x80000000))return 1;
 return 0;
}
int main(void){
 uint8_t d[64]={0};
 vm[0]^=1u;
 if(ar_m756_register_divloop(d,sizeof(d))==AR_OK||fn)return 1;
 vm[0]^=1u;
 if(ar_m756_register_divloop(d,sizeof(d))!=AR_OK||!fn)return 2;
 if(run(4u,4u,0x003c4fe4u,3u))return 3; /* EQ + SO */
 if(run(5u,4u,0x003c4fe0u,5u))return 4; /* GT + SO */
 ppu_context c={0};c.gpr[9]=4;c.gpr[7]=0;c.cr=0x12345678;
 if(fn(&c)!=AR_PPC_UNSUPPORTED||c.cia!=0x003c4fc8||
    c.cr!=0x12345678)return 5;
 puts("M7.56 native 7 PPC words: authenticated two windows, DIVWU/MULLW/SUBFC/ADDIC/CMPWI/BEQ and both successors PASS");
 return 0;
}
