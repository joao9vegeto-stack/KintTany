/* KosmicKrispiOS static ICD bridge. MIT. */
#include <vulkan/vulkan.h>
#include <string.h>
extern VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL vk_icdGetInstanceProcAddr(VkInstance instance,const char *name);
VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL vkGetInstanceProcAddr(VkInstance instance,const char *name)
{
 if(!name)return (PFN_vkVoidFunction)0;
 if(strcmp(name,"vkGetInstanceProcAddr")==0)return (PFN_vkVoidFunction)&vkGetInstanceProcAddr;
 return vk_icdGetInstanceProcAddr(instance,name);
}
