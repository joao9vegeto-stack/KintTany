#include <vulkan/vulkan.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
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
                 "ICD entrypoints OK, but WSI extensions missing: VK_KHR_surface=%d VK_EXT_metal_surface=%d",
                 has_surface, has_metal_surface);
        return 0;
    }

    snprintf(g_kk_probe_message, sizeof(g_kk_probe_message),
             "ICD loaded; %u extensions enumerated; VK_KHR_surface and VK_EXT_metal_surface available. Swapchain/device test pending.",
             returned);
    return 1;
#endif
}

const char *SpartanKosmicKrispProbeMessage(void) { return g_kk_probe_message; }
