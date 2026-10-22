#!/usr/bin/env python3
"""Apply explicit iOS portability patches to pinned rePOP; fail on unexpected sources.
No original game data is modified; retail only. Based on Android runtime semantics.
"""
from pathlib import Path
import sys

def sub(src, old, new, name):
    count=src.count(old)
    if count != 1: raise RuntimeError(f'{name}: expected one anchor, got {count}: {old[:90]}')
    return src.replace(old,new,1)

def main(root):
    fixes={
        'port/third_party/xboxrecomp/src/kernel/nv2a_hw_d3d11.inc': [
            ('#if defined(_WIN32) || defined(__ANDROID__)',
             '#if defined(_WIN32) || defined(__ANDROID__) || defined(__APPLE__)')],
        'port/third_party/xboxrecomp/src/video/fb_present.c': [
            ('#if defined(_WIN32) || defined(__ANDROID__)',
             '#if defined(_WIN32) || defined(__ANDROID__) || defined(__APPLE__)'),
            ('#if defined(__ANDROID__)\n    /* RE-SoT: avoid driving',
             '#if defined(__ANDROID__) || defined(__APPLE__)\n    /* RE-SoT: avoid driving'),
            ('#if defined(__ANDROID__)\n        /* RE-SoT: sleep',
             '#if defined(__ANDROID__) || defined(__APPLE__)\n        /* RE-SoT: sleep')],
        'port/third_party/xboxrecomp/src/kernel/nv2a_hw_native.inc': [
            ('''static void ng_submit_encoded(void)
{
    if (s_ng.cmd) {
        if (s_ng_visibility.pending) {
            SDL_GPUFence *fence = SDL_SubmitGPUCommandBufferAndAcquireFence(s_ng.cmd);
            if (!fence || !ng_vis_submitted(&s_ng_visibility,fence)) ng_fail("visibility submission fence");
        } else if (!SDL_SubmitGPUCommandBuffer(s_ng.cmd)) ng_fail("submit");
    }
    s_ng.cmd = NULL;
    /* RE-SoT: retain the append position across submissions; cycle only
     * when the vertex ring wraps, preserving resources used by prior draws. */
    s_ng.command_samplers = 0;
    s_ng.vc_valid = s_ng.pc_valid = 0;
    s_ng.last_cslot = s_ng.last_pslot = -1; /* RE-SoT: uniforms live per command buffer. */
}''','''static void ng_submit_encoded(void)
{
#if defined(__APPLE__)
    static unsigned long long submissions;
    int submitted=0;
#endif
    if (s_ng.cmd) {
        if (s_ng_visibility.pending) {
            SDL_GPUFence *fence = SDL_SubmitGPUCommandBufferAndAcquireFence(s_ng.cmd);
            if (!fence || !ng_vis_submitted(&s_ng_visibility,fence)) ng_fail("visibility submission fence");
#if defined(__APPLE__)
            submitted=1;
#endif
        } else if (!SDL_SubmitGPUCommandBuffer(s_ng.cmd)) ng_fail("submit");
#if defined(__APPLE__)
        else submitted=1;
#endif
    }
    s_ng.cmd = NULL;
#if defined(__APPLE__)
    /* Build24 iPhone: the fatal ARM64 path is exactly ng_fail("submit")
     * after SDL_SubmitGPUCommandBuffer returned false at ~4 minutes.
     * Periodically drain *completed GPU submissions*, not guest draws, so
     * Metal/KosmicKrisp can retire in-flight descriptor and buffer storage.
     * SDL-WaitForGPUIdle is documented to return a real success/error. */
    if (submitted) {
        ++submissions;
        if ((submissions % 24ull)==0) {
            if (!SDL_WaitForGPUIdle(s_ng.device)) ng_fail("B25 GPU backlog drain");
            if ((submissions % 240ull)==0) {
                char line[160];
                snprintf(line,sizeof line,
                         "GPU B25: drained GPU queue after %llu real command submissions",
                         submissions);
                poptst_engine_trace(line);
            }
        }
    }
#endif
    /* RE-SoT: retain the append position across submissions; cycle only
     * when the vertex ring wraps, preserving resources used by prior draws. */
    s_ng.command_samplers = 0;
    s_ng.vc_valid = s_ng.pc_valid = 0;
    s_ng.last_cslot = s_ng.last_pslot = -1; /* RE-SoT: uniforms live per command buffer. */
}'''),
            ('''static void ng_fail(const char *where)
{
    fprintf(stderr, "[HW native] fatal %s: %s\\n", where, SDL_GetError());
    abort(); /* RE-SoT: never silently lose submitted guest draws. */
}''','''static void ng_fail(const char *where)
{
#if defined(__APPLE__)
    /* Persist SDL's failure reason into the iPhone's exportable native
     * trace before the fail-closed abort; stderr was missing in B24 logs. */
    char detail[430];
    snprintf(detail,sizeof detail,"GPU B25 FATAL: %s; SDL: %.295s",
             where,SDL_GetError());
    poptst_engine_trace(detail);
#endif
    fprintf(stderr, "[HW native] fatal %s: %s\\n", where, SDL_GetError());
    abort(); /* RE-SoT: never silently lose submitted guest draws. */
}'''),

            ('#if defined(__ANDROID__)\n/* RE-SoT: Android links the patched SDL directly;',
             '#if defined(__ANDROID__) || defined(__APPLE__)\n/* RE-SoT: mobile links the patched SDL directly;'),
            ('#if !defined(__ANDROID__)\n    if (s_ng.window) SDL_DestroyWindow(s_ng.window);',
             '#if !defined(__ANDROID__) && !defined(__APPLE__)\n    if (s_ng.window) SDL_DestroyWindow(s_ng.window);'),
            ('#include <SDL3/SDL.h>\n#include "nv2a_native_shaders.h"',
             '#include <SDL3/SDL.h>\n#if defined(__APPLE__)\nextern bool poptst_ios_gpu_claim_window(SDL_GPUDevice *, SDL_Window *);\nextern void poptst_ios_gpu_release_window(SDL_GPUDevice *, SDL_Window *);\nextern bool poptst_ios_gpu_window_size(SDL_Window *, int *, int *);\nextern SDL_WindowFlags poptst_ios_gpu_window_flags(SDL_Window *);\nextern void poptst_engine_trace(const char *);\n#endif\n#include "nv2a_native_shaders.h"'),
            ('    if (!s_ng.device || !SDL_ClaimWindowForGPUDevice(s_ng.device, s_ng.window)) goto fail;',
             '''#if defined(__APPLE__)
    if (!s_ng.device || !poptst_ios_gpu_claim_window(s_ng.device, s_ng.window)) goto fail;
#else
    if (!s_ng.device || !SDL_ClaimWindowForGPUDevice(s_ng.device, s_ng.window)) goto fail;
#endif'''),
            ('        if (s_ng.window) SDL_ReleaseWindowFromGPUDevice(s_ng.device, s_ng.window);',
             '''#if defined(__APPLE__)
        if (s_ng.window) poptst_ios_gpu_release_window(s_ng.device, s_ng.window);
#else
        if (s_ng.window) SDL_ReleaseWindowFromGPUDevice(s_ng.device, s_ng.window);
#endif'''),
            ('    return 1;\nfail:\n    fprintf(stderr, "[HW native] %s initialization failed: %s; falling back to %s\\n", backend, SDL_GetError(),',
             '''#if defined(__APPLE__)
    poptst_engine_trace("GPU B23: native NV2A renderer initialized: device, shaders, queries");
#endif
    return 1;
fail:
#if defined(__APPLE__)
    poptst_engine_trace("GPU B23: native NV2A renderer initialization FAILED");
#endif
    fprintf(stderr, "[HW native] %s initialization failed: %s; falling back to %s\\n", backend, SDL_GetError(),'''),
            ('        SDL_GetWindowSizeInPixels(s_ng.window, &cw, &ch);',
             '''#if defined(__APPLE__)
        poptst_ios_gpu_window_size(s_ng.window, &cw, &ch);
#else
        SDL_GetWindowSizeInPixels(s_ng.window, &cw, &ch);
#endif'''),
            ('    if (!s_ng.composed || bw != s_ng.compose_w || bh != s_ng.compose_h) {',
             '''#if defined(__APPLE__)
    /* B28: on scale/orientation changes a newly allocated composed render
     * target has undefined previous contents. Clear it before LOAD/blit:
     * otherwise a single frame can expose arbitrary Metal tile memory. */
    int poptst_new_composed = !s_ng.composed || bw != s_ng.compose_w || bh != s_ng.compose_h;
#endif
    if (!s_ng.composed || bw != s_ng.compose_w || bh != s_ng.compose_h) {'''),
            ('    /* RE-SoT: combine the background clear with the front-surface draw.\n     * Tile GPUs otherwise store and reload a full display-sized attachment. */\n    if (!s_ng.front) {',
             '''    /* RE-SoT: combine the background clear with the front-surface draw.
     * Tile GPUs otherwise store and reload a full display-sized attachment. */
#if defined(__APPLE__)
    if (!s_ng.front || poptst_new_composed) {
#else
    if (!s_ng.front) {
#endif'''),
            ('    if (SDL_GetWindowFlags(s_ng.window) & SDL_WINDOW_MINIMIZED) return;',
             '''#if defined(__APPLE__)
    if (poptst_ios_gpu_window_flags(s_ng.window) & SDL_WINDOW_MINIMIZED) return;
#else
    if (SDL_GetWindowFlags(s_ng.window) & SDL_WINDOW_MINIMIZED) return;
#endif'''),
            ('#include <SDL3/SDL.h>\n#if defined(__APPLE__)\nextern bool poptst_ios_gpu_claim_window',
             '#include <SDL3/SDL.h>\n#if defined(__APPLE__)\nextern void poptst_ios_fps_presented(void);\nextern bool poptst_ios_gpu_claim_window'),
            ('    s_ng.device = SDL_CreateGPUDevice(SDL_GPU_SHADERFORMAT_DXIL | SDL_GPU_SHADERFORMAT_SPIRV,\n                                     getenv("RESOT_GPU_DEBUG") != NULL,\n                                     s_ng.active == 12 ? "direct3d12" : "vulkan");',
             '''    s_ng.device = SDL_CreateGPUDevice(SDL_GPU_SHADERFORMAT_DXIL | SDL_GPU_SHADERFORMAT_SPIRV,
                                     getenv("RESOT_GPU_DEBUG") != NULL,
                                     s_ng.active == 12 ? "direct3d12" : "vulkan");
#if defined(__APPLE__)
    /* 2026-10-22 iPhone crash: Metal IOGPU resource allocator aborted while
     * closing a guest NV2A render pass; .ips shows >1.1 GiB IOAccelerator.
     * Limit in-flight swapchain submissions to ONE on iOS, not Android.
     * This is a GPU pressure safeguard, not a claim of resolved driver bug. */
    if (s_ng.device && !SDL_SetGPUAllowedFramesInFlight(s_ng.device,1))
        fprintf(stderr,"[HW native] B24 1 frame-in-flight unsupported: %s\\n",SDL_GetError());
#endif'''),
            ('    uint32_t i;\n    void *mapped;\n    uint32_t staged;\n    if (!s_ng.queued_count) return;',
             '''    uint32_t i;
    void *mapped;
    uint32_t staged;
#if defined(__APPLE__)
    unsigned draws_in_command = 0;
#endif
    if (!s_ng.queued_count) return;'''),
            ('        new_samplers = !pass || last_color != draw->color || last_depth != draw->depth ||',
             '''#if defined(__APPLE__)
        /* Break long Metal resource tables before the IOGPU endEncoding
         * allocator grows unchecked. End/resolve actual queries, then
         * submit and reopen with LOAD so no guest draw is lost. */
        if (draws_in_command >= 48u && pass) {
            if (query) s_ng_visibility.api->end(s_ng.cmd,query->query);
            SDL_EndGPURenderPass(pass);
            if (query) s_ng_visibility.api->resolve(s_ng.cmd,query->query);
            query=NULL; pass=NULL;
            last_color=last_depth=NULL;
            bound_pipeline=NULL;bound_textures=NULL;bound_dynamic=NULL;
            ng_submit_encoded();
            draws_in_command=0;
        }
#endif
        new_samplers = !pass || last_color != draw->color || last_depth != draw->depth ||'''),
            ('        if (draw->index_count) {\n            /* RE-SoT: vs_uber',
             '''#if defined(__APPLE__)
        ++draws_in_command;
#endif
        if (draw->index_count) {
            /* RE-SoT: vs_uber'''),
            ('    ng_submit();\n    QueryPerformanceCounter(&after);\n    s_hw.present_ticks +=',
             '''    ng_submit();
#if defined(__APPLE__)
    if (swap) {
        poptst_ios_fps_presented();
        static volatile unsigned first_guest_present;
        if (!__atomic_exchange_n(&first_guest_present,1,__ATOMIC_RELAXED))
            poptst_engine_trace("GPU B23: FIRST REAL NV2A COMPOSED SWAPCHAIN FRAME SUBMITTED");
    }
#endif
    QueryPerformanceCounter(&after);
    s_hw.present_ticks +=''')],
        'port/third_party/xboxrecomp/src/kernel/nv2a_pb_exec.c': [
            ('#if defined(__ANDROID__)\n        n = e && *e ? atoi(e) : 0;',
             '#if defined(__ANDROID__) || defined(__APPLE__)\n        n = e && *e ? atoi(e) : 0;')],
        'port/third_party/xboxrecomp/src/kernel/guest_vmem.c': [
            ('#ifdef __ANDROID__\n    bytes = (GUEST_VMEM_TOP - s_lo)',
             '#if defined(__ANDROID__) || defined(__APPLE__)\n    bytes = (GUEST_VMEM_TOP - s_lo)')],
        'port/third_party/xboxrecomp/src/kernel/xbox_memory_layout.c': [
            ('#if defined(__ANDROID__)\n        /* RE-SoT: reserve the whole 4 GB guest space.',
             '#if defined(__ANDROID__) || defined(__APPLE__)\n        /* RE-SoT: reserve the whole 4 GB guest space.'),
            ('#if defined(__ANDROID__)\n        if (g_span_base)',
             '#if defined(__ANDROID__) || defined(__APPLE__)\n        if (g_span_base)')],
    }
    updates={}
    for path, pairs in fixes.items():
        f=root/path
        data=f.read_text()
        for old,new in pairs:data=sub(data,old,new,path)
        updates[f]=data
    # Android input bridge is platform-neutral below the JNI controls: retain
    # physical gamepad mapping unchanged while supplying iOS touch state.
    android=(root/'port/android/src/input_android.c').read_text()
    android=sub(android,'#include <jni.h>\n','', 'input JNI include')
    first=android.index('/* ── touch (TouchControls.java, UI thread) ──')
    after=android.index('/* ── physical gamepads (SDL thread opens them) ──',first)
    touch='''/* iOS touch state: same Xbox pad field contract as upstream Android. */
static pthread_mutex_t s_touch_lock = PTHREAD_MUTEX_INITIALIZER;
static int32_t s_touch[7];
static volatile int s_rumble;
void poptst_touch_state(int32_t lx, int32_t ly, int32_t rx, int32_t ry,
                        int32_t lt, int32_t rt, int32_t buttons) {
    pthread_mutex_lock(&s_touch_lock);
    int32_t incoming[7]={lx,ly,rx,ry,lt,rt,buttons};
    memcpy(s_touch,incoming,sizeof incoming);
    pthread_mutex_unlock(&s_touch_lock);
}
'''
    android=android[:first]+touch+'\n'+android[after:]
    # B26: rePOP routes analog axes [4] and [5] into XBOX_BUTTON_LTRIGGER
    # / XBOX_BUTTON_RTRIGGER. Explicit RT/LT touch controls set those axis
    # slots; no synthetic keys, no overriding Xbox game-native bindings.
    # The main menu calls the retail title-specific camera hook at sub_000DBDE0.
    # B25 changed only the phone's pad deflection while the authoritative
    # s_look_sensitivity remained at the default 200%%. Expose a setter so
    # changing CAM updates the post-deadzone multiplier inside the game.
    option_path=root/'port/android/src/options_android.c'
    options=option_path.read_text()
    options=sub(options,'void resot_scale_look(float *axes)\n{',
        '''void poptst_ios_set_look_percent(int percent)
{
    AcquireSRWLockExclusive(&s_lock);
    s_look_sensitivity=resot_look_percent(percent);
    ReleaseSRWLockExclusive(&s_lock);
}
void resot_scale_look(float *axes)
{''','B26 native real retail camera sensitivity')
    updates[option_path]=options
    # Keep exact existing SDL gamepad->Xbox logic (including axis inversion,
    # movie skip and options filtering) without importing Android JNI code.
    out=root/'port/ios/generated_input_ios.c'
    out.parent.mkdir(parents=True, exist_ok=True)
    updates[out]=android
    for path,content in updates.items():
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(content)
    patch_ios_mach_compat(root)
    patch_posix_win32_traps(root)
    print('PoPTST patched',len(updates)+1,'rePOP sources; retail only; iPhoneOS mmap64')


