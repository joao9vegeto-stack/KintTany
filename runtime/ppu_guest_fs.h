/* M7.51 native PS3 guest filesystem bridge. No game payload stored. */
#ifndef AR_GUEST_FS_H
#define AR_GUEST_FS_H
#include <stdint.h>
#include <stddef.h>
#include "ppu_bridge.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Host returns 0 only when a relative, manifest-authorized regular file
 * exists and the requested read (if any) succeeds. Never returns a path.
 * count==0 is a stat/open authorization check; no bytes are copied. */
typedef int (*ar_fs_host_io)(const char *relative,uint64_t offset,
                             void *dst,size_t count,size_t *actual,
                             uint64_t *file_size);
typedef struct {
 uint32_t open_calls,open_ok,read_calls,read_ok,close_calls;
 uint32_t last_fd,last_error;
 uint64_t bytes_read;
 char last_path[256];
} ar_fs_trace;
void ar_fs_reset(void);
void ar_fs_set_host_io(ar_fs_host_io fn);
int ar_fs_bind_syscalls(void);
int ar_fs_guest_open(ppu_context*);
int ar_fs_guest_read(ppu_context*);
int ar_fs_guest_close(ppu_context*);
void ar_fs_snapshot(ar_fs_trace*);
#ifdef __cplusplus
}
#endif
#endif
