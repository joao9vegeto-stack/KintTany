/* FAIRY2_KTGL_MODE4_NATIVE_FALLBACK
 * iOS Fairy Tail 2 v458752 only. Invoked by a synchronous guest BRK at the
 * original mode-4 inflater on its *failure* path. The normal guest inflater
 * succeeds uninterrupted; we never insert canned G1T/G1S or bypass parsers.
 *
 * This code is embedded into the existing NXNative crash.c for the Fairy2iOS
 * framework ONLY. No heap allocation, dlopen, or dlsym occurs in the SIGTRAP
 * handler: libz entry points are resolved before gameplay in a constructor.
 * zlib internal allocation uses a bounded TLS bump arena.
 */
#include <dlfcn.h>
#include <zlib.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include <stdio.h>

enum { F2_ZLIB_POOL = 131072, F2_ZLIB_MAX_OUT = 16384 };
static int (*f2_inflate_init)(z_streamp, int, const char *, int);
static int (*f2_inflate_run)(z_streamp, int);
static int (*f2_inflate_end)(z_streamp);
static __thread struct {
  unsigned valid;
  uint64_t sp, dst, capacity, written, compressed, compressed_n;
  unsigned used;
  unsigned char pool[F2_ZLIB_POOL];
  unsigned char output[F2_ZLIB_MAX_OUT];
} f2_zlib_tls;
static unsigned f2_codec_ok, f2_codec_rejected;

__attribute__((constructor)) static void f2_native_zlib_init(void) {
  void *h = dlopen("/usr/lib/libz.1.dylib", RTLD_NOW | RTLD_LOCAL);
  if (!h) return;
  /* POSIX dlsym: use memcpy to transfer function pointers, preserving C type. */
  void *sym = dlsym(h, "inflateInit2_");
  memcpy(&f2_inflate_init, &sym, sizeof f2_inflate_init);
  sym = dlsym(h, "inflate");
  memcpy(&f2_inflate_run, &sym, sizeof f2_inflate_run);
  sym = dlsym(h, "inflateEnd");
  memcpy(&f2_inflate_end, &sym, sizeof f2_inflate_end);
}

static voidpf f2_zalloc(voidpf opaque, uInt n, uInt size) {
  (void)opaque;
  size_t bytes = (size_t)n * size;
  if (n && bytes / n != size) return NULL;
  size_t at = ((size_t)f2_zlib_tls.used + 15u) & ~(size_t)15u;
  if (bytes > F2_ZLIB_POOL || at > F2_ZLIB_POOL - bytes) return NULL;
  f2_zlib_tls.used = (unsigned)(at + bytes);
  memset(f2_zlib_tls.pool + at, 0, bytes);
  return f2_zlib_tls.pool + at;
}
static void f2_zfree(voidpf opaque, voidpf addr) {
  (void)opaque; (void)addr;
}
static int f2_is_zlib_header(const unsigned char *p) {
  /* DEFLATE CMF compression method 8; CINFO <= 7, FCHECK mod31. */
  unsigned cmf=p[0], flg=p[1];
  return (cmf & 15u) == 8u && (cmf >> 4) <= 7u &&
         (((cmf << 8) | flg) % 31u) == 0u && !(flg & 0x20u);
}

/* Reproduce original mode-4 inflater ABI on failure only:
 * x0=output guest buffer, x1=maximum decompressed bytes, x2=u64 *written,
 * x3=8-byte KTGL integrity prefix followed by zlib CMF/FLG stream,
 * x4=stored byte count including prefix.
 * The intact guest inflater is the primary validator; the native fallback
 * requires a complete zlib stream with a valid Adler32 and no trailing bytes.
 */
