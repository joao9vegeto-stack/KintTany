/* M7.28: scalar reference VMX/AltiVec + Cell partial vector memory.
 * Shared by authenticated PPC fallback and future statically lifted ARM64 AOT.
 * Canonical vector lanes are BIG-ENDIAN bytes in vr[v]._u64[0..1].
 * Avoid host SIMD layout/endian assumptions; all effects go through guest VM.
 */
#ifndef ASCENSION_PPU_VMX_CELL_H
#define ASCENSION_PPU_VMX_CELL_H
#include <stdint.h>
#include <string.h>
#include <math.h>
#include <fenv.h>
#include "ppu_bridge.h"
static inline uint8_t ar_vmx_byte(const ppu_context*c,unsigned v,unsigned n){
 const uint64_t word=c->vr[v]._u64[n>>3];
 return (uint8_t)(word >> (56u-8u*(n&7u)));
}
static inline void ar_vmx_setbyte(ppu_context*c,unsigned v,unsigned n,uint8_t value){
 const unsigned w=n>>3,sh=56u-8u*(n&7u);
 const uint64_t mask=UINT64_C(255)<<sh;
 c->vr[v]._u64[w]=(c->vr[v]._u64[w]&~mask)|((uint64_t)value<<sh);
}
static inline uint32_t ar_vmx_word(const ppu_context*c,unsigned v,unsigned n){
 return ((uint32_t)ar_vmx_byte(c,v,n*4)<<24) |
        ((uint32_t)ar_vmx_byte(c,v,n*4+1)<<16) |
        ((uint32_t)ar_vmx_byte(c,v,n*4+2)<<8) |
        ((uint32_t)ar_vmx_byte(c,v,n*4+3));
}
static inline void ar_vmx_splat_imm(ppu_context*c,unsigned vd,unsigned imm,
                                   unsigned width){
 /* VMX 5-bit signed value sign-extended to byte/halfword/word width. */
 const uint32_t sign=(imm&16u)?(imm|~UINT32_C(31)):imm;
 uint8_t pattern[4];
 for(unsigned k=0;k<width;k++)pattern[k]=(uint8_t)(sign>>(8u*(width-1u-k)));
 for(unsigned k=0;k<16u;k++)ar_vmx_setbyte(c,vd,k,pattern[k%width]);
}
static inline int ar_vmx_splatw(ppu_context*c,unsigned vd,unsigned vb,unsigned index){
 if(index>3u)return AR_PPC_UNSUPPORTED;
 const uint32_t value=ar_vmx_word(c,vb,index);
 for(unsigned k=0;k<4u;k++){
   ar_vmx_setbyte(c,vd,k*4u,(uint8_t)(value>>24));
   ar_vmx_setbyte(c,vd,k*4u+1u,(uint8_t)(value>>16));
   ar_vmx_setbyte(c,vd,k*4u+2u,(uint8_t)(value>>8));
   ar_vmx_setbyte(c,vd,k*4u+3u,(uint8_t)value);
 }
 return AR_OK;
}
static inline int ar_vmx_guest_load(ppu_context*c,unsigned vd,uint64_t ea,
                                    unsigned kind){
 /* kind 0=lvx, 1=lvlx, 2=lvrx.  Cell lvlx loads starting
  * at EA into LEFT vector lanes; right lanes are zeroed. */
 uint8_t temp[16]={0};
 const unsigned eb=(unsigned)(ea&15u);
 uint64_t start=ea;size_t n=16u;
 if(kind==0u)start=ea&~UINT64_C(15);
 else if(kind==1u)n=16u-eb;
 else if(kind==2u){start=ea&~UINT64_C(15);n=eb;}
 else return AR_PPC_UNSUPPORTED;
 if(n && ar_vm_read_bytes(start,temp+(kind==2u?16u-n:0u),n)!=AR_OK)
   return AR_MEM_FAULT;
 for(unsigned k=0;k<16u;k++)ar_vmx_setbyte(c,vd,k,temp[k]);
 return AR_OK;
}
static inline int ar_vmx_guest_store(const ppu_context*c,unsigned vs,uint64_t ea,
                                     unsigned kind){
 /* kind 0=stvx, 1=stvlx, 2=stvrx.
  * Validate the full guest range before any write, all-or-nothing. */
 uint8_t temp[16];
 for(unsigned k=0;k<16u;k++)temp[k]=ar_vmx_byte(c,vs,k);
 const unsigned eb=(unsigned)(ea&15u);
 uint64_t start=ea;size_t n=16u;size_t src=0u;
 if(kind==0u)start=ea&~UINT64_C(15);
 else if(kind==1u)n=16u-eb;
 else if(kind==2u){start=ea&~UINT64_C(15);src=16u-eb;n=eb;}
 else return AR_PPC_UNSUPPORTED;
 if(n && ar_vm_load(start,temp+src,n)!=AR_OK)return AR_MEM_FAULT;
 return AR_OK;
}

