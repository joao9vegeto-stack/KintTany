/* Execute the actual emitted M7.63 AOT function at the first physical stop
   without a PPC interpreter. The 14 guest words are authenticated separately. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
extern int ar_m763_native_002c53bc(ppu_context*);
static uint8_t storage[64];
static int error, writes, fail_second;
int ar_last_error(void){return error;}
void ar_write32(uint64_t ea,uint32_t v){
 if(ea<UINT64_C(0x8ec9c0) || ea+4u>UINT64_C(0x8ec9c0)+sizeof(storage) || (ea&3)) {error=AR_MEM_FAULT;return;}
 if(fail_second && writes==1) {error=AR_MEM_FAULT;return;}
 const unsigned at=(unsigned)(ea-UINT64_C(0x8ec9c0));
 storage[at]=(uint8_t)(v>>24);storage[at+1]=(uint8_t)(v>>16);storage[at+2]=(uint8_t)(v>>8);storage[at+3]=(uint8_t)v;
 writes++;
}
static uint32_t be32(unsigned p){return (uint32_t)storage[p]<<24 | (uint32_t)storage[p+1]<<16 | (uint32_t)storage[p+2]<<8 | storage[p+3];}
static void require(int ok,const char*why){if(!ok){fprintf(stderr,"M7.63 semantic failure: %s\n",why);__builtin_trap();}}
static void run(uint64_t guest_r3,int expect_ca){
 ppu_context c;memset(&c,0,sizeof(c));memset(storage,0,sizeof(storage));error=writes=fail_second=0;
 c.gpr[3]=guest_r3;c.lr=UINT64_C(0x002c1734);c.gpr[1]=UINT64_C(0xA87C50);
 int rc=ar_m763_native_002c53bc(&c);
 require(rc==AR_OK && c.cia==c.lr,"guest return LR");
 require(c.gpr[1]==UINT64_C(0xA87C50),"stack preserved");
 require(c.gpr[6]==UINT64_C(0x8ec9c0),"addic r6 indexed EA");
 require(c.gpr[5]==UINT64_C(0xc018),"ORI replacement of r5");
 require(c.gpr[8]==UINT64_C(0),"r8 preserved while ORI writes r5");
 require(c.gpr[3]==guest_r3+UINT64_C(0xc018),"ADDC register destination");
 require(c.gpr[4]==guest_r3+UINT64_C(0x8010),"ADDC r4");
 require(c.gpr[7]==guest_r3+UINT64_C(0x4008),"ADDIC r7");
 require(!!(c.xer&UINT32_C(0x20000000))==!!expect_ca,"XER.CA after final ADDC");
 require(writes==4,"exactly four guest big-endian stores");
 require(be32(0)==(uint32_t)guest_r3,"guest EA first value");
 require(be32(4)==(uint32_t)(guest_r3+UINT64_C(0x4008)),"guest store r7");
 require(be32(8)==(uint32_t)(guest_r3+UINT64_C(0x8010)),"guest store r4");
 require(be32(12)==(uint32_t)(guest_r3+UINT64_C(0xc018)),"guest store r3");
}
int main(void){
 run(UINT64_C(0x2001EE30),0);
 run(UINT64_MAX,1);
 ppu_context c;memset(&c,0,sizeof(c));memset(storage,0,sizeof(storage));
 error=writes=0;fail_second=1;c.gpr[3]=UINT64_C(0x2001EE30);c.lr=UINT64_C(0x2c1734);
 require(ar_m763_native_002c53bc(&c)==AR_MEM_FAULT,"guest memory fault propagated");
 require(writes==1 && be32(8)==0,"no stores after memory error");
 puts("M7.63 real 0x002C53BC AOT: memory, LR, ADDIC/ADDC XER.CA, big-endian stores, fail-closed PASS");return 0;
}