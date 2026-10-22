/* rePOP Xbox retail -> iOS host boot order, based on upstream
 * port/android/src/main_android.c @ 4ee36260e71d39fd8b02028fd614b1907a0d451b.
 * Compiles ONLY against the real rePOP runtime. No emulator or placeholder
 * implementation is linked into production. MIT integration source.
 */
#include "poptst_retail_boot.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <inttypes.h>
#include <limits.h>
#include <sys/stat.h>

#include "platform/win32_compat.h"
#include "kernel.h"
#include "xbox_memory_layout.h"
#include "apu.h"
#include "target.h"
#include "host_files.h"
#include "sha256.h"

#ifndef RESOT_RUNTIME_RETAIL
#error "PoPTST supports xbox-retail only"
#endif
#if defined(RESOT_RUNTIME_DEMO)
#error "Do not build the demo as an iOS app"
#endif

extern RECOMP_TLS uint32_t g_esp;
extern ptrdiff_t g_xbox_mem_offset;
extern MCPXAPUState *g_apu_state;
extern void xbe_entry_point(void);
extern int recomp_dispatch_init(void);
extern void xbox_OhciInit(void);
extern void xbox_path_init(const char *, const char *);
extern void xbox_WatchdogStart(void);
extern void poptst_engine_report_status(const char *message);
extern const char *poptst_ios_vm_failure_detail(void);
extern void poptst_engine_guest_entered_aot(void);

static void error_text(char *why, unsigned cap, const char *message)
{
    if (why && cap) snprintf(why, cap, "%s", message);
}

static int file_present(const char *dir, const char *item, int directory)
{
    return resot_path_kind(dir, item, NULL, 0) == (directory ? 2 : 1);
}

static int validate_tree(const char *dir, char *why, unsigned cap)
{
    static const struct { const char *name; int isdir; } required[] = {
        {"default.xbe",0}, {"prince.bf",0}, {"shaders.bin",0},
        {"VIDEO",1}, {"SOUND",1}, {"MEDIA",1}, {"POP1",1}, {"POP2",1}
    };
    unsigned i;
    for (i = 0; i < sizeof(required)/sizeof(required[0]); ++i) {
        if (!file_present(dir, required[i].name, required[i].isdir)) {
            if (why && cap) snprintf(why, cap, "Missing retail input: %s", required[i].name);
            return 0;
        }
    }
    return 1;
}

static int verified_retail_xbe(const char *dir, void **output, size_t *size,
                              char *why, unsigned cap)
{
    char path[4096];
    char digest[65];
    FILE *f;
    long length;
    void *memory;
    ResotSha256 checksum;

    if (resot_path_kind(dir, "default.xbe", path, sizeof(path)) != 1) {
        error_text(why, cap, "Cannot locate retail default.xbe");
        return 0;
    }
    f = fopen(path, "rb");
    if (!f) { error_text(why,cap,"Cannot open retail default.xbe"); return 0; }
    /* Match Swift's validation: only the first 4,603,904 bytes are the XBE.
     * Some Colab extracts append arbitrary ISO data; ignore the suffix,
     * authenticate the exact retail XBE prefix, never execute extra bytes. */
    const size_t guest_xbe_size = 4603904u;
    if (fseek(f, 0, SEEK_END) || (length = ftell(f)) < 0 ||
        (unsigned long)length < guest_xbe_size ||
        (unsigned long)length > 64u * 1024u * 1024u || fseek(f, 0, SEEK_SET)) {
        fclose(f);
        error_text(why,cap,"Retail XBE invalid length (expected 4603904-byte prefix)");
        return 0;
    }
    memory = malloc(guest_xbe_size);
    if (!memory || fread(memory, 1, guest_xbe_size, f) != guest_xbe_size) {
        free(memory); fclose(f);
        error_text(why,cap,"Could not read retail XBE into memory");
        return 0;
    }
    /* The user's Colab extraction proved the 15-MiB XBE suffix may contain
     * nonzero ISO data. Ignore it entirely after verifying the exact retail
     * 4,603,904-byte prefix. It is never copied to guest executable memory. */
    fclose(f);
    resot_sha256_init(&checksum);
    resot_sha256_update(&checksum, memory, guest_xbe_size);
    resot_sha256_hex(&checksum, digest);
    if (strcmp(digest, RESOT_XBE_SHA256) != 0) {
        free(memory);
        error_text(why,cap,"Retail XBE SHA-256 does not match supported release");
        return 0;
    }
    *output = memory; *size = guest_xbe_size;
    return 1;
}

