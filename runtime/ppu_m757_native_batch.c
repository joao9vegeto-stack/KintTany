/* M7.57: two authenticated PPC64 owner spans compiled natively for iPhone ARM64.
 * 0x003C5050..0x003C5080: 13 instructions, inner BEQ and terminal BLT.
 * 0x003C50C8..0x003C50D0: 3 instructions, terminal BLT.
 * No PPC interpreter, no JIT, no synthetic guest branch, no fake filesystem I/O.
 */
#include <stdint.h>
#include <stddef.h>
#include "ppu_bridge.h"
extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);
#define AR_CA UINT32_C(0x20000000)
#define AR_SO UINT32_C(0x80000000)
#define AR_CR_LT UINT32_C(0x80000000)
#define AR_CR_EQ UINT32_C(0x20000000)
static void ar_m757_setca(ppu_context*c,uint64_t lhs,uint64_t rhs,uint64_t result){
  c->xer=(c->xer&~AR_CA)|((result<lhs)?AR_CA:0u);
  (void)rhs;
}
static void ar_m757_compare(ppu_context*c,int less,int greater){
  const uint32_t nibble=(less?8u:greater?4u:2u) |
                        ((c->xer&AR_SO)?1u:0u);
  c->cr=(c->cr&UINT32_C(0x0fffffff))|(nibble<<28u);
}
static int ar_m757_suffix_5070(ppu_context*c){
  uint64_t*r=c->gpr;
  /* 003C5070 addc r29,r28,r4 -- unsigned carry; all XER other bits kept. */
  const uint64_t lhs=r[28],rhs=r[4];
  const uint64_t sum=lhs+rhs;
  r[29]=sum;
  ar_m757_setca(c,lhs,rhs,sum);
  /* 003C5074 cmplwi cr0,r28,0x20: compare unsigned low word. */
  const uint32_t w=(uint32_t)r[28];
  ar_m757_compare(c,w<32u,w>32u);
  /* 003C5078 rlwinm r30,r30,2,4,29; PPC64 high half clear. */
  const uint32_t original=(uint32_t)r[30];
  const uint32_t rotated=(uint32_t)((original<<2u)|(original>>30u));
  r[30]=(uint64_t)(rotated & UINT32_C(0x0ffffffc));
  /* 003C507C rldicl r29,r29,0,32, exact PPC64 zero-extension. */
  r[29]=(uint64_t)(uint32_t)r[29];
  /* 003C5080 blt cr0,+0x48 -> 003C50C8, else 003C5084. */
  c->cia=(c->cr&AR_CR_LT)?UINT32_C(0x003c50c8):
                          UINT32_C(0x003c5084);
  return AR_TAIL;
}
int ar_m757_native_003c5050(ppu_context*c){
  if(!c)return AR_BAD_ARGS;
  uint64_t*r=c->gpr;
  const uint64_t src=r[31];
  /* 003C5050 addic r8,r31,4 updates XER.CA. */
  r[8]=src+UINT64_C(4);
  ar_m757_setca(c,src,UINT64_C(4),r[8]);
  /* 003C5054 divwu r8,r8,r7. No division when low word divisor 0. */
  const uint32_t divisor=(uint32_t)r[7];
  if(!divisor){c->cia=UINT32_C(0x003c5054);return AR_PPC_UNSUPPORTED;}
  r[8]=(uint64_t)((uint32_t)r[8]/divisor);
  /* 003C5058 mullw r8,r8,r7: low signed result sign-extended. */
  const uint32_t product=(uint32_t)((uint64_t)(uint32_t)r[8]*divisor);
  r[8]=(uint64_t)(int64_t)(int32_t)product;
  /* 003C505C subfc r28,r8,r31 = r31-r8, no-borrow CA. */
  const uint64_t old=r[8],diff=r[31]-old;
  r[28]=diff;
  c->xer=(c->xer&~AR_CA)|((r[31]>=old)?AR_CA:0u);
  /* 003C5060 addic r28,r28,4. */
  r[28]=diff+UINT64_C(4);
  ar_m757_setca(c,diff,UINT64_C(4),r[28]);
  /* 003C5064 cmpwi cr0,r28,0 with sticky XER.SO. */
  const int32_t cmp=(int32_t)(uint32_t)r[28];
  ar_m757_compare(c,cmp<0,cmp>0);
  /* 003C5068 beq 003C5070; otherwise 003C506C subfc r28,r28,r7. */
  if(!(c->cr&AR_CR_EQ)){
    const uint64_t ra=r[28],rb=r[7];
    r[28]=rb-ra;
    c->xer=(c->xer&~AR_CA)|((rb>=ra)?AR_CA:0u);
  }
  return ar_m757_suffix_5070(c);
}
int ar_m757_native_003c50c8(ppu_context*c){
  if(!c)return AR_BAD_ARGS;
  uint64_t*r=c->gpr;
  /* 003C50C8 subfc r4,r29,r30 = r30-r29. */
  const uint64_t ra=r[29],rb=r[30];
  r[4]=rb-ra;
  c->xer=(c->xer&~AR_CA)|((rb>=ra)?AR_CA:0u);
  /* 003C50CC cmplwi cr0,r4,16. */
  const uint32_t v=(uint32_t)r[4];
  ar_m757_compare(c,v<16u,v>16u);
  /* 003C50D0 blt cr0,+0xB0 -> 003C5180, else 003C50D4. */
  c->cia=(c->cr&AR_CR_LT)?UINT32_C(0x003c5180):
                          UINT32_C(0x003c50d4);
  return AR_TAIL;
}
struct ar_m757_span{uint32_t pc;uint32_t count;const uint32_t*words;ar_ppu_fn fn;};
static const uint32_t ar_m757_owner_5050[13]={
 UINT32_C(0x311f0004),UINT32_C(0x7d083b96),UINT32_C(0x7d0839d6),
 UINT32_C(0x7f88f810),UINT32_C(0x339c0004),UINT32_C(0x2c1c0000),
 UINT32_C(0x41820008),UINT32_C(0x7f9c3810),UINT32_C(0x7fbc2014),
 UINT32_C(0x281c0020),UINT32_C(0x57de113a),UINT32_C(0x7bbd0020),
 UINT32_C(0x41800048)
};
static const uint32_t ar_m757_owner_50c8[3]={
 UINT32_C(0x7c9df010),UINT32_C(0x28040010),UINT32_C(0x418000b0)
};
int ar_m757_register_owner(const uint8_t*elf,size_t len){
 if(!elf||len<64u)return AR_BAD_ARGS;
 static const struct ar_m757_span spans[]={
   {UINT32_C(0x003c5050),13u,ar_m757_owner_5050,
    ar_m757_native_003c5050},
   {UINT32_C(0x003c50c8),3u,ar_m757_owner_50c8,
    ar_m757_native_003c50c8}
 };
 /* Validate both full segments including branch words BEFORE registering
  * either AOT entry, avoiding partially installed tables on a mismatch. */
 for(unsigned span=0;span<sizeof(spans)/sizeof(spans[0]);span++){
  const struct ar_m757_span*q=&spans[span];
  for(unsigned i=0;i<q->count;i+=4u){
    uint32_t words[6]={0};
    const unsigned n=q->count-i<4u?q->count-i:4u;
    if(ar_m712_exec_window(elf,len,q->pc+4u*i,words)!=AR_OK||
       words[4]<n||!(words[5]&1u))return AR_BAD_ARGS;
    for(unsigned j=0;j<n;j++){
      const uint32_t at=q->pc+4u*(i+j);
      if(words[j]!=q->words[i+j]||ar_read32(at)!=q->words[i+j]||
         ar_last_error()!=AR_OK)return AR_BAD_ARGS;
    }
  }
 }
 /* 003C5050 was the M7.56 unresolved PC: it MUST be newly installed. */
 int rc=ar_register(spans[0].pc,spans[0].fn);
 if(rc!=AR_OK)return rc;
 /* 003C50C8 already has _ar_bulk_ppu_003c50c8 in the signed M7.18
  * historical ARM64 batch. Installing a duplicate caused M7.57 loader -62.
  * Keep the first authenticated AOT owner (the bridge deliberately rejects
  * duplicate registrations). If the pre-existing translation is absent in
  * a different build, install this verified 3-word native continuation. */
 rc=ar_register(spans[1].pc,spans[1].fn);
 return rc==AR_DUPLICATE ? AR_OK : rc;
}
