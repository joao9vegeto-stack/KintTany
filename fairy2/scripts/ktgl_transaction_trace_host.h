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

/* FAIRY2_G1T_ORIGINAL_DISPATCH_AUDIT: never fabricates asset bytes, changes a
 * parser result or replaces a backing reader. Equivalent to the original
 * ARM64 LDR x0,[x0,#0x10] at main+0xc09728, and resumes at +0xc0972c.
 * VM peeks and stdout are read-only; this is a diagnostic build ONLY. */
extern unsigned char fairy2_g1t_original_fdata_packet[137];
extern unsigned long long fairy2_g1t_original_fdata_guest_address;
enum { F2_RING = 64 };
struct f2_read_event {
    unsigned seq, has_result;
    uint64_t backing, vt, request_x3, quota_before, got_x0;
    uint64_t inner, inner_vt, inner_data, inner_limit;
};
static __thread struct f2_read_event f2_ring[F2_RING];
static __thread unsigned f2_adapter_reads_local;
static __thread uint64_t f2_adapter_backing_local;
static __thread uint64_t f2_adapter_vtable_local;
static __thread uint64_t f2_adapter_method_local;
static __thread uint64_t f2_adapter_arg1_local;
static __thread uint64_t f2_adapter_arg2_local;
static __thread uint64_t f2_adapter_x3_local;
static int f2_adapter_peek(uint64_t addr, void *dst, size_t n) {
    vm_size_t done=0;
    if (!addr) return 0;
    kern_return_t kr=vm_read_overwrite(mach_task_self(),
         (vm_address_t)addr,(vm_size_t)n,(vm_address_t)dst,&done);
    return kr==KERN_SUCCESS && done==(vm_size_t)n;
}
static int f2_adapter_original_load(ucontext_t *uc) {
    uint64_t pc=uc->uc_mcontext->__ss.__pc;
    module_t *m=module_of((void *)(uintptr_t)pc);
    if (!m || strcmp(m->name,"main") ||
        pc-(uint64_t)(uintptr_t)m->base!=0xc09728u) return 0;
    if (*(volatile uint32_t *)(uintptr_t)pc!=0xd43e4040u) return 0;
    uint64_t adapter=uc->uc_mcontext->__ss.__x[0];
    uint64_t backing=0,vt=0,method=0,raw[6]={0};
    int adapter_ok=f2_adapter_peek(adapter+0x10,&backing,sizeof backing);
    int backing_ok=adapter_ok && f2_adapter_peek(backing,raw,sizeof raw);
    if (backing_ok) vt=raw[0];
    int method_ok=backing_ok && f2_adapter_peek(vt+0x20,&method,sizeof method);
    unsigned seq=++f2_adapter_reads_local;
    f2_adapter_backing_local=backing;
    f2_adapter_vtable_local=vt;
    f2_adapter_method_local=method;
    f2_adapter_arg1_local=uc->uc_mcontext->__ss.__x[1];
    f2_adapter_arg2_local=uc->uc_mcontext->__ss.__x[2];
    f2_adapter_x3_local=uc->uc_mcontext->__ss.__x[3];
    struct f2_read_event *e=&f2_ring[(seq-1)%F2_RING];
    memset(e,0,sizeof *e);
    e->seq=seq; e->backing=backing; e->vt=vt;
    e->request_x3=f2_adapter_x3_local;
    if (vt==(uint64_t)(uintptr_t)m->base+0x2a644f8u) {
        e->quota_before=raw[2]; e->inner=raw[1];
        uint64_t fields[3]={0};
        if (f2_adapter_peek(raw[1],fields,sizeof fields)) {
            e->inner_vt=fields[0]; e->inner_data=fields[1];
            e->inner_limit=fields[2];
        }
    }
    if (seq<=16 || (seq<=2048 &&
          (f2_adapter_x3_local==20 || f2_adapter_x3_local==28 ||
           f2_adapter_x3_local==184))) {
        char msg[570];
        int len=snprintf(msg,sizeof msg,
          "[dm] FAIRY2_STREAM_ADAPTER seq=%u adapter=%#llx source_ok=%d backing=%#llx backing_ok=%d vt=%#llx method=%#llx method_ok=%d arg1=%#llx arg2=%#llx x3_request=%#llx quota=%#llx state=%016llx,%016llx,%016llx,%016llx\n",
          seq,(unsigned long long)adapter,adapter_ok,
          (unsigned long long)backing,backing_ok,(unsigned long long)vt,
          (unsigned long long)method,method_ok,
          (unsigned long long)f2_adapter_arg1_local,
          (unsigned long long)f2_adapter_arg2_local,
          (unsigned long long)f2_adapter_x3_local,
          (unsigned long long)e->quota_before,
          (unsigned long long)raw[1],(unsigned long long)raw[2],
          (unsigned long long)raw[3],(unsigned long long)raw[4]);
        if (len>0 && (size_t)len<sizeof msg) (void)write(2,msg,(size_t)len);
    }
    /* Original instruction: LDR x0,[x0,#0x10]. On an invalid pointer the
     * original guest would fault; x0=0 causes the next untouched LDR to
     * fault rather than returning a fake successful read. */
    uc->uc_mcontext->__ss.__x[0]=backing;
    uc->uc_mcontext->__ss.__pc=
       (uint64_t)(uintptr_t)m->base+0xc0972cu;
    return 1;
}
/* Exact original SUB x8,x20,x0 at main+0xc0962c (not SUBS).
 * x0 is the real bytes returned by the KTGL underlying reader.
 * No parser result, buffer, or guest NZCV is changed. */
