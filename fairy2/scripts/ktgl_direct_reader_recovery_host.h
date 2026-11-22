/* FAIRY2_KTGL_DIRECT_MODE4_SOURCE_RECOVERY
 * Reconstruct one failed original 2-byte-header KTGL mode4 block from its
 * actual backing RDB/FDATA bytes. This operates *below* the G1T/G1S parser
 * and is needed when the original reader returns 0 before entering inflate.
 *
 * Restricted to the v458752 mode4 direct-reader vtable whose +0x38 parser is
 * c121a8 (u16 compressed count + 8), with a valid first-block source and
 * a complete RFC1950/Adler32 stream. It changes no data on failure.
 */
#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include <stdio.h>

struct f2_direct_snapshot {
    uint64_t sp, reader, destination, destination_off, requested;
    uint64_t raw, compressed_pos, compressed_end, decoded_pos, decoded_end;
};
static __thread struct {
    unsigned size;
    struct f2_direct_snapshot frames[16];
} f2_direct_tls;
static unsigned f2_direct_recover_ok, f2_direct_recover_refused;

static int f2_direct_recover_original_block(const struct f2_direct_snapshot *s) {
    if (!s || !s->reader || !s->destination || !s->raw ||
        !s->requested || s->requested > F2_ZLIB_MAX_OUT ||
        s->destination_off > 0x10000000u ||
        s->compressed_pos > s->compressed_end ||
        s->decoded_pos != s->decoded_end ||
        s->decoded_pos != 0 ||
        s->compressed_end - s->compressed_pos < 10 ||
        s->compressed_end - s->compressed_pos > 0x1000000u)
        return 0;

    const unsigned char *source = (const unsigned char *)(uintptr_t)s->raw;
    uint64_t avail = s->compressed_end - s->compressed_pos;
    uint64_t pos = s->compressed_pos;
    const unsigned char *head = source + pos;
    uint16_t compressed_payload;
    memcpy(&compressed_payload, head, sizeof compressed_payload);
    if (!compressed_payload || compressed_payload > 0xfff0u)
        return 0;
    uint64_t packet_bytes = (uint64_t)compressed_payload + 8u;
    if (packet_bytes > avail - 2u) return 0;
    uint64_t unpacked = 0;
    /* Entire output is retained in the guest's OWN 16KiB decoded cache,
     * so the very next original reader call handles its remaining bytes. */
    unsigned char *cache = (unsigned char *)(uintptr_t)(s->reader + 0x30);
    if (!f2_zlib_original_chunk(cache, F2_ZLIB_MAX_OUT, &unpacked,
                                head + 2, (size_t)packet_bytes))
        return 0;
    if (unpacked < s->requested) return 0;

    unsigned char *dest = (unsigned char *)(uintptr_t)
                          (s->destination + s->destination_off);
    memcpy(dest, cache, (size_t)s->requested);
    uint64_t after = pos + 2 + packet_bytes;
    uint64_t decoded_cursor = s->requested;
    /* Commit only on FULLY validated original-byte decompress. Preserve
     * every unrelated field of the original reader object. */
    memcpy((void *)(uintptr_t)(s->reader + 0x8), &s->raw, 8);
    memcpy((void *)(uintptr_t)(s->reader + 0x10), &after, 8);
    memcpy((void *)(uintptr_t)(s->reader + 0x18), &s->compressed_end, 8);
    memcpy((void *)(uintptr_t)(s->reader + 0x20), &decoded_cursor, 8);
    memcpy((void *)(uintptr_t)(s->reader + 0x28), &unpacked, 8);
    return 1;
}

static void f2_direct_reader_snapshot(const struct f2_direct_snapshot *s) {
    if (f2_direct_tls.size < 16)
        f2_direct_tls.frames[f2_direct_tls.size++] = *s;
}
static int f2_direct_reader_pop(uint64_t sp, struct f2_direct_snapshot *result) {
    for (unsigned i=f2_direct_tls.size; i>0; --i) {
        if (f2_direct_tls.frames[i-1].sp != sp) continue;
        *result = f2_direct_tls.frames[i-1];
        memmove(&f2_direct_tls.frames[i-1], &f2_direct_tls.frames[i],
                (f2_direct_tls.size-i)*sizeof f2_direct_tls.frames[0]);
        --f2_direct_tls.size;
        return 1;
    }
    return 0;
}

