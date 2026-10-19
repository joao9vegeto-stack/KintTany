/* M7.67 private ELF+PRX import evidence. Does not decode PPC instructions. */
#ifndef AR_M767_LIVE_IMPORT_H
#define AR_M767_LIVE_IMPORT_H
#include <stdint.h>
typedef struct {
 int32_t forward_status,reverse_status,bind_status,hle_status;
 uint32_t matched,stub,nid,slot_va;
 int32_t slot_pre_status,slot_post_status;
 uint32_t slot_pre_be,slot_post_be;
 char module[48];
} ar_m767_import_evidence;
void ar_m767_last_import_evidence(ar_m767_import_evidence *out);
#endif
