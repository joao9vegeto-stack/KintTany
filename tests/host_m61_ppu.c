/* Synthetic PPU ELF with no copyrighted game instructions. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
extern int ar_private_elf_inspect(const uint8_t*,size_t,uint32_t[5]);
extern int ar_ppu_bootstrap_eight(const uint8_t*,size_t,const uint32_t[5],uint32_t[6]);
static void p16(uint8_t*d,int i,uint16_t x){d[i]=x>>8;d[i+1]=x;}
static void p32(uint8_t*d,int i,uint32_t x){
 d[i]=x>>24;d[i+1]=x>>16;d[i+2]=x>>8;d[i+3]=x;
}
static void p64(uint8_t*d,int i,uint64_t x){p32(d,i,x>>32);p32(d,i+4,x);}
int main(void){
 uint8_t d[0x300]={0};uint32_t info[5]={0},res[6]={0};
 memcpy(d,"\177ELF",4);d[4]=2;d[5]=2;d[6]=1;d[7]=0x66;
 p16(d,16,2);p16(d,18,21);p32(d,20,1);p64(d,24,0x20000);
 p64(d,32,64);p16(d,52,64);p16(d,54,56);p16(d,56,2);
 p32(d,64,1);p32(d,68,5);p64(d,72,0x100);p64(d,80,0x10000);
 p64(d,96,0x80);p64(d,104,0x80);
 p32(d,120,1);p32(d,124,6);p64(d,128,0x180);p64(d,136,0x20000);
 p64(d,152,0x80);p64(d,160,0x100);
 p32(d,0x100,0x38400000);p32(d,0x104,0x64420002);
 p32(d,0x108,0x60420000);p32(d,0x10c,0x80420004);
 p32(d,0x110,0xf821ff91);p32(d,0x114,0x39c00000);
 p32(d,0x118,0xf9c10000);p32(d,0x11c,0x48000011);
 p32(d,0x180,0x10000);p32(d,0x184,0x20010);
 if(ar_private_elf_inspect(d,sizeof d,info))return 1;
 if(ar_ppu_bootstrap_eight(d,sizeof d,info,res))return 2;
 if(res[0]!=8||res[1]!=0x20010||res[2]!=0x1002c||
    res[3]!=0x10020||res[4]!=0x07000f90||res[5]!=2)return 3;
 p32(d,0x118,0xffffffff);
 if(ar_ppu_bootstrap_eight(d,sizeof d,info,res)!=-950||res[0]!=6)return 4;
 p32(d,0x118,0xf9c10000);p32(d,0x11c,0x48000109);
 if(ar_ppu_bootstrap_eight(d,sizeof d,info,res)!=-949)return 5;
 puts("M6.1 PPU8 stack and BL PASS");return 0;
}