def patch_ios_mach_compat(root):
    # iPhoneOS SDK deliberately blocks <mach/mach_vm.h>. On iOS, use 64-bit
    # mmap without MAP_FIXED for other allocations; MAP_FIXED only replaces
    # pages in the 4GiB guest mapping we explicitly own.
    path=root/'port/third_party/xboxrecomp/src/platform/win32_compat.c'
    s=path.read_text()
    s=sub(s,'#include <mach/mach_vm.h>',
        '#include <TargetConditionals.h>\n#if !TARGET_OS_IPHONE\n#include <mach/mach_vm.h>\n#endif\n#if TARGET_OS_IPHONE && !defined(MAP_NORESERVE)\n#define MAP_NORESERVE 0\n#endif',
        'Darwin iPhoneOS mach_vm.h')
    s=sub(s,'static void *mach_map_fixed(void *address, size_t size, int prot)\n{',
        '''static void *mach_map_fixed(void *address, size_t size, int prot, int owned)
{
#if TARGET_OS_IPHONE
    const int flags=MAP_PRIVATE | MAP_ANONYMOUS | (owned ? MAP_FIXED : 0);
    void *p=mmap(address,size,prot,flags,-1,0);
    if (p != address) {
        if (p != MAP_FAILED) munmap(p,size);
        return MAP_FAILED;
    }
    return p;
#else
    (void)owned;''','Darwin iPhoneOS mmap64')
    s=sub(s,'    return (void *)(uintptr_t)addr;\n}\n#endif',
        '    return (void *)(uintptr_t)addr;\n#endif\n}\n#endif',
        'Darwin compat mapping close')
    s=sub(s,'p = mach_map_fixed(address, size, prot ? prot : PROT_READ | PROT_WRITE);',
        'p = mach_map_fixed(address, size, prot, owned);',
        'Darwin preserve PROT_NONE and only owned fixed allocation')
    # The second mach_map_fixed call lives inside MapViewOfFileEx and can be
    # reached for a guest address outside our reserved 4 GiB. iPhoneOS does
    # not provide mach_vm_map and MAP_FIXED there would replace unknown
    # allocations. Refuse this case, never silently remap a foreign range.
    s=sub(s,'        if (mach_map_fixed(baseAddr, len, PROT_READ | PROT_WRITE) == MAP_FAILED) {',
        '''#if TARGET_OS_IPHONE
        SetLastError(ERROR_INVALID_ADDRESS);
        return NULL;
#else
        if (mach_map_fixed(baseAddr, len, PROT_READ | PROT_WRITE, 0) == MAP_FAILED) {''',
        'MapViewOfFileEx Darwin 4 argument mach_map_fixed')
    s=sub(s,'        flags |= MAP_FIXED;\n#else\n        flags |= MAP_FIXED;\n#endif\n    }',
        '''        flags |= MAP_FIXED;
#endif /* TARGET_OS_IPHONE */
#else
        flags |= MAP_FIXED;
#endif
    }''',
        'Darwin non-iPhone fixed-view close')
    path.write_text(s)



