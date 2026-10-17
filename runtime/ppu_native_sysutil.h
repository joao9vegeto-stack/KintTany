#ifndef AR_NATIVE_SYSUTIL_H
#define AR_NATIVE_SYSUTIL_H
#include "ppu_bridge.h"
#include <stdint.h>
void ar_sysutil_reset(void);
int ar_sysutil_bind_core(uint32_t nid,uint32_t stub);
int ar_sysutil_load_module(ppu_context*);
int ar_sysutil_register_callback(ppu_context*);
int ar_sysutil_unregister_callback(ppu_context*);
int ar_sysutil_check_callback(ppu_context*);
int ar_sysutil_get_system_param_int(ppu_context*);
uint32_t ar_sysutil_core_mask(void);
uint32_t ar_sysutil_is_native_ready(void);
#endif
