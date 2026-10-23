#include "xowue_engine.h"

#include <array>
#include <iostream>
#include <string>

#if defined(__linux__)
#include <execinfo.h>
#include <signal.h>
#include <ucontext.h>
#include <unistd.h>

static void onSegfault(int signal, siginfo_t *info, void *rawContext) {
    auto *context = static_cast<ucontext_t *>(rawContext);
    const auto pc = static_cast<unsigned long long>(context->uc_mcontext.gregs[REG_RIP]);
    const auto dst = static_cast<unsigned long long>(context->uc_mcontext.gregs[REG_RDI]);
    const auto src = static_cast<unsigned long long>(context->uc_mcontext.gregs[REG_RSI]);
    const auto len = static_cast<unsigned long long>(context->uc_mcontext.gregs[REG_RDX]);
    dprintf(STDERR_FILENO, "SIGSEGV address=%p PC=0x%llx RDI=0x%llx RSI=0x%llx RDX=0x%llx\n", info->si_addr, pc, dst, src, len);
    void *frames[32];
    const int count = backtrace(frames, 32);
    backtrace_symbols_fd(frames, count, STDERR_FILENO);
    _exit(128 + signal);
}

static void installSegfaultReporter() {
    struct sigaction action {};
    action.sa_sigaction = onSegfault;
    action.sa_flags = SA_SIGINFO;
    sigemptyset(&action.sa_mask);
    sigaction(SIGSEGV, &action, nullptr);
}
#else
static void installSegfaultReporter() {}
#endif

int main(int argc, char **argv) {
    installSegfaultReporter();
    if (argc < 2 || argc > 3) {
        std::cerr << "usage: XOWUEHostSmoke <default.xex> [inspect|boot]\n";
        return 64;
    }
    const bool boot = argc == 3 && std::string(argv[2]) == "boot";
    std::array<char, 32768> output{};
    std::cerr << (boot ? "Calling guest entry point\n" : "Inspecting XEX\n");
    const int result = boot
        ? xowue_boot_xex(argv[1], output.data(), output.size())
        : xowue_inspect_xex(argv[1], output.data(), output.size());
    std::cout << output.data() << '\n';
    return result;
}
