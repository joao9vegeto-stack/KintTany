#include "ppu_native_sysutil.h"
#include <stdint.h>
enum {SYSEINVAL=0x8002b003u,SYSUNKNOWN=0x80012002u};
static struct {uint32_t opd,userdata;} callbacks[4];
static unsigned mask,active;
void ar_sysutil_reset(void){mask=active=0;for(unsigned i=0;i<4;i++){callbacks[i].opd=0;callbacks[i].userdata=0;}}
uint32_t ar_sysutil_core_mask(void){return mask;}
uint32_t ar_sysutil_is_native_ready(void){return active;}
int ar_sysutil_register_callback(ppu_context*c){
 if(!c||!active)return AR_HLE_FAILURE;
 uint64_t slot=c->gpr[3];if(slot>=4||c->gpr[4]>UINT32_MAX||c->gpr[5]>UINT32_MAX){c->gpr[3]=SYSEINVAL;return AR_OK;}
 callbacks[slot].opd=(uint32_t)c->gpr[4];callbacks[slot].userdata=(uint32_t)c->gpr[5];c->gpr[3]=0;return AR_OK;
}
int ar_sysutil_unregister_callback(ppu_context*c){
 if(!c||!active)return AR_HLE_FAILURE;
 if(c->gpr[3]>=4){c->gpr[3]=SYSEINVAL;return AR_OK;}
 callbacks[c->gpr[3]].opd=0;callbacks[c->gpr[3]].userdata=0;c->gpr[3]=0;return AR_OK;
}
int ar_sysutil_check_callback(ppu_context*c){
 if(!c||!active)return AR_HLE_FAILURE;
 c->gpr[3]=0;return AR_OK;
}
int ar_sysutil_get_system_param_int(ppu_context*c){
 if(!c||!active)return AR_HLE_FAILURE;
 uint64_t v=c->gpr[3],out=c->gpr[4];
 if(!out||(out&3u)||out>UINT32_MAX-3u)return AR_BAD_ARGS;
 if(v!=0x111 && v!=0x112 && v!=0x113 && v!=0x114){c->gpr[3]=SYSEINVAL;return AR_OK;}
 (void)ar_read8(out+3);if(ar_last_error())return AR_MEM_FAULT;
 ar_write32(out,v==0x111?1u:0u);if(ar_last_error())return AR_MEM_FAULT;
 c->gpr[3]=0;return AR_OK;
}
int ar_sysutil_bind_core(uint32_t nid,uint32_t stub){
 static const uint32_t nids[4]={0x189a74da,0x9d98afa0,0x02ff3c1b,0x40e895d3};
 static const ar_hle_fn impl[4]={ar_sysutil_check_callback,ar_sysutil_register_callback,ar_sysutil_unregister_callback,ar_sysutil_get_system_param_int};
 for(unsigned i=0;i<4;i++)if(nids[i]==nid){
  if(mask&(1u<<i))return AR_DUPLICATE;
  int rc=ar_bind_import(stub,nid);if(rc)return rc;
  rc=ar_bind_hle(nid,impl[i]);if(rc)return rc;
  mask|=1u<<i;return AR_OK;
 }
 return AR_MISSING_HLE;
}
int ar_sysutil_load_module(ppu_context*c){
 if(!c)return AR_BAD_ARGS;
 if(c->gpr[3]!=0x15u){c->gpr[3]=SYSUNKNOWN;return AR_OK;}
 if(mask!=15u)return AR_MISSING_HLE;
 if(active){c->gpr[3]=0x80012001u;return AR_OK;}
 active=1;c->gpr[3]=0;return AR_OK;
}
