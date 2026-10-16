/* Generated fixture; no commercial title data. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
extern int ar_private_elf_inspect(const uint8_t*,size_t,uint32_t[5]);
static void p16(uint8_t*d,int i,uint16_t x){d[i]=x>>8;d[i+1]=x;}
static void p32(uint8_t*d,int i,uint32_t x){
 d[i]=x>>24;d[i+1]=x>>16;d[i+2]=x>>8;d[i+3]=x;
}
static void p64(uint8_t*d,int i,uint64_t x){p32(d,i,x>>32);p32(d,i+4,x);}
int main(void){
 uint8_t d[0x300]={0};uint32_t o[5]={0};
 memcpy(d,"\177ELF",4);d[4]=2;d[5]=2;d[6]=1;d[7]=0x66;
 p16(d,16,2);p16(d,18,21);p32(d,20,1);p64(d,24,0x20000);
 p64(d,32,64);p16(d,52,64);p16(d,54,56);p16(d,56,2);
 p32(d,64,1);p32(d,68,5);p64(d,72,0x100);p64(d,80,0x10000);
 p64(d,96,0x80);p64(d,104,0x80);
 p32(d,120,1);p32(d,124,6);p64(d,128,0x180);p64(d,136,0x20000);
 p64(d,152,0x80);p64(d,160,0x100);
 p32(d,0x100,0x38400000);p32(d,0x180,0x10000);p32(d,0x184,0x20010);
 if(ar_private_elf_inspect(d,sizeof d,o))return 1;
 if(o[0]!=0x20000||o[1]!=0x10000||o[2]!=0x20010||o[3]!=0x38400000||o[4]!=2)return 2;
 d[0]='S';if(!ar_private_elf_inspect(d,sizeof d,o))return 3;d[0]=0x7f;
 d[5]=1;if(!ar_private_elf_inspect(d,sizeof d,o))return 4;d[5]=2;
 p32(d,0x180,0xff001122);if(!ar_private_elf_inspect(d,sizeof d,o))return 5;
 p32(d,0x180,0x10000);p64(d,96,0xffffffffffffffffULL);
 if(!ar_private_elf_inspect(d,sizeof d,o))return 6;
 puts("M5.9 host ELF validator PASS");return 0;
}
