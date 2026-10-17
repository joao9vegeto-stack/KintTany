/* Authentic sysPrxForUser imports; no fixed game stub addresses. */
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "ppu_mmapper.h"
extern int ar_private_import_find_nid(const uint8_t*,size_t,uint32_t,
 const char*,uint32_t[4],char[48]);
int ar_m711_bind_memory(const uint8_t*d,size_t len,uint32_t*out){
 const struct {uint32_t nid;ar_hle_fn fn;} services[]={
  {0xb257540bu,ar_sys_mmapper_allocate_memory},
  {0xdc578057u,ar_sys_mmapper_map_memory},
  {0x4643ba6eu,ar_sys_mmapper_unmap_memory},
  {0x409ad939u,ar_sys_mmapper_free_memory}};
 if(ar_bind_syscall(0x14au,ar_sys_mmapper_allocate_address)!=AR_OK)return AR_BAD_ARGS;
 for(unsigned i=0;i<4;i++){
  uint32_t imp[4]={0};char lib[48]={0};
  if(ar_private_import_find_nid(d,len,services[i].nid,"sysPrxForUser",imp,lib)!=0||
     imp[0]!=services[i].nid||!imp[1]||strcmp(lib,"sysPrxForUser"))
     return AR_MISSING_HLE;
  if(ar_bind_import(imp[1],imp[0])!=AR_OK||
     ar_bind_hle(imp[0],services[i].fn)!=AR_OK)return AR_BAD_ARGS;
 }
 if(out)out[15]|=0x2000u;
 return AR_OK;
}
