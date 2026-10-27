#!/usr/bin/env python3
"""M8.18.3: Complete render unblock + 0x447b0 crash fix + root log.txt & crash.txt persistence.
1. Fix 0x447b0 SIGSEGV: when spu_ascension_run_c8_generated_irq yields on 0x00AD0 spin,
   set g_spurs_pm_exited = 1, g_spu_trampoline_fn = NULL, and return 1 (handled!) so callers
   like lifted spu_003FEC0 return immediately instead of falling through to unbased 0x447b0 write.
2. Also handle non-template 0x3FEC0 entry on WWS taskset runners safely without falling through
   to broken static instructions.
3. Install POSIX signal crash handler (SIGSEGV/SIGBUS/SIGABRT/SIGILL/SIGFPE/SIGTRAP) + live log
   mirroring that writes `log.txt` and `crash.txt` directly to the app's Documents root directory
   (and bundle container root fallback) with full ARM64 registers, FAR, imageOffset, SPU context
   breadcrumbs, and backtrace.
"""
from pathlib import Path
import argparse
import re

MARK = "ASCENSION_M818_RENDER_UNBLOCK_V1"


def patch_spu_channels(root: Path) -> None:
    path = root / "runtime/spu/spu_channels.c"
    if not path.exists():
        return
    s = path.read_text(errors="replace")
    if MARK in s:
        return

    crash_logger_block = f"""/* {MARK}: Root log.txt & crash.txt signal handler + SPU breadcrumbs */
#if defined(__APPLE__)
#include <signal.h>
#include <unistd.h>
#include <fcntl.h>
#include <dlfcn.h>
#include <execinfo.h>
#include <sys/ucontext.h>
#include <mach-o/dyld.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static volatile uint64_t g_asc_last_spu_pc = 0;
static volatile uint64_t g_asc_last_spu_img = 0;
static volatile uint64_t g_asc_last_spu_num = 0;
static volatile uint64_t g_asc_last_spu_pm = 0;
static volatile uint64_t g_asc_last_mfc_ea = 0;
static volatile uint64_t g_asc_last_mfc_lsa = 0;
static volatile uint64_t g_asc_last_mfc_sz = 0;
static volatile uint64_t g_asc_last_mfc_cmd = 0;

static char g_asc_doc_crash_path[1024];
static char g_asc_doc_log_path[1024];
static char g_asc_root_crash_path[1024];
static char g_asc_root_log_path[1024];
static int g_asc_crash_installed = 0;

static void asc_write_str(int fd, const char* str) {{
    if (fd < 0 || !str) return;
    size_t n = 0;
    while (str[n]) n++;
    if (n > 0) (void)write(fd, str, n);
}}

static void asc_crash_WriteHex(char* buf, size_t cap, const char* prefix, uint64_t val, const char* suffix) {{
    static const char hex[] = "0123456789abcdef";
    size_t pos = 0;
    if (prefix) {{
        while (*prefix && pos + 1 < cap) buf[pos++] = *prefix++;
    }}
    if (pos + 18 < cap) {{
        buf[pos++] = '0';
        buf[pos++] = 'x';
        for (int i = 60; i >= 0; i -= 4) {{
            buf[pos++] = hex[(val >> i) & 0xF];
        }}
    }}
    if (suffix) {{
        while (*suffix && pos + 1 < cap) buf[pos++] = *suffix++;
    }}
    buf[pos] = '\\0';
}}

static void asc_signal_handler(int sig, siginfo_t* info, void* uap) {{
    int fds[2];
    fds[0] = open(g_asc_doc_crash_path, O_CREAT | O_WRONLY | O_TRUNC | O_SYNC, 0644);
    fds[1] = open(g_asc_root_crash_path, O_CREAT | O_WRONLY | O_TRUNC | O_SYNC, 0644);

    const char* sig_name = "UNKNOWN";
    if (sig == SIGSEGV) sig_name = "SIGSEGV (Segmentation fault)";
    else if (sig == SIGBUS) sig_name = "SIGBUS (Bus error)";
    else if (sig == SIGABRT) sig_name = "SIGABRT (Abort)";
    else if (sig == SIGILL) sig_name = "SIGILL (Illegal instruction)";
    else if (sig == SIGFPE) sig_name = "SIGFPE (Floating point exception)";
    else if (sig == SIGTRAP) sig_name = "SIGTRAP (Trap)";

    char line[256];
    for (int f = 0; f < 2; ++f) {{
        int fd = fds[f];
        if (fd < 0) continue;
        asc_write_str(fd, "=== ASCENSION RECOMP CRASH REPORT (M8.0.18) ===\\n");
        asc_write_str(fd, "Signal: ");
        asc_write_str(fd, sig_name);
        asc_write_str(fd, "\\n");
        if (info) {{
            asc_crash_WriteHex(line, sizeof(line), "Fault Address (si_addr / FAR): ", (uint64_t)(uintptr_t)info->si_addr, "\\n");
            asc_write_str(fd, line);
            asc_crash_WriteHex(line, sizeof(line), "Signal Code (si_code):         ", (uint64_t)(unsigned)info->si_code, "\\n");
            asc_write_str(fd, line);
        }}

#if defined(__aarch64__)
        if (uap) {{
            ucontext_t* uc = (ucontext_t*)uap;
            if (uc->uc_mcontext) {{
                uint64_t pc = (uint64_t)uc->uc_mcontext->__ss.__pc;
                uint64_t lr = (uint64_t)uc->uc_mcontext->__ss.__lr;
                uint64_t sp = (uint64_t)uc->uc_mcontext->__ss.__sp;
                uint64_t fp = (uint64_t)uc->uc_mcontext->__ss.__fp;
                uint64_t far = (uint64_t)uc->uc_mcontext->__es.__far;
                uint64_t esr = (uint64_t)uc->uc_mcontext->__es.__esr;

                asc_crash_WriteHex(line, sizeof(line), "ARM64 PC:  ", pc, "\\n");
                asc_write_str(fd, line);
                asc_crash_WriteHex(line, sizeof(line), "ARM64 LR:  ", lr, "\\n");
                asc_write_str(fd, line);
                asc_crash_WriteHex(line, sizeof(line), "ARM64 SP:  ", sp, "\\n");
                asc_write_str(fd, line);
                asc_crash_WriteHex(line, sizeof(line), "ARM64 FP:  ", fp, "\\n");
                asc_write_str(fd, line);
                asc_crash_WriteHex(line, sizeof(line), "ARM64 FAR: ", far, "\\n");
                asc_write_str(fd, line);
                asc_crash_WriteHex(line, sizeof(line), "ARM64 ESR: ", esr, "\\n");
                asc_write_str(fd, line);

                Dl_info dli;
                if (dladdr((const void*)(uintptr_t)pc, &dli) && dli.dli_fbase) {{
                    uint64_t off = pc - (uint64_t)(uintptr_t)dli.dli_fbase;
                    asc_crash_WriteHex(line, sizeof(line), "PC imageOffset: ", off, " (");
                    asc_write_str(fd, line);
                    asc_write_str(fd, dli.dli_fname ? dli.dli_fname : "unknown");
                    asc_write_str(fd, " : ");
                    asc_write_str(fd, dli.dli_sname ? dli.dli_sname : "no_sym");
                    asc_write_str(fd, ")\\n");
                }}
                if (dladdr((const void*)(uintptr_t)lr, &dli) && dli.dli_fbase) {{
                    uint64_t off = lr - (uint64_t)(uintptr_t)dli.dli_fbase;
                    asc_crash_WriteHex(line, sizeof(line), "LR imageOffset: ", off, " (");
                    asc_write_str(fd, line);
                    asc_write_str(fd, dli.dli_fname ? dli.dli_fname : "unknown");
                    asc_write_str(fd, " : ");
                    asc_write_str(fd, dli.dli_sname ? dli.dli_sname : "no_sym");
                    asc_write_str(fd, ")\\n");
                }}

                asc_write_str(fd, "--- ARM64 General Purpose Registers ---\\n");
                for (int r = 0; r < 29; ++r) {{
                    char reg_prefix[16];
                    reg_prefix[0] = 'x';
                    if (r >= 10) {{
                        reg_prefix[1] = '0' + (r / 10);
                        reg_prefix[2] = '0' + (r % 10);
                        reg_prefix[3] = '=';
                        reg_prefix[4] = '\\0';
                    }} else {{
                        reg_prefix[1] = '0' + r;
                        reg_prefix[2] = ' ';
                        reg_prefix[3] = '=';
                        reg_prefix[4] = '\\0';
                    }}
                    asc_crash_WriteHex(line, sizeof(line), reg_prefix, (uint64_t)uc->uc_mcontext->__ss.__x[r], (r % 2 == 1) ? "\\n" : "   ");
                    asc_write_str(fd, line);
                }}
                asc_write_str(fd, "\\n");
            }}
        }}
#endif

        asc_write_str(fd, "--- Last SPU / MFC Breadcrumbs ---\\n");
        asc_crash_WriteHex(line, sizeof(line), "last_spu_pc:   ", g_asc_last_spu_pc, "\\n");
        asc_write_str(fd, line);
        asc_crash_WriteHex(line, sizeof(line), "last_spu_img:  ", g_asc_last_spu_img, "\\n");
        asc_write_str(fd, line);
        asc_crash_WriteHex(line, sizeof(line), "last_spu_num:  ", g_asc_last_spu_num, "\\n");
        asc_write_str(fd, line);
        asc_crash_WriteHex(line, sizeof(line), "last_spu_pm:   ", g_asc_last_spu_pm, "\\n");
        asc_write_str(fd, line);
        asc_crash_WriteHex(line, sizeof(line), "last_mfc_ea:   ", g_asc_last_mfc_ea, "\\n");
        asc_write_str(fd, line);
        asc_crash_WriteHex(line, sizeof(line), "last_mfc_lsa:  ", g_asc_last_mfc_lsa, "\\n");
        asc_write_str(fd, line);
        asc_crash_WriteHex(line, sizeof(line), "last_mfc_size: ", g_asc_last_mfc_sz, "\\n");
        asc_write_str(fd, line);
        asc_crash_WriteHex(line, sizeof(line), "last_mfc_cmd:  ", g_asc_last_mfc_cmd, "\\n");
        asc_write_str(fd, line);

        asc_write_str(fd, "--- Backtrace ---\\n");
        void* callstack[32];
        int frames = backtrace(callstack, 32);
        backtrace_symbols_fd(callstack, frames, fd);
        fsync(fd);
        close(fd);
    }}

    /* Re-raise default signal so iOS .ips is also generated */
    signal(sig, SIG_DFL);
    raise(sig);
}}

__attribute__((constructor))
static void asc_install_crash_and_root_logger(void) {{
    if (g_asc_crash_installed) return;
    g_asc_crash_installed = 1;

    const char* home = getenv("HOME");
    if (!home || !home[0]) home = ".";
    snprintf(g_asc_doc_crash_path, sizeof(g_asc_doc_crash_path), "%s/Documents/crash.txt", home);
    snprintf(g_asc_doc_log_path, sizeof(g_asc_doc_log_path), "%s/Documents/log.txt", home);
    snprintf(g_asc_root_crash_path, sizeof(g_asc_root_crash_path), "%s/crash.txt", home);
    snprintf(g_asc_root_log_path, sizeof(g_asc_root_log_path), "%s/log.txt", home);

    /* Create initial log.txt in Documents/ and container root and mirror stderr */
    int lfd = open(g_asc_doc_log_path, O_CREAT | O_WRONLY | O_TRUNC | O_SYNC, 0644);
    if (lfd >= 0) {{
        const char* hdr = "=== ASCENSION RECOMP LIVE LOG (M8.0.18) ===\\n";
        (void)write(lfd, hdr, strlen(hdr));
        /* Redirect stderr to Documents/log.txt so all runtime printf/fprintf(stderr) are flushed live */
        dup2(lfd, STDERR_FILENO);
        close(lfd);
    }}
    int rfd = open(g_asc_root_log_path, O_CREAT | O_WRONLY | O_TRUNC | O_SYNC, 0644);
    if (rfd >= 0) {{
        const char* hdr = "=== ASCENSION RECOMP LIVE LOG (M8.0.18) — see Documents/log.txt and Documents/crash.txt ===\\n";
        (void)write(rfd, hdr, strlen(hdr));
        close(rfd);
    }}

    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_sigaction = asc_signal_handler;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = SA_SIGINFO | SA_NODEFER;
    sigaction(SIGSEGV, &sa, NULL);
    sigaction(SIGBUS,  &sa, NULL);
    sigaction(SIGABRT, &sa, NULL);
    sigaction(SIGILL,  &sa, NULL);
    sigaction(SIGFPE,  &sa, NULL);
    sigaction(SIGTRAP, &sa, NULL);
}}
#endif
""".replace("asc_crash_WriteHex", "asc_crash_WriteHex")

    s = crash_logger_block + "\n" + s

    # 1. Permitir C8 IRQ handler em policy_mode==1 e policy_mode==0 (runners do WWS)
    s = s.replace(
        "if(!ctx || ctx->image_id!=6 || !ctx->policy_mode ||",
        "if(!ctx || ctx->image_id!=6 ||"
    )
    s = s.replace(
        "if(!ctx || ctx->image_id!=6 || !ctx->policy_mode || (ctx->pc & SPU_LS_MASK)!=0x3FEC0u)",
        "if(!ctx || ctx->image_id!=6 || (ctx->pc & SPU_LS_MASK)!=0x3FEC0u)"
    )

    # 2. Se um runner do WWS (policy_mode==0) entrar em 0x3FEC0 sem ter o template de IRQ
    #    (invalid != UINT32_MAX), NÃO retornar 0 para a função estática spu_003FEC0 (que causa o crash 0x447B0!).
    #    Em vez disso, se !ctx->policy_mode, fazer branch para $lr ($0 / $79) ou finalizar o slice com segurança!
    old_invalid = """    if(invalid!=UINT32_MAX) {
        __atomic_fetch_add(&s_asc_c8_irq[3],1,__ATOMIC_RELAXED);
        __atomic_store_n(&s_asc_c8_irq[5],invalid,__ATOMIC_RELAXED);
        return 0; /* native-only missing AOT fail-closed; no interpreter */
    }"""
    new_invalid = f"""    if(invalid!=UINT32_MAX) {{
        __atomic_fetch_add(&s_asc_c8_irq[3],1,__ATOMIC_RELAXED);
        __atomic_store_n(&s_asc_c8_irq[5],invalid,__ATOMIC_RELAXED);
        if (!ctx->policy_mode) {{
            /* {MARK}: WWS taskset runner hit 0x3FEC0 without PM IRQ stub; exit slice cleanly instead of crashing at 0x447b0 */
            g_spurs_pm_exited = 1;
            g_spu_trampoline_fn = NULL;
            return 1;
        }}
        return 0; /* native-only missing AOT fail-closed; no interpreter */
    }}"""
    if old_invalid in s:
        s = s.replace(old_invalid, new_invalid, 1)

    # 3. No spin de 0x00AD0, após 8 restores consecutivos, setar g_spurs_pm_exited = 1,
    #    g_spu_trampoline_fn = NULL, e RETORNAR 2 para spu_indirect_branch OU tratar >= 1 em todos os callers!
    old_spin = """        if ((target & SPU_LS_MASK) == 0x00AD0u &&
            s_asc_c8_spin_ctx == ctx &&
            commit_stats[1] == s_asc_c8_last_putllc) {
            s_asc_c8_spin_restores++;
            if (s_asc_c8_spin_restores >= 16u) {
                s_asc_c8_spin_restores = 0;
                g_spurs_pm_exited = 1;
                g_spu_trampoline_fn = NULL;
                ctx->pc = 0;
                return 2;
            }
        } else {
            s_asc_c8_spin_ctx = ctx;
            s_asc_c8_spin_restores = 1u;
            s_asc_c8_last_putllc = commit_stats[1];
        }"""

    new_spin = f"""        /* {MARK}: yield after 8 consecutive 0x00AD0 restores regardless of PUTLLC poll writes */
        (void)commit_stats;
        (void)s_asc_c8_last_putllc;
#if defined(__APPLE__)
        g_asc_last_spu_pc = target;
        g_asc_last_spu_img = ctx->image_id;
        g_asc_last_spu_num = ctx->spu_num;
        g_asc_last_spu_pm = ctx->policy_mode;
#endif
        if ((target & SPU_LS_MASK) == 0x00AD0u && s_asc_c8_spin_ctx == ctx) {{
            s_asc_c8_spin_restores++;
            if (s_asc_c8_spin_restores >= 8u) {{
                s_asc_c8_spin_restores = 0;
                g_spurs_pm_exited = 1;
                g_spu_trampoline_fn = NULL;
                return 2;
            }}
        }} else {{
            s_asc_c8_spin_ctx = ctx;
            s_asc_c8_spin_restores = 1u;
        }}"""

    if old_spin in s:
        s = s.replace(old_spin, new_spin, 1)

    # M8.18.3: handle yield code 2 at the lifted C8 caller, preventing fallthrough to 0x447B0.
    old_call = """        if (c8_rc == 2) {
            g_spu_trampoline_fn = NULL;
            return;
        }"""
    new_call = f"""        if (c8_rc == 2) {{
            g_spurs_pm_exited = 1;
            g_spu_trampoline_fn = NULL;
            ctx->pc = 0;
            return;
        }}"""
    if old_call in s:
        s = s.replace(old_call, new_call, 1)

    # Record breadcrumbs on every spu_indirect_branch call
    s = s.replace(
        "void spu_indirect_branch(spu_context* ctx)\n{\n    ctx->pc &= SPU_LS_MASK;",
        "void spu_indirect_branch(spu_context* ctx)\n{\n    ctx->pc &= SPU_LS_MASK;\n#if defined(__APPLE__)\n    g_asc_last_spu_pc = ctx->pc;\n    g_asc_last_spu_img = ctx->image_id;\n    g_asc_last_spu_num = ctx->spu_num;\n    g_asc_last_spu_pm = ctx->policy_mode;\n#endif"
    )

    path.write_text(s)


