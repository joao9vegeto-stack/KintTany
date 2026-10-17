#include "ppu_native_sysutil.h"
#include <string.h>
extern int ar_private_import_find_nid(const uint8_t*,size_t,uint32_t,
const char*,uint32_t[4],char[48]);
int ar_m711_bind_sysutil(const uint8_t*d,size_t n,uint32_t*out){
 const uint32_t ids[]={0x189a74da,0x9d98afa0,0x02ff3c1b,0x40e895d3};
 for(unsigned i=0;i<4;i++){
  uint32_t m[4]={0};char lib[48]={0};
  if(ar_private_import_find_nid(d,n,ids[i],"cellSysutil",m,lib) ||
    !m[1] || m[0]!=ids[i] || strcmp(lib,"cellSysutil"))return AR_MISSING_HLE;
  if(ar_sysutil_bind_core(m[0],m[1])!=AR_OK)return AR_BAD_ARGS;
 }
 uint32_t m[4]={0};char lib[48]={0};
 if(ar_private_import_find_nid(d,n,0x32267a31u,"cellSysmodule",m,lib) ||
    !m[1] || m[0]!=0x32267a31u || strcmp(lib,"cellSysmodule"))return AR_MISSING_HLE;
 if(ar_bind_import(m[1],m[0]) || ar_bind_hle(m[0],ar_sysutil_load_module))
   return AR_BAD_ARGS;
 if(out)out[15]|=0x800u;
 return AR_OK;
}
