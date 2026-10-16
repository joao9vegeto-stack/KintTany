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
 uint8_t d[0x900]={0};uint32_t info[5]={0},out[20]={0},trace[24]={0};
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
  0x60e30000u, /* ori r3,r7,0 : process entry main thread ID */
  0x61040000u, /* ori r4,r8,0 : PT_TLS vaddr */
  0x61250000u, /* ori r5,r9,0 : PT_TLS file size */
  0x61460000u, /* ori r6,r10,0 : PT_TLS memory size */
  0x60000000u, /* nop; no hardcoded args */
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
 /* Fourth PHDR would overlap instruction bytes at 0x100. Move the
  * synthetic PHDR table into an unmapped, file-backed area. */
 memcpy(d+0x500,d+64,3u*56u);
 p64(d,32,0x500);p16(d,56,4);
 const unsigned tlsph=0x500u+3u*56u;
 p32(d,tlsph,7u);p32(d,tlsph+4u,4u);
 p64(d,tlsph+8u,0x290u);p64(d,tlsph+16u,0x20050u);
 p64(d,tlsph+32u,4u);p64(d,tlsph+40u,16u);
 if(ar_private_elf_inspect(d,sizeof(d),info))return 1;
 int rc=ar_ppu_bootstrap_fortyeight_trace_m672(
         d,sizeof(d),info,out,trace,details);
 if(rc!=-1007||out[0]!=11u||out[19]!=0u)return 2;
 rc=ar_ppu_bootstrap_fortyeight_trace_m674(
         d,sizeof(d),info,out,trace,details,tls);
 if(rc!=-990||out[0]!=12u||out[8]!=0x10030u||
    out[19]!=1u||tls[0]!=1u||tls[1]!=1u||tls[2]!=1u||
    tls[3]!=0x20050u||tls[4]!=4u||tls[5]!=16u||
    tls[6]!=0x0e007000u||tls[7]!=4u||tls[10]!=0x10030u||
    tls[9]!=1u||tls[11]!=0x100000u){
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
 p64(d,tlsph+40u,2u); /* PT_TLS memsz < filesz */
 rc=ar_ppu_bootstrap_fortyeight_trace_m674(
         d,sizeof(d),info,out,trace,details,tls);
 if(rc!=-1021||out[0]!=0u||tls[0]||tls[8]!=1021u)return 5;
 p64(d,tlsph+40u,16u);
 /* Verified NID but guest image source unmapped -> no fake success. */
 p64(d,tlsph+16u,0x20400u); /* PT_TLS source outside data PT_LOAD */
 rc=ar_ppu_bootstrap_fortyeight_trace_m674(
         d,sizeof(d),info,out,trace,details,tls);
 if(rc!=-1021||tls[0]||tls[8]!=1021u)return 6;
 p64(d,tlsph+16u,0x20050u);
 /* PT_TLS absent is allowed: valid main thread, zero image size. */
 p32(d,tlsph,0u);
 rc=ar_ppu_bootstrap_fortyeight_trace_m674(
         d,sizeof(d),info,out,trace,details,tls);
 if(rc!=-990||tls[0]!=1u||tls[2]!=1u||
    tls[4]!=0u||tls[5]!=0u||tls[9]!=0u)return 7;
 puts("M6.7.5 ELF PT_TLS process-entry ABI and negative tests PASS");
 /* M6.7.6: synthetic caller restores LR via an actual guest data pointer
  * after a real matched TLS HLE. It then executes blr to guest code.
  * This exercises mtctr/mtlr as DISTINCT special registers. */
 p32(d,tlsph,7u); /* restore real PT_TLS */
 p32(d,0x130,0x3d600002u); /* lis r11,2 */
 p32(d,0x134,0x800b0064u); /* lwz r0,0x64(r11): saved LR 0x10070 */
 p32(d,0x138,0x7c0803a6u); /* mtlr r0: restore guest PPC64 LR */
 p32(d,0x13c,0x4e800020u); /* blr to verified executable address */
 p32(d,0x2a4,0x10070u); /* guest data-backed return target */
 p32(d,0x170,0xffffffffu); /* sentinel only after successful blr */
 rc=ar_ppu_bootstrap_fortyeight_trace_m674(
         d,sizeof(d),info,out,trace,details,tls);
 if(rc!=-990 || out[0]!=16u || out[8]!=0x10070u ||
    out[19]!=2u || !tls[0] || details[22]!=0x10038u ||
    details[23]!=0x10070u){
   fprintf(stderr,"M6.7.6 return failed rc=%d steps=%u pc=%x branches=%u mtlr=%x LR=%x TLS=%u\\n",
           rc,out[0],out[8],out[19],details[22],details[23],tls[0]);
   return 8;
 }
 /* Invalid return addresses must NOT result in arbitrary guest execution. */
 p32(d,0x2a4,0x100e4u);
 rc=ar_ppu_bootstrap_fortyeight_trace_m674(
         d,sizeof(d),info,out,trace,details,tls);
 if(rc!=-1022 || out[0]!=15u || out[8]!=0x1003cu ||
    details[22]!=0x10038u || tls[0]!=1u)return 9;
 p32(d,0x2a4,0x10070u);
 /* Unsupported conditional bclr requires CR modeling: never guess. */
 p32(d,0x13c,0x4e000020u);
 rc=ar_ppu_bootstrap_fortyeight_trace_m674(
         d,sizeof(d),info,out,trace,details,tls);
 if(rc!=-1024 || out[0]!=15u)return 10;
 p32(d,0x13c,0x4e800020u);
 /* Illegal Rc variant of mtlr cannot mutate LR. */
 p32(d,0x138,0x7c0803a7u);
 rc=ar_ppu_bootstrap_fortyeight_trace_m674(
         d,sizeof(d),info,out,trace,details,tls);
 if(rc!=-1006 || out[0]!=14u || details[22]!=0u)return 11;
 puts("M6.7.6 mtlr LR restore and guarded blr return PASS");
 return 0;
}