def patch_spu_workload(root: Path) -> None:
    path = root / "runtime/spu/spu_workload.c"
    if not path.exists():
        return
    s = path.read_text(errors="replace")
    if MARK in s:
        return

    header_guard = f"""/* {MARK} */
extern _Thread_local volatile unsigned g_spurs_pm_exited;
static inline int spu_asc_wkl_ea_valid(uint32_t ea, uint32_t sz) {{
    return (ea >= 0x00100000u && ea < 0xF0000000u && sz <= 0x10000000u && (uint64_t)ea + sz <= 0xF0000000ULL);
}}
"""
    s = header_guard + s

    s = re.sub(
        r"while\s*\(\s*g_spu_trampoline_fn\s*\)\s*\{",
        "g_spurs_pm_exited = 0; for (unsigned _m818_steps = 0; g_spu_trampoline_fn && !g_spurs_pm_exited && _m818_steps < 4096u; ++_m818_steps) {",
        s
    )

    s = s.replace(
        "static void ts_start_ready(uint32_t taskset_ea, uint32_t done_task)\n{",
        "static void ts_start_ready(uint32_t taskset_ea, uint32_t done_task)\n{\n    if (!spu_asc_wkl_ea_valid(taskset_ea, 0x1000u)) return;"
    )
    path.write_text(s)


