/* M7.0 native AOT dispatcher ELF+HLE integration synthetic test. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
extern int ar_private_elf_inspect(const uint8_t*,size_t,uint32_t[5]);
extern int ar_m70_native_runtime_probe(const uint8_t*,size_t,uint32_t,uint32_t[16]);

static void p16(uint8_t*d,unsigned i,uint16_t x){d[i]=x>>8;d[i+1]=(uint8_t)x;}
static void p32(uint8_t*d,unsigned i,uint32_t x){
 d[i]=(uint8_t)(x>>24);d[i+1]=(uint8_t)(x>>16);
 d[i+2]=(uint8_t)(x>>8);d[i+3]=(uint8_t)x;
}
static void p64(uint8_t*d,unsigned i,uint64_t x){
 p32(d,i,(uint32_t)(x>>32));p32(d,i+4,(uint32_t)x);
}
int main(void){
 uint8_t d[0x900]={0};uint32_t out[16]={0};
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
 int rc=ar_m70_native_runtime_probe(d,sizeof(d),0x10060u,out);
 if(rc!=0 || out[0]!=0u || out[1]!=0x10000u ||
    out[2]!=0x20010u || out[3]!=2u ||
    out[4]!=256u*1024u*1024u || out[5]!=0u ||
    (int32_t)out[6]!=-3 || out[7]!=0x10000u ||
    (int32_t)out[8]!=0 || (int32_t)out[9]!=0 ||
    (int32_t)out[10]!=0 || (int32_t)out[11]!=0 ||
    out[12]!=0x28000u || out[14]!=0x60e30000u ||
    out[15]!=15u){
  fprintf(stderr,"m70 unexpected: rc=%d loader=%d entry=%x TOC=%x segments=%u cap=%x AOT=%d missing=%x HLE=%d TLSr13=%x opcode=%x flags=%x\n",
      rc,(int32_t)out[0],out[1],out[2],out[3],out[4],
      (int32_t)out[6],out[7],(int32_t)out[11],out[12],out[14],out[15]);
  return 2;
 }
 /* Reimporting same guest after shutdown must reset registered functions,
  * memory and imports, not preserve a fabricated success from a prior run. */
 if(ar_m70_native_runtime_probe(d,sizeof(d),0u,out) ||
    out[5]!=0u || out[7]!=0x10000u || out[8]!=UINT32_MAX ||
    out[11]!=0u || out[15]!=9u)return 3;
 /* Authenticated NID checks must not treat unrelated imports as TLS. */
 p32(d,0x340,0x12345678u);
 if(ar_m70_native_runtime_probe(d,sizeof(d),0x10060u,out) ||
    out[5]!=0u || out[7]!=0x10000u ||
    out[12]!=0u || (out[15]&6u))return 4;
 p32(d,0x340,0x744680a2u);
 d[0]='x';
 if(ar_m70_native_runtime_probe(d,sizeof(d),0x10060u,out)!=-21)return 5;
 d[0]=0x7f;
 /* Bounded guest staging rejects PT_LOAD data beyond the 256 MiB RAM window. */
 p64(d,0x500u+56u+40u,0x10000000u);
 if(ar_m70_native_runtime_probe(d,sizeof(d),0x10060u,out)!=-23)return 6;
 puts("M7.0 signed native PPU staging, real NID/HLE, and honest AOT unresolved PASS");
 return 0;
}
