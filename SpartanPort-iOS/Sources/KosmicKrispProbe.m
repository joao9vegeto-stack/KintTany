#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <pthread.h>
#include <TargetConditionals.h>

/* Keep the probe ABI deliberately small: the provider is a pinned iOS dylib,
 * loaded exactly like PoPTST's proven SDL adapter. This avoids linking Mesa's
 * internal dispatch archives into the launcher executable. */
typedef struct VkInstance_T *VkInstance;
typedef int32_t VkResult;
typedef void (*PFN_vkVoidFunction)(void);
typedef PFN_vkVoidFunction (*PFN_vkGetInstanceProcAddr)(VkInstance, const char *);
typedef VkResult (*PFN_vkEnumerateInstanceExtensionProperties)(
    const char *, uint32_t *, struct VkExtensionProperties *);
typedef struct VkExtensionProperties {
    char extensionName[256];
    uint32_t specVersion;
} VkExtensionProperties;

enum { VK_SUCCESS = 0, VK_INCOMPLETE = 5 };

static char g_kk_probe_message[512];
static void *g_kk_library;
static PFN_vkGetInstanceProcAddr g_get_instance_proc_addr;
static pthread_once_t g_kk_load_once = PTHREAD_ONCE_INIT;

static void load_kosmickrisp(void)
{
    g_kk_library = dlopen("@executable_path/Frameworks/libKosmicKrisp.dylib",
                          RTLD_NOW | RTLD_LOCAL);
    if (!g_kk_library) {
        const char *error = dlerror();
        snprintf(g_kk_probe_message, sizeof(g_kk_probe_message),
                 "KosmicKrisp dlopen failed: %s", error ? error : "unknown dyld error");
        return;
    }

    dlerror();
    void *symbol = dlsym(g_kk_library, "vk_icdGetInstanceProcAddr");
    const char *error = dlerror();
    if (error || !symbol) {
        snprintf(g_kk_probe_message, sizeof(g_kk_probe_message),
                 "KosmicKrisp ICD entrypoint unavailable: %s",
                 error ? error : "dlsym returned NULL");
        return;
    }

    /* POSIX dlsym returns an object pointer; Apple uses pointer-sized function
     * pointers for this ABI. memcpy avoids an ISO C object/function cast. */
    memcpy(&g_get_instance_proc_addr, &symbol, sizeof(g_get_instance_proc_addr));
}

int SpartanKosmicKrispProbe(void)
{
#if TARGET_OS_SIMULATOR
    snprintf(g_kk_probe_message, sizeof(g_kk_probe_message),
             "KosmicKrisp device dylib is not loaded in Simulator builds.");
    return 0;
#else
    pthread_once(&g_kk_load_once, load_kosmickrisp);
    if (!g_get_instance_proc_addr)
        return 0;

    PFN_vkEnumerateInstanceExtensionProperties enumerate_extensions =
        (PFN_vkEnumerateInstanceExtensionProperties)
        g_get_instance_proc_addr(NULL, "vkEnumerateInstanceExtensionProperties");
    PFN_vkVoidFunction create_instance =
        g_get_instance_proc_addr(NULL, "vkCreateInstance");
    if (!enumerate_extensions || !create_instance) {
        snprintf(g_kk_probe_message, sizeof(g_kk_probe_message),
                 "ICD entrypoints missing: enumerate=%d create=%d",
                 enumerate_extensions != NULL, create_instance != NULL);
        return 0;
    }

    uint32_t count = 0;
    VkResult result = enumerate_extensions(NULL, &count, NULL);
    if (result != VK_SUCCESS || count == 0) {
        snprintf(g_kk_probe_message, sizeof(g_kk_probe_message),
                 "Instance extension query failed: VkResult=%d count=%u", result, count);
        return 0;
    }

    VkExtensionProperties *extensions = calloc(count, sizeof(*extensions));
    if (!extensions) {
        snprintf(g_kk_probe_message, sizeof(g_kk_probe_message),
                 "Unable to allocate %u Vulkan extension records.", count);
        return 0;
    }

    uint32_t returned = count;
    result = enumerate_extensions(NULL, &returned, extensions);
    if (result != VK_SUCCESS && result != VK_INCOMPLETE) {
        snprintf(g_kk_probe_message, sizeof(g_kk_probe_message),
                 "Instance extension enumeration failed: VkResult=%d", result);
        free(extensions);
        return 0;
    }

    int has_surface = 0;
    int has_metal_surface = 0;
    for (uint32_t i = 0; i < returned; ++i) {
        if (strcmp(extensions[i].extensionName, "VK_KHR_surface") == 0)
            has_surface = 1;
        if (strcmp(extensions[i].extensionName, "VK_EXT_metal_surface") == 0)
            has_metal_surface = 1;
    }
    free(extensions);

    if (!has_surface || !has_metal_surface) {
        snprintf(g_kk_probe_message, sizeof(g_kk_probe_message),
                 "ICD loaded, but WSI extensions missing: VK_KHR_surface=%d VK_EXT_metal_surface=%d",
                 has_surface, has_metal_surface);
        return 0;
    }

    snprintf(g_kk_probe_message, sizeof(g_kk_probe_message),
             "ICD loaded via pinned PsTJohn dylib; %u extensions enumerated; "
             "VK_KHR_surface and VK_EXT_metal_surface available. Swapchain/device test pending.",
             returned);
    return 1;
#endif
}

const char *SpartanKosmicKrispProbeMessage(void) { return g_kk_probe_message; }
