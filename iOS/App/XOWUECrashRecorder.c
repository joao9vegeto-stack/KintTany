// XOWUE iOS native fatal breadcrumbs inspired by PoPTST, without guest CPU
// emulation, synthetic returns or masking crashes. Signal handler uses only
// arithmetic, static buffers and write() to a descriptor opened at startup.
#include "XOWUECrashRecorder.h"
#include <signal.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdlib.h>
#include <dlfcn.h>
#include <sys/ucontext.h>

static volatile sig_atomic_t s_fd = -1;
static volatile sig_atomic_t s_recording = 0;
static uintptr_t s_image_base = 0;

static char *append_text(char *p, char *end, const char *text) {
    while (text && *text && p < end) *p++ = *text++;
    return p;
}
static char *append_hex(char *p, char *end, uintptr_t value) {
    static const char hex[] = "0123456789ABCDEF";
    p = append_text(p,end,"0x");
    for (int shift = (int)(sizeof(uintptr_t)*8)-4; shift>=0 && p<end; shift-=4)
        *p++=hex[(value >> shift)&15u];
    return p;
}
static void fatal_line(const char *prefix, uintptr_t a,
                       const char *middle, uintptr_t b) {
    int fd = (int)s_fd;
    if (fd<0) return;
    char line[256], *p=line;
    char *end=line+sizeof(line)-2;
    p=append_text(p,end,prefix);
    p=append_hex(p,end,a);
    p=append_text(p,end,middle);
    p=append_hex(p,end,b);
    if (p<end) *p++='\n';
    (void)write(fd,line,(size_t)(p-line));
}

void XOWUECrashRecorderWriteFatal(const char *event) {
    const int fd=(int)s_fd;
    if (fd<0 || !event) return;
    const char header[]="FATAL AOT_DISPATCH ";
    (void)write(fd,header,sizeof(header)-1);
    const size_t length=strnlen(event,1536);
    (void)write(fd,event,length);
    (void)write(fd,"\n",1);
}

static void crash_handler(int sig, siginfo_t *info, void *context) {
    if (!s_recording) {
        s_recording=1;
        const uintptr_t addr=(uintptr_t)(info ? info->si_addr : 0);
        const uintptr_t code=(uintptr_t)(info ? info->si_code : 0);
        uintptr_t pc=0, lr=0, sp=0, x0=0, x1=0, x2=0, x3=0;
#if defined(__APPLE__) && defined(__aarch64__)
        const ucontext_t ctx=(ucontext_t)context;
        if (ctx && ctx->uc_mcontext) {
            pc=(uintptr_t)ctx->uc_mcontext->__ss.__pc;
            lr=(uintptr_t)ctx->uc_mcontext->__ss.__lr;
            sp=(uintptr_t)ctx->uc_mcontext->__ss.__sp;
            x0=(uintptr_t)ctx->uc_mcontext->__ss.__x[0];
            x1=(uintptr_t)ctx->uc_mcontext->__ss.__x[1];
            x2=(uintptr_t)ctx->uc_mcontext->__ss.__x[2];
            x3=(uintptr_t)ctx->uc_mcontext->__ss.__x[3];
        }
#else
        (void)context;
#endif
        fatal_line("FATAL SIGNAL sig=", (uintptr_t)(unsigned)sig, " host=", addr);
        fatal_line("SIGDETAIL pc=",pc," code=",code);
        fatal_line("SIGDETAIL image_base=",s_image_base," dylib_offset=",
                   pc>=s_image_base?pc-s_image_base:0);
        fatal_line("ARM64REG lr=",lr," sp=",sp);
        fatal_line("ARM64REG x0=",x0," x1=",x1);
        fatal_line("ARM64REG x2=",x2," x3=",x3);
    }
    // SA_RESETHAND restores the crash disposition, allowing system .ips.
    kill(getpid(),sig);
    _exit(128+sig);
}

void XOWUECrashRecorderInstall(const char *crashFilePath) {
    if (!crashFilePath || !crashFilePath[0]) return;
    int fd=open(crashFilePath,O_WRONLY|O_CREAT|O_APPEND|O_CLOEXEC,0600);
    if (fd<0) return;
    const int previous=(int)s_fd;
    s_fd=(sig_atomic_t)fd;
    if (previous>=0) close(previous);
    Dl_info image={0};
    if (dladdr((void *)&XOWUECrashRecorderInstall,&image) && image.dli_fbase)
        s_image_base=(uintptr_t)image.dli_fbase;
    static const int signals[]={SIGABRT,SIGSEGV,SIGBUS,SIGILL,SIGFPE,SIGTRAP};
    for (size_t i=0;i<sizeof(signals)/sizeof(signals[0]);++i) {
        struct sigaction action;
        memset(&action,0,sizeof(action));
        action.sa_sigaction=crash_handler;
        action.sa_flags=SA_SIGINFO|SA_RESETHAND;
        sigemptyset(&action.sa_mask);
        sigaction(signals[i],&action,NULL);
    }
}
