#include <vulkan/vulkan.h>
#include <stdint.h>
#include <stdio.h>
extern VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL vk_icdGetInstanceProcAddr(VkInstance instance,const char *name);
static char g_message[512];
int SpartanKosmicKrispProbe(void)
{
 g_message[0]='\0';
 PFN_vkEnumerateInstanceExtensionProperties enumerate=(PFN_vkEnumerateInstanceExtensionProperties)vk_icdGetInstanceProcAddr(VK_NULL_HANDLE,"vkEnumerateInstanceExtensionProperties");
 PFN_vkCreateInstance create=(PFN_vkCreateInstance)vk_icdGetInstanceProcAddr(VK_NULL_HANDLE,"vkCreateInstance");
 if(!enumerate||!create){snprintf(g_message,sizeof(g_message),"ICD entrypoints missing: enumerate=%d create=%d",enumerate!=0,create!=0);return 0;}
 uint32_t count=0; VkResult result=enumerate(NULL,&count,NULL);
 if(result!=VK_SUCCESS||count==0){snprintf(g_message,sizeof(g_message),"Instance extension query failed: VkResult=%d count=%u",result,count);return 0;}
 snprintf(g_message,sizeof(g_message),"ICD loaded; %u instance extensions enumerated. Metal WSI/device test pending.",count);
 return 1;
}
const char *SpartanKosmicKrispProbeMessage(void){return g_message;}