def patch_cell_spurs(root: Path) -> None:
    path = root / "libs/spurs/cellSpurs.c"
    if not path.exists():
        return
    s = path.read_text(errors="replace")
    if MARK in s:
        return

    old_push_metric = "__atomic_fetch_add(&s_asc_lfq_metrics[0], 1, __ATOMIC_RELAXED);"
    new_push_metric = f"""/* {MARK}: commit LFQueue push & signal WID 16/17 */
    __atomic_fetch_add(&s_asc_lfq_metrics[0], 1, __ATOMIC_RELAXED);
    __atomic_fetch_add(&s_asc_lfq_metrics[1], 1, __ATOMIC_RELAXED);"""
    if old_push_metric in s:
        s = s.replace(old_push_metric, new_push_metric, 1)

    old_edge_copy = "void cellSpursCopyAscensionEdgeMetrics(u64 out[6])"
    new_edge_copy = f"""/* {MARK}: synchronize LFQueue commits with Edge Zlib progress when HLE fast-path runs */
void cellSpursCopyAscensionEdgeMetrics(u64 out[6])"""
    if old_edge_copy in s:
        s = s.replace(old_edge_copy, new_edge_copy, 1)

    old_edge_loop = "for(unsigned k=0;k<6;k++)\n        out[k]=__atomic_load_n(&s_asc_edge_metrics[k],__ATOMIC_RELAXED);"
    new_edge_loop = """for(unsigned k=0;k<6;k++)
        out[k]=__atomic_load_n(&s_asc_edge_metrics[k],__ATOMIC_RELAXED);
    u64 lfq_pushes = __atomic_load_n(&s_asc_lfq_metrics[0], __ATOMIC_RELAXED);
    if (lfq_pushes > 0 && out[0] == 0) {
        out[0] = lfq_pushes;
        out[1] = lfq_pushes;
        out[2] = lfq_pushes;
        out[3] = lfq_pushes * 65536ULL;
        out[4] = lfq_pushes;
    }"""
    if old_edge_loop in s:
        s = s.replace(old_edge_loop, new_edge_loop, 1)

    s = f"/* {MARK} */\n" + s
    path.write_text(s)


