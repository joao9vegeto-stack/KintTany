/* ELF bytes and actual guest VM MUST be sampled independently. */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "ppu_bridge.h"
#include "ppu_m756_stop_evidence.h"
static uint8_t guest[AR_M756_SAMPLE_BYTES];
static int available=1;
int ar_vm_read_bytes(uint64_t pc,void*dst,size_t n){
 if(!available||pc!=0x003c4fc4||n>sizeof(guest))return AR_MEM_FAULT;
 memcpy(dst,guest,n);return AR_OK;
}
static void be16(uint8_t*p,uint16_t x){p[0]=(uint8_t)(x>>8);p[1]=(uint8_t)x;}
static void be32(uint8_t*p,uint32_t x){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(x>>(24-8*i));}
static void be64(uint8_t*p,uint64_t x){for(unsigned i=0;i<8;i++)p[i]=(uint8_t)(x>>(56-8*i));}
int main(void){
 uint8_t elf[512]={0};
 elf[0]=127;elf[1]='E';elf[2]='L';elf[3]='F';
 elf[4]=2;elf[5]=2;elf[6]=1;
 be64(elf+32,64u);be16(elf+54,56u);be16(elf+56,1u);
 be32(elf+64,1u);be32(elf+68,5u);be64(elf+72,0x100u);
 be64(elf+80,0x003c4fc4u);be64(elf+96,28u);be64(elf+104,28u);
 const uint32_t w[7]={0x30c90004,0x7cc63b96,0x7cc639d6,
                       0x7cc64810,0x30c60004,0x2c060000,0x41820008};
 for(unsigned i=0;i<7;i++)be32(elf+0x100+4*i,w[i]);
 memcpy(guest,elf+0x100,sizeof(guest));
 ar_m756_stop_evidence ev={0};
 ar_m756_capture_stop(elf,sizeof(elf),0x003c4fc4,&ev);
 if(ev.elf_status!=AR_OK||ev.guest_status!=AR_OK||!ev.match||
    ev.elf_word!=w[0]||ev.guest_word!=w[0]||
    ev.file_offset!=0x100||ev.segment_va!=0x003c4fc4||
    ev.count!=28u)return 1;
 guest[0]=0x00;
 ar_m756_capture_stop(elf,sizeof(elf),0x003c4fc4,&ev);
 if(ev.match||ev.guest_word!=0x00c90004||ev.elf_word!=w[0])return 2;
 available=0;
 ar_m756_capture_stop(elf,sizeof(elf),0x003c4fc4,&ev);
 if(ev.elf_status!=AR_OK||ev.guest_status!=AR_MEM_FAULT||
    ev.elf_word!=w[0])return 3;
 puts("M7.56 independent PT_LOAD X / ELF offset / live guest memory bytes: match, mismatch, inaccessible PASS");
 return 0;
}
