/* M7.57: synthetic guest registers; real owner PPC words, authenticated VM. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
extern int ar_m757_register_owner(const uint8_t*,size_t);
static const uint32_t original[16]={
 0x311f0004,0x7d083b96,0x7d0839d6,0x7f88f810,
 0x339c0004,0x2c1c0000,0x41820008,0x7f9c3810,
 0x7fbc2014,0x281c0020,0x57de113a,0x7bbd0020,
 0x41800048,0x7c9df010,0x28040010,0x418000b0
};
static uint32_t live[16]={
 0x311f0004,0x7d083b96,0x7d0839d6,0x7f88f810,
 0x339c0004,0x2c1c0000,0x41820008,0x7f9c3810,
 0x7fbc2014,0x281c0020,0x57de113a,0x7bbd0020,
 0x41800048,0x7c9df010,0x28040010,0x418000b0
};
static ar_ppu_fn first,second;
static unsigned idx(uint32_t pc){
 if(pc>=0x003c5050u&&pc<0x003c5084u)return (pc-0x003c5050u)/4u;
 if(pc>=0x003c50c8u&&pc<0x003c50d4u)return 13u+(pc-0x003c50c8u)/4u;
 return 99u;
}
int ar_m712_exec_window(const uint8_t*d,size_t len,uint32_t pc,uint32_t out[6]){
 if(!d||len<64||idx(pc)>=16)return AR_BAD_ARGS;
 memset(out,0,6*sizeof(*out));const unsigned start=idx(pc);
 const unsigned avail=start<13?13-start:16-start;
 for(unsigned i=0;i<avail&&i<4;i++)out[i]=original[start+i];
 out[4]=avail<4?avail:4;out[5]=5;return AR_OK;
}
uint32_t ar_read32(uint64_t pc){
 const unsigned k=idx((uint32_t)pc);return k<16?live[k]:0;
}
int ar_last_error(void){return AR_OK;}
int ar_register(uint32_t pc,ar_ppu_fn f){
 if(pc==0x003c5050u&&!first){first=f;return AR_OK;}
 if(pc==0x003c50c8u&&!second){second=f;return AR_OK;}
 return AR_DUPLICATE;
}
static int run(uint64_t r31,uint64_t r7,uint64_t r4,uint64_t r30,
               uint32_t expected28,uint32_t expected29,
               uint64_t target,uint32_t cr){
 ppu_context c={0};
 c.gpr[31]=r31;c.gpr[7]=r7;c.gpr[4]=r4;c.gpr[30]=r30;
 c.cr=0x01234567;c.xer=0x80000000;c.lr=0xbeef;c.ctr=50;
 if(first(&c)!=AR_TAIL||c.cia!=target||
    (uint32_t)c.gpr[28]!=expected28||
    (uint32_t)c.gpr[29]!=expected29||
    ((c.cr>>28)&15)!=cr||
    (c.cr&0xfffffff)!=0x01234567||
    !(c.xer&0x80000000)||c.lr!=0xbeef||c.ctr!=50)return 1;
 return 0;
}
int main(void){
 uint8_t fake[64]={0};
 live[13]^=1u;
 if(ar_m757_register_owner(fake,sizeof(fake))==AR_OK||first||second)
  return 1;
 live[13]^=1u;
 if(ar_m757_register_owner(fake,sizeof(fake))!=AR_OK||!first||!second)
  return 2;
 /* EQ case: skips subfc 506C, then LT at 5080. */
 if(run(4,4,0,0,0,0,0x003c50c8,9))return 3;
 /* NE case: subtract on 506C, still LT 5080. */
 if(run(5,4,0,0,3,3,0x003c50c8,9))return 4;
 /* NE case, r28 >= 32 (unsigned): alternate PC 5084. */
 if(run(1,64,0,0,59,59,0x003c5084,5))return 5;
 /* Rotated R30 low-word semantics and register alias. */
 ppu_context c={0};c.gpr[31]=4;c.gpr[7]=4;
 c.gpr[30]=0x80000001ULL;
 if(first(&c)!=AR_TAIL||c.gpr[30]!=4ULL||c.cia!=0x003c50c8)return 6;
 /* Native 50C8: (R30 - R29), compare unsigned word to 16. */
 ppu_context next={0};next.gpr[29]=0;next.gpr[30]=5;
 next.xer=0x80000000;next.lr=0xabc;next.cr=0x01234567;
 if(second(&next)!=AR_TAIL||next.cia!=0x003c5180||
    next.gpr[4]!=5||(next.cr>>28)!=9||
    next.lr!=0xabc||!(next.xer&0x20000000))return 7;
 next.gpr[29]=40;next.gpr[30]=0;
 if(second(&next)!=AR_TAIL||next.cia!=0x003c50d4||
    (uint32_t)next.gpr[4]!=UINT32_MAX-39u||
    (next.cr>>28)!=5||(next.xer&0x20000000))return 8;
 ppu_context bad={0};bad.gpr[7]=0;bad.gpr[31]=8;bad.cr=0x12345678;
 if(first(&bad)!=AR_PPC_UNSUPPORTED||bad.cia!=0x003c5054||
    bad.cr!=0x12345678)return 9;
 puts("M7.57: two original PPC native ARM64 spans (13+3), three real branch decisions, CR/XER and divide-zero fail-closed PASS");
 return 0;
}
