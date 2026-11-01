#include <vulkan/vulkan.h>
#include <stdint.h>
#include <stdio.h>
#include <TargetConditionals.h>

#if !TARGET_OS_SIMULATOR
extern VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL
vk_icdGetInstanceProcAddr(VkInstance instance, const char *name) __attribute__((weak_import));
#endif

static char g_kk_probe_message[512];

int SpartanKosmicKrispProbe(void)
{
#if TARGET_OS_SIMULATOR
    snprintf(g_kk_probe_message, sizeof(g_kk_probe_message),
             "KosmicKrisp iOS device archive is intentionally not linked into Simulator builds.");
    return 0;
#else
    if (!vk_icdGetInstanceProcAddr) {
        snprintf(g_kk_probe_message, sizeof(g_kk_probe_message),
                 "KosmicKrisp ICD archive is not linked into this device target.");
        return 0;
    }
    PFN_vkEnumerateInstanceExtensionProperties enumerate_extensions =
        (PFN_vkEnumerateInstanceExtensionProperties)
        vk_icdGetInstanceProcAddr(VK_NULL_HANDLE, "vkEnumerateInstanceExtensionProperties");
    PFN_vkCreateInstance create_instance =
        (PFN_vkCreateInstance)
        vk_icdGetInstanceProcAddr(VK_NULL_HANDLE, "vkCreateInstance");
    if (!enumerate_extensions || !create_instance) {
        snprintf(g_kk_probe_message, sizeof(g_kk_probe_message),
                 "ICD entrypoints missing: enumerate=%d create=%d",
                 enumerate_extensions != 0, create_instance != 0);
        return 0;
    }
    uint32_t count = 0;
    VkResult result = enumerate_extensions(NULL, &count, NULL);
    if (result != VK_SUCCESS || count == 0) {
        snprintf(g_kk_probe_message, sizeof(g_kk_probe_message),
                 "Instance extension query failed: VkResult=%d count=%u", result, count);
        return 0;
    }
    snprintf(g_kk_probe_message, sizeof(g_kk_probe_message),
             "ICD loaded; %u instance extensions enumerated. Metal WSI/device test pending.", count);
    return 1;
#endif
}
const char *SpartanKosmicKrispProbeMessage(void) { return g_kk_probe_message; }