/* M7.48 VCFSX: convert 4 signed 32-bit fixed-point words to IEEE754
 * float32. Integer implementation of RN ties-to-even is independent
 * of ARM FPCR, and is correct for all PPC UIMM scale bits 0..31.
 * Snapshot source first: VD may alias VB. No FPSCR/CR changes. */
static inline uint32_t ar_vmx_vcfsx_lane(int32_t val,unsigned scale){
 const uint32_t neg=val<0?UINT32_C(0x80000000):0u;
 const uint32_t mag=val<0?(uint32_t)(-(int64_t)val):(uint32_t)val;
 if(!mag)return 0u;
 const unsigned msb=31u-(unsigned)__builtin_clz(mag);
 unsigned exponent=127u+msb-scale;
 uint32_t significant;
 if(msb<=23u){
  significant=mag<<(23u-msb);
 }else{
  const unsigned drop=msb-23u;
  const uint32_t mask=(UINT32_C(1)<<drop)-1u;
  const uint32_t rem=mag&mask,half=UINT32_C(1)<<(drop-1u);
  significant=mag>>drop;
  if(rem>half || (rem==half && (significant&1u)))significant++;
  if(significant==UINT32_C(0x01000000)){significant>>=1;exponent++;}
 }
 return neg|(exponent<<23)|(significant&UINT32_C(0x007fffff));
}
static inline void ar_vmx_vcfsx(ppu_context*c,unsigned vd,unsigned vb,unsigned scale){
 uint32_t src[4],dst[4];
 for(unsigned i=0;i<4u;i++)src[i]=ar_vmx_word(c,vb,i);
 for(unsigned i=0;i<4u;i++)dst[i]=ar_vmx_vcfsx_lane((int32_t)src[i],scale);
 for(unsigned i=0;i<4u;i++)
  for(unsigned j=0;j<4u;j++)
   ar_vmx_setbyte(c,vd,i*4u+j,(uint8_t)(dst[i]>>(24u-8u*j)));
}

/* M7.51 VMX vsubfp VD,VA,VB (VX opcode 74).
 * Four IEEE-754 single-precision lanes, read before any write so VD can
 * alias VA/VB. Fail closed for unsupported exceptional/denormal cases.
 * Do not change CR/XER/FPSCR or GPRs; VSCR mode is not emulated here. */
static inline int ar_vmx_vsubfp(ppu_context *c,unsigned vd,
                                unsigned va,unsigned vb){
 if(!c||vd>=32u||va>=32u||vb>=32u||fegetround()!=FE_TONEAREST)
   return AR_PPC_UNSUPPORTED;
 uint32_t words[4];
 for(unsigned i=0;i<4u;i++){
  uint32_t aa=ar_vmx_word(c,va,i),bb=ar_vmx_word(c,vb,i);
  float a,b;
  memcpy(&a,&aa,4u);memcpy(&b,&bb,4u);
  if(!isfinite(a)||!isfinite(b)||
     fpclassify(a)==FP_SUBNORMAL||fpclassify(b)==FP_SUBNORMAL)
    return AR_PPC_UNSUPPORTED;
  volatile float result=a-b;
  float v=result;
  if(!isfinite(v)||fpclassify(v)==FP_SUBNORMAL ||
     (v==0.0f && a!=b))
    return AR_PPC_UNSUPPORTED;
  memcpy(&words[i],&v,4u);
 }
 for(unsigned i=0;i<4u;i++)
  for(unsigned j=0;j<4u;j++)
   ar_vmx_setbyte(c,vd,4u*i+j,(uint8_t)(words[i]>>(24u-8u*j)));
 return AR_OK;
}

/* M7.52: VSLDOI packs VA|VB big-endian 16-byte vectors then selects
 * 16 bytes starting at SHB (0..15). Source snapshot handles VD==VA/VB.
 * The operation does not change scalar FPSCR, CR, XER or GPRs. */