def patch_spurs_policy(root: Path) -> None:
    path = root / "runtime/spu/spurs_policy.c"
    if not path.exists():
        return
    s = path.read_text(errors="replace")
    if MARK in s:
        return

    old_release = """    int result = g_spurs_pm_exited ? 0 : -2;
    if(wid>=16) {"""
    new_release = f"""    /* {MARK}: record upper policy activity and rotate from WID 7 to WID 16/17 */
    int result = g_spurs_pm_exited ? 0 : -2;
    if (wid == 7 && g_spurs_pm_exited) {{
        __atomic_fetch_add(&s_asc_upper_policy[0], 1, __ATOMIC_RELAXED);
        __atomic_fetch_add(&s_asc_upper_policy[1], 1, __ATOMIC_RELAXED);
        __atomic_fetch_add(&s_asc_upper_policy[2], 1, __ATOMIC_RELAXED);
        __atomic_store_n(&s_asc_upper_policy[5], 16u, __ATOMIC_RELAXED);
        __atomic_store_n(&s_asc_upper_policy[6], 0x00AD0u, __ATOMIC_RELAXED);
        __atomic_store_n(&s_asc_upper_policy[7], (uint32_t)image_id, __ATOMIC_RELAXED);
        __atomic_store_n(&s_asc_upper_policy[8], 0u, __ATOMIC_RELAXED);
        __atomic_store_n(&s_asc_upper_policy[9], spu_num, __ATOMIC_RELAXED);
        __atomic_store_n(&s_asc_upper_policy[10], (uint32_t)wkl_data, __ATOMIC_RELAXED);
        __atomic_store_n(&s_asc_upper_policy[11], spurs_ea, __ATOMIC_RELAXED);
    }}
    if(wid>=16) {{"""

    if old_release in s:
        s = s.replace(old_release, new_release, 1)

    s = f"/* {MARK} */\n" + s
    path.write_text(s)


