#!/usr/bin/env python3
"""Temporary, game-local iOS bin-list memory tracer for a single host-only repack.

The released NXNative pinned source is NOT modified in Git. The workflow syncs
the pinned engine then patches its working tree before building this game's
native iOS framework. No guest/shader code is regenerated.

The faulting allocator's bin index 47 lives at alias+0x95800178 on the
2026-11-22 iPhone boot. This poll captures first-value, all changes (bounded),
and thread PC/LR near the first out-of-range transition.
"""
from pathlib import Path
import argparse
import re

ANCHOR = "void probe_install(void) {\n#if !TARGET_OS_IPHONE"
POLL = r"""
#if TARGET_OS_IPHONE
// FAIRY2 ONLY: forensic iOS equivalent of NXNative's Mac DM_PROBE_POLL.
// Do not protect the page or turn off the valid NVN DeviceShared guard.
// All reads use vm_read_overwrite: an unmapped 4K guest page is not dereferenced.
static void fairy2_bin47_snapshot(void) {
    thread_act_array_t threads = NULL;
    mach_msg_type_number_t count = 0;
    if (task_threads(mach_task_self(), &threads, &count) != KERN_SUCCESS) {
        fprintf(stderr, "[dm] FAIRY2 bin47: task_threads unavailable on device\n");
        return;
    }
    int printed = 0;
    for (mach_msg_type_number_t i = 0; i < count && printed < 18; i++) {
        arm_thread_state64_t state;
        mach_msg_type_number_t n = ARM_THREAD_STATE64_COUNT;
        if (thread_get_state(threads[i], ARM_THREAD_STATE64,
                             (thread_state_t)&state, &n) != KERN_SUCCESS) continue;
        uint64_t pc = __darwin_arm_thread_state64_get_pc(state);
        uint64_t lr = __darwin_arm_thread_state64_get_lr(state);
        module_t *m = module_of((void *)(uintptr_t)pc);
        module_t *l = module_of((void *)(uintptr_t)lr);
        if (!m && !l) continue;
        fprintf(stderr, "[dm] FAIRY2 bin47 thread %u pc=%s+%#llx lr=%s+%#llx\n",
                (unsigned)i,
                m ? m->name : "host", (unsigned long long)(m ? pc - (uintptr_t)m->base : pc),
                l ? l->name : "host", (unsigned long long)(l ? lr - (uintptr_t)l->base : lr));
        printed++;
    }
    for (mach_msg_type_number_t i = 0; i < count; i++)
        mach_port_deallocate(mach_task_self(), threads[i]);
    vm_deallocate(mach_task_self(), (vm_address_t)threads, count * sizeof *threads);
}
static void *fairy2_bin47_poll(void *arg) {
    (void)arg;
    uint8_t *alias = NULL; size_t alias_size = 0;
    void svc_alias_range(uint8_t **base, size_t *size);
    while (!alias) {
        svc_alias_range(&alias, &alias_size);
        if (!alias) usleep(1000);
    }
    // Same game-allocator root virtual region as the crash log, expressed
    // relative to the actual host alias base to survive host ASLR.
    const uint64_t offset = 0x95800178ull;
    if (alias_size < offset + 8) {
        fprintf(stderr, "[dm] FAIRY2 bin47: alias too small\n");
        return NULL;
    }
    uint64_t addr = (uint64_t)(uintptr_t)alias + offset;
    uint64_t before = 0;
    int armed = 0, changes = 0, invalids = 0, no_access = 0;
    for (;;) {
        uint64_t value = 0;
        vm_size_t got = 0;
        kern_return_t kr = vm_read_overwrite(mach_task_self(), (vm_address_t)addr,
                                             8, (vm_address_t)&value, &got);
        if (kr != KERN_SUCCESS || got != 8) {
            if (!armed && ++no_access == 3000)
                fprintf(stderr, "[dm] FAIRY2 bin47: polling waiting for mapped alias+%#llx, kr=%d\n",
                        (unsigned long long)offset, (int)kr);
            usleep(200);
            continue;
        }
        if (!armed) {
            before = value; armed = 1;
            fprintf(stderr, "[dm] FAIRY2 bin47 armed addr=%#llx initial=%#llx (alias=%p)\n",
                    (unsigned long long)addr, (unsigned long long)value, alias);
        } else if (value != before) {
            // The guest's legitimate list nodes are zero or aligned pointers
            // within its reserved guest AS. Other values deserve a snapshot;
            // they do not authorize changing or masking guest metadata.
            int invalid = value &&
                (value < 0x300000000ull || value >= 0x440000000ull || (value & 7));
            if (changes++ < 100 || invalid)
                fprintf(stderr, "[dm] FAIRY2 bin47 change #%d %#llx -> %#llx%s\n",
                        changes, (unsigned long long)before,
                        (unsigned long long)value, invalid ? " INVALID_GUEST_POINTER" : "");
            if (invalid && invalids++ < 3)
                fairy2_bin47_snapshot();
            before = value;
        }
        usleep(100);
    }
    return NULL;
}
static void fairy2_bin47_start(void) {
    pthread_t t;
    int e = pthread_create(&t, NULL, fairy2_bin47_poll, NULL);
    if (e) fprintf(stderr, "[dm] FAIRY2 bin47: pthread_create error=%d\n", e);
    else pthread_detach(t);
}
#endif
"""

def apply(path: Path, bin_offset: int = 0x95800178):
    source = path.read_text()
    if source.count(ANCHOR) != 1 or "fairy2_bin47_poll" in source:
        raise RuntimeError("Pinned NXNative probe.c does not match the audited version")
    source = source.replace(ANCHOR,
        POLL.replace("0x95800178ull", f"0x{bin_offset:x}ull") + "\nvoid probe_install(void) {\n"
        "#if TARGET_OS_IPHONE\n    fairy2_bin47_start();\n#endif\n"
        "#if !TARGET_OS_IPHONE")
    if source.count("fairy2_bin47_start();") != 1:
        raise RuntimeError("Failed to install exactly one iOS poll")
    path.write_text(source)
    print("[Fairy2iOS] Host-only iOS bin47 source instrumentation installed; Metal unchanged.", flush=True)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--bin-offset", type=lambda x:int(x,0), default=0x95800178)
    args = p.parse_args()
    if args.bin_offset not in (0x95800178, 0xc5800178):
        raise RuntimeError("Not an audited KTGL bin table offset")
    apply(args.source,args.bin_offset)
