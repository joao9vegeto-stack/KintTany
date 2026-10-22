/* PoPTST iOS SDL3 launcher; real Xbox retail AOT is started by poptst_boot_retail.
 * The UIKit SwiftUI front-end is only the folder picker; SDL owns the game window.
 */
/* SwiftUI owns UIApplicationMain; SDL must not replace that entry point. */
#define SDL_MAIN_HANDLED 1
#include <SDL3/SDL_main.h>
#include <SDL3/SDL.h>
#include <SDL3/SDL_vulkan.h>
#include <pthread.h>
#if defined(__APPLE__)
#include <dispatch/dispatch.h>
#endif
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <limits.h>
#include <stdatomic.h>
#include <signal.h>
#include <fcntl.h>
#include <errno.h>
#include <time.h>
#include "poptst_retail_boot.h"

extern void xbox_FramebufferAndroidSetWindow(void *window);
extern void poptst_ios_install_faults(void);
extern void poptst_ios_touch_overlay_install(SDL_Window *window);
extern void poptst_ios_touch_overlay_uninstall(void);
extern void poptst_ios_touch_overlay_tick(void);
extern void xbox_FramebufferSetWowProvider(void (*)(char *, size_t));
extern void resot_current_wow(char *, size_t);
extern void resot_android_input_start(SDL_Window *window);
extern void resot_android_input_event(const SDL_Event *event);
extern void resot_options_init(void);

static SDL_Window *window;
static char game_path[PATH_MAX], data_path[PATH_MAX];
static pthread_t guest;
static atomic_int game_done;
static atomic_int guest_entered_aot;
static atomic_int overlay_installed;
static atomic_int exit_to_menu;
static atomic_int native_exit_reported;
/* Count actual submitted NV2A/Vulkan swapchain frames, not SDL pump ticks.
 * A 0.5-second sliding measurement published atomically to UIKit. */
static atomic_int s_real_fps_tenths;
static atomic_uint_fast64_t s_last_present_ns;
void poptst_ios_fps_presented(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC,&ts);
    uint64_t now=(uint64_t)ts.tv_sec*1000000000ull+(uint64_t)ts.tv_nsec;
    static uint64_t start;
    static unsigned frames;
    if (!start) start=now;
    ++frames;
    if (now-start >= 500000000ull) {
        uint64_t duration=now-start;
        unsigned scaled=(unsigned)((uint64_t)frames*10000000000ull/duration);
        if (scaled>10000u) scaled=10000u;
        atomic_store_explicit(&s_real_fps_tenths,(int)scaled,memory_order_release);
        start=now; frames=0;
    }
    atomic_store_explicit(&s_last_present_ns,now,memory_order_release);
}
float poptst_ios_real_fps(void) {
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC,&ts);
    uint64_t now=(uint64_t)ts.tv_sec*1000000000ull+(uint64_t)ts.tv_nsec;
    uint64_t last=atomic_load_explicit(&s_last_present_ns,memory_order_acquire);
    if (!last || now-last>1200000000ull) return 0.0f;
    return (float)atomic_load_explicit(&s_real_fps_tenths,memory_order_acquire)*0.1f;
}
void poptst_engine_trace(const char *stage);


/* B23: SDL_gpu.h explicitly requires SDL_ClaimWindowForGPUDevice to run on
 * the SAME thread that created the SDL_Window. The window is created on
 * UIKit's main thread; the real NV2A GPU first boots from nv2a_ack_thread.
 * Dispatch ONLY swapchain/window ownership, keeping render commands on the
 * guest GPU worker. Dispatch_sync_f needs no compiler blocks flag and executes
 * the callback before the guest thread uses the swapchain. */
typedef struct {
    SDL_GPUDevice *device;
    SDL_Window *target;
    bool success;
    char error[192];
} PoPTSTGpuWindowOp;

