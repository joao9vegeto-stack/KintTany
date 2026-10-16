/* M7.1 signed native PowerPC continuous interpreter on private ELF. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
extern int ar_private_elf_inspect(const uint8_t*,size_t,uint32_t[5]);
extern int ar_m71_private_continuous_probe(const uint8_t*,size_t,uint32_t,uint32_t,uint32_t[16]);

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
 int rc=ar_m71_private_continuous_probe(d,sizeof(d),0x10060u,512u,out);
 if(rc!=0 || (int32_t)out[0]!=-1311 || out[1]!=12u ||
    out[2]!=0x10030u || out[3]!=0xffffffffu ||
    out[5]!=1u || out[6]!=0x28000u ||
    out[11]!=0u || out[12]!=0x744680a2u ||
    out[13]!=0x10060u || out[14]!=1u){
    fprintf(stderr,"M7.1 genuine import failed rc=%d state=%d steps=%u pc=%x word=%x HLE=%u r13=%x aot=%u nid=%x\n",
       rc,(int32_t)out[0],out[1],out[2],out[3],out[5],
       out[6],out[11],out[12]);return 2;
 }
 /* Wrong NID: no HLE bypass, no fake TLS, stop at real indirect branch. */
 p32(d,0x340,0x12345678u);
 rc=ar_m71_private_continuous_probe(d,sizeof(d),0x10060u,512u,out);
 if(rc || (int32_t)out[0]!=-1314 || out[1]!=11u ||
    out[5]!=0u||out[6]!=0u||out[12]!=0u)return 3;
 p32(d,0x340,0x744680a2u);
 /* Truly continuous guest decoding, not an increasing 48-step window.
  * Place a 76-opcode sequence in mapped executable ELF file data. */
 uint8_t dlong[0x1200]={0};
 memcpy(dlong,d,sizeof(d));
 const unsigned ep=0x500u;
 p64(dlong,ep+8u,0x900u);p64(dlong,ep+32u,0x180u);
 p64(dlong,ep+40u,0x180u);
 for(unsigned k=0;k<76u;k++)p32(dlong,0x900u+4u*k,0x60000000u);
 p32(dlong,0x900u+4u*76u,0xffffffffu);
 rc=ar_m71_private_continuous_probe(dlong,sizeof(dlong),0x10060u,512u,out);
 if(rc || (int32_t)out[0]!=-1311 || out[1]!=76u ||
    out[2]!=0x10130u || out[3]!=0xffffffffu ||
    out[5]!=0u || out[11]!=0u){
    fprintf(stderr,"M7.1 continuous 76 step failed rc=%d reason=%d steps=%u pc=%x word=%x\n",
       rc,(int32_t)out[0],out[1],out[2],out[3]);return 4;
 }
 /* Budget is enforced independently of instruction support. */
 rc=ar_m71_private_continuous_probe(dlong,sizeof(dlong),0u,64u,out);
 if(rc || (int32_t)out[0]!=-1310 || out[1]!=64u ||
    out[2]!=0x10100u)return 5;
 /* Invalid game entry opcode stops immediately and reports guest PC. */
 p32(d,0x100u,0xffffffffu);
 rc=ar_m71_private_continuous_probe(d,sizeof(d),0x10060u,512u,out);
 if(rc || (int32_t)out[0]!=-1311 || out[1]!=0u ||
    out[2]!=0x10000u || out[3]!=0xffffffffu)return 6;
 /* Corrupt ELF header rejected before mapping guest memory. */
 d[0]='x';
 if(ar_m71_private_continuous_probe(d,sizeof(d),0x10060u,512u,out)!=-1320)
    return 7;
 puts("M7.1 signed native PowerPC continuous 76-step, import TLS and fail-closed ISA PASS");
 return 0;
}
