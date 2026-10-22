/* PoPTST: Vulkan loader adapter for the user's prebuilt KosmicKrisp ICD.
 * Copyright (c) 2026. MIT. Does not contain the Xbox executable or game code.
 * This translation unit has NO dependency on RPCS3. It exposes the single
 * SDL3 UIKit Vulkan loader entry point and delegates to the existing ICD.
 *
 * Link as Frameworks/libvulkan.dylib, place libKosmicKrisp.dylib beside it,
 * and set SDL_HINT_VULKAN_LIBRARY to the full libvulkan.dylib path before SDL_Init.
 */
#include <dlfcn.h>
#include <stdio.h>
#include <string.h>
#include <pthread.h>

#ifndef RTLD_LOCAL
#define RTLD_LOCAL 0
#endif

typedef struct VkInstance_T *PoPTSTVkInstance;
typedef void (*PoPTSTVkVoidFunction)(void);
typedef PoPTSTVkVoidFunction (*PoPTSTICDGetInstanceProcAddr)(PoPTSTVkInstance, const char *);

static void *s_icd;
static PoPTSTICDGetInstanceProcAddr s_icd_get;
static pthread_once_t s_icd_once = PTHREAD_ONCE_INIT;
static char s_error[512];

static void poptst_init_icd(void)
{
    /* @loader_path resolves relative to this shim's Frameworks/ directory;
     * avoids global library lookup and reuses the exact user-tested binary. */
    s_icd = dlopen("@loader_path/libKosmicKrisp.dylib", RTLD_NOW | RTLD_LOCAL);
    if (!s_icd) {
        const char *failure = dlerror();
        snprintf(s_error, sizeof s_error, "KosmicKrisp unavailable: %s", failure ? failure : "dlopen failed");
        return;
    }
    void *sym = dlsym(s_icd, "vk_icdGetInstanceProcAddr");
    if (!sym) {
        snprintf(s_error, sizeof s_error, "KosmicKrisp lacks vk_icdGetInstanceProcAddr");
        return;
    }
    /* dlsym converts to a function pointer on Apple and other POSIX ABIs. */
    memcpy(&s_icd_get, &sym, sizeof s_icd_get);
}

__attribute__((visibility("default")))
PoPTSTVkVoidFunction vkGetInstanceProcAddr(PoPTSTVkInstance instance, const char *name)
{
    if (!name) return NULL;
    pthread_once(&s_icd_once, poptst_init_icd);
    if (!s_icd_get) return NULL;
    if (strcmp(name, "vkGetInstanceProcAddr") == 0)
        return (PoPTSTVkVoidFunction)&vkGetInstanceProcAddr;
    return s_icd_get(instance, name);
}

/* A status channel useful before creating SDL's VkInstance. Never returns a
 * fabricated Vulkan function pointer or silently falls back to MoltenVK. */
__attribute__((visibility("default")))
const char *PoPTST_VulkanDriverError(void)
{
    pthread_once(&s_icd_once, poptst_init_icd);
    return s_icd_get ? NULL : s_error;
}