static void poptst_gpu_claim_main(void *opaque) {
    PoPTSTGpuWindowOp *op=(PoPTSTGpuWindowOp *)opaque;
#if defined(__APPLE__)
    if (!pthread_main_np()) { op->success=false; return; }
#endif
    op->success=SDL_ClaimWindowForGPUDevice(op->device,op->target);
    if (!op->success) snprintf(op->error,sizeof op->error,"%s",SDL_GetError());
}
static void poptst_gpu_release_main(void *opaque) {
    PoPTSTGpuWindowOp *op=(PoPTSTGpuWindowOp *)opaque;
    SDL_ReleaseWindowFromGPUDevice(op->device,op->target);
}
bool poptst_ios_gpu_claim_window(SDL_GPUDevice *device, SDL_Window *target) {
    if (!device || !target || target != window) {
        poptst_engine_trace("GPU B23: rejected invalid/non-owner SDL window");
        return false;
    }
    PoPTSTGpuWindowOp op={0};
    op.device=device;op.target=target;
    poptst_engine_trace("GPU B23: claim dispatched to UIKit main thread");
#if defined(__APPLE__)
    if (pthread_main_np()) poptst_gpu_claim_main(&op);
    else dispatch_sync_f(dispatch_get_main_queue(),&op,poptst_gpu_claim_main);
#else
    poptst_gpu_claim_main(&op);
#endif
    if (op.success) {
        poptst_engine_trace("GPU B23: SDL window claimed + Metal/Vulkan surface created ON MAIN");
    } else {
        char msg[270];
        snprintf(msg,sizeof msg,"GPU B23: SDL claim FAILED: %s",op.error);
        poptst_engine_trace(msg);
    }
    return op.success;
}
void poptst_ios_gpu_release_window(SDL_GPUDevice *device, SDL_Window *target) {
    if (!device || !target || target != window) {
        poptst_engine_trace("GPU B23: release skipped invalid/non-owner SDL window");
        return;
    }
    PoPTSTGpuWindowOp op={0};
    op.device=device;op.target=target;
#if defined(__APPLE__)
    if (pthread_main_np()) poptst_gpu_release_main(&op);
    else dispatch_sync_f(dispatch_get_main_queue(),&op,poptst_gpu_release_main);
#else
    poptst_gpu_release_main(&op);
#endif
    poptst_engine_trace("GPU B23: SDL swapchain released ON MAIN; host window retained");
}


/* B23.3: SDL_GetWindowSizeInPixels and SDL_GetWindowFlags are also
 * explicitly main-thread-only in SDL3 release-3.4.18. NV2A previously
 * called both in its worker on each composed frame. Only UIKit main
 * reads the view; the GPU thread consumes C11 atomic snapshots. */
static atomic_int s_gpu_window_width;
static atomic_int s_gpu_window_height;
static atomic_uint_fast64_t s_gpu_window_flags;
static void poptst_gpu_capture_window_metrics_main(void) {
#if defined(__APPLE__)
    if (!pthread_main_np() || !window) return;
#endif
    if (!window) return;
    int w=0,h=0;
    (void)SDL_GetWindowSizeInPixels(window,&w,&h);
    SDL_WindowFlags flags=SDL_GetWindowFlags(window);
    atomic_store_explicit(&s_gpu_window_width,w,memory_order_release);
    atomic_store_explicit(&s_gpu_window_height,h,memory_order_release);
    atomic_store_explicit(&s_gpu_window_flags,(uint_fast64_t)flags,memory_order_release);
}
bool poptst_ios_gpu_window_size(SDL_Window *target,int *w,int *h) {
    if (!target || target!=window) {
        if (w) *w=0;
        if (h) *h=0;
        return false;
    }
    if (w) *w=atomic_load_explicit(&s_gpu_window_width,memory_order_acquire);
    if (h) *h=atomic_load_explicit(&s_gpu_window_height,memory_order_acquire);
    return true;
}
SDL_WindowFlags poptst_ios_gpu_window_flags(SDL_Window *target) {
    if (!target || target!=window) return SDL_WINDOW_HIDDEN;
    return (SDL_WindowFlags)atomic_load_explicit(&s_gpu_window_flags,memory_order_acquire);
}

