/* PS3 LV2 352 sys_memory_get_user_memory_size, big-endian guest struct. */
#include "lv2_smoke.h"
int ar_lv2_memory_get_user_size(ppu_context*c) {
 if(!c||c->gpr[3]>UINT32_MAX)return AR_BAD_ARGS;
 uint64_t dst=c->gpr[3];
 ar_write32(dst,0x10000000u); /* 256 MiB PS3 user memory */
 ar_write32(dst+4,0x0c000000u); /* 192 MiB free at initial guest boot */
 if(ar_last_error()==AR_MEM_FAULT)return AR_MEM_FAULT;
 c->gpr[3]=0;
 return AR_OK;
}
