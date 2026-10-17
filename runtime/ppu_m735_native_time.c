/* M7.35: Seven owner-ELF authenticated PPC64 ARM64 entrypoints
 * covering 80 distinct guest opcodes (82 counting overlap at 0052AAD8).
 * No commercial ELF data is included. Importer first verifies the SHA-256
 * of the owner's ELF, then each block's executable-memory FNV fingerprint.
 * Never treat unknown opcodes as NOPs or PPC interpretation as AOT.
 */
#include <stdint.h>
#include <stddef.h>
#include "ppu_bridge.h"
extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);
#define XER_CA UINT32_C(0x20000000)
#define AAD0 UINT32_C(0x0052aad0)
#define AAFC UINT32_C(0x0052aafc)
#define AB58 UINT32_C(0x0052ab58)
#define ABE8 UINT32_C(0x0052abe8)
static uint64_t extend_32(uint32_t w) { return (uint64_t)(int64_t)(int32_t)w; }
static uint64_t arith_shift64(ppu_context *c, uint64_t x, unsigned amount) {
  const uint64_t negative=x>>63;
  const uint64_t lost=amount?(x&(UINT64_MAX>>(64u-amount))):0;
  uint64_t result=amount?x>>amount:x;
  if(negative&&amount) result|=UINT64_MAX<<(64u-amount);
  c->xer=(c->xer&~XER_CA)|((negative&&lost)?XER_CA:0u);
  return result;
}
static uint64_t mul_high_signed(uint64_t a,uint64_t b) {
  const __int128 product=(__int128)(int64_t)a*(__int128)(int64_t)b;
  return (uint64_t)((unsigned __int128)product>>64u);
}
static int get32(uint64_t addr,uint64_t *out) {
  *out=ar_read32(addr);return ar_last_error()==AR_OK?AR_OK:AR_MEM_FAULT;
}
static int get64(uint64_t addr,uint64_t *out) {
  *out=ar_read64(addr);return ar_last_error()==AR_OK?AR_OK:AR_MEM_FAULT;
}
static int get16(uint64_t addr,uint64_t *out) {
  *out=ar_read16(addr);return ar_last_error()==AR_OK?AR_OK:AR_MEM_FAULT;
}
static int put32(uint64_t addr,uint32_t val) {
  ar_write32(addr,val);return ar_last_error()==AR_OK?AR_OK:AR_MEM_FAULT;
}
static void cmpw7(ppu_context *c,uint64_t a,uint64_t b) {
  const int32_t l=(int32_t)(uint32_t)a,r=(int32_t)(uint32_t)b;
  const uint32_t bits=l<r?8u:l>r?4u:2u;
  c->cr=(c->cr&~UINT32_C(0xf))|bits|((c->xer>>31u)&1u);
}
/* 0052AAB0..0052AACC: CR7 EQ branch chooses normal date path or
 * special base-address setup. Real guest memory stores happen before branch.
 */
int ar_m735_native_0052aab0(ppu_context *c){
  if(!c)return AR_BAD_ARGS;
  uint64_t *r=c->gpr;
  r[0]=(uint32_t)r[31]&UINT64_C(3); /* clrlwi r0,r31,30 */
  r[6]=r[30]-r[3];
  cmpw7(c,r[0],0);
  if(put32(r[28]+20u,(uint32_t)r[31])!=AR_OK)return AR_MEM_FAULT;
  if(put32(r[28]+28u,(uint32_t)r[6])!=AR_OK)return AR_MEM_FAULT;
  if(!(c->cr&2u)){c->cia=AAD0;return AR_TAIL;} /* bf CR7.EQ */
  cmpw7(c,r[31],0);
  c->cia=(c->cr&2u)?AAD0:ABE8;
  return AR_TAIL;
}
/* 0052ABE8..0052ABEC: alternative branch recovers guest TOC global
 * without adding 24 to its base pointer. */
