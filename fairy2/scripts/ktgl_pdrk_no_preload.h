/* Fairy Tail 2 PDRK header compatibility, based on the iPhone-working
 * Romance of the Three Kingdoms 8 Remake archive format. The high word
 * of the 16-byte PDRK header is the optional preload extent in this title:
 * device traces read exactly that extent after the initial header read.
 * Advertise no preload, leaving every IDRK byte and file offset intact.
 * The game continues through its own ordinary record-by-record reader.
 * No G1T/G1S interception, no resource substitution, no size change.
 */
#ifndef FAIRY2_PDRK_NO_PRELOAD_H
#define FAIRY2_PDRK_NO_PRELOAD_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>

static uint32_t f2_pdrk_u32le(const unsigned char *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1]<<8) |
           ((uint32_t)p[2]<<16) | ((uint32_t)p[3]<<24);
}
static uint32_t f2_pdrk_preload_extent(const unsigned char head[16],
                                      uint64_t file_size) {
    if (file_size<16 || memcmp(head,"PDRK0000",8)!=0 ||
        f2_pdrk_u32le(head+8)!=16) return 0;
    uint32_t extent=f2_pdrk_u32le(head+12);
    if(extent<=16 || (uint64_t)extent>file_size) return 0;
    return extent;
}
/* Apply only bytes in [12,16) overlapping THIS returned read. A split
 * header read sees exactly the same virtual header as a full read.
 * Content outside the extension is never touched. */
static size_t f2_pdrk_hide_preload(const unsigned char head[16],
                                   uint64_t file_size, uint64_t off,
                                   void *buffer, size_t got) {
    if (!buffer || !got || off>=16 || got<=12-(off<12?off:12)
        || !f2_pdrk_preload_extent(head,file_size)) return 0;
    uint64_t begin=off>12?off:12;
    uint64_t n=(uint64_t)got-(begin-off);
    if(n>16-begin)n=16-begin;
    memset((unsigned char*)buffer+(size_t)(begin-off),0,(size_t)n);
    return (size_t)n;
}
#endif