static int f2_zlib_original_chunk(unsigned char *dst, size_t capacity,
                                  uint64_t *written,
                                  const unsigned char *source, size_t stored) {
  if (!f2_inflate_init || !f2_inflate_run || !f2_inflate_end ||
      !dst || !source || !written || stored < 10 || stored > 65535 ||
      capacity == 0 || capacity > F2_ZLIB_MAX_OUT ||
      !f2_is_zlib_header(source + 8)) return 0;
  z_stream stream;
  memset(&stream, 0, sizeof stream);
  f2_zlib_tls.used = 0;
  stream.zalloc = f2_zalloc;
  stream.zfree = f2_zfree;
  stream.next_in = (Bytef *)(uintptr_t)(source + 8);
  stream.avail_in = (uInt)(stored - 8);
  stream.next_out = f2_zlib_tls.output;
  stream.avail_out = (uInt)capacity;
  int init = f2_inflate_init(&stream, 15, ZLIB_VERSION, (int)sizeof stream);
  if (init != Z_OK) return 0;
  int status = f2_inflate_run(&stream, Z_FINISH);
  size_t n = (size_t)stream.total_out;
  int valid = status == Z_STREAM_END && n > 0 && n <= capacity &&
              stream.avail_in == 0 && (size_t)stream.total_in == stored - 8;
  (void)f2_inflate_end(&stream);
  if (!valid) return 0;
  memcpy(dst, f2_zlib_tls.output, n);
  *written = n;
  return 1;
}

static int f2_zlib_fail_path_trap(ucontext_t *uc) {
  uint64_t pc = uc->uc_mcontext->__ss.__pc;
  module_t *module = module_of((void *)(uintptr_t)pc);
  if (!module || strcmp(module->name, "main")) return 0;
  uint64_t off = pc - (uint64_t)(uintptr_t)module->base;
  if (off != 0xc0ef8cULL && off != 0xc0f0d4ULL) return 0;
  /* A synchronous trap must originate in one of our TWO pinned AArch64
   * original-code sites, not from any other host/guest exception. */
  if (*(volatile uint32_t *)(uintptr_t)pc != 0xd43e4040u) return 0;

  if (off == 0xc0ef8cULL) {
    /* Original instruction: add x9, sp, #0x78. Save args before the
     * guest mutates x0-x4 in its actual inflater body. */
    f2_zlib_tls.valid = 1;
    f2_zlib_tls.sp = uc->uc_mcontext->__ss.__sp;
    f2_zlib_tls.dst = uc->uc_mcontext->__ss.__x[0];
    f2_zlib_tls.capacity = uc->uc_mcontext->__ss.__x[1];
    f2_zlib_tls.written = uc->uc_mcontext->__ss.__x[2];
    f2_zlib_tls.compressed = uc->uc_mcontext->__ss.__x[3];
    f2_zlib_tls.compressed_n = uc->uc_mcontext->__ss.__x[4];
    uc->uc_mcontext->__ss.__x[9] = f2_zlib_tls.sp + 0x78;
    uc->uc_mcontext->__ss.__pc = pc + 4;
    return 1;
  }

  /* c0f0d4 normally executes "mov w0, wzr" after failed guest inflate,
   * then runs the ORIGINAL epilogue at c0f0d8. Attempt libz on original
   * bytes, not the RDB hash, only for the same stack frame. */
  int ok = 0;
  if (f2_zlib_tls.valid && f2_zlib_tls.sp == uc->uc_mcontext->__ss.__sp) {
    uint64_t len = f2_zlib_tls.capacity;
    if (len > F2_ZLIB_MAX_OUT) len = F2_ZLIB_MAX_OUT;
    ok = f2_zlib_original_chunk(
        (unsigned char *)(uintptr_t)f2_zlib_tls.dst, (size_t)len,
        (uint64_t *)(uintptr_t)f2_zlib_tls.written,
        (const unsigned char *)(uintptr_t)f2_zlib_tls.compressed,
        (size_t)f2_zlib_tls.compressed_n);
  }
  f2_zlib_tls.valid = 0;
  uc->uc_mcontext->__ss.__x[0] = ok ? 1 : 0;
  uc->uc_mcontext->__ss.__pc = pc + 4;
  if (ok) {
    __atomic_fetch_add(&f2_codec_ok, 1, __ATOMIC_RELAXED);
    const char msg[] = "[dm] FAIRY2_MODE4_ORIGINAL_ZLIB_RECOVERED verified DEFLATE+Adler32, native parser next\n";
    (void)write(2, msg, sizeof msg - 1);
  } else __atomic_fetch_add(&f2_codec_rejected, 1, __ATOMIC_RELAXED);
  return 1;
}