/* DARWIN_SIGNAL_ONLY (excluded from Linux pure C-data regression builds) */
static int f2_direct_reader_trap(ucontext_t *uc) {
    uint64_t pc = uc->uc_mcontext->__ss.__pc;
    module_t *module = module_of((void *)(uintptr_t)pc);
    if (!module || strcmp(module->name, "main")) return 0;
    uint64_t off = pc - (uint64_t)(uintptr_t)module->base;
    if (off != 0xc11b80u && off != 0xc11f9cu) return 0;
    if (*(volatile uint32_t *)(uintptr_t)pc != 0xd43e4040u) return 0;

    if (off == 0xc11b80u) {
        uint64_t reader=uc->uc_mcontext->__ss.__x[0];
        if (!reader) return 0; /* Original NULL dereference must not be swallowed. */
        if (reader) {
            uint64_t vt=0;
            memcpy(&vt,(void *)(uintptr_t)reader,8);
            if (vt == (uint64_t)(uintptr_t)module->base + 0x2a64b50u) {
                struct f2_direct_snapshot snapshot={0};
                snapshot.sp=uc->uc_mcontext->__ss.__sp;
                snapshot.reader=reader;
                snapshot.destination=uc->uc_mcontext->__ss.__x[1];
                snapshot.destination_off=uc->uc_mcontext->__ss.__x[2];
                snapshot.requested=uc->uc_mcontext->__ss.__x[3];
                memcpy(&snapshot.raw,(void *)(uintptr_t)(reader+0x8),8);
                memcpy(&snapshot.compressed_pos,(void *)(uintptr_t)(reader+0x10),8);
                memcpy(&snapshot.compressed_end,(void *)(uintptr_t)(reader+0x18),8);
                memcpy(&snapshot.decoded_pos,(void *)(uintptr_t)(reader+0x20),8);
                memcpy(&snapshot.decoded_end,(void *)(uintptr_t)(reader+0x28),8);
                f2_direct_reader_snapshot(&snapshot);
            }
            /* Emulate ORIGINAL ldp x8,x9,[x0,#8] even on non-mode4 readers;
             * they must retain the original semantics, no forced data. */
            memcpy(&uc->uc_mcontext->__ss.__x[8],
                   (void *)(uintptr_t)(reader+0x8),8);
            memcpy(&uc->uc_mcontext->__ss.__x[9],
                   (void *)(uintptr_t)(reader+0x10),8);
        }
        uc->uc_mcontext->__ss.__pc=pc+4;
        return 1;
    }

    /* ORIGINAL mov x0,x19. A failed block read that never reached the
     * inflater is the only input to this native original-source recovery. */
    uint64_t original=uc->uc_mcontext->__ss.__x[19];
    struct f2_direct_snapshot snapshot={0};
    if (f2_direct_reader_pop(uc->uc_mcontext->__ss.__sp,&snapshot) &&
        original==0 && f2_direct_recover_original_block(&snapshot)) {
        uc->uc_mcontext->__ss.__x[0]=snapshot.requested;
        __atomic_fetch_add(&f2_direct_recover_ok,1,__ATOMIC_RELAXED);
        char msg[200];
        int n=snprintf(msg,sizeof msg,
           "[dm] FAIRY2_KTGL_ORIGINAL_DIRECT_READ_RECOVERED original mode4 bytes=%llu, retained guest reader cursor\n",
           (unsigned long long)snapshot.requested);
        if (n>0 && (size_t)n<sizeof msg) (void)write(2,msg,(size_t)n);
    } else {
        uc->uc_mcontext->__ss.__x[0]=original;
        if (original==0)
            __atomic_fetch_add(&f2_direct_recover_refused,1,__ATOMIC_RELAXED);
    }
    uc->uc_mcontext->__ss.__pc=pc+4;
    return 1;
}
