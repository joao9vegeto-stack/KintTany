/* Read-only comparison of original PT_LOAD/X bytes and live guest RAM.
 * Sample after ar_run but BEFORE ar_bridge_shutdown. Never use fallback
 * counters as opcode evidence. No ELF/game content retained globally.
 */
#ifndef AR_M756_STOP_EVIDENCE_H
#define AR_M756_STOP_EVIDENCE_H
#include <stddef.h>
#include <stdint.h>
enum { AR_M756_SAMPLE_BYTES=28u };
typedef struct {
 uint32_t pc;
 int32_t elf_status,guest_status;
 uint32_t segment_flags;
 uint64_t segment_va,segment_file_offset,segment_file_size;
 uint64_t file_offset;
 uint32_t count,match;
 uint32_t elf_word,guest_word;
 uint8_t elf_bytes[AR_M756_SAMPLE_BYTES];
 uint8_t guest_bytes[AR_M756_SAMPLE_BYTES];
} ar_m756_stop_evidence;
void ar_m756_capture_stop(const uint8_t*,size_t,uint32_t,ar_m756_stop_evidence*);
#endif
