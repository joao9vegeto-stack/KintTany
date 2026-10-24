// XOWUE fatal-signal reporting. Boot failures are reported separately.
#include "XOWUECrashRecorder.h"
#include <signal.h>
#include <fcntl.h>
#include <limits.h>
#include <string.h>
#include <unistd.h>
#include <stdint.h>

static char g_crashFilePath[PATH_MAX];
static volatile sig_atomic_t g_recordingCrash = 0;

static char *append_text(char *p, char *end, const char *text) {
    while (*text && p < end) *p++ = *text++;
    return p;
}

static char *append_hex(char *p, char *end, uintptr_t number) {
    static const char digits[] = "0123456789ABCDEF";
    p = append_text(p, end, "0x");
    for (int shift = (int)(sizeof(uintptr_t) * 8 - 4);
         shift >= 0 && p < end; shift -= 4) {
        *p++ = digits[(number >> shift) & 0xFu];
    }
    return p;
}

static void crash_handler(int sig, siginfo_t *info, void *context) {
    (void)context;
    if (!g_recordingCrash) {
        g_recordingCrash = 1;
        if (g_crashFilePath[0]) {
            char message[256];
            char *p = message;
            char *end = message + sizeof(message) - 2;
            p = append_text(p, end, "NATIVE_FATAL_SIGNAL signal=");
            p = append_hex(p, end, (uintptr_t)sig);
            p = append_text(p, end, " fault_address=");
            p = append_hex(p, end, (uintptr_t)(info ? info->si_addr : 0));
            if (p < end) *p++ = '\n';
            int fd = open(g_crashFilePath, O_WRONLY | O_CREAT | O_APPEND, 0600);
            if (fd >= 0) {
                (void)write(fd, message, (size_t)(p - message));
                close(fd);
            }
        }
    }
    // SA_RESETHAND reinstates the original signal disposition on entry.
    kill(getpid(), sig);
    _exit(128 + sig);
}

void XOWUECrashRecorderInstall(const char *crashFilePath) {
    if (!crashFilePath) return;
    size_t length = strlen(crashFilePath);
    if (!length || length >= sizeof(g_crashFilePath)) return;
    memcpy(g_crashFilePath, crashFilePath, length + 1);
    const int signals[] = {SIGABRT, SIGSEGV, SIGBUS, SIGILL, SIGFPE};
    for (size_t i = 0; i < sizeof(signals) / sizeof(signals[0]); ++i) {
        struct sigaction action;
        memset(&action, 0, sizeof(action));
        action.sa_sigaction = crash_handler;
        sigemptyset(&action.sa_mask);
        action.sa_flags = SA_SIGINFO | SA_RESETHAND;
        sigaction(signals[i], &action, NULL);
    }
}
