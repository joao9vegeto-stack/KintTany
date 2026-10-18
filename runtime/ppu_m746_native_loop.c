/* M7.46: real native AOT of 69 ELF-authenticated NPUA80918 PPC words.
 * Four entry PCs; two CTR loops. No JIT, RPCS3 or game assets in IPA.
 * Whole GOWA.ELF SHA-256 must pass before registration. */
#include <stdint.h>
#include <stddef.h>
#include "ppu_bridge.h"
extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);
#define CA UINT32_C(0x20000000)
static uint64_t addic(ppu_context*c,uint64_t lhs,int32_t imm){
 const uint64_t rhs=(uint64_t)(int64_t)imm,v=lhs+rhs;
 c->xer=(c->xer&~CA)|(v<lhs?CA:0u);return v;
}
static int st8(uint64_t p,uint64_t v){ar_write8(p,(uint8_t)v);return ar_last_error()==AR_OK?AR_OK:AR_MEM_FAULT;}
static int st32(uint64_t p,uint64_t v){ar_write32(p,(uint32_t)v);return ar_last_error()==AR_OK?AR_OK:AR_MEM_FAULT;}
static int st64(uint64_t p,uint64_t v){ar_write64(p,v);return ar_last_error()==AR_OK?AR_OK:AR_MEM_FAULT;}
static int execute(ppu_context*c,unsigned entry){
 if(!c)return AR_BAD_ARGS;
 uint64_t*r=c->gpr;
 if(entry==0){
   const uint64_t prev=r[1],next=prev-UINT64_C(64);
   if(st64(next,prev)!=AR_OK)return AR_MEM_FAULT;
   r[1]=next;r[7]=0;r[4]=UINT64_MAX;r[6]=0;r[8]=32;
   if(st8(r[3],r[7])!=AR_OK)return AR_MEM_FAULT;
   r[5]=r[3];
   if(st32(r[3]+832u,r[7])!=AR_OK)return AR_MEM_FAULT;
   c->ctr=r[8];
   if(st32(r[3]+836u,r[7])!=AR_OK)return AR_MEM_FAULT;
   if(st32(r[3]+840u,r[4])!=AR_OK)return AR_MEM_FAULT;
   if(st64(r[3]+848u,r[6])!=AR_OK)return AR_MEM_FAULT;
   if(st32(r[3]+856u,r[7])!=AR_OK)return AR_MEM_FAULT;
   if(st32(r[3]+860u,r[7])!=AR_OK)return AR_MEM_FAULT;
   if(st32(r[3]+2480u,r[7])!=AR_OK)return AR_MEM_FAULT;
   if(st32(r[3]+828u,r[7])!=AR_OK)return AR_MEM_FAULT;
   if(st32(r[3]+824u,r[7])!=AR_OK)return AR_MEM_FAULT;
   if(st32(r[3]+864u,r[7])!=AR_OK)return AR_MEM_FAULT;
   if(st8(r[3]+889u,r[7])!=AR_OK)return AR_MEM_FAULT;
   if(st32(r[3]+2484u,r[7])!=AR_OK)return AR_MEM_FAULT;
   if(st32(r[3]+868u,r[7])!=AR_OK)return AR_MEM_FAULT;
   if(st32(r[3]+880u,r[7])!=AR_OK)return AR_MEM_FAULT;
   if(st32(r[3]+884u,r[7])!=AR_OK)return AR_MEM_FAULT;
   if(st32(r[3]+876u,r[7])!=AR_OK)return AR_MEM_FAULT;
   if(st32(r[3]+872u,r[7])!=AR_OK)return AR_MEM_FAULT;
   if(st8(r[3]+888u,r[7])!=AR_OK)return AR_MEM_FAULT;
   if(st8(r[3]+890u,r[7])!=AR_OK)return AR_MEM_FAULT;
   if(st64(r[1]+56u,r[31])!=AR_OK)return AR_MEM_FAULT;
   if(st32(r[3]+892u,r[7])!=AR_OK)return AR_MEM_FAULT;
   if(st32(r[3]+896u,r[7])!=AR_OK)return AR_MEM_FAULT;
 }
 if(entry<=1){
   /* Real PPC 0x003EF744..0x003EF7A8, BDNZ back to loop head. */
   unsigned i=0;
   for(;;){
     if(i++==64u){c->cia=UINT32_C(0x003ef744);return AR_PPC_LIMIT;}
     r[8]=addic(c,r[5],920);r[9]=addic(c,r[5],912);
     r[8]=(uint32_t)r[8];r[10]=addic(c,r[5],924);
     r[9]=(uint32_t)r[9];r[11]=addic(c,r[5],944);
     r[12]=addic(c,r[5],904);
     r[10]=(uint32_t)r[10];r[11]=(uint32_t)r[11];
     if(st32(r[8],r[7])!=AR_OK)return AR_MEM_FAULT;
     r[8]=(uint32_t)r[12];
     if(st64(r[9],r[6])!=AR_OK)return AR_MEM_FAULT;
     r[31]=addic(c,r[5],948);
     r[9]=addic(c,r[5],928);
     if(st8(r[10],r[7])!=AR_OK)return AR_MEM_FAULT;
     if(st32(r[11],r[7])!=AR_OK)return AR_MEM_FAULT;
     r[10]=(uint32_t)r[31];
     if(st32(r[8],r[7])!=AR_OK)return AR_MEM_FAULT;
     r[11]=addic(c,r[5],936);
     r[8]=(uint32_t)r[9];r[9]=(uint32_t)r[11];
     r[5]=addic(c,r[5],48);
     if(st8(r[10],r[7])!=AR_OK)return AR_MEM_FAULT;
     if(st32(r[8],r[7])!=AR_OK)return AR_MEM_FAULT;
     if(st64(r[9],r[6])!=AR_OK)return AR_MEM_FAULT;
     c->ctr--;if(c->ctr==0u)break;
   }
 }
 if(entry<=2){r[5]=5u;c->ctr=r[5];}
 /* 003EF7B4..003EF7D0 second BDNZ loop, five iterations. */
 unsigned steps=0;
 for(;;){
   if(steps++==64u){c->cia=UINT32_C(0x003ef7b4);return AR_PPC_LIMIT;}
   r[5]=addic(c,r[3],2440);r[6]=addic(c,r[3],2444);
   r[5]=(uint32_t)r[5];r[6]=(uint32_t)r[6];
   r[3]=addic(c,r[3],8);
   if(st32(r[5],r[4])!=AR_OK)return AR_MEM_FAULT;
   if(st32(r[6],r[4])!=AR_OK)return AR_MEM_FAULT;
   c->ctr--;if(c->ctr==0u)break;
 }
 const uint64_t saved=ar_read64(r[1]+56u);
 if(ar_last_error()!=AR_OK)return AR_MEM_FAULT;
 r[31]=saved;r[1]+=UINT64_C(64);return AR_OK;
}
int ar_m746_native_003ef6cc(ppu_context*c){return execute(c,0u);}
int ar_m746_native_003ef744(ppu_context*c){return execute(c,1u);}
int ar_m746_native_003ef7ac(ppu_context*c){return execute(c,2u);}
int ar_m746_native_003ef7b4(ppu_context*c){return execute(c,3u);}
typedef struct {uint32_t pc,n;uint64_t fnv;ar_ppu_fn fn;} owner_span;
static const owner_span spans[]={
 {0x003ef6ccu,69u,UINT64_C(0x7a88b667fbb62b89),ar_m746_native_003ef6cc},
 {0x003ef744u,39u,UINT64_C(0x2a969db8283955ff),ar_m746_native_003ef744},
 {0x003ef7acu,13u,UINT64_C(0x90f80017c002acdd),ar_m746_native_003ef7ac},
 {0x003ef7b4u,11u,UINT64_C(0x53cf015c5e88d5fc),ar_m746_native_003ef7b4}
};
int ar_m746_register_hotloop(const uint8_t*elf,size_t len){
 if(!elf||len<64)return AR_BAD_ARGS;
 /* Validate ALL original ELF + guest-VM bytes before ANY registration. */
 for(unsigned i=0;i<sizeof(spans)/sizeof(spans[0]);i++){
   const owner_span*s=&spans[i];uint64_t h=UINT64_C(14695981039346656037);
   for(uint32_t j=0;j<s->n;j+=4u){
     uint32_t w[6]={0};
     const uint32_t n=(s->n-j<4u)?s->n-j:4u;
     if(ar_m712_exec_window(elf,len,s->pc+j*4u,w)!=AR_OK||
        w[4]<n||!(w[5]&1u))return AR_BAD_ARGS;
     for(unsigned k=0;k<n;k++){
       const uint32_t v=w[k];
       if(ar_read32(s->pc+(j+k)*4u)!=v||ar_last_error()!=AR_OK)return AR_BAD_ARGS;
       for(unsigned a=0;a<4;a++){h^=(uint8_t)(v>>(24u-8u*a));h*=UINT64_C(1099511628211);}
     }
   }
   if(h!=s->fnv)return AR_BAD_ARGS;
 }
 for(unsigned i=0;i<sizeof(spans)/sizeof(spans[0]);i++)
   if(ar_register(spans[i].pc,spans[i].fn)!=AR_OK)return AR_DUPLICATE;
 return AR_OK;
}