static int f2_wrapper_post_read(ucontext_t *uc) {
    uint64_t pc=uc->uc_mcontext->__ss.__pc;
    module_t *m=module_of((void *)(uintptr_t)pc);
    if (!m || strcmp(m->name,"main") ||
        pc-(uint64_t)(uintptr_t)m->base!=0xc0962cu) return 0;
    if (*(volatile uint32_t *)(uintptr_t)pc!=0xd43e4040u) return 0;
    uint64_t wrapper=uc->uc_mcontext->__ss.__x[19];
    uint64_t quota=uc->uc_mcontext->__ss.__x[20];
    uint64_t got=uc->uc_mcontext->__ss.__x[0];
    for (unsigned i=0;i<F2_RING && i<f2_adapter_reads_local;i++) {
        unsigned seq=f2_adapter_reads_local-i;
        struct f2_read_event *e=&f2_ring[(seq-1)%F2_RING];
        if (e->seq==seq && e->backing==wrapper && !e->has_result) {
            e->got_x0=got; e->has_result=1; break;
        }
    }
    uc->uc_mcontext->__ss.__x[8]=quota-got;
    uc->uc_mcontext->__ss.__pc=(uint64_t)(uintptr_t)m->base+0xc09630u;
    return 1;
}
static void f2_trace_original_packet_and_reader(void) {
    unsigned long long addr=__atomic_load_n(
       &fairy2_g1t_original_fdata_guest_address,__ATOMIC_ACQUIRE);
    unsigned char live[137]={0};
    int readable=addr && f2_adapter_peek((uint64_t)addr,live,sizeof live);
    int same=readable && !memcmp(live,fairy2_g1t_original_fdata_packet,137);
    char msg[450];
    int len=snprintf(msg,sizeof msg,
      "[dm] FAIRY2_G1T_CACHE_PROOF recorded=%u source_guest=%#llx readable=%d original_137B_same=%d stream_calls=%u last_backing=%#llx last_vt=%#llx last_method=%#llx last_arg1=%#llx last_arg2=%#llx\n",
      !!addr,addr,readable,same,f2_adapter_reads_local,
      (unsigned long long)f2_adapter_backing_local,
      (unsigned long long)f2_adapter_vtable_local,
      (unsigned long long)f2_adapter_method_local,
      (unsigned long long)f2_adapter_arg1_local,
      (unsigned long long)f2_adapter_arg2_local);
    if (len>0 && (size_t)len<sizeof msg) (void)write(2,msg,(size_t)len);
    unsigned n=f2_adapter_reads_local<F2_RING ? f2_adapter_reads_local:F2_RING;
    unsigned from=f2_adapter_reads_local-n+1;
    for (unsigned seq=from;seq<=f2_adapter_reads_local;seq++) {
        const struct f2_read_event *e=&f2_ring[(seq-1)%F2_RING];
        if (e->seq!=seq) continue;
        char row[460];
        int len=snprintf(row,sizeof row,
          "[dm] FAIRY2_READ_PROVENANCE seq=%u vtable=%#llx backing=%#llx x3_requested=%#llx quota_before=%#llx result_seen=%u got_x0=%#llx inner=%#llx inner_vt=%#llx inner_data=%#llx inner_limit=%#llx\n",
          seq,(unsigned long long)e->vt,(unsigned long long)e->backing,
          (unsigned long long)e->request_x3,(unsigned long long)e->quota_before,
          e->has_result,(unsigned long long)e->got_x0,
          (unsigned long long)e->inner,(unsigned long long)e->inner_vt,
          (unsigned long long)e->inner_data,(unsigned long long)e->inner_limit);
        if (len>0 && (size_t)len<sizeof row) (void)write(2,row,(size_t)len);
    }
}

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
        f2_trace_original_packet_and_reader();
    }
    /* Exact original semantics: B.EQ main+0x6121d4; else fall through.
     * AArch64 cond branch B.EQ observes PSTATE.Z, does not modify flags. */
    uc->uc_mcontext->__ss.__pc =
      (uint64_t)(uintptr_t)mod->base + (z?0x6121d4u:0x612124u);
    return 1;
}
