/* ASURA_IOS_ARM64_CRASH_REGISTERS_V1
 * Async-signal-safe fatal recorder adapted from the XOWUE iOS recorder.
 */
#include "asura_crash_recorder.h"
#include <signal.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdlib.h>
#include <sys/ucontext.h>
static volatile sig_atomic_t s_crash_fd = -1;
static volatile sig_atomic_t s_recording = 0;
static char *append_text(char *p,char *end,const char *text){while(text&&*text&&p<end)*p++=*text++;return p;}
static char *append_hex(char *p,char *end,uintptr_t value){static const char digits[]="0123456789ABCDEF";p=append_text(p,end,"0x");for(int shift=(int)(sizeof(uintptr_t)*8)-4;shift>=0&&p<end;shift-=4)*p++=digits[(value>>shift)&15u];return p;}
static void record_pair(const char *name,uintptr_t a,const char *middle,uintptr_t b){int fd=(int)s_crash_fd;if(fd<0)return;char line[256],*p=line,*end=line+sizeof(line)-2;p=append_text(p,end,name);p=append_hex(p,end,a);p=append_text(p,end,middle);p=append_hex(p,end,b);if(p<end)*p++='\n';(void)write(fd,line,(size_t)(p-line));}
static void asura_crash_signal_handler(int sig,siginfo_t *info,void *context){
 if(!s_recording){s_recording=1;uintptr_t pc=0,lr=0,fp=0,sp=0,x0=0,x1=0,x2=0,x3=0,x4=0,x5=0,x6=0,x7=0;
#if defined(__APPLE__) && defined(__aarch64__)
 const ucontext_t *ctx=(const ucontext_t*)context;if(ctx&&ctx->uc_mcontext){pc=(uintptr_t)ctx->uc_mcontext->__ss.__pc;lr=(uintptr_t)ctx->uc_mcontext->__ss.__lr;fp=(uintptr_t)ctx->uc_mcontext->__ss.__fp;sp=(uintptr_t)ctx->uc_mcontext->__ss.__sp;x0=(uintptr_t)ctx->uc_mcontext->__ss.__x[0];x1=(uintptr_t)ctx->uc_mcontext->__ss.__x[1];x2=(uintptr_t)ctx->uc_mcontext->__ss.__x[2];x3=(uintptr_t)ctx->uc_mcontext->__ss.__x[3];x4=(uintptr_t)ctx->uc_mcontext->__ss.__x[4];x5=(uintptr_t)ctx->uc_mcontext->__ss.__x[5];x6=(uintptr_t)ctx->uc_mcontext->__ss.__x[6];x7=(uintptr_t)ctx->uc_mcontext->__ss.__x[7];}
#else
 (void)context;
#endif
 record_pair("FATAL_SIGNAL sig=", (uintptr_t)(unsigned)sig," fault_address=",(uintptr_t)(info?info->si_addr:0));
 record_pair("SIGNAL_DETAIL si_code=",(uintptr_t)(info?info->si_code:0)," signal=",(uintptr_t)(info?info->si_signo:sig));
 record_pair("ARM64_PC pc=",pc," lr=",lr);record_pair("ARM64_FRAME fp=",fp," sp=",sp);
 record_pair("ARM64_X0_X1 x0=",x0," x1=",x1);record_pair("ARM64_X2_X3 x2=",x2," x3=",x3);
 record_pair("ARM64_X4_X5 x4=",x4," x5=",x5);record_pair("ARM64_X6_X7 x6=",x6," x7=",x7);
}
 sigset_t unblocked;sigemptyset(&unblocked);sigaddset(&unblocked,sig);(void)sigprocmask(SIG_UNBLOCK,&unblocked,NULL);(void)kill(getpid(),sig);_exit(128+sig);
}
__attribute__((visibility("default"))) void AsuraCrashRecorderInstall(const char *path){if(!path||!path[0])return;int fd=open(path,O_WRONLY|O_CREAT|O_APPEND|O_CLOEXEC|O_SYNC,0600);if(fd<0)return;int old=(int)s_crash_fd;s_crash_fd=(sig_atomic_t)fd;if(old>=0)close(old);static const int signals[]={SIGABRT,SIGSEGV,SIGBUS,SIGILL,SIGFPE,SIGTRAP};for(size_t i=0;i<sizeof(signals)/sizeof(signals[0]);++i){struct sigaction action;memset(&action,0,sizeof(action));action.sa_sigaction=asura_crash_signal_handler;action.sa_flags=SA_SIGINFO|SA_RESETHAND;sigemptyset(&action.sa_mask);(void)sigaction(signals[i],&action,NULL);}}
