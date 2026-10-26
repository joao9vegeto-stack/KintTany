#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

/* Returns 0 on success and writes a human-readable result to output. */
int xowue_inspect_xex(const char *path, char *output, size_t output_capacity);
int xowue_boot_xex(const char *path, char *output, size_t output_capacity);
/* Request cooperative cancellation of all guest PPC threads and the Xenos pump. */
void xowue_request_stop(void);
/* Monotonic Xbox guest timebase at 50 MHz, shared with recompiled mftb. */
uint64_t xowue_guest_timebase(void);
/* Writes the guest big-endian LARGE_INTEGER for QueryPerformanceCounter. */
uint64_t xowue_qpc_write(uint32_t out_ptr, uint64_t tb64, uint32_t caller_lr);
/* Emits all guest-thread PCs/LRs/wait states into the normal runtime diagnostic. */
void xowue_log_stall_threads(void);
int xowue_runtime_snapshot(char *output, size_t output_capacity);
int xowue_set_runtime_trace_path(const char *path);
void xowue_set_touch_controller_state(uint32_t buttons, uint8_t left_trigger,
                                      uint8_t right_trigger, int16_t left_x,
                                      int16_t left_y, int16_t right_x,
                                      int16_t right_y);

#ifdef __cplusplus
}
#endif