int ar_m735_native_0052abe8(ppu_context*c){
  if(!c)return AR_BAD_ARGS;
  uint64_t *r=c->gpr;
  if(get32(r[2]+(uint64_t)(int64_t)-22952,&r[9])!=AR_OK)
    return AR_MEM_FAULT;
  c->cia=UINT32_C(0x0052aad8);
  return AR_TAIL;
}
/* 0052AAD8 and 0052AADC are a second valid entry into the loop. */
int ar_m735_native_0052aad8(ppu_context*c){
  if(!c)return AR_BAD_ARGS;
  uint64_t*r=c->gpr;
  r[11]=r[9]+UINT64_C(22);
  r[7]=UINT64_C(12);
  c->cia=UINT32_C(0x0052aae0);
  return AR_TAIL;
}
/* 0052AAD0..0052AAF8: loop reads 16-bit guest data through guest r2 TOC.
 * No host filesystem access, no direct guest pointer dereference. */
int ar_m735_native_0052aad0(ppu_context *c) {
  if(!c)return AR_BAD_ARGS;
  uint64_t *r=c->gpr;
  uint64_t tmp=0;
  if(get32(r[2]+(uint64_t)(int64_t)-22952,&tmp)!=AR_OK)return AR_MEM_FAULT;
  r[9]=tmp;
  r[9]+=UINT64_C(24);
  r[11]=r[9]+UINT64_C(22);
  r[7]=UINT64_C(12);
  /* 0052AAE0 is a loop header, re-entered after every true comparison. */
  c->cia=UINT32_C(0x0052aae0);
  return AR_TAIL;
}
int ar_m735_native_0052aae0(ppu_context *c){
  if(!c)return AR_BAD_ARGS;
  uint64_t *r=c->gpr;
  r[9]=(uint32_t)r[11];
  r[7]-=1u;
  r[11]-=2u;
  uint64_t readval=0;
  if(get16(r[9],&readval)!=AR_OK)return AR_MEM_FAULT;
  r[0]=readval;
  r[3]=(uint64_t)(int64_t)(int16_t)(uint16_t)r[0];
  cmpw7(c,r[6],r[3]);
  c->cia=(c->cr&8u)?UINT32_C(0x0052aae0):AAFC;
  return AR_TAIL;
}
/* 0052AAFC..0052AB54: no internal jumps; LLVM ARM64 keeps all PPC GPRs. */
int ar_m735_native_0052aafc(ppu_context *c){
  if(!c)return AR_BAD_ARGS;
  uint64_t*r=c->gpr;
  r[0]=UINT64_C(0x18450000);
  if(get64(r[1]+152u,&r[29])!=AR_OK)return AR_MEM_FAULT;
  r[9]=r[6]-r[3];
  if(get64(r[1]+160u,&r[30])!=AR_OK)return AR_MEM_FAULT;
  r[0]|=UINT64_C(0xc8a0);
  if(get64(r[1]+168u,&r[31])!=AR_OK)return AR_MEM_FAULT;
  r[9]+=1u;
  r[0]<<=32u;
  if(put32(r[28]+12u,(uint32_t)r[9])!=AR_OK)return AR_MEM_FAULT;
  r[0]|=UINT64_C(0xce510000);
  r[10]=UINT64_C(0x48d10000);
  r[0]|=UINT64_C(0x2957);
  r[10]|=UINT64_C(0x59e2);
  r[8]=extend_32(UINT32_C(0x88880000));
  r[10]<<=32u;
  r[8]|=UINT64_C(0x8888);
  r[10]|=UINT64_C(0x6af30000);
  r[8]<<=32u;
  r[10]|=UINT64_C(0x7c05);
  r[8]|=UINT64_C(0x88880000);
  r[3]=r[28];
  r[8]|=UINT64_C(0x8889);
  if(put32(r[28]+16u,(uint32_t)r[7])!=AR_OK)return AR_MEM_FAULT;
  c->cia=AB58;return AR_TAIL;
}
/* 0052AB58..0052ABE4: signed 128-bit mulhd, arithmetic shifts, guest
 * stores, PPC LR restoration and stack epilogue. Return from guest call. */
