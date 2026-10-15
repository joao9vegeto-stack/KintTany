/* Isolated PPU dispatcher for smoke tests, not full PS3Recomp runtime. */
#include "ppu_bridge.h"
#include <stdlib.h>
#include <string.h>
#define MAX_FUNCS 8192
#define MAX_MEM (128u*1024u*1024u)
#define MAX_DEPTH 64
static struct {uint32_t pc;ar_ppu_fn fn;} funcs[MAX_FUNCS];
static size_t nfunc,mem_size;
static uint8_t *mem;
static int fault;
static uint32_t missing,budget,depth;
int ar_bridge_init(size_t n) {
  if(!n||n>MAX_MEM)return AR_BAD_ARGS;
  ar_bridge_shutdown();
  mem=(uint8_t*)calloc(n,1);
  if(!mem)return AR_NO_MEMORY;
  mem_size=n;return AR_OK;
}
void ar_bridge_shutdown(void){
  free(mem);mem=0;mem_size=0;nfunc=0;fault=0;missing=0;budget=0;depth=0;
}
int ar_last_error(void){return fault;}
uint32_t ar_last_unresolved(void){return missing;}
size_t ar_registered_count(void){return nfunc;}
static int bounds(uint64_t a,size_t n){
  if(!mem||a>UINT32_MAX||a>mem_size||n>mem_size-(size_t)a){
    fault=AR_MEM_FAULT;return 0;
  }
  return 1;
}
int ar_vm_load(uint64_t a,const void* b,size_t n) {
  if((!b&&n)||!bounds(a,n))return AR_MEM_FAULT;
  if(n)memcpy(mem+(size_t)a,b,n);return AR_OK;
}
int ar_vm_zero(uint64_t a,size_t n) {
  if(!bounds(a,n))return AR_MEM_FAULT;
  if(n)memset(mem+(size_t)a,0,n);return AR_OK;
}
static uint64_t read_be(uint64_t a,size_t n) {
  if(!bounds(a,n))return 0;
  uint64_t v=0;for(size_t i=0;i<n;i++)v=(v<<8)|mem[(size_t)a+i];
  return v;
}
static void write_be(uint64_t a,uint64_t v,size_t n){
  if(!bounds(a,n))return;
  for(size_t i=0;i<n;i++){mem[(size_t)a+n-1-i]=(uint8_t)v;v>>=8;}
}
uint8_t ar_read8(uint64_t a){return (uint8_t)read_be(a,1);}
uint16_t ar_read16(uint64_t a){return (uint16_t)read_be(a,2);}
uint32_t ar_read32(uint64_t a){return (uint32_t)read_be(a,4);}
uint64_t ar_read64(uint64_t a){return read_be(a,8);}
void ar_write8(uint64_t a,uint8_t v){write_be(a,v,1);}
void ar_write16(uint64_t a,uint16_t v){write_be(a,v,2);}
void ar_write32(uint64_t a,uint32_t v){write_be(a,v,4);}
void ar_write64(uint64_t a,uint64_t v){write_be(a,v,8);}
int ar_register(uint32_t pc,ar_ppu_fn fn){
  if(!pc||(pc&3)||!fn||nfunc>=MAX_FUNCS)return AR_BAD_ARGS;
  for(size_t i=0;i<nfunc;i++)if(funcs[i].pc==pc)return AR_DUPLICATE;
  funcs[nfunc].pc=pc;funcs[nfunc++].fn=fn;return AR_OK;
}
static ar_ppu_fn lookup(uint64_t addr){
  if(addr>UINT32_MAX||(addr&3))return 0;
  for(size_t i=0;i<nfunc;i++)if(funcs[i].pc==addr)return funcs[i].fn;
  return 0;
}
static int dispatch(ppu_context *c,uint64_t pc){
  if(depth>=MAX_DEPTH){fault=AR_DEPTH;return AR_DEPTH;}
  depth++;int result=AR_OK;
  for(;;){
    if(!budget){result=fault=AR_BUDGET;break;}
    budget--;
    ar_ppu_fn fn=lookup(pc);
    if(!fn){missing=(uint32_t)pc;result=fault=AR_UNRESOLVED;break;}
    int status=fn(c);
    if(fault){result=fault;break;}
    if(status==AR_TAIL){pc=c->cia;continue;}
    if(status==AR_OK){result=AR_OK;break;}
    result=fault=status;break;
  }
  depth--;return result;
}
int ar_guest_call(ppu_context *c,uint64_t pc){
  if(!c||!depth)return AR_BAD_ARGS;
  return dispatch(c,pc);
}
int ar_run(ppu_context *c,uint32_t pc,uint32_t ticks){
  if(!c||!pc||!ticks||!mem||depth)return AR_BAD_ARGS;
  fault=0;missing=0;budget=ticks;
  return dispatch(c,pc);
}