static inline int ar_vmx_vsldoi(ppu_context*c,unsigned vd,
                               unsigned va,unsigned vb,unsigned shb){
 if(!c||vd>=32u||va>=32u||vb>=32u||shb>=16u)
   return AR_PPC_UNSUPPORTED;
 uint8_t both[32];
 for(unsigned i=0;i<16u;i++){
   both[i]=ar_vmx_byte(c,va,i);
   both[i+16u]=ar_vmx_byte(c,vb,i);
 }
 for(unsigned i=0;i<16u;i++)ar_vmx_setbyte(c,vd,i,both[i+shb]);
 return AR_OK;
}
/* M7.53 VMX floating-point arithmetic family.
 * Four big-endian IEEE754 lanes; snapshot first to support dest/source alias.
 * Approximate vrefp estimate via correctly-rounded single-precision reciprocal:
 * numerical estimate is not bit-exact to Cell hardware. For now nonfinite,
 * zero, subnormal and abnormal result states fail closed, not silently skip.
 * A fused multiply-add is used for VMADDfp/VNMSUBfp. CR/XER/FPSCR unaffected.
 */
static inline int ar_vmx_float_lane(uint32_t bits,float *value){
 if(!value)return AR_PPC_UNSUPPORTED;
 memcpy(value,&bits,sizeof(*value));
 if(!isfinite(*value)||fpclassify(*value)==FP_SUBNORMAL)
    return AR_PPC_UNSUPPORTED;
 return AR_OK;
}
static inline int ar_vmx_float_pack(ppu_context*c,unsigned vd,
                                    const uint32_t output[4]){
 if(!c||vd>=32u||!output)return AR_PPC_UNSUPPORTED;
 for(unsigned i=0;i<4u;i++)
  for(unsigned k=0;k<4u;k++)
   ar_vmx_setbyte(c,vd,4u*i+k,(uint8_t)(output[i]>>(24u-8u*k)));
 return AR_OK;
}
static inline int ar_vmx_fp_result(float f,uint32_t *bits){
 if(!bits||!isfinite(f)||fpclassify(f)==FP_SUBNORMAL)
   return AR_PPC_UNSUPPORTED;
 memcpy(bits,&f,4u);
 return AR_OK;
}
static inline int ar_vmx_vrefp(ppu_context*c,unsigned vd,unsigned vb){
 if(!c||vd>=32u||vb>=32u||fegetround()!=FE_TONEAREST)
  return AR_PPC_UNSUPPORTED;
 uint32_t out[4];
 for(unsigned i=0;i<4u;i++){
  float b=0.0f;
  if(ar_vmx_float_lane(ar_vmx_word(c,vb,i),&b)!=AR_OK || b==0.0f)
   return AR_PPC_UNSUPPORTED;
  volatile float q=1.0f/b;
  if(ar_vmx_fp_result(q,&out[i])!=AR_OK)return AR_PPC_UNSUPPORTED;
 }
 return ar_vmx_float_pack(c,vd,out);
}
static inline int ar_vmx_vmaddfp(ppu_context*c,unsigned vd,unsigned va,
                                  unsigned vb,unsigned vc,int negate){
 if(!c||vd>=32u||va>=32u||vb>=32u||vc>=32u||
    fegetround()!=FE_TONEAREST)return AR_PPC_UNSUPPORTED;
 uint32_t out[4];
 for(unsigned i=0;i<4u;i++){
  float a=0.0f,b=0.0f,z=0.0f;
  if(ar_vmx_float_lane(ar_vmx_word(c,va,i),&a)!=AR_OK||
     ar_vmx_float_lane(ar_vmx_word(c,vb,i),&b)!=AR_OK||
     ar_vmx_float_lane(ar_vmx_word(c,vc,i),&z)!=AR_OK)
      return AR_PPC_UNSUPPORTED;
  /* PPC VMADDfp: VA*VC+VB. VNMSUBfp: -(VA*VC-VB). */
  float result=negate ? fmaf(-a,z,b) : fmaf(a,z,b);
  if(ar_vmx_fp_result(result,&out[i])!=AR_OK)
    return AR_PPC_UNSUPPORTED;
 }
 return ar_vmx_float_pack(c,vd,out);
}

#endif
