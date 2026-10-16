/* Synthetic PPU fixture: NO Ascension bytes or license. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
extern int ar_private_elf_inspect(const uint8_t*,size_t,uint32_t[5]);
extern int ar_ppu_bootstrap_thirtytwo(const uint8_t*,size_t,
                                   const uint32_t[5],uint32_t[10]);
static void p16(uint8_t*d,int i,uint16_t x){d[i]=x>>8;d[i+1]=x;}
static void p32(uint8_t*d,int i,uint32_t x){
 d[i]=x>>24;d[i+1]=x>>16;d[i+2]=x>>8;d[i+3]=x;
}
static void p64(uint8_t*d,int i,uint64_t x){p32(d,i,x>>32);p32(d,i+4,x);}
int main(void){
 uint8_t d[0x400]={0};uint32_t info[5]={0},cpu[10]={0};
 memcpy(d,"\177ELF",4);d[4]=2;d[5]=2;d[6]=1;d[7]=0x66;
 p16(d,16,2);p16(d,18,21);p32(d,20,1);p64(d,24,0x20000);
 p64(d,32,64);p16(d,52,64);p16(d,54,56);p16(d,56,2);
 p32(d,64,1);p32(d,68,5);p64(d,72,0x100);p64(d,80,0x10000);
 p64(d,96,0x90);p64(d,104,0x90);
 p32(d,120,1);p32(d,124,6);p64(d,128,0x240);p64(d,136,0x20000);
 p64(d,152,0x80);p64(d,160,0x100);
 static const uint32_t program[16]={
   0x38400000u,0x64420002u,0x60420000u,0x80420004u,
   0xf821ff91u,0x39c00000u,0xf9c10000u,0x48000011u,
   0xf821ff61u,0x7c0802a6u,0xfb410070u,0xfb810080u,
   0xfbc10090u,0xfbe10098u,0xfb610078u,0xfba10088u
 };
 for(unsigned i=0;i<8;i++)p32(d,0x100+4*i,program[i]);
 for(unsigned i=8;i<16;i++)p32(d,0x12c+4*(i-8),program[i]);
 static const uint32_t more[8]={
   0x3ca00001u,0x3900ffffu,0x60840002u,0xf8a100a0u,
   0xe8c100a0u,0x7cc63378u,0x90c100a4u,0x79040020u
 };
 for(unsigned i=0;i<8;i++)p32(d,0x14c+4*i,more[i]);
 static const uint32_t tail[8]={
   0xf88100a8u,0xe8a100a8u,0x7ca42b78u,0x39600007u,
   0x916100b0u,0x60000000u,0x60000000u,0x48000004u
 };
 for(unsigned i=0;i<8;i++)p32(d,0x16c+4*i,tail[i]);
 p32(d,0x240,0x10000);p32(d,0x244,0x20010);
 if(ar_private_elf_inspect(d,sizeof d,info))return 1;
 int rc=ar_ppu_bootstrap_thirtytwo(d,sizeof d,info,cpu);
 if(rc){fprintf(stderr,"M6.3 sandbox first pass failed rc=%d steps=%u PC=%X word=%X\n",rc,cpu[0],cpu[8],cpu[7]);return 2;}
 if(cpu[0]!=32u||cpu[1]!=0x20010u||cpu[2]!=0x1008cu||
    cpu[3]!=0x10020u||cpu[4]!=0x07000ef0u||
    cpu[5]!=13u||cpu[6]!=0x10020u||
    cpu[7]!=0x48000004u||cpu[8]!=0x10088u||
    cpu[9]!=0xffffffffu){
     fprintf(stderr,"M6.4 state steps=%u toc=%X PC=%X LR=%X SP=%X stores=%u r0=%X op=%X fetch=%X r4=%X\n",
       cpu[0],cpu[1],cpu[2],cpu[3],cpu[4],cpu[5],cpu[6],cpu[7],cpu[8],cpu[9]);
     return 3;
 }
 uint64_t masked=0;
 extern int ar_ppu_rldicl(uint32_t,uint64_t,uint64_t*);
 if(ar_ppu_rldicl(0x79040020u,UINT64_C(0x12345678fedcba98),&masked)||
    masked!=UINT64_C(0xfedcba98))return 6;
 if(ar_ppu_rldicl(0x79040021u,~UINT64_C(0),&masked)==0)return 7;
 if(ar_ppu_rldicl(0x79040024u,~UINT64_C(0),&masked)==0)return 8;
 p32(d,0x168,0x79040021u);
 if(ar_ppu_bootstrap_thirtytwo(d,sizeof d,info,cpu)!=-998||
    cpu[0]!=23u||cpu[8]!=0x10068u)return 9;
 p32(d,0x168,more[7]);
 p32(d,0x16c,0xffffffffu);
 if(ar_ppu_bootstrap_thirtytwo(d,sizeof d,info,cpu)!=-990||
    cpu[0]!=24u||cpu[8]!=0x1006cu||cpu[7]!=0xffffffffu)return 4;
 p32(d,0x16c,tail[0]);
 p32(d,0x12c,0xf8210101); /* invalid positive DS stack address */
 if(ar_ppu_bootstrap_thirtytwo(d,sizeof d,info,cpu)!=-987)return 5;
 puts("M6.4 PPU32 and rldicl PASS");return 0;
}
