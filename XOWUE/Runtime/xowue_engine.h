#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

/* Returns 0 on success and writes a human-readable result to output. */
int xowue_inspect_xex(const char *path, char *output, size_t output_capacity);
int xowue_boot_xex(const char *path, char *output, size_t output_capacity);
int xowue_runtime_snapshot(char *output, size_t output_capacity);
void xowue_set_touch_controller_state(uint32_t buttons, uint8_t left_trigger,
                                      uint8_t right_trigger, int16_t left_x,
                                      int16_t left_y, int16_t right_x,
                                      int16_t right_y);

#ifdef __cplusplus
}
#endif
