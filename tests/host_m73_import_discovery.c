/* M7.1 signed native PowerPC continuous interpreter on private ELF. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
extern int ar_private_elf_inspect(const uint8_t*,size_t,uint32_t[5]);
extern int ar_m71_private_continuous_probe(const uint8_t*,size_t,uint32_t,uint32_t,uint32_t[16]);
extern int ar_m73_private_import_probe(const uint8_t*,size_t,uint32_t,uint32_t,
                                        uint32_t[16],uint32_t[16],char[48]);

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
 /* A second REAL PRX import follows the already valid TLS startup:
  * same bctrl instruction words, a different code stub and different NID.
  * The old implementation reports -1314 without identifying it. */
 p16(d,0x2e6,2u);
 p32(d,0x344,0xABCDEF01u);
 p32(d,0x364,0x10080u);
 p32(d,0x180,0x39800000u);
 p32(d,0x184,0x658c0083u);
 p32(d,0x264,0x10080u);
 p32(d,0x130,0x3d800002u); /* lis r12,2 */
 p32(d,0x134,0x618c0024u); /* ori r12,r12,0x24 -> 0x20024 */
 p32(d,0x138,0x818c0000u); /* lwz r12,0(r12) -> 0x10080 */
 p32(d,0x13c,0x800c0000u); /* lwz r0,0(r12) -> invalid CTR opcode */
 p32(d,0x140,0x804c0004u); /* lwz r2,4(r12) */
 p32(d,0x144,0x7c0903a6u); /* mtctr r0 */
 p32(d,0x148,0x4e800421u); /* real second PRX bctrl */
 uint32_t evidence[16]={0};char library[48]={0};
 int rc=ar_m73_private_import_probe(d,sizeof(d),0x10060u,512u,out,evidence,library);
 if(rc || (int32_t)out[0]!=-1314 || out[1]!=18u ||
    out[2]!=0x10048u || out[3]!=0x4e800421u ||
    out[5]!=1u || out[6]!=0x28000u || out[11]!=0u ||
    evidence[0]!=0x10048u || evidence[1]!=0x10080u ||
    evidence[2]!=0x39800000u || evidence[3]!=0x658c0083u ||
    evidence[4]!=0x39800000u || evidence[5]!=0x658c0083u ||
    evidence[6]!=0xABCDEF01u || (int32_t)evidence[7]!=0 ||
    evidence[8]!=31u || evidence[9]!=2u || evidence[10]!=1u ||
    evidence[15]!=0x39800000u || strcmp(library,"sysPrxForUser")!=0){
   fprintf(stderr,"M7.3 import evidence failed rc=%d guest=%d steps=%u pc=%x nid=%x status=%d code=%x flags=%x lib=%s\\n",
        rc,(int32_t)out[0],out[1],out[2],evidence[6],(int32_t)evidence[7],
        evidence[1],evidence[8],library);return 2;
 }
 /* The old signed interpreter ABI must remain intact with the same stop. */
 rc=ar_m71_private_continuous_probe(d,sizeof(d),0x10060u,512u,out);
 if(rc||(int32_t)out[0]!=-1314||out[1]!=18u)return 3;
 /* A pointer missing from PRX metadata stays unrecognized. */
 p32(d,0x364,0x10090u);
 rc=ar_m73_private_import_probe(d,sizeof(d),0x10060u,512u,out,evidence,library);
 if(rc||(int32_t)out[0]!=-1314||(int32_t)evidence[7]!=-1||
    evidence[6]!=0u||library[0]!=0||
    (evidence[8]&8u)!=0u)return 4;
 p32(d,0x364,0x10080u);
 /* A pointer into writable data cannot be interpreted as executable
  * function descriptor or be approved for HLE dispatch. */
 p32(d,0x264,0x20040u);
 rc=ar_m73_private_import_probe(d,sizeof(d),0x10060u,512u,out,evidence,library);
 if(rc||(int32_t)out[0]!=-1314||evidence[1]!=0x20040u||
    (evidence[8]&1u)!=0u||evidence[6]!=0u)return 5;
 /* Invalid argument pointers are fail-closed without reading host data. */
 rc=ar_m73_private_import_probe(d,sizeof(d),0x10060u,512u,out,NULL,library);
 if(rc!=-1320)return 6;
 puts("M7.3 real second PRX stub library NID identified, unknown HLE blocked PASS");
 return 0;
}
