/* Generic bounded implementation of PS3 sys_initialize_tls; single-thread. */
#include "ppu_tls.h"
#include <stdint.h>
static uint32_t next_tls,tls_limit;
int ar_tls_configure(uint32_t begin,uint32_t end) {
 if(!begin||(begin&4095u)||(end&4095u)||end<=begin||end>256u*1024u*1024u)
  return AR_BAD_ARGS;
 next_tls=begin;tls_limit=end;return AR_OK;
}
int ar_sys_initialize_tls(ppu_context*c){
 if(!c||!next_tls)return AR_BAD_ARGS;
 uint64_t src=c->gpr[4],filesz=c->gpr[5],memsz=c->gpr[6];
 if(src>UINT32_MAX||memsz>1024u*1024u||filesz>memsz)return AR_BAD_ARGS;
 uint64_t total=(memsz+0x7000u+0x1000u+0xfffu)&~(uint64_t)0xfffu;
 if(total>(uint64_t)tls_limit-next_tls)return AR_NO_MEMORY;
 uint32_t base=next_tls;
 if(ar_vm_zero(base,(size_t)(memsz?memsz:1))!=AR_OK)return AR_MEM_FAULT;
 for(uint64_t i=0;i<filesz;i++){
   uint8_t val=ar_read8(src+i);
   if(ar_last_error()==AR_MEM_FAULT)return AR_MEM_FAULT;
   ar_write8((uint64_t)base+i,val);
   if(ar_last_error()==AR_MEM_FAULT)return AR_MEM_FAULT;
 }
 next_tls+=(uint32_t)total;
 c->gpr[13]=(uint64_t)base+0x7000u;
 c->gpr[3]=0;
 return AR_OK;
}