/* Xbox x86 I/O port instructions reached from the retail D3D8 lifted code.
 * Port 0x80C0 is the video-encoder field/status pin, not NV2A MMIO.
 * Fail closed for unsupported port addresses; never quietly skip I/O.
 * These source mappings are validated against original XBE VAs by CI. */
static atomic_uint s_video_pin_ctl;
static atomic_int s_port_io_seen;
void poptst_guest_out8(uint16_t port, uint8_t value, uint32_t va) {
    if (port != 0x80C0u) {
        char m[160]; snprintf(m,sizeof(m),"FATAL: Xbox OUT8 unsupported port=0x%04X value=0x%02X VA=0x%08X",(unsigned)port,(unsigned)value,va);
        poptst_engine_trace(m);
        __builtin_trap();
    }
    atomic_store_explicit(&s_video_pin_ctl,value,memory_order_relaxed);
    if (!atomic_exchange(&s_port_io_seen,1)) {
        char m[130]; snprintf(m,sizeof(m),"Xbox D3D8 I/O OUT8 field pin port=0x%04X value=0x%02X VA=0x%08X",(unsigned)port,(unsigned)value,va);
        poptst_engine_trace(m);
    }
}
uint8_t poptst_guest_in8(uint16_t port, uint32_t va) {
    if (port != 0x80C0u) {
        char m[150]; snprintf(m,sizeof(m),"FATAL: Xbox IN8 unsupported port=0x%04X VA=0x%08X",(unsigned)port,va);
        poptst_engine_trace(m);
        __builtin_trap();
    }
    /* Original D3D code tests bit 5: video field parity. No guest GPU frame
     * clock is available during first init; use host monotonic ~59.94 Hz
     * alternation until an actual NV2A vblank counter is exposed. */
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC,&ts);
    uint64_t ns = (uint64_t)ts.tv_sec*1000000000ull+(uint64_t)ts.tv_nsec;
    uint8_t parity=((ns/16683350ull)&1u) ? 0x20u : 0u;
    return (uint8_t)((atomic_load(&s_video_pin_ctl)&0xDFu) | parity);
}
void poptst_guest_wbinvd(uint32_t va) {
    /* The iOS CPU sees the same coherent guest mmap RAM backing through
     * every alias. An ordering barrier is still required at this x86 site;
     * GPU DMA cache synchronization is a separate backend responsibility. */
    atomic_thread_fence(memory_order_seq_cst);
    static atomic_int logged;
    if (!atomic_exchange(&logged,1)) {
        char m[108]; snprintf(m,sizeof(m),"Xbox D3D8 WBINVD guest cache fence VA=0x%08X",va);
        poptst_engine_trace(m);
    }
}

static char status_text[512] = "Não iniciado";
static pthread_mutex_t status_mutex = PTHREAD_MUTEX_INITIALIZER;
/* Build 16: persistent breadcrumbs survive process death in LiveContainer.
 * No memory allocation/stdio/locks in a synchronous fatal-signal handler. */
static volatile sig_atomic_t s_crash_fd = -1;
void poptst_engine_trace(const char *stage) {
    int fd = (int)s_crash_fd;
    if (fd < 0 || !stage) return;
    int saved = errno;
    char line[720];
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    int n = snprintf(line, sizeof line, "%lld.%03ld  %s\n",
        (long long)ts.tv_sec, ts.tv_nsec / 1000000L, stage);
    if (n > 0) {
        size_t len = (size_t)n < sizeof line ? (size_t)n : sizeof line - 1u;
        (void)write(fd, line, len);
        (void)fsync(fd);  /* boot checkpoints are rare; persist before fatal exit */
    }
    errno = saved;
}
/* Native iOS ExitProcess must not tear down LiveContainer's shared host.
 * Invoked by the real rePOP guest on a guest-thread; caller terminates that
 * thread via pthread_exit while the SwiftUI main/UI process stays alive.
 * The guest may have other workers, so GPU/VM resources are retained. */
