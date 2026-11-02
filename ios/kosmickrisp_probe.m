#import <Foundation/Foundation.h>
#import <dlfcn.h>
#import <vulkan/vulkan.h>
#import <stdatomic.h>

typedef PFN_vkVoidFunction (VKAPI_PTR *KKGetProcAddr)(VkInstance, const char *);
static _Atomic(bool) g_kk_probe_ran = false;

__attribute__((constructor))
static void AsuraKosmicKrispProbe(void) {
    if (atomic_exchange(&g_kk_probe_ran, true)) return;
    @autoreleasepool {
        NSURL *frameworks = NSBundle.mainBundle.privateFrameworksURL;
        NSURL *driver = [frameworks URLByAppendingPathComponent:@"libvulkan_kosmickrisp.dylib"];
        void *handle = dlopen(driver.fileSystemRepresentation, RTLD_NOW | RTLD_LOCAL);
        if (!handle) {
            NSLog(@"ASURA_KOSMICKRISP_LOAD_FAIL %s", dlerror());
            return;
        }
        KKGetProcAddr getProc = (KKGetProcAddr)dlsym(handle, "vk_icdGetInstanceProcAddr");
        if (!getProc) {
            NSLog(@"ASURA_KOSMICKRISP_SYMBOL_FAIL %s", dlerror());
            return;
        }
        PFN_vkCreateInstance createInstance =
            (PFN_vkCreateInstance)getProc(VK_NULL_HANDLE, "vkCreateInstance");
        if (!createInstance) {
            NSLog(@"ASURA_KOSMICKRISP_CREATE_INSTANCE_MISSING");
            return;
        }
        VkApplicationInfo app = {
            .sType = VK_STRUCTURE_TYPE_APPLICATION_INFO,
            .pApplicationName = "Asura's Wrath iOS",
            .applicationVersion = 1,
            .pEngineName = "ReXGlue",
            .engineVersion = 1,
            .apiVersion = VK_API_VERSION_1_1
        };
        VkInstanceCreateInfo info = {
            .sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,
            .pApplicationInfo = &app
        };
        VkInstance instance = VK_NULL_HANDLE;
        VkResult result = createInstance(&info, NULL, &instance);
        NSLog(@"ASURA_KOSMICKRISP_INSTANCE result=%d instance=%p", result, instance);
        if (instance) {
            PFN_vkDestroyInstance destroyInstance =
                (PFN_vkDestroyInstance)getProc(instance, "vkDestroyInstance");
            if (destroyInstance) destroyInstance(instance, NULL);
        }
    }
}
