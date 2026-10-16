/* Synthetic PPU fixture: NO Ascension bytes or license. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
extern int ar_private_elf_inspect(const uint8_t*,size_t,uint32_t[5]);
extern int ar_ppu_bootstrap_fortyeight(const uint8_t*,size_t,
                                   const uint32_t[5],uint32_t[20]);
extern int ar_ppu_bootstrap_fortyeight_trace(const uint8_t*,size_t,
                  const uint32_t[5],uint32_t[20],uint32_t[24]);
extern int ar_ppu_bootstrap_thirtytwo(const uint8_t*,size_t,
                                   const uint32_t[5],uint32_t[10]);
static void p16(uint8_t*d,int i,uint16_t x){d[i]=x>>8;d[i+1]=x;}
static void p32(uint8_t*d,int i,uint32_t x){
 d[i]=x>>24;d[i+1]=x>>16;d[i+2]=x>>8;d[i+3]=x;
}
static void p64(uint8_t*d,int i,uint64_t x){p32(d,i,x>>32);p32(d,i+4,x);}
int main(void){
 uint8_t d[0x400]={0};uint32_t info[5]={0},cpu[20]={0},trace[24]={0};
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
 /* synthetic: mflr r0 sets 0x10020, ori r0,r0,0x6c makes 0x1006c.
  * ctr <- gpr0 at step 38; bctr step 39 jumps to prior executable
  * instruction 0x1004c, then 8 more bounded guest steps. */
 p32(d,0x180,0x6000006cu);
 p32(d,0x1a4,0x7c0903a6u); /* mtctr r0, exact iPhone opcode */
 p32(d,0x1a8,0x4e800420u); /* bctr, unconditional */
 int rc=ar_ppu_bootstrap_fortyeight_trace(d,sizeof d,info,cpu,trace);
 if(rc || cpu[0]!=48u||cpu[2]!=0x1008cu||cpu[3]!=0x10020u||
    cpu[5]!=17u||cpu[9]!=0xffffffffu||cpu[15]!=2u||
    cpu[16]!=0u||cpu[17]!=0x1006cu||cpu[18]!=0u||
    cpu[19]!=1u||
    trace[0]!=0x10080u||trace[1]!=0x6000006cu||
    trace[3]!=0x1006cu||trace[7]<2u||
    trace[10]!=0x100a4u||trace[11]!=0u||
    trace[12]!=0x1006cu||trace[14]!=0x100a8u||
    trace[15]!=48u){
   fprintf(stderr,"m66 first rc=%d steps=%u pc=%X lr=%X stores=%u ctr=%X indirect=%u\n",
      rc,cpu[0],cpu[2],cpu[3],cpu[5],cpu[17],cpu[19]);
   return 2;
 }
 /* bctrl must set LR to the next sequential instruction and branch. */
 p32(d,0x1a8,0x4e800421u);
 if(ar_ppu_bootstrap_fortyeight(d,sizeof d,info,cpu)||
    cpu[0]!=48u||cpu[3]!=0x100acu||cpu[19]!=1u)return 3;
 p32(d,0x1a8,0x4e800420u);
 /* Invalid CTR PC outside executable segment must fail closed. */
 p32(d,0x180,0x600000e4u); /* CTR=0x100e4, unmapped */
 if(ar_ppu_bootstrap_fortyeight_trace(d,sizeof d,info,cpu,trace)!=-1007||
    cpu[0]!=39u||cpu[8]!=0x100a8u||cpu[17]!=0x100e4u||
    trace[0]!=0x10080u||trace[1]!=0x600000e4u||
    trace[3]!=0x100e4u||trace[14]!=0x100a8u||
    trace[5]!=0x100e4u||trace[15]!=40u)return 4;
 p32(d,0x180,0x6000006cu);
 /* Unsupported conditional bcctr: CR is intentionally not modeled. */
 p32(d,0x1a8,0x4e000420u);
 if(ar_ppu_bootstrap_fortyeight(d,sizeof d,info,cpu)!=-1008||
    cpu[0]!=39u)return 5;
 p32(d,0x1a8,0x4e800420u);
 /* Reject incorrect special register and Rc bit: no fake mtctr. */
 p32(d,0x1a4,0x7c0803a6u); /* mtlr r0 */
 if(ar_ppu_bootstrap_fortyeight(d,sizeof d,info,cpu)!=-1006||
    cpu[0]!=38u)return 6;
 p32(d,0x1a4,0x7c0903a7u); /* Rc variant forbidden */
 if(ar_ppu_bootstrap_fortyeight(d,sizeof d,info,cpu)!=-1006)return 7;
 p32(d,0x1a4,0x7c0903a6u);
 /* Non-memory failure must not display stale EA from previous stw. */
 p32(d,0x1a4,0xffffffffu);
 if(ar_ppu_bootstrap_fortyeight(d,sizeof d,info,cpu)!=-990||
    cpu[0]!=38u||cpu[16]!=0u||
    cpu[10]!=0u||cpu[11]!=0u||cpu[12]!=0u)return 8;
 puts("M6.7 bounded r0 provenance CTR trace PASS");
 return 0;
}