void poptst_engine_report_status(const char *message);
void poptst_engine_guest_request_exit(unsigned code, uintptr_t caller) {
    char detail[320];
    snprintf(detail,sizeof detail,"Xbox ExitProcess code=%u caller=0x%llx, stage=%s",
        code,(unsigned long long)caller,
        atomic_load(&guest_entered_aot)?"guest AOT":"pre-AOT");
    poptst_engine_trace(detail);
    atomic_store(&native_exit_reported,1);
    atomic_store(&exit_to_menu,1);
    atomic_store(&game_done,1);
    if (code) {
        char fail[400]; snprintf(fail,sizeof fail,"FATAL: %s",detail);
        poptst_engine_report_status(fail);
    } else {
        char ok[400]; snprintf(ok,sizeof ok,"MENU: %s",detail);
        poptst_engine_report_status(ok);
    }
}
static void poptst_atexit_trace(void) {
    poptst_engine_trace("HOST atexit invoked: libc exit/normal process termination");
}
void poptst_engine_set_trace_path(const char *path) {
    if (!path || !*path) return;
    int fd = open(path, O_WRONLY|O_APPEND|O_CREAT|O_CLOEXEC, 0600);
    if (fd < 0) return;
    int prev = (int)s_crash_fd;
    s_crash_fd = (sig_atomic_t)fd;
    if (prev >= 0) close(prev);
    poptst_engine_trace("BUILD 28 trace opened; app launcher entered boot");
}
static char *poptst_hex16(char *p, uintptr_t value) {
    static const char digits[] = "0123456789abcdef";
    for (int i = (int)(sizeof(uintptr_t)*2u)-1; i >= 0; --i)
        *p++ = digits[(value >> (i*4)) & 15u];
    return p;
}
/* Async-signal-safe: only stack, arithmetic and write. Safe from SIGBUS/SEGV,
 * SIGILL and SIGABRT; no printf or malloc from signal context. */
void poptst_engine_signal_event(int sig, uintptr_t fault, uintptr_t pc) {
    int fd=(int)s_crash_fd;
    if (fd<0) return;
    char buf[108], *p=buf;
    const char *start="FATAL SIGNAL ";
    while (*start) *p++=*start++;
    *p++='0'+((sig/10)%10); *p++='0'+(sig%10);
    const char *tag=" host=0x"; while (*tag) *p++=*tag++;
    p=poptst_hex16(p,fault);
    tag=" pc=0x"; while (*tag) *p++=*tag++;
    p=poptst_hex16(p,pc);
    *p++='\n';
    (void)write(fd,buf,(size_t)(p-buf));
}


/* B19 real-fault provenance. Signal context: no malloc, locks, printf,
 * dladdr, file I/O except one write on an already-open descriptor. */
void poptst_engine_signal_detail(int sig, uintptr_t fault, uintptr_t pc,
                                 int si_code, uintptr_t guest_base,
                                 uintptr_t dylib_base) {
    int fd = (int)s_crash_fd;
    if (fd < 0) return;
    char buf[300], *p = buf;
    const char *label = "SIGDETAIL sig=0x";
    while (*label) *p++ = *label++;
    p = poptst_hex16(p, (uintptr_t)(unsigned)sig);
    label = " code=0x";
    while (*label) *p++ = *label++;
    p = poptst_hex16(p, (uintptr_t)(uint32_t)si_code);
    label = " guest_base=0x";
    while (*label) *p++ = *label++;
    p = poptst_hex16(p, guest_base);
    label = " host_addr=0x";
    while (*label) *p++ = *label++;
    p = poptst_hex16(p, fault);
    if (guest_base && fault >= guest_base && fault - guest_base < 0x100000000ULL) {
        label = " xbox_va=0x";
        while (*label) *p++ = *label++;
        p = poptst_hex16(p, fault - guest_base);
    } else {
        label = " xbox_va=OUTSIDE_GUEST_RANGE";
        while (*label) *p++ = *label++;
    }
    label = " image_base=0x";
    while (*label) *p++ = *label++;
    p = poptst_hex16(p, dylib_base);
    label = " pc=0x";
    while (*label) *p++ = *label++;
    p = poptst_hex16(p, pc);
    if (dylib_base && pc >= dylib_base && pc - dylib_base < 0x2200000ULL) {
        label = " dylib_offset=0x";
        while (*label) *p++ = *label++;
        p = poptst_hex16(p, pc - dylib_base);
    } else {
        label = " dylib_offset=OUTSIDE_RETAIL_IMAGE";
        while (*label) *p++ = *label++;
    }
    *p++ = '\n';
    (void)write(fd, buf, (size_t)(p-buf));
}

