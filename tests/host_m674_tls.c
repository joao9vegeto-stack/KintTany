/* M6.7.4: synthetic main-thread sys_initialize_tls import, no game data. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
extern int ar_private_elf_inspect(const uint8_t*,size_t,uint32_t[5]);
extern int ar_ppu_bootstrap_fortyeight_trace_m674(const uint8_t*,size_t,
 const uint32_t[5],uint32_t[20],uint32_t[24],uint32_t[24],uint32_t[12]);
extern int ar_ppu_bootstrap_fortyeight_trace_m672(const uint8_t*,size_t,
 const uint32_t[5],uint32_t[20],uint32_t[24],uint32_t[24]);
static void p16(uint8_t*d,unsigned i,uint16_t x){d[i]=x>>8;d[i+1]=(uint8_t)x;}
static void p32(uint8_t*d,unsigned i,uint32_t x){
 d[i]=(uint8_t)(x>>24);d[i+1]=(uint8_t)(x>>16);
 d[i+2]=(uint8_t)(x>>8);d[i+3]=(uint8_t)x;
}
static void p64(uint8_t*d,unsigned i,uint64_t x){
 p32(d,i,(uint32_t)(x>>32));p32(d,i+4,(uint32_t)x);
}
int main(void){
 uint8_t d[0x600]={0};uint32_t info[5]={0},out[20]={0},trace[24]={0};
 uint32_t details[24]={0},tls[12]={0};
 memcpy(d,"\177ELF",4);d[4]=2;d[5]=2;d[6]=1;d[7]=0x66;
 p16(d,16,2);p16(d,18,21);p32(d,20,1);p64(d,24,0x20000);
 p64(d,32,64);p16(d,52,64);p16(d,54,56);p16(d,56,3);
 p32(d,64,1);p32(d,68,5);p64(d,72,0x100);p64(d,80,0x10000);
 p64(d,96,0xc0);p64(d,104,0xc0);
 p32(d,120,1);p32(d,124,6);p64(d,128,0x240);p64(d,136,0x20000);
 p64(d,152,0x240);p64(d,160,0x240);
 p32(d,176,0x60000002u);p32(d,180,4);p64(d,184,0x2c0);
 p64(d,192,0x20080);p64(d,208,32);p64(d,216,32);
 p32(d,0x240,0x10000);p32(d,0x244,0x20010);
 const uint32_t boot[13]={
  0x38600001u, /* li r3,1 (synthetic main thread ID) */
  0x3c800002u, /* lis r4,2 */
  0x60840050u, /* ori r4,r4,0x50 -> template 0x20050 */
  0x38a00004u, /* li r5,4 template bytes */
  0x38c00010u, /* li r6,16 TLS image bytes */
  0x3d800002u, /* lis r12,2 */
  0x618c0020u, /* ori r12,r12,0x20 -> pointer slot 0x20020 */
  0x818c0000u, /* lwz r12,0(r12) -> trampoline VA */
  0x800c0000u, /* lwz r0,0(r12) -> code word */
  0x804c0004u, /* lwz r2,4(r12) -> code word */
  0x7c0903a6u, /* mtctr r0 */
  0x4e800421u, /* bctrl */
  0xffffffffu  /* deliberate next opcode failure, proves return */
 };
 for(unsigned i=0;i<13;i++)p32(d,0x100u+i*4u,boot[i]);
 p32(d,0x160,0x39800000u);p32(d,0x164,0x658c0083u);
 p32(d,0x260,0x10060u);
 p32(d,0x290,0xdeadbeefu);
 p32(d,0x2c4,0x1b434cecu);
 p32(d,0x2d8,0x200a0);p32(d,0x2dc,0x200cc);
 d[0x2e0]=0x2c;p16(d,0x2e6,1);
 p32(d,0x2f0,0x200d0);p32(d,0x2f4,0x20100);p32(d,0x2f8,0x20120);
 memcpy(d+0x310,"sysPrxForUser",14);
 p32(d,0x340,0x744680a2u);p32(d,0x360,0x10060u);
 if(ar_private_elf_inspect(d,sizeof(d),info))return 1;
 int rc=ar_ppu_bootstrap_fortyeight_trace_m672(
         d,sizeof(d),info,out,trace,details);
 if(rc!=-1007||out[0]!=11u||out[19]!=0u)return 2;
 rc=ar_ppu_bootstrap_fortyeight_trace_m674(
         d,sizeof(d),info,out,trace,details,tls);
 if(rc!=-990||out[0]!=12u||out[8]!=0x10030u||
    out[19]!=1u||tls[0]!=1u||tls[1]!=1u||tls[2]!=1u||
    tls[3]!=0x20050u||tls[4]!=4u||tls[5]!=16u||
    tls[6]!=0x0e007000u||tls[7]!=4u||tls[10]!=0x10030u){
   fprintf(stderr,"TLS success rc=%d steps=%u pc=%08X indirect=%u initialized=%u reason=%u r13=%08X\n",
       rc,out[0],out[8],out[19],tls[0],tls[8],tls[6]);return 3;
 }
 /* An unknown NID must never trick the CPU into returning from a HLE. */
 p32(d,0x340,0x12345678u);
 rc=ar_ppu_bootstrap_fortyeight_trace_m674(
         d,sizeof(d),info,out,trace,details,tls);
 if(rc!=-1007||out[0]!=11u||out[19]!=0u||tls[0])return 4;
 p32(d,0x340,0x744680a2u);
 /* Valid import but invalid TLS size: reject without creating an image. */
 p32(d,0x110,0x38c00002u); /* r6=2 but r5=4 */
 rc=ar_ppu_bootstrap_fortyeight_trace_m674(
         d,sizeof(d),info,out,trace,details,tls);
 if(rc!=-1011||out[0]!=11u||tls[0]||tls[8]!=1011u||
    tls[4]!=4u||tls[5]!=2u)return 5;
 p32(d,0x110,0x38c00010u);
 /* Verified NID but guest image source unmapped -> no fake success. */
 p32(d,0x108,0x60840400u); /* r4=0x20400, outside data PT_LOAD */
 rc=ar_ppu_bootstrap_fortyeight_trace_m674(
         d,sizeof(d),info,out,trace,details,tls);
 if(rc!=-1013||tls[0]||tls[8]!=1013u)return 6;
 puts("M6.7.4 bounded sys_initialize_tls HLE and negative tests PASS");
 return 0;
}
