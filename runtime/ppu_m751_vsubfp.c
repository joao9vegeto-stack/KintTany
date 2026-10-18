/* M7.51: native owner VMX vsubfp at real M7.50 failure PC 0x003B0604.
 * AOT installs only when exact original ELF/PT_LOAD-X/guest-VM word matches.
 */
#include <stdint.h>
#include <stddef.h>
#include "ppu_bridge.h"
#include "ppu_vmx_cell.h"
extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);
int ar_m751_native_003b0604(ppu_context *c){
 if(!c)return AR_BAD_ARGS;
 int rc=ar_vmx_vsubfp(c,3u,2u,3u);
 if(rc!=AR_OK){c->cia=UINT32_C(0x003b0604);return rc;}
 c->cia=UINT32_C(0x003b0608);return AR_TAIL;
}
int ar_m751_register_vsubfp(const uint8_t *elf,size_t len){
 if(!elf||len<64u)return AR_BAD_ARGS;
 uint32_t w[6]={0};
 const uint32_t pc=UINT32_C(0x003b0604),word=UINT32_C(0x1062184a);
 if(ar_m712_exec_window(elf,len,pc,w)!=AR_OK||
    w[4]<1u||!(w[5]&1u)||w[0]!=word||
    ar_read32(pc)!=word||ar_last_error()!=AR_OK)return AR_BAD_ARGS;
 uint64_t h=UINT64_C(14695981039346656037);
 for(unsigned i=0;i<4u;i++){
  h^=(uint8_t)(word>>(24u-8u*i));h*=UINT64_C(1099511628211);
 }
 if(h!=UINT64_C(0x7aefeb06ce41cf95))return AR_BAD_ARGS;
 return ar_register(pc,ar_m751_native_003b0604);
}
