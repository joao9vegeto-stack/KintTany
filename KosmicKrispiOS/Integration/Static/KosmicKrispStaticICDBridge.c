/* KosmicKrispiOS static ICD bridge. MIT. */
#include <vulkan/vulkan.h>
#include <string.h>
#include <TargetConditionals.h>
#if !TARGET_OS_SIMULATOR
extern VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL
vk_icdGetInstanceProcAddr(VkInstance instance,const char *name) __attribute__((weak_import));
#endif
VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL
vkGetInstanceProcAddr(VkInstance instance,const char *name)
{
#if TARGET_OS_SIMULATOR
    (void)instance; (void)name; return (PFN_vkVoidFunction)0;
#else
    if(!name || !vk_icdGetInstanceProcAddr) return (PFN_vkVoidFunction)0;
    if(strcmp(name,"vkGetInstanceProcAddr")==0) return (PFN_vkVoidFunction)&vkGetInstanceProcAddr;
    return vk_icdGetInstanceProcAddr(instance,name);
#endif
}
