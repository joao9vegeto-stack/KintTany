/* KosmicKrispiOS dynamic Vulkan loader adapter. MIT.
 * Place this as Frameworks/libvulkan.dylib beside libKosmicKrisp.dylib.
 */
#include <dlfcn.h>
#include <stdio.h>
#include <string.h>
#include <pthread.h>
#ifndef RTLD_LOCAL
#define RTLD_LOCAL 0
#endif
typedef struct VkInstance_T *KKVkInstance;
typedef void (*KKVkVoidFunction)(void);
typedef KKVkVoidFunction (*KKICDGetProc)(KKVkInstance,const char *);
static void *g_icd;
static KKICDGetProc g_get_proc;
static pthread_once_t g_once=PTHREAD_ONCE_INIT;
static char g_error[512];
static void kk_load_icd(void)
{
 g_icd=dlopen("@loader_path/libKosmicKrisp.dylib",RTLD_NOW|RTLD_LOCAL);
 if(!g_icd){const char *e=dlerror();snprintf(g_error,sizeof(g_error),"KosmicKrisp load failed: %s",e?e:"dlopen failed");return;}
 void *sym=dlsym(g_icd,"vk_icdGetInstanceProcAddr");
 if(!sym){snprintf(g_error,sizeof(g_error),"KosmicKrisp ICD entrypoint missing");return;}
 memcpy(&g_get_proc,&sym,sizeof(g_get_proc));
}
__attribute__((visibility("default")))
KKVkVoidFunction vkGetInstanceProcAddr(KKVkInstance instance,const char *name)
{
 if(!name)return NULL;
 pthread_once(&g_once,kk_load_icd);
 if(!g_get_proc)return NULL;
 if(strcmp(name,"vkGetInstanceProcAddr")==0)return (KKVkVoidFunction)&vkGetInstanceProcAddr;
 return g_get_proc(instance,name);
}
__attribute__((visibility("default")))
const char *KosmicKrispVulkanDriverError(void)
{
 pthread_once(&g_once,kk_load_icd);
 return g_get_proc?NULL:g_error;
}
