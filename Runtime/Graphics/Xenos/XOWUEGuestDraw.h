// XOWUE native Xenos PM4 draw packet ABI. GPL-3.0-or-later.
#pragma once
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#ifdef __cplusplus
extern "C" {
#endif
enum { XOWUE_GPU_CONSTANT_WORDS = 2296, XOWUE_GPU_MAX_DRAWS = 128 };
typedef struct XOWUEGuestDraw {
  uint64_t vertex_hash, pixel_hash;
  uint32_t initiator, index_count, index_address, index_info, index_offset;
  uint32_t pa_cl_vte_cntl;
  // Raw Xenos render-target state from the instant this draw was queued.
  uint32_t rb_modecontrol, rb_surface_info, rb_depthcontrol, rb_color_mask;
  uint32_t rb_color_info[4], rb_depth_info, rb_copy_control;
  uint32_t rb_blendcontrol[4];
  uint32_t pa_sc_window_scissor_tl, pa_sc_window_scissor_br;
  uint32_t viewport_register_bits[4];
  uint32_t vertex_fetch_mask, texture_2d_mask, texture_3d_mask, texture_cube_mask;
  uint32_t vertex_memexport, pixel_memexport, color_target_mask;
  uint32_t fetch_used[3];
  uint32_t fetch_strides[96], fetch_extents[96];
  uint32_t constants[XOWUE_GPU_CONSTANT_WORDS];
} XOWUEGuestDraw;
size_t xowue_xenos_take_draws(XOWUEGuestDraw *out, size_t capacity);
size_t xowue_xenos_linked_fragment_spirv_words(uint64_t vertex_hash,
  uint64_t pixel_hash, uint32_t *out, size_t capacity);
void xowue_xenos_record_submitted(uint32_t count);
void xowue_xenos_record_rejected(uint32_t count, const char *why);
bool xowue_xenos_copy_guest_physical(uint32_t address, void *out, size_t size);
// Guest-backed tiled/linear RGBA8 and R10G10B10A2 fetch, never synthesized.
bool xowue_xenos_copy_guest_texture2d(const uint32_t fetch[6], void *rgba, size_t bytes);
#ifdef __cplusplus
}
#endif
