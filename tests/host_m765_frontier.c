/* M7.65 realistic iPhone CR 0x22000042, no guest interpreter.
   Two actual PPC CFG successors, signed guest BE LWZ/STB and call LR, return. */
#include "ppu_bridge.h"
#include <stdio.h>
#include <string.h>
extern int ar_m765_native_00539308(ppu_context*);
extern int ar_m765_native_0053930c(ppu_context*);
extern int ar_m765_native_005392f4(ppu_context*);
static int fault;
static unsigned char bytes[32];
int ar_last_error(void){return fault;}
uint8_t ar_read8(uint64_t ea){if(ea>=0xab20u&&ea<0xab40u)return bytes[ea-0xab20u];fault=AR_MEM_FAULT;return 0;}
uint32_t ar_read32(uint64_t ea){if(ea==0x839b08u)return 0xab20u;if(ea==0x839b0cu)return 0xab10u;fault=AR_MEM_FAULT;return 0;}
uint64_t ar_read64(uint64_t ea){if(ea==0x1100a0u)return 0x10858u;if(ea==0x110078u)return 0x12234u;fault=AR_MEM_FAULT;return 0;}
void ar_write8(uint64_t ea,uint8_t x){if(ea>=0xab20u&&ea<0xab40u){bytes[ea-0xab20u]=x;return;}fault=AR_MEM_FAULT;}
void ar_write64(uint64_t ea,uint64_t x){(void)ea;(void)x;fault=AR_MEM_FAULT;}
int main(void){
 ppu_context c;memset(&c,0,sizeof(c));memset(bytes,0xa5,sizeof(bytes));
 c.cr=0x22000042u;c.gpr[1]=0x110000u;c.gpr[2]=0x83f2b0u;c.gpr[3]=1u;c.lr=0x10858u;
 if(ar_m765_native_00539308(&c)!=AR_TAIL||c.cia!=0x53930cu)return 1;
 if(ar_m765_native_0053930c(&c)!=AR_TAIL||c.cia!=0x539654u||
    c.lr!=0x539324u||c.gpr[29]!=0xab20u||c.gpr[4]!=0xab10u||bytes[4]!=0)return 2;
 c.cr&=~(1u<<(31-6));
 if(ar_m765_native_00539308(&c)!=AR_TAIL||c.cia!=0x5392f4u)return 3;
 c.gpr[1]=0x110000u;c.lr=0;fault=0;
 if(ar_m765_native_005392f4(&c)!=AR_TAIL||c.cia!=0x10858u||c.lr!=0x10858u||
    c.gpr[29]!=0x12234u||c.gpr[1]!=0x110090u)return 4;
 puts("M7.65 real PPC CFG 0x539308 both BO4 branches, native LWZ/STB/BL/LD/MTLR/BLR PASS");
 return 0;
}
