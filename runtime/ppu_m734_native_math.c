/* M7.34: 29 PPC64 instructions from the real private Ascension PPU
 * executable translated into signed native ARM64, at guest 0x0052AA1C.
 *
 * The ELF itself and all 29 original instruction words are PRIVATE.
 * Registration is behind the EXISTING full-ELF private SHA-256 gate.
 * A checksum of the 116-byte executable window, paired with a byte-for-
 * byte comparison to loaded executable guest memory, refuses mismatches.
 * No owner ELF bytes or commercial asset payload are shipped as source.
 *
 * SRADI/SRAWI update XER.CA; signed high multiplications use 128-bit and
 * 64-bit intermediate arithmetic without undefined signed overflow.
 */
#include <stdint.h>
#include <stddef.h>
#include "ppu_bridge.h"
extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);
#define FIRST UINT32_C(0x0052aa1c)
#define NEXT  UINT32_C(0x0052aa94)
#define XER_CA UINT32_C(0x20000000)
static uint64_t ar_m734_srad(uint64_t value,unsigned sh,uint32_t *xer){
 const uint64_t sign=value>>63;
 const uint64_t lowmask=sh?(UINT64_MAX>>(64u-sh)):UINT64_C(0);
 const uint64_t shifted=sh?(value>>sh):value;
 const uint64_t v=shifted|((sign&&sh)?(UINT64_MAX<<(64u-sh)):UINT64_C(0));
 const int carry=sign && ((value&lowmask)!=0);
 *xer=(*xer&~XER_CA)|(carry?XER_CA:0u);
 return v;
}
static uint64_t ar_m734_sraw(uint64_t value,unsigned sh,uint32_t *xer){
 const uint32_t bits=(uint32_t)value;
 const unsigned sign=bits>>31;
 uint32_t out=sh?bits>>sh:bits;
 if(sh&&sign)out|=UINT32_MAX<<(32u-sh);
 const uint32_t dropped=sh?(bits&((UINT32_C(1)<<sh)-1u)):0u;
 *xer=(*xer&~XER_CA)|((sign&&dropped)?XER_CA:0u);
 return (uint64_t)(int64_t)(int32_t)out;
}
static uint64_t ar_m734_mulhd(uint64_t a,uint64_t b){
 const __int128 product=(__int128)(int64_t)a*(__int128)(int64_t)b;
 const unsigned __int128 raw=(unsigned __int128)product;
 return (uint64_t)(raw>>64u);
}
static uint64_t ar_m734_mulhw(uint64_t a,uint64_t b){
 const int64_t product=(int64_t)(int32_t)(uint32_t)a*
                       (int64_t)(int32_t)(uint32_t)b;
 const uint64_t raw=(uint64_t)product;
 return (uint64_t)(int64_t)(int32_t)(uint32_t)(raw>>32u);
}
int ar_m734_native_0052aa1c(ppu_context *cpu){
 if(!cpu)return AR_BAD_ARGS;
 uint64_t *r=cpu->gpr;
 /* 0x0052AA1C: sradi r26,r27,63 */
 r[26]=ar_m734_srad(r[27],63u,&cpu->xer);
 /* real constant-building PPC immediates, no texture or game data */
 r[0]|=UINT64_C(0xc8a0);                                    /* ori */
 r[11]=(uint64_t)(int64_t)(int32_t)UINT32_C(0xb38c0000);    /* lis */
 r[0]<<=32u;                                                /* sldi */
 r[11]|=UINT64_C(0xf9b1);                                   /* ori */
 r[0]|=UINT64_C(0xce510000);                                /* oris */
 r[9]=(uint64_t)(int64_t)(int32_t)UINT32_C(0x92490000);     /* lis */
 r[0]|=UINT64_C(0x2957);                                    /* ori */
 r[9]|=UINT64_C(0x2493);                                    /* ori */
 r[0]=ar_m734_mulhd(r[27],r[0]);                            /* mulhd */
 r[0]=ar_m734_srad(r[0],13u,&cpu->xer);                     /* sradi */
 r[30]=r[0]-r[26];                                          /* sub */
 r[10]=r[30]+UINT64_C(1);                                   /* addi */
 r[8]=ar_m734_sraw(r[30],31u,&cpu->xer);                    /* srawi */
 r[9]=ar_m734_mulhw(r[10],r[9]);                            /* mulhw */
 r[9]+=r[10];                                               /* add */
 r[0]=ar_m734_sraw(r[10],31u,&cpu->xer);                    /* srawi */
 r[9]=ar_m734_sraw(r[9],2u,&cpu->xer);                      /* srawi */
 r[11]=ar_m734_mulhw(r[30],r[11]);                          /* mulhw */
 r[11]+=r[30];                                              /* add */
 r[9]-=r[0];                                                /* sub */
 r[11]=ar_m734_sraw(r[11],8u,&cpu->xer);                    /* srawi */
 r[0]=(uint64_t)((uint32_t)r[9]<<3u);                       /* slwi */
 r[31]=r[11]-r[8];                                          /* sub */
 r[0]-=r[9];                                                /* sub */
 r[29]=(uint64_t)((uint64_t)r[31]*UINT64_C(365));           /* mulli */
 r[10]-=r[0];                                               /* sub */
 ar_write32(r[28]+UINT64_C(24),(uint32_t)r[10]);             /* stw */
 if(ar_last_error()!=AR_OK)return AR_MEM_FAULT;
 cpu->cia=NEXT;                                             /* b */
 return AR_TAIL;
}
int ar_m734_register_block(const uint8_t*elf,size_t size){
 if(!elf || size<64u)return AR_BAD_ARGS;
 /* Reference hash: 29 owner words x 4 bytes, computed only locally.
  * Entire original private ELF SHA-256 must already be authenticated. */
 uint64_t fingerprint=UINT64_C(14695981039346656037);
 for(unsigned j=0;j<29u;j+=4u){
   uint32_t words[6]={0};
   const unsigned n=(29u-j<4u)?29u-j:4u;
   if(ar_m712_exec_window(elf,size,FIRST+4u*j,words)!=AR_OK ||
      words[4]<n || !(words[5]&1u))return AR_BAD_ARGS;
   for(unsigned k=0;k<n;k++){
      const uint32_t w=words[k];
      if(ar_read32(FIRST+4u*(j+k))!=w || ar_last_error()!=AR_OK)
         return AR_BAD_ARGS;
      for(unsigned byte=0;byte<4u;byte++){
         fingerprint ^= (uint8_t)(w>>(24u-8u*byte));
         fingerprint *= UINT64_C(1099511628211);
      }
   }
 }
 if(fingerprint!=UINT64_C(0x01e13a933aae13b9))return AR_BAD_ARGS;
 return ar_register(FIRST,ar_m734_native_0052aa1c);
}
