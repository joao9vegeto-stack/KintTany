/* FAIRY2_KTGL_TRANSACTION_TRACE_ONLY
 * This logs ONE already-failing guest G1T result and accurately emulates the
 * original ARM64 B.EQ: test condition PSTATE.Z. There is NO override of the
 * parser result, no invented bytes, no retries and no changed resource stream.
 */
#include <unistd.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <mach/mach.h>
static unsigned f2_g1t_failure_trace_seq;
static int f2_g1t_validator_branch(ucontext_t *uc) {
    uint64_t pc=uc->uc_mcontext->__ss.__pc;
    module_t *mod=module_of((void *)(uintptr_t)pc);
    if (!mod || strcmp(mod->name,"main")) return 0;
    if (pc-(uint64_t)(uintptr_t)mod->base!=0x612120u) return 0;
    if (*(volatile uint32_t *)(uintptr_t)pc!=0xd43e4040u) return 0;
    unsigned z=(uc->uc_mcontext->__ss.__cpsr>>30)&1u;
    unsigned seq=__atomic_add_fetch(&f2_g1t_failure_trace_seq,1,__ATOMIC_RELAXED);
    if (z && seq<=64) {
        /* x23 = original reader argument to main+0x60db9c, x20 = target,
         * and [sp+0x50] = parsed header metadata before B.EQ, read-only. */
        uint64_t rp=uc->uc_mcontext->__ss.__x[23];
        uint64_t sp=uc->uc_mcontext->__ss.__sp;
        uint64_t raw[8]={0},local[8]={0};
        vm_size_t n=0;
        kern_return_t r=rp?vm_read_overwrite(mach_task_self(),
           (vm_address_t)rp,sizeof raw,(vm_address_t)raw,&n):KERN_INVALID_ADDRESS;
        int reader_valid=(r==KERN_SUCCESS && n==sizeof raw);
        n=0;
        r=vm_read_overwrite(mach_task_self(),(vm_address_t)(sp+0x50),
                           sizeof local,(vm_address_t)local,&n);
        int local_valid=(r==KERN_SUCCESS && n==sizeof local);
        char b[730];
        int len=snprintf(b,sizeof b,
          "[dm] FAIRY2_G1T_VALIDATOR_REAL_FAIL seq=%u w0=%#llx reader=%#llx target=%#llx reader_ok=%d raw=%016llx,%016llx,%016llx,%016llx local_ok=%d meta=%016llx,%016llx,%016llx,%016llx PSTATE.Z=%u\n",
          seq,(unsigned long long)uc->uc_mcontext->__ss.__x[0],
          (unsigned long long)rp,
          (unsigned long long)uc->uc_mcontext->__ss.__x[20],
          reader_valid,
          (unsigned long long)raw[0],(unsigned long long)raw[1],
          (unsigned long long)raw[2],(unsigned long long)raw[3],
          local_valid,
          (unsigned long long)local[0],(unsigned long long)local[1],
          (unsigned long long)local[2],(unsigned long long)local[3],z);
        if (len>0 && (size_t)len<sizeof b) (void)write(2,b,(size_t)len);
    }
    /* Exact original semantics: B.EQ main+0x6121d4; else fall through.
     * AArch64 cond branch B.EQ observes PSTATE.Z, does not modify flags. */
    uc->uc_mcontext->__ss.__pc =
      (uint64_t)(uintptr_t)mod->base + (z?0x6121d4u:0x612124u);
    return 1;
}
