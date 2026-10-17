/* Entirely synthetic container validates 4 native PPC operations + CA. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
extern int ar_m713_register_fragment(const uint8_t*,size_t);
extern int ar_m713_aot_003c4d94(ppu_context*);
static void be16(uint8_t*p,uint16_t n){p[0]=(uint8_t)(n>>8);p[1]=(uint8_t)n;}
static void be32(uint8_t*p,uint32_t n){p[0]=(uint8_t)(n>>24);p[1]=(uint8_t)(n>>16);p[2]=(uint8_t)(n>>8);p[3]=(uint8_t)n;}
static void be64(uint8_t*p,uint64_t n){be32(p,(uint32_t)(n>>32));be32(p+4,(uint32_t)n);}
int main(void) {
    uint8_t elf[640]={0};
    memcpy(elf,"\177ELF",4);elf[4]=2;elf[5]=2;elf[6]=1;
    be16(elf+16,2);be16(elf+18,21);be32(elf+20,1);
    be64(elf+32,64);be16(elf+54,56);be16(elf+56,1);
    uint8_t *ph=elf+64;
    be32(ph,1);be32(ph+4,5);be64(ph+8,0x200);
    be64(ph+16,0x003c4d94);be64(ph+32,16);be64(ph+40,16);
    const uint32_t words[4]={0x7c7ef814,0x3ca00085,0x3063fffc,0x309d0040};
    for(unsigned i=0;i<4;i++)be32(elf+0x200+4*i,words[i]);
    if(ar_bridge_init(0x1000)!=AR_OK)return 1;
    /* Changed bytes or removed PF_X must never register an AOT entry. */
    elf[0x203]^=1;
    if(ar_m713_register_fragment(elf,sizeof(elf))!=AR_BAD_ARGS || ar_registered_count()) return 2;
    elf[0x203]^=1;
    be32(ph+4,4);
    if(ar_m713_register_fragment(elf,sizeof(elf))!=AR_BAD_ARGS || ar_registered_count()) return 3;
    be32(ph+4,5);
    if(ar_m713_register_fragment(elf,sizeof(elf))!=AR_OK || ar_registered_count()!=1) return 4;
    if(ar_m713_register_fragment(elf,sizeof(elf))!=AR_DUPLICATE) return 5;
    ppu_context c={0};
    c.gpr[30]=5;c.gpr[31]=7;c.gpr[29]=0;
    c.lr=0x1234;c.ctr=8;c.cr=0xa00b000a;c.xer=0x80000000;
    int rc=ar_run(&c,0x003c4d94,4);
    if(rc!=AR_UNRESOLVED||ar_last_unresolved()!=0x003c4da4||c.cia!=0x003c4da4) return 6;
    if(c.gpr[3]!=8||c.gpr[4]!=64||c.gpr[5]!=0x850000) return 7;
    if(c.lr!=0x1234||c.ctr!=8||c.cr!=0xa00b000a||c.xer!=0x80000000) return 8;
    /* All arithmetic must wrap as 64 bit; final addic sets XER.CA. */
    ar_bridge_shutdown();
    if(ar_bridge_init(0x1000)!=AR_OK||ar_m713_register_fragment(elf,sizeof(elf))!=AR_OK) return 9;
    memset(&c,0,sizeof(c));
    c.gpr[30]=UINT64_MAX;c.gpr[31]=2;c.gpr[29]=UINT64_MAX-10;
    rc=ar_run(&c,0x003c4d94,4);
    if(rc!=AR_UNRESOLVED||c.gpr[3]!=UINT64_MAX-2||c.gpr[4]!=53 ||
       (c.xer & 0x20000000u)==0) return 10;
    ar_bridge_shutdown();
    puts("M7.13 authentic four-instruction AOT fragment, XER carry and next-PC PASS");
    return 0;
}
