/* M7.53: authenticated block of FOUR contiguous PPC VMX FP operations.
 * Not a fabricated bootstrap: entry at actual M7.52 iPhone stop 003B062C.
 * Both ELF executable PT_LOAD and mapped guest memory must match exact words.
 * Generic VMX helpers shared by CFG lifter and interpreter fallback.
 * vrefp uses a bounded numerical estimate, not hardware-bit-exact.
 */
#include <stdint.h>
#include <stddef.h>
#include "ppu_bridge.h"
#include "ppu_vmx_cell.h"
extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);
int ar_m753_native_003b062c(ppu_context *c){
 if(!c)return AR_BAD_ARGS;
 int rc=ar_vmx_vrefp(c,5u,3u);
 if(rc!=AR_OK){c->cia=UINT32_C(0x003b062c);return rc;}
 rc=ar_vmx_vmaddfp(c,3u,5u,31u,3u,1);
 if(rc!=AR_OK){c->cia=UINT32_C(0x003b0630);return rc;}
 rc=ar_vmx_vmaddfp(c,3u,3u,5u,5u,0);
 if(rc!=AR_OK){c->cia=UINT32_C(0x003b0634);return rc;}
 rc=ar_vmx_vmaddfp(c,3u,3u,30u,4u,0);
 if(rc!=AR_OK){c->cia=UINT32_C(0x003b0638);return rc;}
 c->cia=UINT32_C(0x003b063c);
 return AR_TAIL;
}
int ar_m753_register_vectorfp(const uint8_t *elf,size_t len){
 if(!elf||len<64u)return AR_BAD_ARGS;
 static const uint32_t expected[4]={
  UINT32_C(0x10a0190a),UINT32_C(0x1065f8ef),
  UINT32_C(0x1063296e),UINT32_C(0x1063f12e)
 };
 uint32_t window[6]={0};
 const uint32_t pc=UINT32_C(0x003b062c);
 if(ar_m712_exec_window(elf,len,pc,window)!=AR_OK||
    window[4]!=4u||!(window[5]&1u))return AR_BAD_ARGS;
 uint64_t hash=UINT64_C(14695981039346656037);
 for(unsigned i=0;i<4u;i++){
  if(window[i]!=expected[i]||ar_read32(pc+i*4u)!=expected[i]||
     ar_last_error()!=AR_OK)return AR_BAD_ARGS;
  for(unsigned k=0;k<4u;k++){
   hash^=(uint8_t)(expected[i]>>(24u-8u*k));
   hash*=UINT64_C(1099511628211);
  }
 }
 if(hash!=UINT64_C(0x3c537b4133a8bd88))return AR_BAD_ARGS;
 return ar_register(pc,ar_m753_native_003b062c);
}
