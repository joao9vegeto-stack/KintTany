/* Darwin arm64 SIGSEGV/SIGBUS guest-MMIO bridge. Uses actual decoded A64
 * instructions from rePOP; never substitutes values for undecoded accesses. */
#include <sys/types.h>
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <signal.h>
#include <dlfcn.h>
#include <pthread.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/ucontext.h> /* Darwin AArch64 context; avoid deprecated getcontext API gate */
#include "xbox_memory_layout.h"
extern ptrdiff_t g_xbox_mem_offset;
extern void poptst_engine_signal_event(int sig, uintptr_t fault, uintptr_t pc);
extern void poptst_engine_signal_detail(int sig, uintptr_t fault, uintptr_t pc,
                                       int si_code, uintptr_t guest_base,
                                       uintptr_t dylib_base);
extern void poptst_engine_signal_registers(uintptr_t lr, uintptr_t sp,
                                           uintptr_t x0, uintptr_t x1,
                                           uintptr_t x2, uintptr_t x3);
extern bool apu_hook_handle_mmio(void *ctx, uintptr_t host, uint32_t va, int write);
extern int xbox_OhciOwnsAddress(uint32_t va);
extern int xbox_OhciHandleMmio(void *ctx, uint32_t va);
extern int xbox_Ac97HandleFault(void *ctx, uintptr_t host);

static struct sigaction old_segv, old_bus, old_ill, old_abrt, old_fpe, old_trap;
static uintptr_t fault_pc(void *context) {
    ucontext_t *uc=(ucontext_t *)context;
    return uc && uc->uc_mcontext ? (uintptr_t)uc->uc_mcontext->__ss.__pc : 0;
}
static pthread_once_t once=PTHREAD_ONCE_INIT;
/* Capture the Mach-O base on the guest thread outside any signal callback. */
static uintptr_t s_retail_image_base;
static void report_real_fault(int sig, siginfo_t *info, void *context) {
    uintptr_t pc = fault_pc(context);
    uintptr_t addr = info ? (uintptr_t)info->si_addr : 0;
    int code = info ? info->si_code : 0;
    poptst_engine_signal_event(sig,addr,pc);
    poptst_engine_signal_detail(sig,addr,pc,code,
                                (uintptr_t)g_xbox_mem_offset,s_retail_image_base);
    {
        ucontext_t *uc=(ucontext_t *)context;
        if (uc && uc->uc_mcontext) {
            poptst_engine_signal_registers(
                (uintptr_t)uc->uc_mcontext->__ss.__lr,
                (uintptr_t)uc->uc_mcontext->__ss.__sp,
                (uintptr_t)uc->uc_mcontext->__ss.__x[0],
                (uintptr_t)uc->uc_mcontext->__ss.__x[1],
                (uintptr_t)uc->uc_mcontext->__ss.__x[2],
                (uintptr_t)uc->uc_mcontext->__ss.__x[3]);
        }
    }
}
static void dispatch(int sig,siginfo_t *info,void *context) {
    uintptr_t fault=(uintptr_t)info->si_addr;
    uintptr_t start=(uintptr_t)g_xbox_mem_offset;
    if (start && fault>=start && fault-start<0x100000000ULL) {
        uint32_t va=(uint32_t)(fault-start);
        if (va>=0xFE800000u && va<0xFE880000u &&
            apu_hook_handle_mmio(context,fault,va,0)) return;
        if (xbox_OhciOwnsAddress(va) && xbox_OhciHandleMmio(context,va)) return;
        if (xbox_Ac97HandleFault(context,fault)) return;
    }
    report_real_fault(sig,info,context);
    static const char error[]="PoPTST FATAL: unhandled real guest MMIO/memory fault\n";
    (void)write(STDERR_FILENO,error,sizeof error-1);
    struct sigaction *previous=sig==SIGBUS?&old_bus:&old_segv;
    sigaction(sig,previous,NULL);
    raise(sig);
}
static void fatal_instruction(int sig, siginfo_t *info, void *context) {
    report_real_fault(sig,info,context);
    struct sigaction *old = sig==SIGILL ? &old_ill :
                           sig==SIGFPE ? &old_fpe :
                           sig==SIGTRAP ? &old_trap : &old_abrt;
    sigaction(sig,old,NULL);
    raise(sig);
}
static void install_once(void) {
    struct sigaction action={0};
    action.sa_sigaction=dispatch;
    action.sa_flags=SA_SIGINFO|SA_ONSTACK;
    sigemptyset(&action.sa_mask);
    sigaction(SIGSEGV,&action,&old_segv);
    sigaction(SIGBUS,&action,&old_bus);
    /* Fail-closed retail AOT uses SIGILL traps and SIGABRT for unresolved
       symbols; LiveContainer may not leave a standalone .ips report. */
    action.sa_sigaction=fatal_instruction;
    sigaction(SIGILL,&action,&old_ill);
    sigaction(SIGABRT,&action,&old_abrt);
    sigaction(SIGFPE,&action,&old_fpe);
    sigaction(SIGTRAP,&action,&old_trap);
}
void poptst_ios_install_faults(void) {
    Dl_info image = {0};
    if (dladdr((void *)&poptst_ios_install_faults, &image) && image.dli_fbase)
        s_retail_image_base = (uintptr_t)image.dli_fbase;
    static __thread unsigned char *alt_stack;
    if (!alt_stack) {
        alt_stack=malloc(1u<<20);
        if (alt_stack) {
            stack_t stack={.ss_sp=alt_stack,.ss_size=1u<<20,.ss_flags=0};
            sigaltstack(&stack,NULL);
        }
    }
    pthread_once(&once,install_once);
}
