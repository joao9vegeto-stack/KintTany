/* Asura's Wrath iOS Vulkan loader shim: adapts the KosmicKrisp ICD to ReXGlue. */
#include <dlfcn.h>
#include <stdio.h>
#include <string.h>
#include <pthread.h>
#ifndef RTLD_LOCAL
#define RTLD_LOCAL 0
#endif
typedef struct VkInstance_T *AsuraVkInstance;
typedef struct VkAllocationCallbacks VkAllocationCallbacks;
typedef void (*AsuraICDDestroyInstance)(AsuraVkInstance, const VkAllocationCallbacks *);
typedef void (*AsuraVkVoidFunction)(void);
typedef AsuraVkVoidFunction (*AsuraICDGetInstanceProcAddr)(AsuraVkInstance, const char *);
static void *s_icd;
static AsuraICDGetInstanceProcAddr s_icd_get;
static pthread_once_t s_icd_once = PTHREAD_ONCE_INIT;
static char s_error[512];
static void asura_init_icd(void) {
    s_icd = dlopen("@loader_path/libvulkan_kosmickrisp.dylib", RTLD_NOW | RTLD_LOCAL);
    if (!s_icd) { const char *failure = dlerror(); snprintf(s_error, sizeof s_error, "KosmicKrisp ICD unavailable: %s", failure ? failure : "dlopen failed"); fprintf(stderr, "[Asura-iOS] %s\n", s_error); return; }
    void *sym = dlsym(s_icd, "vk_icdGetInstanceProcAddr");
    if (!sym) { snprintf(s_error, sizeof s_error, "KosmicKrisp ICD lacks vk_icdGetInstanceProcAddr"); fprintf(stderr, "[Asura-iOS] %s\n", s_error); return; }
    memcpy(&s_icd_get, &sym, sizeof s_icd_get);
}
__attribute__((visibility("default")))
AsuraVkVoidFunction vkGetInstanceProcAddr(AsuraVkInstance instance, const char *name) {
    if (!name) return NULL;
    pthread_once(&s_icd_once, asura_init_icd);
    if (!s_icd_get) return NULL;
    if (strcmp(name, "vkGetInstanceProcAddr") == 0) return (AsuraVkVoidFunction)&vkGetInstanceProcAddr;
    return s_icd_get(instance, name);
}
__attribute__((visibility("default")))
const char *AsuraVulkanDriverError(void) { pthread_once(&s_icd_once, asura_init_icd); return s_icd_get ? NULL : s_error; }

#define ASURA_IOS_VK_DESTROY_INSTANCE_EXPORT_V1
__attribute__((visibility("default")))
void vkDestroyInstance(AsuraVkInstance instance, const VkAllocationCallbacks *allocator) {
    pthread_once(&s_icd_once, asura_init_icd);
    if (!s_icd_get || !instance) return;
    AsuraICDDestroyInstance destroy_instance =
        (AsuraICDDestroyInstance)s_icd_get(instance, "vkDestroyInstance");
    if (destroy_instance) destroy_instance(instance, allocator);
}
