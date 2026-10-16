/* Synthetic PPU fixture: NO Ascension bytes or license. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
extern int ar_private_elf_inspect(const uint8_t*,size_t,uint32_t[5]);
extern int ar_ppu_bootstrap_fortyeight(const uint8_t*,size_t,
                                   const uint32_t[5],uint32_t[20]);
extern int ar_ppu_bootstrap_fortyeight_trace_m672(const uint8_t*,size_t,
                  const uint32_t[5],uint32_t[20],uint32_t[24],uint32_t[24]);
extern int ar_ppu_bootstrap_thirtytwo(const uint8_t*,size_t,
                                   const uint32_t[5],uint32_t[10]);
static void p16(uint8_t*d,int i,uint16_t x){d[i]=x>>8;d[i+1]=x;}
static void p32(uint8_t*d,int i,uint32_t x){
 d[i]=x>>24;d[i+1]=x>>16;d[i+2]=x>>8;d[i+3]=x;
}
static void p64(uint8_t*d,int i,uint64_t x){p32(d,i,x>>32);p32(d,i+4,x);}
int main(void){
 uint8_t d[0x400]={0};uint32_t info[5]={0},cpu[20]={0},trace[24]={0},detail[24]={0};
 memcpy(d,"\177ELF",4);d[4]=2;d[5]=2;d[6]=1;d[7]=0x66;
 p16(d,16,2);p16(d,18,21);p32(d,20,1);p64(d,24,0x20000);
 p64(d,32,64);p16(d,52,64);p16(d,54,56);p16(d,56,2);
 p32(d,64,1);p32(d,68,5);p64(d,72,0x100);p64(d,80,0x10000);
 p64(d,96,0xc0);p64(d,104,0xc0);
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
 static const uint32_t next[8]={
   0x39620050u,0x3ba01234u,0x93ab0000u,0x818b0000u,
   0x396b0080u,0x93ab0000u,0x81ab0000u,0x48000004u
 };
 for(unsigned i=0;i<8;i++)p32(d,0x18c+4*i,next[i]);
 p32(d,0x240,0x10000);p32(d,0x244,0x20010);
 p32(d,0x2a0,0xfeedface); /* immutable original backing at VA 0x20060 */
 if(ar_private_elf_inspect(d,sizeof d,info))return 1;

 p32(d,0x180,0x6000006cu);  /* r0 = 0x1006c */
 p32(d,0x198,0x600c0000u); /* r12 = r0, points to PPC code */
 p32(d,0x19c,0x800c0000u); /* lwz r0,0(r12) */
 p32(d,0x1a0,0x804c0004u); /* lwz r2,4(r12) */
 p32(d,0x1a4,0x7c0903a6u); /* mtctr r0 */
 p32(d,0x1a8,0x4e800421u); /* bctrl */
 int rc=ar_ppu_bootstrap_fortyeight_trace_m672(d,sizeof d,info,cpu,trace,detail);
 if(rc!=-1007||cpu[0]!=39u||cpu[19]!=0u||
    trace[0]!=0x1009cu||trace[1]!=0x800c0000u||
    detail[0]!=0x10098u||detail[3]!=0x1006cu||
    detail[8]!=0x1006cu||detail[9]!=0xf88100a8u||
    detail[10]!=2u||detail[11]!=5u||
    detail[12]!=0x10070u||detail[13]!=0xe8a100a8u||
    detail[14]!=2u||detail[15]!=5u){
   fprintf(stderr,"Code-as-descriptor rc=%d steps=%u r12=%X region=%u\n",
    rc,cpu[0],detail[3],detail[10]);return 2;
 }
 p32(d,0x198,0x604c0000u); /* ori r12,r2,0 */
 p32(d,0x250,0x1006cu);    /* two-word descriptor: entry */
 p32(d,0x254,0x20010u);    /* TOC */
 rc=ar_ppu_bootstrap_fortyeight_trace_m672(d,sizeof d,info,cpu,trace,detail);
 if(rc||cpu[0]!=48u||cpu[19]!=1u||
    detail[0]!=0x10098u||detail[3]!=0x20010u||
    detail[8]!=0x20010u||detail[9]!=0x1006cu||
    detail[10]!=3u||detail[11]!=6u||
    detail[12]!=0x20014u||detail[13]!=0x20010u||
    detail[14]!=3u||detail[15]!=6u){
   fprintf(stderr,"Valid-descriptor rc=%d steps=%u r12=%X region=%u\n",
    rc,cpu[0],detail[3],detail[10]);return 3;
 }
 puts("M6.7.2 r12 descriptor classification PASS");
 return 0;
}
