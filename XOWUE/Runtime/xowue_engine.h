#pragma once
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif

/* Returns 0 on success and writes a human-readable result to output. */
int xowue_inspect_xex(const char *path, char *output, size_t output_capacity);
int xowue_boot_xex(const char *path, char *output, size_t output_capacity);

#ifdef __cplusplus
}
#endif