int ar_m735_native_0052ab58(ppu_context*c){
  if(!c)return AR_BAD_ARGS;
  uint64_t*r=c->gpr;
  r[0]=mul_high_signed(r[27],r[0]);
  r[0]=arith_shift64(c,r[0],13u);
  r[0]-=r[26];
  if(get64(r[1]+128u,&r[26])!=AR_OK)return AR_MEM_FAULT;
  r[11]=r[0]<<9u;
  r[0]<<=7u;
  r[11]-=r[0];
  r[9]=r[11]<<4u;
  r[9]-=r[11];
  r[0]=r[9]<<4u;
  r[0]-=r[9];
  r[0]=r[27]-r[0];
  if(get64(r[1]+136u,&r[27])!=AR_OK)return AR_MEM_FAULT;
  r[9]=arith_shift64(c,r[0],63u);
  r[10]=mul_high_signed(r[0],r[10]);
  r[10]=arith_shift64(c,r[10],10u);
  r[10]-=r[9];
  if(put32(r[28]+8u,(uint32_t)r[10])!=AR_OK)return AR_MEM_FAULT;
  r[10]*=UINT64_C(3600);
  r[10]=r[0]-r[10];
  r[9]=arith_shift64(c,r[10],63u);
  r[8]=mul_high_signed(r[10],r[8]);
  r[8]+=r[10];
  r[8]=arith_shift64(c,r[8],5u);
  r[8]-=r[9];
  r[0]=r[8]<<6u;
  r[9]=r[8]<<2u;
  if(put32(r[28]+4u,(uint32_t)r[8])!=AR_OK)return AR_MEM_FAULT;
  r[0]-=r[9];
  r[10]-=r[0];
  if(get64(r[1]+192u,&r[0])!=AR_OK)return AR_MEM_FAULT;
  if(put32(r[28],(uint32_t)r[10])!=AR_OK)return AR_MEM_FAULT;
  c->lr=r[0];
  if(get64(r[1]+144u,&r[28])!=AR_OK)return AR_MEM_FAULT;
  r[1]+=UINT64_C(176);
  c->cia=c->lr&~UINT64_C(3);
  return AR_OK;
}
/* Strong owner provenance, not merely the address: authenticated whole
 * ELF in ios/ARLivePPUBridge, then PT_LOAD execute + mapped guest bytes,
 * then FNV fingerprint for the exact 3 disjoint contiguous windows. */
struct m735_desc {uint32_t pc,insns;uint64_t fingerprint;ar_ppu_fn function;};
static const struct m735_desc owner_blocks[]={
 {UINT32_C(0x0052aab0),8u,UINT64_C(0x21ff3a4a82f19351),ar_m735_native_0052aab0},
 {UINT32_C(0x0052abe8),2u,UINT64_C(0xa8c22b930d9eae7c),ar_m735_native_0052abe8},
 {UINT32_C(0x0052aad8),2u,UINT64_C(0x1c578e3c0b4f8655),ar_m735_native_0052aad8},
 {AAD0,4u,UINT64_C(0x02489214c8802ece),ar_m735_native_0052aad0},
 {UINT32_C(0x0052aae0),7u,UINT64_C(0x488991ae301b31ab),ar_m735_native_0052aae0},
 {AAFC,23u,UINT64_C(0x5ca17a15c98f0eb4),ar_m735_native_0052aafc},
 {AB58,36u,UINT64_C(0x6b7ebf66b80bd223),ar_m735_native_0052ab58}
};
int ar_m735_register_owner(const uint8_t *elf,size_t size){
  if(!elf||size<64u)return AR_BAD_ARGS;
  for(size_t i=0;i<sizeof(owner_blocks)/sizeof(owner_blocks[0]);i++){
    const struct m735_desc *b=&owner_blocks[i];
    uint64_t h=UINT64_C(14695981039346656037);
    for(uint32_t j=0;j<b->insns;j+=4u){
      uint32_t word[6]={0};
      const uint32_t count=b->insns-j<4?b->insns-j:4u;
      if(ar_m712_exec_window(elf,size,b->pc+4u*j,word)!=AR_OK ||
         word[4]<count || !(word[5]&1u))return AR_BAD_ARGS;
      for(uint32_t k=0;k<count;k++){
        uint32_t w=word[k];
        if(ar_read32(b->pc+4u*(j+k))!=w || ar_last_error()!=AR_OK)
          return AR_BAD_ARGS;
        for(unsigned q=0;q<4;q++){
          h^=(uint8_t)(w>>(24u-8u*q));h*=UINT64_C(1099511628211);
        }
      }
    }
    if(h!=b->fingerprint)return AR_BAD_ARGS;
  }
  for(size_t i=0;i<sizeof(owner_blocks)/sizeof(owner_blocks[0]);i++){
    const int result=ar_register(owner_blocks[i].pc,owner_blocks[i].function);
    if(result!=AR_OK)return result;
  }
  return AR_OK;
}
