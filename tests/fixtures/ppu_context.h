/* Synthetic-only mirror; CI checks layout against pinned upstream header. */
#ifndef PPU_CONTEXT_H
#define PPU_CONTEXT_H
#include <stdint.h>
typedef union { uint64_t _u64[2]; uint64_t d[2]; uint32_t _u32[4]; uint8_t _u8[16]; } ar_vec128 __attribute__((aligned(16)));
typedef struct ppu_context {
  uint64_t gpr[32]; double fpr[32];
  ar_vec128 vr[32] __attribute__((aligned(16)));
  uint32_t cr; uint64_t lr,ctr; uint32_t xer,fpscr,vscr;
  uint64_t cia,thread_id,reserve_addr,reserve_value; int reserve_valid;
} ppu_context;
#endif