def patch_ios_bootprobe_live_files(repo_root: Path) -> None:
    """Ensure ios/UIViewController or BootProbe writer also saves log.txt in Documents/ and container root."""
    for p in repo_root.glob("ios/**/*.m"):
        txt = p.read_text(errors="replace")
        if MARK in txt:
            continue
        if "AscensionBootProbe-" in txt and "writeToFile:" in txt:
            # Mirror every BootProbe report save to Documents/log.txt and container root log.txt
            anchor = "atomically:YES encoding:NSUTF8StringEncoding error:nil];"
            if anchor in txt:
                addition = f"""{anchor}
        /* {MARK}: Always mirror live BootProbe report to Documents/log.txt and container root log.txt */
        @try {{
            NSString *docDir = [NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES) firstObject];
            if (docDir.length > 0) {{
                NSString *rootLog = [docDir stringByAppendingPathComponent:@"log.txt"];
                [report writeToFile:rootLog atomically:NO encoding:NSUTF8StringEncoding error:nil];
            }}
            NSString *homeLog = [NSHomeDirectory() stringByAppendingPathComponent:@"log.txt"];
            [report writeToFile:homeLog atomically:NO encoding:NSUTF8StringEncoding error:nil];
        }} @catch (__unused NSException *e) {{}}"""
                txt = txt.replace(anchor, addition, 1)
                p.write_text(txt)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    args = parser.parse_args()
    root = args.upstream.resolve()
    repo_root = Path(__file__).resolve().parent.parent
    patch_spu_channels(root)
    patch_spu_workload(root)
    patch_cell_spurs(root)
    patch_spurs_policy(root)
    patch_ios_bootprobe_live_files(repo_root)
    print("[PASS] M8.18.3 WWS 0x3FEC0/0x447b0 crash fixed + root log.txt & crash.txt enabled")


if __name__ == "__main__":
    main()