int poptst_boot_retail(const char *game_dir, const char *data_dir,
                       char *why, unsigned why_capacity)
{
    void *xbe = NULL;
    size_t xbe_bytes = 0;
    char saves[4096];
    struct stat st;
    if (why && why_capacity) *why = 0;
    if (!game_dir || !data_dir || !*game_dir || !*data_dir) {
        error_text(why,why_capacity,"Missing game or data folder"); return 1;
    }
    if (stat(data_dir,&st) || !S_ISDIR(st.st_mode)) {
        error_text(why,why_capacity,"Invalid writable sandbox"); return 1;
    }
    poptst_engine_report_status("Verificando arquivos retail e SHA-256…");
    if (!validate_tree(game_dir,why,why_capacity) ||
        !verified_retail_xbe(game_dir,&xbe,&xbe_bytes,why,why_capacity)) return 1;

    /* Do not permit guest execution without successful 4GB guest mapping. */
    poptst_engine_report_status("Reservando e mapeando memória Xbox (4 GiB)…");
    if (!xbox_MemoryLayoutInit(xbe, xbe_bytes)) {
        free(xbe);
        const char *vm_failure = poptst_ios_vm_failure_detail();
        error_text(why,why_capacity,(vm_failure && *vm_failure)
                   ? vm_failure : "Guest 4GiB layout unavailable (VM stage unreported)");
        return 1;
    }
    free(xbe);
    g_xbox_mem_offset = xbox_GetMemoryOffset();
    {
        extern void poptst_engine_trace(const char *);
        char vm[160];
        snprintf(vm,sizeof vm,"VM ADDRESS BASE guest_zero=0x%016llX",
                 (unsigned long long)(uintptr_t)g_xbox_mem_offset);
        poptst_engine_trace(vm);
    }

    /* Upstream retail order: device, kernel, guest filesystem, bridge,
     * optional mirror + sound hooks, input bus, stack, indirect dispatch. */
    poptst_engine_report_status("Inicializando APU e kernel Xbox…");
    g_apu_state = mcpx_apu_init_standalone((uint8_t *)xbox_GetMemoryBase());
    if (!g_apu_state) {
        error_text(why,why_capacity,"APU initialization failed"); return 1;
    }
    xbox_kernel_init();
    if (snprintf(saves,sizeof saves,"%s/saves/xbox-retail",data_dir) >= (int)sizeof saves) {
        error_text(why,why_capacity,"Save path exceeds platform limit"); return 1;
    }
    xbox_path_init(game_dir,saves);
    xbox_kernel_bridge_init();
#ifdef RESOT_D3D_DEVICE_GLOBAL
    xbox_Nv2aMirrorFence(RESOT_D3D_DEVICE_GLOBAL, RESOT_D3D_FENCE_ISSUED, RESOT_D3D_FENCE_GPU_PTR);
#endif
#ifdef RESOT_DSOUND_CODE_BEGIN
    xbox_SetApuPhysicalCallers(RESOT_DSOUND_CODE_BEGIN, RESOT_DSOUND_CODE_END);
#endif
    poptst_engine_report_status("Inicializando controles USB e despacho AOT…");
    xbox_OhciInit();
    g_esp = XBOX_STACK_TOP;
    if (!recomp_dispatch_init()) {
        /* The upstream retail dispatch supports the fallback lookup, but
         * any other missing symbol must still cause link failure. */
        fprintf(stderr,"[PoPTST] dispatch index unavailable; using rePOP fallback\n");
    }
    xbox_WatchdogStart();
    fprintf(stderr,"[PoPTST] retail AOT entry reached; XBE hash verified\n");
    poptst_engine_report_status("Executando código Xbox retail x86 recompilado para ARM64…");
    poptst_engine_guest_entered_aot();
    /* The last successful Build 15 checkpoint was immediately before this
     * call. Distinguish first instructions, Xbox ExitProcess, host signals,
     * and a normal return; never claim gameplay merely on reaching this VA. */
    extern void poptst_engine_trace(const char *);
    poptst_engine_trace("AOT ENTER: xbe_entry_point 0x00335753, before guest first instruction");
    xbe_entry_point(); /* real statically recompiled retail symbol */
    poptst_engine_trace("AOT RETURN: xbe_entry_point returned to iOS host");
    return 0;
}
