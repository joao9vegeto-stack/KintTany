#ifndef POPTST_RETAIL_BOOT_H
#define POPTST_RETAIL_BOOT_H
#ifdef __cplusplus
extern "C" {
#endif
/* A synchronous entry for a pthread owned by the SDL iOS host. It never
 * supplies substitutes for the Xbox runtime, AOT code or GPU. On failure it
 * returns nonzero and writes a diagnostic to why; on game return it returns 0.
 * Only the official NTSC retail XBE can reach the entry point. */
int poptst_boot_retail(const char *game_dir, const char *data_dir,
                       char *why, unsigned why_capacity);
#ifdef __cplusplus
}
#endif
#endif