/* B20: upstream Android prints AArch64 PC/LR and title registers on fatal
 * faults. Keep the equivalent iOS payload within async-signal-safe writes. */
void poptst_engine_signal_registers(uintptr_t lr, uintptr_t sp,
                                    uintptr_t x0, uintptr_t x1,
                                    uintptr_t x2, uintptr_t x3) {
    int fd = (int)s_crash_fd;
    if (fd < 0) return;
    char buf[220], *p=buf;
    const char *lab="ARM64REG lr=0x";
    while(*lab)*p++=*lab++;
    p=poptst_hex16(p,lr);
    lab=" sp=0x";while(*lab)*p++=*lab++;
    p=poptst_hex16(p,sp);
    lab=" x0=0x";while(*lab)*p++=*lab++;
    p=poptst_hex16(p,x0);
    lab=" x1=0x";while(*lab)*p++=*lab++;
    p=poptst_hex16(p,x1);
    lab=" x2=0x";while(*lab)*p++=*lab++;
    p=poptst_hex16(p,x2);
    lab=" x3=0x";while(*lab)*p++=*lab++;
    p=poptst_hex16(p,x3);
    *p++='\n';
    (void)write(fd,buf,(size_t)(p-buf));
}

/* Publish progress from the guest thread without racing SwiftUI's polling. */
void poptst_engine_report_status(const char *message) {
    if (!message) return;
    pthread_mutex_lock(&status_mutex);
    snprintf(status_text, sizeof status_text, "%s", message);
    pthread_mutex_unlock(&status_mutex);
    poptst_engine_trace(message);
    fprintf(stderr, "[PoPTST] %s\n", message);
    fflush(stderr);
}
static void poptst_engine_report_error(const char *prefix, const char *detail) {
    char buf[512];
    snprintf(buf, sizeof buf, "FATAL: %s: %s", prefix, detail ? detail : "unknown");
    poptst_engine_report_status(buf);
}


int poptst_engine_can_start(void) { return window == NULL; }
const char *resot_android_data_dir(void) { return data_path; }
void resot_android_wait_foreground(void) { /* iOS background is driven by SDL and app lifecycle; no unbounded spin. */ }
void resot_android_set_frame_limit(int fps) { (void)fps; /* xbox_SetFrameLimit owns guest frame pacing */ }
const char *poptst_engine_status(void) {
    static _Thread_local char safe_snapshot[512];
    pthread_mutex_lock(&status_mutex);
    memcpy(safe_snapshot, status_text, sizeof status_text);
    pthread_mutex_unlock(&status_mutex);
    safe_snapshot[sizeof safe_snapshot - 1] = '\0';
    return safe_snapshot;
}

/* Called on the guest thread only when the actual x86 AOT entry is reached;
 * never install controls above SwiftUI during guest-memory preflight. */
void poptst_engine_guest_entered_aot(void) { atomic_store(&guest_entered_aot,1); }

/* The Xbox AOT guest, NV2A and audio use background threads that cannot
 * be pthread_cancel'ed while holding kernel/SDL/Vulkan locks. On iOS, there is
 * NO safe way to return to the launcher and destroy them independently yet.
 * Unlike B26's hidden window, an explicit confirmed EXIT MUST actually stop
 * the entire process. Users relaunch PoPTST/LiveContainer to play again. */
const char *poptst_engine_data_path(void) { return data_path; }
void poptst_engine_exit_to_launcher(void) {
    if (atomic_exchange(&exit_to_menu,1)) return;
    poptst_engine_trace("EXIT B27: user confirmed whole process termination; guest and GPU will not run hidden");
    int fd=(int)s_crash_fd;
    if (fd>=0) (void)fsync(fd);
    _exit(0);
}

