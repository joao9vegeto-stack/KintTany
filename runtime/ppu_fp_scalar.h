/* M7.29: PowerPC64 PPU scalar FP subset for real owner ELF startup.
 * FPR is the pinned ps3recomp double[32] ABI, but LFD/STFD and FCFID
 * transfer IEEE754 raw BITS. Never treat integer payload as a C double.
 * Guest memory is big endian; all reads/writes validate as complete units.
 *
 * FCFID: only exactly representable i64 with FPSCR default RN supported.
 * FDIV: finite/normal IEEE754 values, default RN; keep FPSCR FPRF/FR/FI,
 * and sticky FX/XX when exact fused residual detects inexact rounding.
 * Complex NaNs, traps, non-default RN and under/overflow fail closed.
 * This is a deliberate, measurable ISA subset, NOT full FPSCR support.
 */
#ifndef AR_PPU_FP_SCALAR_H
#define AR_PPU_FP_SCALAR_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <math.h>
#include <fenv.h>
#include "ppu_bridge.h"
static inline uint64_t ar_fp_raw64(const ppu_context*c,unsigned i){
  uint64_t raw=0;memcpy(&raw,&c->fpr[i],sizeof(raw));return raw;
}
static inline void ar_fp_setraw(ppu_context*c,unsigned i,uint64_t raw){
  memcpy(&c->fpr[i],&raw,sizeof(raw));
}
static inline uint64_t ar_fp_be(const uint8_t *b,size_t n){
  uint64_t x=0;
  for(size_t i=0;i<n;i++)x=(x<<8)|b[i];
  return x;
}
static inline void ar_fp_pack(uint8_t *b,uint64_t x,size_t n){
  for(size_t i=n;i>0;){b[--i]=(uint8_t)x;x>>=8;}
}
static inline int ar_fp_load(ppu_context*c,unsigned ft,uint64_t ea,int single){
  uint8_t src[8]={0};
  const size_t n=single?4u:8u;
  if(ar_vm_read_bytes(ea,src,n)!=AR_OK)return AR_MEM_FAULT;
  if(single){
    const uint32_t bits=(uint32_t)ar_fp_be(src,4u);
    float val;
    memcpy(&val,&bits,sizeof(val));
    /* PPC LFS widens the single IEEE754 value into double FPR. */
    c->fpr[ft]=(double)val;
  }else{
    ar_fp_setraw(c,ft,ar_fp_be(src,8u));
  }
  return AR_OK;
}
static inline int ar_fp_store(ppu_context*c,unsigned fs,uint64_t ea,int single){
  uint8_t dst[8]={0};
  if(single){
    /* Keep this narrow conversion conservative until its FPSCR exception
     * flags, RN modes and SNAN behavior are fully implemented. */
    if((c->fpscr&7u)!=0u || fegetround()!=FE_TONEAREST ||
       !isfinite(c->fpr[fs]))return AR_PPC_UNSUPPORTED;
    volatile float narrow=(float)c->fpr[fs];
    float val=narrow;
    if(!isfinite(val) || (val==0.0f && c->fpr[fs]!=0.0) ||
       (fpclassify(val)==FP_SUBNORMAL))return AR_PPC_UNSUPPORTED;
    uint32_t bits;memcpy(&bits,&val,4);
    ar_fp_pack(dst,bits,4u);
    return ar_vm_load(ea,dst,4u)==AR_OK?AR_OK:AR_MEM_FAULT;
  }
  ar_fp_pack(dst,ar_fp_raw64(c,fs),8u);
  return ar_vm_load(ea,dst,8u)==AR_OK?AR_OK:AR_MEM_FAULT;
}
static inline void ar_fp_class(ppu_context*c,double v,int rounded,int roundedup){
  const uint32_t fprf=v==0.0?(signbit(v)?18u:2u):
                       (signbit(v)?8u:4u);
  c->fpscr=(c->fpscr & ~UINT32_C(0x0007f000)) | (fprf<<12);
  if(rounded){
    c->fpscr|=UINT32_C(0x82020000); /* FX, XX, FI */
    if(roundedup)c->fpscr|=UINT32_C(0x00040000);
  }
}
static inline int ar_fp_fcfid(ppu_context*c,unsigned dst,unsigned src){
  if((c->fpscr&7u)!=0u || fegetround()!=FE_TONEAREST)
     return AR_PPC_UNSUPPORTED;
  const int64_t signedval=(int64_t)ar_fp_raw64(c,src);
  /* Within +/- 2^53, integer -> f64 is exact and never alters flags.
   * Larger inputs are rejected until precise FR/FI rounding is implemented. */
  if(signedval>INT64_C(9007199254740992) ||
     signedval<-INT64_C(9007199254740992))return AR_PPC_UNSUPPORTED;
  volatile double calc=(double)signedval;
  const double v=calc;
  c->fpr[dst]=v;
  ar_fp_class(c,v,0,0);
  return AR_OK;
}
static inline int ar_fp_fdiv(ppu_context*c,unsigned dst,
                            unsigned ra,unsigned rb){
  if((c->fpscr&7u)!=0u || fegetround()!=FE_TONEAREST)
     return AR_PPC_UNSUPPORTED;
  const double a=c->fpr[ra],b=c->fpr[rb];
  if(!isfinite(a) || !isfinite(b) || b==0.0 ||
     fpclassify(a)==FP_SUBNORMAL || fpclassify(b)==FP_SUBNORMAL)
     return AR_PPC_UNSUPPORTED;
  volatile double quotient=a/b;
  const double result=quotient;
  if(!isfinite(result) || fpclassify(result)==FP_SUBNORMAL ||
     (result==0.0 && a!=0.0))return AR_PPC_UNSUPPORTED;
  /* FMA calculates the sign of the exact rounding residual in one step.
   * For b<0 its sign reverses; capture PPC FPSCR.FR direction faithfully
   * for normal, finite quotients. Otherwise do not claim support. */
  const double residual=fma(-result,b,a);
  if(!isfinite(residual))return AR_PPC_UNSUPPORTED;
  const int inexact=(residual!=0.0);
  const int roundedup=inexact &&
        (signbit(b)?(residual>0.0):(residual<0.0));
  c->fpr[dst]=result;
  ar_fp_class(c,result,inexact,roundedup);
  return AR_OK;
}
#endif
