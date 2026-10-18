/* M7.49: original GOWA.ELF 0x003B1D5C FRSP f1,f1.
 * Genuine statically compiled C -> ARM64 after whole owner SHA gate.
 * The 4 executable bytes must match ELF PT_LOAD X and loaded guest VM.
 */
#include <stdint.h>
#include <stddef.h>
#include "ppu_bridge.h"
#include "ppu_fp_scalar.h"
extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);
int ar_m749_native_003b1d5c(ppu_context*c){
 if(!c)return AR_BAD_ARGS;
 const int rc=ar_fp_frsp(c,1u,1u);
 if(rc!=AR_OK)return rc;
 c->cia=UINT32_C(0x003b1d60);
 return AR_TAIL;
}
int ar_m749_register_frsp(const uint8_t*elf,size_t len){
 if(!elf||len<64u)return AR_BAD_ARGS;
 uint32_t w[6]={0};
 const uint32_t pc=UINT32_C(0x003b1d5c),expect=UINT32_C(0xfc200818);
 if(ar_m712_exec_window(elf,len,pc,w)!=AR_OK||
    w[4]<1u||!(w[5]&1u)||w[0]!=expect)return AR_BAD_ARGS;
 if(ar_read32(pc)!=expect||ar_last_error()!=AR_OK)return AR_BAD_ARGS;
 uint64_t fnv=UINT64_C(14695981039346656037);
 for(unsigned i=0;i<4u;i++){
  fnv^=(uint8_t)(w[0]>>(24u-8u*i));
  fnv*=UINT64_C(1099511628211);
 }
 if(fnv!=UINT64_C(0xb452445b9eadfb69))return AR_BAD_ARGS;
 return ar_register(pc,ar_m749_native_003b1d5c);
}