def patch_posix_win32_traps(root):
    # Windows vectored-exception callbacks dereference Windows-only CONTEXT
    # members and must not be compiled under iPhoneOS. POSIX has native
    # SIGSEGV/MMIO decoder instead. Never silently translate these handlers.
    path=root/'port/third_party/xboxrecomp/src/kernel/xbox_memory_layout.c'
    s=path.read_text()
    s=sub(s,'static LONG CALLBACK ac97_write_veh(PEXCEPTION_POINTERS ep)',
        '#if defined(_WIN32)\nstatic LONG CALLBACK ac97_write_veh(PEXCEPTION_POINTERS ep)',
        'guard Win32 AC97 VEH declaration')
    s=sub(s,'    return EXCEPTION_CONTINUE_SEARCH;\n}\n\n/* Arm the trap.',
        '    return EXCEPTION_CONTINUE_SEARCH;\n}\n#endif /* _WIN32 AC97 VEH */\n\n/* Arm the trap.',
        'guard Win32 AC97 VEH definition')
    s=sub(s,'    g_ac97_veh = AddVectoredExceptionHandler(1, ac97_write_veh);',
        '#if defined(_WIN32)\n    g_ac97_veh = AddVectoredExceptionHandler(1, ac97_write_veh);',
        'guard Win32 AC97 VEH installation')
    s=sub(s,'            XBOX_MCPX_BASE + AC97_NABM_OFFSET);\n}\n\n#if defined(__ANDROID__) && defined(__aarch64__)',
        '            XBOX_MCPX_BASE + AC97_NABM_OFFSET);\n#endif /* Win32 install */\n}\n\n#if defined(__ANDROID__) && defined(__aarch64__)',
        'guard Win32 AC97 VEH installer')
    s=sub(s,'static LONG CALLBACK watch_veh(PEXCEPTION_POINTERS ep)',
        '#if defined(_WIN32)\nstatic LONG CALLBACK watch_veh(PEXCEPTION_POINTERS ep)',
        'guard Win32 memory watch VEH declaration')
    s=sub(s,'    return EXCEPTION_CONTINUE_SEARCH;\n}\n\n/* The target, which may be reached',
        '    return EXCEPTION_CONTINUE_SEARCH;\n}\n#endif /* Win32 watch VEH */\n\n/* The target, which may be reached',
        'guard Win32 memory watch VEH definition')
    s=sub(s,'static int watch_arm(uint32_t va)\n{\n    DWORD old;',
        'static int watch_arm(uint32_t va)\n{\n#if defined(_WIN32)\n    DWORD old;',
        'guard Win32 memory watch installation')
    s=sub(s,'    return 1;\n}\n\n/* Print the RECOMP_PEEK globals.',
        '    return 1;\n#else\n    (void)va;\n    fprintf(stderr,"  WATCH: Windows VEH watch unsupported on iOS; no memory page modified\\n");\n    return 0;\n#endif\n}\n\n/* Print the RECOMP_PEEK globals.',
        'fail safely on unsupported iOS page watch')
    path.write_text(s)

if __name__=='__main__':
    if len(sys.argv)!=2: raise SystemExit('usage: patch_repop_ios.py <repop checkout>')
    main(Path(sys.argv[1]).resolve())
