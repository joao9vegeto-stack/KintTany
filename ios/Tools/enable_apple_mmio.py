#!/usr/bin/env python3
"""Port existing x86 MMIO fault instruction decoder from Linux AArch64 ucontext
 to Darwin AArch64 ucontext without substituting any MMIO register results.
 Treat unknown instructions as faults and abort the run, not as completed ops.
"""
import sys
from pathlib import Path

def repl(t,a,b,file):
 n=t.count(a)
 if n!=1: raise RuntimeError(f'{file}: {n} matching anchors: {a[:100]}')
 return t.replace(a,b,1)

def main(root):
 f=root/'port/third_party/xboxrecomp/src/platform/mmio_decode.h'
 s=f.read_text()
 s=repl(s,'#elif defined(__aarch64__) && defined(__linux__)',
        '#elif defined(__aarch64__) && (defined(__linux__) || defined(__APPLE__))',f)
 s=repl(s,'#include <ucontext.h>\n\ntypedef uint64_t (*mmio_read_fn)', '''#if defined(__APPLE__)
#include <sys/ucontext.h>
#else
#include <ucontext.h>
#endif
#if defined(__APPLE__)
/* The original portable instruction decoder uses a Linux-style CPU state.
 * Snapshot real Darwin registers, let it interpret the guest MMIO instruction,
 * then restore results into Darwin ucontext only when decoding succeeded. */
typedef struct {
 struct { uint64_t regs[31],sp,pc,fault_address;
          unsigned char __reserved[1024]; } uc_mcontext;
} PoPTSTUContext;
#define ucontext_t PoPTSTUContext
#define mmio_emulate poptst_mmio_emulate_inner
#endif

typedef uint64_t (*mmio_read_fn)''',f)
 wrapper='''#if defined(__APPLE__)
#undef mmio_emulate
#undef ucontext_t
static inline int mmio_emulate(void *context, uint32_t off, void *dev,
                               mmio_read_fn rd, mmio_write_fn wr)
{
    ucontext_t *actual=(ucontext_t *)context;
    if (!actual || !actual->uc_mcontext) return 0;
    PoPTSTUContext cpu={0};
    for (unsigned i=0;i<29;i++) cpu.uc_mcontext.regs[i]=actual->uc_mcontext->__ss.__x[i];
    cpu.uc_mcontext.regs[29]=actual->uc_mcontext->__ss.__fp;
    cpu.uc_mcontext.regs[30]=actual->uc_mcontext->__ss.__lr;
    cpu.uc_mcontext.sp=actual->uc_mcontext->__ss.__sp;
    cpu.uc_mcontext.pc=actual->uc_mcontext->__ss.__pc;
    cpu.uc_mcontext.fault_address=actual->uc_mcontext->__es.__far;
    uint32_t magic=0x46508001u, record_size=528, fpsr=actual->uc_mcontext->__ns.__fpsr,
             fpcr=actual->uc_mcontext->__ns.__fpcr;
    memcpy(cpu.uc_mcontext.__reserved,&magic,4);
    memcpy(cpu.uc_mcontext.__reserved+4,&record_size,4);
    memcpy(cpu.uc_mcontext.__reserved+8,&fpsr,4);
    memcpy(cpu.uc_mcontext.__reserved+12,&fpcr,4);
    memcpy(cpu.uc_mcontext.__reserved+16,actual->uc_mcontext->__ns.__v,32u*16u);
    if (!poptst_mmio_emulate_inner(&cpu,off,dev,rd,wr)) return 0;
    for (unsigned i=0;i<29;i++) actual->uc_mcontext->__ss.__x[i]=cpu.uc_mcontext.regs[i];
    actual->uc_mcontext->__ss.__fp=cpu.uc_mcontext.regs[29];
    actual->uc_mcontext->__ss.__lr=cpu.uc_mcontext.regs[30];
    actual->uc_mcontext->__ss.__sp=cpu.uc_mcontext.sp;
    actual->uc_mcontext->__ss.__pc=cpu.uc_mcontext.pc;
    memcpy(actual->uc_mcontext->__ns.__v,cpu.uc_mcontext.__reserved+16,32u*16u);
    return 1;
}
#endif /* Apple ARM64 context adapter */

'''
 s=repl(s,'#endif /* _WIN32 / arm64 Linux */',wrapper+'#endif /* _WIN32 / arm64 Linux, iOS */',f)
 f.write_text(s)
 paths={
   'port/third_party/xboxrecomp/src/kernel/xbox_memory_layout.c':[
     ('#if defined(__ANDROID__)\n    /* RE-SoT: no vectored handlers or trap flag on Android.',
      '#if defined(__ANDROID__) || defined(__APPLE__)\n    /* Mobile POSIX faults are decoded by platform signal handler.'),
     ('#if defined(__ANDROID__) && defined(__aarch64__)',
      '#if (defined(__ANDROID__) || defined(__APPLE__)) && defined(__aarch64__)')],
   'port/third_party/xboxrecomp/src/apu/apu_mmio_hook.c':[
     ('#if defined(__ANDROID__) && defined(__aarch64__)',
      '#if (defined(__ANDROID__) || defined(__APPLE__)) && defined(__aarch64__)'),
     ('((ucontext_t *)ctx)->uc_mcontext.pc',
      '((' + 'ucontext_t *' + ')ctx)->uc_mcontext' + ('->__ss.__pc' ))],
   'port/third_party/xboxrecomp/src/usb/ohci.c':[
     ('#if defined(_WIN32) || defined(__ANDROID__)   /* RE-SoT: Android traps too */',
      '#if defined(_WIN32) || defined(__ANDROID__) || defined(__APPLE__)   /* PoPTST: Darwin traps too */'),
     ('#if defined(_WIN32) || defined(__ANDROID__)   /* RE-SoT */',
      '#if defined(_WIN32) || defined(__ANDROID__) || defined(__APPLE__)   /* RE-SoT */'),
     ('#elif defined(__ANDROID__)\n    /* RE-SoT: ctx is the SIGSEGV ucontext',
      '#elif defined(__ANDROID__) || defined(__APPLE__)\n    /* RE-SoT: ctx is the SIGSEGV ucontext'),
     ('((ucontext_t *)ctx)->uc_mcontext.pc',
      '((ucontext_t *)ctx)->uc_mcontext' + '->__ss.__pc')]
 }
 for path,pairs in paths.items():
    f=root/path
    s=f.read_text()
    for old,new in pairs:
      # Original Android Linux accesses must remain Linux on Android.
      if 'uc_mcontext.pc' in old:
        replacement='''#if defined(__APPLE__)
        memcpy(&insn,(const void *)(uintptr_t)((ucontext_t *)ctx)->uc_mcontext->__ss.__pc,4);
#else
        memcpy(&insn,(const void *)(uintptr_t)((ucontext_t *)ctx)->uc_mcontext.pc,4);
#endif'''
        # Replaces entire memcpy line below; use dedicated handling.
        source='memcpy(&insn, (const void *)(uintptr_t)((ucontext_t *)ctx)->uc_mcontext.pc, 4);'
        s=repl(s,source,replacement,f)
      else:s=repl(s,old,new,f)
    f.write_text(s)
 print('PoPTST Darwin AArch64 MMIO decoder and 3 fault users ported')

if __name__=='__main__':
 main(Path(sys.argv[1]).resolve())