static void *poptst_guest_thread(void *arg) {
    (void)arg;
    char why[384] = {0};
    poptst_ios_install_faults();
    poptst_engine_report_status("Inicializando Xbox retail recompilado");
    poptst_engine_trace("GUEST THREAD BOOT: after pthread_create, before memory/map/kernel");
    int code = poptst_boot_retail(game_path, data_path, why, sizeof why);
    poptst_engine_trace("Guest bootstrap returned normally; recording result");
    if (code != 0) {
        char detail[448];
        snprintf(detail,sizeof detail,"retail exited (%d): %s",code,why);
        poptst_engine_report_error("Falha no jogo",detail);
    } else {
        poptst_engine_report_status("Jogo encerrou normalmente");
    }
    poptst_engine_trace("guest thread finished; game_done=1");
    atomic_store(&game_done, 1);
    return NULL;
}

int poptst_engine_start(const char *game_dir, const char *data_dir) {
    if (!game_dir || !data_dir || window) return 1;
    if (strlen(game_dir) >= sizeof game_path || strlen(data_dir) >= sizeof data_path) return 1;
    strcpy(game_path,game_dir); strcpy(data_path,data_dir);
    poptst_engine_trace("engine_start: SwiftUI main thread, game/data paths accepted");
    {
        char roots[720];
        snprintf(roots,sizeof roots,"HOST ROOTS game=%.*s data=%.*s",
                 300,game_path,300,data_path);
        poptst_engine_trace(roots);
    }
    static atomic_bool atexit_installed = false;
    if (!atomic_exchange(&atexit_installed,true)) atexit(poptst_atexit_trace);
    atomic_store(&game_done,0);
    atomic_store(&guest_entered_aot,0);
    atomic_store(&overlay_installed,0);
    atomic_store(&exit_to_menu,0);
    atomic_store(&native_exit_reported,0);
    atomic_store(&s_real_fps_tenths,0);
    atomic_store(&s_last_present_ns,0);
    /* SDL3 iOS normally sets its SDL_MainIsReady flag inside the SDL
     * UIKitDelegate, but this app is already running under SwiftUI's @main.
     * SDL_SetMainReady must be called on the real UIKit main thread before
     * any SDL_Init call. Without it SDL_Init always fails with the
     * "did you include SDL_main.h" message seen on Build 12.
     * SDL_MAIN_HANDLED prevents SDL from supplying another UIApplicationMain. */
#if defined(__APPLE__)
    if (!pthread_main_np()) {
        poptst_engine_report_error("SDL bootstrap", "inicie a partir da thread principal UIKit");
        return 2;
    }
#endif
    poptst_engine_trace("SDL_SetMainReady before SDL_Init");
    SDL_SetMainReady();
    poptst_engine_report_status("Build 28: SDL3 pronto no @main SwiftUI; preparando Vulkan");
    if (chdir(data_dir)) { poptst_engine_report_error("Sandbox","diretório de saves inacessível"); return 1; }
    SDL_SetHint(SDL_HINT_ORIENTATIONS, "LandscapeLeft LandscapeRight");
    /* SDL UIKit loader's libvulkan.dylib adapter resolves the existing
       KosmicKrisp vk_icdGetInstanceProcAddr from our Frameworks folder. */
    const char *base = SDL_GetBasePath();
    if (base && strlen(base)+strlen("Frameworks/libvulkan.dylib") < PATH_MAX) {
        char loader[PATH_MAX];
        snprintf(loader,sizeof loader,"%sFrameworks/libvulkan.dylib",base);
        SDL_SetHint(SDL_HINT_VULKAN_LIBRARY,loader);
    }
    if (!SDL_Init(SDL_INIT_VIDEO | SDL_INIT_EVENTS | SDL_INIT_GAMEPAD | SDL_INIT_AUDIO)) {
        poptst_engine_report_error("SDL_Init",SDL_GetError()); SDL_Quit(); return 1;
    }
    poptst_engine_trace("SDL_Init passed; SDL_CreateWindow Vulkan next");
    window=SDL_CreateWindow("PoPTST retail", 0,0,
                            SDL_WINDOW_FULLSCREEN|SDL_WINDOW_HIGH_PIXEL_DENSITY|SDL_WINDOW_VULKAN);
    if (!window) {
        poptst_engine_report_error("SDL Vulkan window",SDL_GetError());
        SDL_Quit(); /* preserve the error text and allow retry without restart */
        return 1;
    }
    /* SDL3 creates a separate UIWindow from the SwiftUI launcher. Keep it
     * hidden until the guest has reached real AOT execution, otherwise a
     * failed 4-GiB reservation leaves virtual buttons covering Export Log. */
    SDL_HideWindow(window);
    poptst_gpu_capture_window_metrics_main();
    poptst_engine_report_status("Build 16: janela Vulkan preparada em segundo plano");
    setenv("RECOMP_PB_EXEC","1",0);
    setenv("RECOMP_FB_WINDOW","1",0);
    setenv("RECOMP_VBLANK","1",0);
    setenv("RECOMP_HW","1",0);
    setenv("RECOMP_AC97_READY","1",0);
    setenv("RECOMP_APU_DSP_ACK","gp+0x810",0);
    setenv("RECOMP_HEAP_RECLAIM","1",0);
    /* B28 visual correctness: rePOP native PSO async workers intentionally
     * SKIP guest draws while shader pipelines compile. On a tile GPU this
     * produces transient missing geometry/background (reported purple
     * flashes). Prefer preserving every draw, even if first-time shader
     * compilation causes a short stall. Scoped to iOS, not upstream Android. */
    setenv("RESOT_ASYNC_PIPELINES","0",1);
    poptst_engine_trace("GPU B28: iOS guest shader pipeline compilation synchronous; NO skipped guest draws");
    setenv("RESOT_RENDERER","vulkan",0);
    setenv("RECOMP_HW_ASPECT","16:9",0);
    xbox_FramebufferAndroidSetWindow(window);
    xbox_FramebufferSetWowProvider(resot_current_wow);
    resot_options_init();
    resot_android_input_start(window);
    pthread_attr_t attrs;
    pthread_attr_init(&attrs);
    pthread_attr_setstacksize(&attrs,64u*1024u*1024u);
    poptst_engine_trace("SDL window created; pthread_create guest thread next");
    if (pthread_create(&guest,&attrs,poptst_guest_thread,NULL)) {
        poptst_engine_report_error("Thread", "não foi possível iniciar o jogo");
        pthread_attr_destroy(&attrs);
        SDL_DestroyWindow(window); window=NULL;
        SDL_Quit();
        return 1;
    }
    pthread_attr_destroy(&attrs);
    pthread_detach(guest);
    return 0;
}
void poptst_engine_pump(void) {
    if (!window) return;
    poptst_gpu_capture_window_metrics_main();
    if (atomic_load(&game_done)) {
        poptst_ios_touch_overlay_uninstall();
        SDL_HideWindow(window);
        /* Only the pre-AOT path has no guest NV2A/worker lifecycle to tear
         * down. After AOT we retain the host resources until app exit to
         * avoid use-after-free by device workers. */
        if (!atomic_load(&guest_entered_aot)) {
            xbox_FramebufferAndroidSetWindow(NULL);
            SDL_DestroyWindow(window); window=NULL;
            SDL_Quit();
        }
        return;
    }
    if (atomic_load(&exit_to_menu)) return;
    if (atomic_load(&guest_entered_aot) && !atomic_exchange(&overlay_installed,1)) {
        SDL_ShowWindow(window);
        poptst_gpu_capture_window_metrics_main();
        poptst_ios_touch_overlay_install(window);
    }
    poptst_ios_touch_overlay_tick();
    SDL_Event e;
    while (SDL_PollEvent(&e)) {
        resot_android_input_event(&e);
        if (e.type == SDL_EVENT_TERMINATING || e.type == SDL_EVENT_QUIT) {
            poptst_engine_exit_to_launcher();
        }
    }
}
