/* M7.12 read-only PPC code inspection on entirely synthetic ELF. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);
static void b16(uint8_t*p,uint16_t n){p[0]=(uint8_t)(n>>8);p[1]=(uint8_t)n;}
static void b32(uint8_t*p,uint32_t n){p[0]=(uint8_t)(n>>24);p[1]=(uint8_t)(n>>16);p[2]=(uint8_t)(n>>8);p[3]=(uint8_t)n;}
static void b64(uint8_t*p,uint64_t n){b32(p,(uint32_t)(n>>32));b32(p+4,(uint32_t)n);}
int main(void){
 uint8_t elf[640]={0};uint32_t out[6]={0};
 memcpy(elf,"\177ELF",4);elf[4]=2;elf[5]=2;elf[6]=1;
 b16(elf+16,2);b16(elf+18,21);b32(elf+20,1);
 b64(elf+32,64);b16(elf+54,56);b16(elf+56,1);
 uint8_t*p=elf+64;
 b32(p,1);b32(p+4,5);b64(p+8,0x200);
 b64(p+16,0x002c1664);b64(p+32,16);b64(p+40,16);
 uint32_t w[4]={0x38600001u,0x4e800020u,0x60000000u,0x48000004u};
 for(unsigned i=0;i<4;i++)b32(elf+0x200+4*i,w[i]);
 if(ar_m712_exec_window(elf,sizeof(elf),0x002c1664,out)||out[4]!=4||out[5]!=5)return 1;
 for(unsigned i=0;i<4;i++)if(out[i]!=w[i])return 2;
 if(ar_m712_exec_window(elf,sizeof(elf),0x002c1670,out)||out[4]!=1||out[0]!=w[3])return 3;
 if(ar_m712_exec_window(elf,sizeof(elf),0x002c1665,out)!=-1)return 4;
 if(ar_m712_exec_window(elf,sizeof(elf),0x002c1674,out)!=-3)return 5;
 b32(p+4,4);
 if(ar_m712_exec_window(elf,sizeof(elf),0x002c1664,out)!=-3)return 6;
 b32(p+4,5);b64(p+32,1024);
 if(ar_m712_exec_window(elf,sizeof(elf),0x002c1664,out)!=-2)return 7;
 puts("M7.12 verified PPC ELF instruction window without execution PASS");
 return 0;
}
