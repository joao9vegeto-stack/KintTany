#import <UIKit/UIKit.h>
#import <QuartzCore/CAMetalLayer.h>
#import <Metal/Metal.h>
#import <mach/mach.h>

#include <vulkan/vulkan.h>

#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "kk_ios_smoke_build.h"

extern VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL
vk_icdGetInstanceProcAddr(VkInstance instance, const char *pName);

static FILE *g_log_file = NULL;

static void
KKLog(NSString *format, ...)
{
   va_list args;
   va_start(args, format);
   NSString *message = [[NSString alloc] initWithFormat:format arguments:args];
   va_end(args);

   NSLog(@"%@", message);
   if (g_log_file) {
      fprintf(g_log_file, "%s\n", message.UTF8String);
      fflush(g_log_file);
   }
   [message release];
}

static double
KKResidentMiB(void)
{
   mach_task_basic_info_data_t info = {0};
   mach_msg_type_number_t count = MACH_TASK_BASIC_INFO_COUNT;
   if (task_info(mach_task_self(), MACH_TASK_BASIC_INFO,
                 (task_info_t)&info, &count) != KERN_SUCCESS)
      return 0.0;
   return (double)info.resident_size / (1024.0 * 1024.0);
}

static bool
KKHasExtension(const VkExtensionProperties *properties, uint32_t count,
               const char *name)
{
   for (uint32_t i = 0; i < count; ++i) {
      if (strcmp(properties[i].extensionName, name) == 0)
         return true;
   }
   return false;
}

typedef struct KKVulkanState {
   VkInstance instance;
   VkPhysicalDevice physical_device;
   VkDevice device;
   VkSurfaceKHR surface;
   VkSwapchainKHR swapchain;
   VkQueue queue;
   uint32_t queue_family;
   VkFormat swapchain_format;
   VkExtent2D swapchain_extent;
   uint32_t swapchain_image_count;
   VkImage swapchain_images[8];

   VkCommandPool command_pool;
   VkCommandBuffer command_buffer;
   VkSemaphore image_available;
   VkSemaphore render_finished;

   PFN_vkDestroyInstance DestroyInstance;
   PFN_vkEnumeratePhysicalDevices EnumeratePhysicalDevices;
   PFN_vkGetPhysicalDeviceProperties GetPhysicalDeviceProperties;
   PFN_vkGetPhysicalDeviceQueueFamilyProperties GetPhysicalDeviceQueueFamilyProperties;
   PFN_vkEnumerateDeviceExtensionProperties EnumerateDeviceExtensionProperties;
   PFN_vkCreateDevice CreateDevice;
   PFN_vkGetDeviceProcAddr GetDeviceProcAddr;

   PFN_vkCreateMetalSurfaceEXT CreateMetalSurfaceEXT;
   PFN_vkDestroySurfaceKHR DestroySurfaceKHR;
   PFN_vkGetPhysicalDeviceSurfaceSupportKHR GetPhysicalDeviceSurfaceSupportKHR;
   PFN_vkGetPhysicalDeviceSurfaceCapabilitiesKHR GetPhysicalDeviceSurfaceCapabilitiesKHR;
   PFN_vkGetPhysicalDeviceSurfaceFormatsKHR GetPhysicalDeviceSurfaceFormatsKHR;

   PFN_vkDestroyDevice DestroyDevice;
   PFN_vkGetDeviceQueue GetDeviceQueue;
   PFN_vkCreateSwapchainKHR CreateSwapchainKHR;
   PFN_vkDestroySwapchainKHR DestroySwapchainKHR;
   PFN_vkGetSwapchainImagesKHR GetSwapchainImagesKHR;
   PFN_vkAcquireNextImageKHR AcquireNextImageKHR;
   PFN_vkQueuePresentKHR QueuePresentKHR;
   PFN_vkCreateCommandPool CreateCommandPool;
   PFN_vkDestroyCommandPool DestroyCommandPool;
   PFN_vkAllocateCommandBuffers AllocateCommandBuffers;
   PFN_vkResetCommandBuffer ResetCommandBuffer;
   PFN_vkBeginCommandBuffer BeginCommandBuffer;
   PFN_vkEndCommandBuffer EndCommandBuffer;
   PFN_vkCmdPipelineBarrier CmdPipelineBarrier;
   PFN_vkCmdClearColorImage CmdClearColorImage;
   PFN_vkCreateSemaphore CreateSemaphore;
   PFN_vkDestroySemaphore DestroySemaphore;
   PFN_vkQueueSubmit QueueSubmit;
   PFN_vkQueueWaitIdle QueueWaitIdle;
   PFN_vkDeviceWaitIdle DeviceWaitIdle;

   uint64_t frame_count;
   bool ready;
} KKVulkanState;

#define KK_LOAD_INSTANCE(state, member, type, symbol) \
   do { \
      (state)->member = (type)vk_icdGetInstanceProcAddr((state)->instance, symbol); \
      if (!(state)->member) { \
         KKLog(@"FAIL missing instance symbol %s", symbol); \
         return false; \
      } \
   } while (0)

#define KK_LOAD_DEVICE(state, member, type, symbol) \
   do { \
      (state)->member = (type)(state)->GetDeviceProcAddr((state)->device, symbol); \
      if (!(state)->member) { \
         KKLog(@"FAIL missing device symbol %s", symbol); \
         return false; \
      } \
   } while (0)

static void
KKDestroySwapchain(KKVulkanState *state)
{
   if (state->device && state->DeviceWaitIdle)
      state->DeviceWaitIdle(state->device);

   if (state->swapchain && state->DestroySwapchainKHR) {
      state->DestroySwapchainKHR(state->device, state->swapchain, NULL);
      state->swapchain = VK_NULL_HANDLE;
   }

   state->swapchain_image_count = 0;
   memset(state->swapchain_images, 0, sizeof(state->swapchain_images));
}

static void
KKDestroyVulkan(KKVulkanState *state)
{
   if (!state)
      return;

   if (state->device && state->DeviceWaitIdle)
      state->DeviceWaitIdle(state->device);

   KKDestroySwapchain(state);

   if (state->device && state->DestroySemaphore) {
      if (state->image_available)
         state->DestroySemaphore(state->device, state->image_available, NULL);
      if (state->render_finished)
         state->DestroySemaphore(state->device, state->render_finished, NULL);
   }

   if (state->device && state->command_pool && state->DestroyCommandPool)
      state->DestroyCommandPool(state->device, state->command_pool, NULL);

   if (state->device && state->DestroyDevice)
      state->DestroyDevice(state->device, NULL);

   if (state->instance && state->surface && state->DestroySurfaceKHR)
      state->DestroySurfaceKHR(state->instance, state->surface, NULL);

   if (state->instance && state->DestroyInstance)
      state->DestroyInstance(state->instance, NULL);

   memset(state, 0, sizeof(*state));
}

static bool
KKCreateSwapchain(KKVulkanState *state, CAMetalLayer *layer)
{
   if (!state->device || !state->surface)
      return false;

   if (state->DeviceWaitIdle(state->device) != VK_SUCCESS) {
      KKLog(@"FAIL vkDeviceWaitIdle before swapchain recreation");
      return false;
   }

   VkSurfaceCapabilitiesKHR caps = {0};
   VkResult result = state->GetPhysicalDeviceSurfaceCapabilitiesKHR(
      state->physical_device, state->surface, &caps);
   if (result != VK_SUCCESS) {
      KKLog(@"FAIL vkGetPhysicalDeviceSurfaceCapabilitiesKHR = %d", result);
      return false;
   }

   uint32_t format_count = 0;
   result = state->GetPhysicalDeviceSurfaceFormatsKHR(
      state->physical_device, state->surface, &format_count, NULL);
   if (result != VK_SUCCESS || format_count == 0) {
      KKLog(@"FAIL surface format count result=%d count=%u", result, format_count);
      return false;
   }

   VkSurfaceFormatKHR *formats =
      (VkSurfaceFormatKHR *)calloc(format_count, sizeof(VkSurfaceFormatKHR));
   if (!formats)
      return false;

   result = state->GetPhysicalDeviceSurfaceFormatsKHR(
      state->physical_device, state->surface, &format_count, formats);
   if (result != VK_SUCCESS) {
      free(formats);
      KKLog(@"FAIL surface formats = %d", result);
      return false;
   }

   VkSurfaceFormatKHR chosen = formats[0];
   for (uint32_t i = 0; i < format_count; ++i) {
      if (formats[i].format == VK_FORMAT_B8G8R8A8_UNORM &&
          formats[i].colorSpace == VK_COLOR_SPACE_SRGB_NONLINEAR_KHR) {
         chosen = formats[i];
         break;
      }
      if (formats[i].format == VK_FORMAT_B8G8R8A8_SRGB)
         chosen = formats[i];
   }
   free(formats);

   if ((caps.supportedUsageFlags & VK_IMAGE_USAGE_TRANSFER_DST_BIT) == 0) {
      KKLog(@"FAIL Metal WSI does not expose TRANSFER_DST swapchain usage (0x%x)",
            caps.supportedUsageFlags);
      return false;
   }

   CGSize drawable = layer.drawableSize;
   VkExtent2D extent = caps.currentExtent;
   if (extent.width == UINT32_MAX || extent.height == UINT32_MAX) {
      extent.width = (uint32_t)MAX(1.0, drawable.width);
      extent.height = (uint32_t)MAX(1.0, drawable.height);
      if (extent.width < caps.minImageExtent.width)
         extent.width = caps.minImageExtent.width;
      if (extent.height < caps.minImageExtent.height)
         extent.height = caps.minImageExtent.height;
      if (extent.width > caps.maxImageExtent.width)
         extent.width = caps.maxImageExtent.width;
      if (extent.height > caps.maxImageExtent.height)
         extent.height = caps.maxImageExtent.height;
   }

   uint32_t image_count = caps.minImageCount;
   if (image_count < 2)
      image_count = 2;
   if (caps.maxImageCount && image_count > caps.maxImageCount)
      image_count = caps.maxImageCount;

   VkCompositeAlphaFlagBitsKHR composite_alpha = VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR;
   if ((caps.supportedCompositeAlpha & composite_alpha) == 0)
      composite_alpha = VK_COMPOSITE_ALPHA_PRE_MULTIPLIED_BIT_KHR;

   VkSwapchainKHR old_swapchain = state->swapchain;
   VkSwapchainCreateInfoKHR create_info = {
      .sType = VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR,
      .surface = state->surface,
      .minImageCount = image_count,
      .imageFormat = chosen.format,
      .imageColorSpace = chosen.colorSpace,
      .imageExtent = extent,
      .imageArrayLayers = 1,
      .imageUsage = VK_IMAGE_USAGE_TRANSFER_DST_BIT,
      .imageSharingMode = VK_SHARING_MODE_EXCLUSIVE,
      .preTransform = caps.currentTransform,
      .compositeAlpha = composite_alpha,
      .presentMode = VK_PRESENT_MODE_FIFO_KHR,
      .clipped = VK_TRUE,
      .oldSwapchain = old_swapchain,
   };

   VkSwapchainKHR new_swapchain = VK_NULL_HANDLE;
   result = state->CreateSwapchainKHR(
      state->device, &create_info, NULL, &new_swapchain);
   if (result != VK_SUCCESS) {
      KKLog(@"FAIL vkCreateSwapchainKHR = %d extent=%ux%u images=%u",
            result, extent.width, extent.height, image_count);
      return false;
   }

   uint32_t actual_count = 0;
   result = state->GetSwapchainImagesKHR(
      state->device, new_swapchain, &actual_count, NULL);
   if (result != VK_SUCCESS || actual_count == 0 ||
       actual_count > (uint32_t)(sizeof(state->swapchain_images) /
                                 sizeof(state->swapchain_images[0]))) {
      state->DestroySwapchainKHR(state->device, new_swapchain, NULL);
      KKLog(@"FAIL swapchain image count result=%d count=%u", result, actual_count);
      return false;
   }

   result = state->GetSwapchainImagesKHR(
      state->device, new_swapchain, &actual_count, state->swapchain_images);
   if (result != VK_SUCCESS) {
      state->DestroySwapchainKHR(state->device, new_swapchain, NULL);
      KKLog(@"FAIL vkGetSwapchainImagesKHR = %d", result);
      return false;
   }

   state->swapchain = new_swapchain;
   state->swapchain_format = chosen.format;
   state->swapchain_extent = extent;
   state->swapchain_image_count = actual_count;

   if (old_swapchain)
      state->DestroySwapchainKHR(state->device, old_swapchain, NULL);

   KKLog(@"SWAPCHAIN PASS extent=%ux%u images=%u format=%d present=FIFO",
         extent.width, extent.height, actual_count, chosen.format);
   return true;
}

static bool
KKCreateVulkan(KKVulkanState *state, CAMetalLayer *layer)
{
   memset(state, 0, sizeof(*state));

   PFN_vkEnumerateInstanceExtensionProperties enumerate_instance_extensions =
      (PFN_vkEnumerateInstanceExtensionProperties)
         vk_icdGetInstanceProcAddr(VK_NULL_HANDLE,
                                   "vkEnumerateInstanceExtensionProperties");
   PFN_vkCreateInstance create_instance =
      (PFN_vkCreateInstance)vk_icdGetInstanceProcAddr(VK_NULL_HANDLE,
                                                      "vkCreateInstance");
   if (!enumerate_instance_extensions || !create_instance) {
      KKLog(@"FAIL ICD global entrypoints unavailable");
      return false;
   }

   uint32_t instance_extension_count = 0;
   VkResult result = enumerate_instance_extensions(
      NULL, &instance_extension_count, NULL);
   if (result != VK_SUCCESS || instance_extension_count == 0) {
      KKLog(@"FAIL instance extension enumeration result=%d count=%u",
            result, instance_extension_count);
      return false;
   }

   VkExtensionProperties *instance_extensions =
      (VkExtensionProperties *)calloc(instance_extension_count,
                                      sizeof(VkExtensionProperties));
   if (!instance_extensions)
      return false;

   result = enumerate_instance_extensions(
      NULL, &instance_extension_count, instance_extensions);
   if (result != VK_SUCCESS) {
      free(instance_extensions);
      KKLog(@"FAIL instance extension list = %d", result);
      return false;
   }

   const bool has_surface =
      KKHasExtension(instance_extensions, instance_extension_count,
                     VK_KHR_SURFACE_EXTENSION_NAME);
   const bool has_metal =
      KKHasExtension(instance_extensions, instance_extension_count,
                     VK_EXT_METAL_SURFACE_EXTENSION_NAME);
   const bool has_portability_enum =
      KKHasExtension(instance_extensions, instance_extension_count,
                     "VK_KHR_portability_enumeration");

   KKLog(@"INSTANCE EXT surface=%d metal_surface=%d portability_enum=%d total=%u",
         has_surface, has_metal, has_portability_enum, instance_extension_count);

   if (!has_surface || !has_metal) {
      free(instance_extensions);
      KKLog(@"FAIL required Metal surface instance extensions missing");
      return false;
   }

   const char *enabled_instance_extensions[3] = {
      VK_KHR_SURFACE_EXTENSION_NAME,
      VK_EXT_METAL_SURFACE_EXTENSION_NAME,
      NULL,
   };
   uint32_t enabled_instance_extension_count = 2;
   VkInstanceCreateFlags instance_flags = 0;

   if (has_portability_enum) {
      enabled_instance_extensions[enabled_instance_extension_count++] =
         "VK_KHR_portability_enumeration";
#ifdef VK_INSTANCE_CREATE_ENUMERATE_PORTABILITY_BIT_KHR
      instance_flags |= VK_INSTANCE_CREATE_ENUMERATE_PORTABILITY_BIT_KHR;
#endif
   }
   free(instance_extensions);

   VkApplicationInfo app_info = {
      .sType = VK_STRUCTURE_TYPE_APPLICATION_INFO,
      .pApplicationName = "KosmicKrisp M3B iOS Smoke",
      .applicationVersion = VK_MAKE_VERSION(0, 3, 2),
      .pEngineName = "Direct KosmicKrisp ICD",
      .engineVersion = VK_MAKE_VERSION(0, 3, 2),
      .apiVersion = VK_API_VERSION_1_3,
   };

   VkInstanceCreateInfo instance_info = {
      .sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,
      .flags = instance_flags,
      .pApplicationInfo = &app_info,
      .enabledExtensionCount = enabled_instance_extension_count,
      .ppEnabledExtensionNames = enabled_instance_extensions,
   };

   result = create_instance(&instance_info, NULL, &state->instance);
   if (result != VK_SUCCESS) {
      KKLog(@"FAIL vkCreateInstance = %d", result);
      return false;
   }
   KKLog(@"INSTANCE PASS");

   KK_LOAD_INSTANCE(state, DestroyInstance, PFN_vkDestroyInstance,
                    "vkDestroyInstance");
   KK_LOAD_INSTANCE(state, EnumeratePhysicalDevices, PFN_vkEnumeratePhysicalDevices,
                    "vkEnumeratePhysicalDevices");
   KK_LOAD_INSTANCE(state, GetPhysicalDeviceProperties, PFN_vkGetPhysicalDeviceProperties,
                    "vkGetPhysicalDeviceProperties");
   KK_LOAD_INSTANCE(state, GetPhysicalDeviceQueueFamilyProperties,
                    PFN_vkGetPhysicalDeviceQueueFamilyProperties,
                    "vkGetPhysicalDeviceQueueFamilyProperties");
   KK_LOAD_INSTANCE(state, EnumerateDeviceExtensionProperties,
                    PFN_vkEnumerateDeviceExtensionProperties,
                    "vkEnumerateDeviceExtensionProperties");
   KK_LOAD_INSTANCE(state, CreateDevice, PFN_vkCreateDevice,
                    "vkCreateDevice");
   KK_LOAD_INSTANCE(state, GetDeviceProcAddr, PFN_vkGetDeviceProcAddr,
                    "vkGetDeviceProcAddr");
   KK_LOAD_INSTANCE(state, CreateMetalSurfaceEXT, PFN_vkCreateMetalSurfaceEXT,
                    "vkCreateMetalSurfaceEXT");
   KK_LOAD_INSTANCE(state, DestroySurfaceKHR, PFN_vkDestroySurfaceKHR,
                    "vkDestroySurfaceKHR");
   KK_LOAD_INSTANCE(state, GetPhysicalDeviceSurfaceSupportKHR,
                    PFN_vkGetPhysicalDeviceSurfaceSupportKHR,
                    "vkGetPhysicalDeviceSurfaceSupportKHR");
   KK_LOAD_INSTANCE(state, GetPhysicalDeviceSurfaceCapabilitiesKHR,
                    PFN_vkGetPhysicalDeviceSurfaceCapabilitiesKHR,
                    "vkGetPhysicalDeviceSurfaceCapabilitiesKHR");
   KK_LOAD_INSTANCE(state, GetPhysicalDeviceSurfaceFormatsKHR,
                    PFN_vkGetPhysicalDeviceSurfaceFormatsKHR,
                    "vkGetPhysicalDeviceSurfaceFormatsKHR");

   VkMetalSurfaceCreateInfoEXT surface_info = {
      .sType = VK_STRUCTURE_TYPE_METAL_SURFACE_CREATE_INFO_EXT,
      .pLayer = layer,
   };
   result = state->CreateMetalSurfaceEXT(
      state->instance, &surface_info, NULL, &state->surface);
   if (result != VK_SUCCESS) {
      KKLog(@"FAIL vkCreateMetalSurfaceEXT = %d", result);
      return false;
   }
   KKLog(@"METAL SURFACE PASS layer=%p", layer);

   uint32_t physical_count = 0;
   result = state->EnumeratePhysicalDevices(
      state->instance, &physical_count, NULL);
   if (result != VK_SUCCESS || physical_count == 0) {
      KKLog(@"FAIL physical device enumeration result=%d count=%u",
            result, physical_count);
      return false;
   }

   VkPhysicalDevice *physical_devices =
      (VkPhysicalDevice *)calloc(physical_count, sizeof(VkPhysicalDevice));
   if (!physical_devices)
      return false;

   result = state->EnumeratePhysicalDevices(
      state->instance, &physical_count, physical_devices);
   if (result != VK_SUCCESS) {
      free(physical_devices);
      KKLog(@"FAIL physical device list = %d", result);
      return false;
   }

   bool found_queue = false;
   for (uint32_t p = 0; p < physical_count && !found_queue; ++p) {
      uint32_t queue_count = 0;
      state->GetPhysicalDeviceQueueFamilyProperties(
         physical_devices[p], &queue_count, NULL);
      VkQueueFamilyProperties *queues =
         (VkQueueFamilyProperties *)calloc(queue_count,
                                           sizeof(VkQueueFamilyProperties));
      if (!queues)
         continue;

      state->GetPhysicalDeviceQueueFamilyProperties(
         physical_devices[p], &queue_count, queues);

      for (uint32_t q = 0; q < queue_count; ++q) {
         VkBool32 surface_support = VK_FALSE;
         state->GetPhysicalDeviceSurfaceSupportKHR(
            physical_devices[p], q, state->surface, &surface_support);
         if ((queues[q].queueFlags & VK_QUEUE_GRAPHICS_BIT) &&
             surface_support == VK_TRUE) {
            state->physical_device = physical_devices[p];
            state->queue_family = q;
            found_queue = true;
            break;
         }
      }
      free(queues);
   }
   free(physical_devices);

   if (!found_queue) {
      KKLog(@"FAIL no graphics+present queue family");
      return false;
   }

   VkPhysicalDeviceProperties properties = {0};
   state->GetPhysicalDeviceProperties(state->physical_device, &properties);
   KKLog(@"GPU PASS name=%s vendor=0x%04x device=0x%04x api=%u.%u.%u queueFamily=%u",
         properties.deviceName, properties.vendorID, properties.deviceID,
         VK_VERSION_MAJOR(properties.apiVersion),
         VK_VERSION_MINOR(properties.apiVersion),
         VK_VERSION_PATCH(properties.apiVersion),
         state->queue_family);

   uint32_t device_extension_count = 0;
   result = state->EnumerateDeviceExtensionProperties(
      state->physical_device, NULL, &device_extension_count, NULL);
   if (result != VK_SUCCESS) {
      KKLog(@"FAIL device extension count = %d", result);
      return false;
   }

   VkExtensionProperties *device_extensions =
      (VkExtensionProperties *)calloc(device_extension_count,
                                      sizeof(VkExtensionProperties));
   if (!device_extensions)
      return false;

   result = state->EnumerateDeviceExtensionProperties(
      state->physical_device, NULL, &device_extension_count, device_extensions);
   if (result != VK_SUCCESS) {
      free(device_extensions);
      KKLog(@"FAIL device extension list = %d", result);
      return false;
   }

   const bool has_swapchain =
      KKHasExtension(device_extensions, device_extension_count,
                     VK_KHR_SWAPCHAIN_EXTENSION_NAME);
   const bool has_portability_subset =
      KKHasExtension(device_extensions, device_extension_count,
                     "VK_KHR_portability_subset");
   KKLog(@"DEVICE EXT swapchain=%d portability_subset=%d total=%u",
         has_swapchain, has_portability_subset, device_extension_count);

   if (!has_swapchain) {
      free(device_extensions);
      KKLog(@"FAIL VK_KHR_swapchain missing");
      return false;
   }

   const char *enabled_device_extensions[2] = {
      VK_KHR_SWAPCHAIN_EXTENSION_NAME,
      NULL,
   };
   uint32_t enabled_device_extension_count = 1;
   if (has_portability_subset)
      enabled_device_extensions[enabled_device_extension_count++] =
         "VK_KHR_portability_subset";
   free(device_extensions);

   float queue_priority = 1.0f;
   VkDeviceQueueCreateInfo queue_info = {
      .sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,
      .queueFamilyIndex = state->queue_family,
      .queueCount = 1,
      .pQueuePriorities = &queue_priority,
   };

   VkDeviceCreateInfo device_info = {
      .sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,
      .queueCreateInfoCount = 1,
      .pQueueCreateInfos = &queue_info,
      .enabledExtensionCount = enabled_device_extension_count,
      .ppEnabledExtensionNames = enabled_device_extensions,
   };

   result = state->CreateDevice(
      state->physical_device, &device_info, NULL, &state->device);
   if (result != VK_SUCCESS) {
      KKLog(@"FAIL vkCreateDevice = %d", result);
      return false;
   }

   KK_LOAD_DEVICE(state, DestroyDevice, PFN_vkDestroyDevice, "vkDestroyDevice");
   KK_LOAD_DEVICE(state, GetDeviceQueue, PFN_vkGetDeviceQueue, "vkGetDeviceQueue");
   KK_LOAD_DEVICE(state, CreateSwapchainKHR, PFN_vkCreateSwapchainKHR,
                  "vkCreateSwapchainKHR");
   KK_LOAD_DEVICE(state, DestroySwapchainKHR, PFN_vkDestroySwapchainKHR,
                  "vkDestroySwapchainKHR");
   KK_LOAD_DEVICE(state, GetSwapchainImagesKHR, PFN_vkGetSwapchainImagesKHR,
                  "vkGetSwapchainImagesKHR");
   KK_LOAD_DEVICE(state, AcquireNextImageKHR, PFN_vkAcquireNextImageKHR,
                  "vkAcquireNextImageKHR");
   KK_LOAD_DEVICE(state, QueuePresentKHR, PFN_vkQueuePresentKHR,
                  "vkQueuePresentKHR");
   KK_LOAD_DEVICE(state, CreateCommandPool, PFN_vkCreateCommandPool,
                  "vkCreateCommandPool");
   KK_LOAD_DEVICE(state, DestroyCommandPool, PFN_vkDestroyCommandPool,
                  "vkDestroyCommandPool");
   KK_LOAD_DEVICE(state, AllocateCommandBuffers, PFN_vkAllocateCommandBuffers,
                  "vkAllocateCommandBuffers");
   KK_LOAD_DEVICE(state, ResetCommandBuffer, PFN_vkResetCommandBuffer,
                  "vkResetCommandBuffer");
   KK_LOAD_DEVICE(state, BeginCommandBuffer, PFN_vkBeginCommandBuffer,
                  "vkBeginCommandBuffer");
   KK_LOAD_DEVICE(state, EndCommandBuffer, PFN_vkEndCommandBuffer,
                  "vkEndCommandBuffer");
   KK_LOAD_DEVICE(state, CmdPipelineBarrier, PFN_vkCmdPipelineBarrier,
                  "vkCmdPipelineBarrier");
   KK_LOAD_DEVICE(state, CmdClearColorImage, PFN_vkCmdClearColorImage,
                  "vkCmdClearColorImage");
   KK_LOAD_DEVICE(state, CreateSemaphore, PFN_vkCreateSemaphore,
                  "vkCreateSemaphore");
   KK_LOAD_DEVICE(state, DestroySemaphore, PFN_vkDestroySemaphore,
                  "vkDestroySemaphore");
   KK_LOAD_DEVICE(state, QueueSubmit, PFN_vkQueueSubmit, "vkQueueSubmit");
   KK_LOAD_DEVICE(state, QueueWaitIdle, PFN_vkQueueWaitIdle, "vkQueueWaitIdle");
   KK_LOAD_DEVICE(state, DeviceWaitIdle, PFN_vkDeviceWaitIdle, "vkDeviceWaitIdle");

   state->GetDeviceQueue(
      state->device, state->queue_family, 0, &state->queue);

   VkCommandPoolCreateInfo pool_info = {
      .sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
      .flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT,
      .queueFamilyIndex = state->queue_family,
   };
   result = state->CreateCommandPool(
      state->device, &pool_info, NULL, &state->command_pool);
   if (result != VK_SUCCESS) {
      KKLog(@"FAIL vkCreateCommandPool = %d", result);
      return false;
   }

   VkCommandBufferAllocateInfo command_info = {
      .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
      .commandPool = state->command_pool,
      .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY,
      .commandBufferCount = 1,
   };
   result = state->AllocateCommandBuffers(
      state->device, &command_info, &state->command_buffer);
   if (result != VK_SUCCESS) {
      KKLog(@"FAIL vkAllocateCommandBuffers = %d", result);
      return false;
   }

   VkSemaphoreCreateInfo semaphore_info = {
      .sType = VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO,
   };
   result = state->CreateSemaphore(
      state->device, &semaphore_info, NULL, &state->image_available);
   if (result != VK_SUCCESS) {
      KKLog(@"FAIL image-available semaphore = %d", result);
      return false;
   }
   result = state->CreateSemaphore(
      state->device, &semaphore_info, NULL, &state->render_finished);
   if (result != VK_SUCCESS) {
      KKLog(@"FAIL render-finished semaphore = %d", result);
      return false;
   }

   if (!KKCreateSwapchain(state, layer))
      return false;

   state->ready = true;
   KKLog(@"VULKAN DEVICE PASS direct-ICD + Metal WSI");
   return true;
}

static bool
KKRenderFrame(KKVulkanState *state, CAMetalLayer *layer)
{
   if (!state->ready || !state->swapchain)
      return false;

   CGSize drawable = layer.drawableSize;
   const uint32_t drawable_width = (uint32_t)MAX(1.0, drawable.width);
   const uint32_t drawable_height = (uint32_t)MAX(1.0, drawable.height);
   if (drawable_width != state->swapchain_extent.width ||
       drawable_height != state->swapchain_extent.height) {
      KKLog(@"RESIZE %ux%u -> %ux%u",
            state->swapchain_extent.width, state->swapchain_extent.height,
            drawable_width, drawable_height);
      if (!KKCreateSwapchain(state, layer))
         return false;
   }

   uint32_t image_index = 0;
   VkResult result = state->AcquireNextImageKHR(
      state->device, state->swapchain, UINT64_MAX,
      state->image_available, VK_NULL_HANDLE, &image_index);

   if (result == VK_ERROR_OUT_OF_DATE_KHR) {
      KKLog(@"ACQUIRE out-of-date; recreating");
      return KKCreateSwapchain(state, layer);
   }
   if (result != VK_SUCCESS && result != VK_SUBOPTIMAL_KHR) {
      KKLog(@"FAIL vkAcquireNextImageKHR = %d", result);
      return false;
   }

   result = state->ResetCommandBuffer(state->command_buffer, 0);
   if (result != VK_SUCCESS) {
      KKLog(@"FAIL vkResetCommandBuffer = %d", result);
      return false;
   }

   VkCommandBufferBeginInfo begin_info = {
      .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
      .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,
   };
   result = state->BeginCommandBuffer(state->command_buffer, &begin_info);
   if (result != VK_SUCCESS) {
      KKLog(@"FAIL vkBeginCommandBuffer = %d", result);
      return false;
   }

   VkImageMemoryBarrier to_clear = {
      .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
      .srcAccessMask = 0,
      .dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT,
      .oldLayout = VK_IMAGE_LAYOUT_UNDEFINED,
      .newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
      .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
      .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
      .image = state->swapchain_images[image_index],
      .subresourceRange = {
         .aspectMask = VK_IMAGE_ASPECT_COLOR_BIT,
         .baseMipLevel = 0,
         .levelCount = 1,
         .baseArrayLayer = 0,
         .layerCount = 1,
      },
   };

   state->CmdPipelineBarrier(
      state->command_buffer,
      VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,
      VK_PIPELINE_STAGE_TRANSFER_BIT,
      0, 0, NULL, 0, NULL, 1, &to_clear);

   const float phase = (float)(state->frame_count % 240u) / 239.0f;
   VkClearColorValue color = {
      .float32 = {0.05f + 0.75f * phase,
                  0.10f + 0.35f * (1.0f - phase),
                  0.55f + 0.35f * (1.0f - phase),
                  1.0f},
   };
   VkImageSubresourceRange range = {
      .aspectMask = VK_IMAGE_ASPECT_COLOR_BIT,
      .baseMipLevel = 0,
      .levelCount = 1,
      .baseArrayLayer = 0,
      .layerCount = 1,
   };
   state->CmdClearColorImage(
      state->command_buffer, state->swapchain_images[image_index],
      VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, &color, 1, &range);

   VkImageMemoryBarrier to_present = {
      .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
      .srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT,
      .dstAccessMask = 0,
      .oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
      .newLayout = VK_IMAGE_LAYOUT_PRESENT_SRC_KHR,
      .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
      .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
      .image = state->swapchain_images[image_index],
      .subresourceRange = range,
   };
   state->CmdPipelineBarrier(
      state->command_buffer,
      VK_PIPELINE_STAGE_TRANSFER_BIT,
      VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT,
      0, 0, NULL, 0, NULL, 1, &to_present);

   result = state->EndCommandBuffer(state->command_buffer);
   if (result != VK_SUCCESS) {
      KKLog(@"FAIL vkEndCommandBuffer = %d", result);
      return false;
   }

   VkPipelineStageFlags wait_stage = VK_PIPELINE_STAGE_TRANSFER_BIT;
   VkSubmitInfo submit_info = {
      .sType = VK_STRUCTURE_TYPE_SUBMIT_INFO,
      .waitSemaphoreCount = 1,
      .pWaitSemaphores = &state->image_available,
      .pWaitDstStageMask = &wait_stage,
      .commandBufferCount = 1,
      .pCommandBuffers = &state->command_buffer,
      .signalSemaphoreCount = 1,
      .pSignalSemaphores = &state->render_finished,
   };
   result = state->QueueSubmit(state->queue, 1, &submit_info, VK_NULL_HANDLE);
   if (result != VK_SUCCESS) {
      KKLog(@"FAIL vkQueueSubmit = %d", result);
      return false;
   }

   VkPresentInfoKHR present_info = {
      .sType = VK_STRUCTURE_TYPE_PRESENT_INFO_KHR,
      .waitSemaphoreCount = 1,
      .pWaitSemaphores = &state->render_finished,
      .swapchainCount = 1,
      .pSwapchains = &state->swapchain,
      .pImageIndices = &image_index,
   };
   result = state->QueuePresentKHR(state->queue, &present_info);
   if (result == VK_ERROR_OUT_OF_DATE_KHR || result == VK_SUBOPTIMAL_KHR) {
      KKLog(@"PRESENT recreate result=%d", result);
      return KKCreateSwapchain(state, layer);
   }
   if (result != VK_SUCCESS) {
      KKLog(@"FAIL vkQueuePresentKHR = %d", result);
      return false;
   }

   result = state->QueueWaitIdle(state->queue);
   if (result != VK_SUCCESS) {
      KKLog(@"FAIL vkQueueWaitIdle = %d", result);
      return false;
   }

   state->frame_count++;
   return true;
}

@interface KKSmokeView : UIView
@end

@implementation KKSmokeView

+ (Class)layerClass
{
   return [CAMetalLayer class];
}

- (void)layoutSubviews
{
   [super layoutSubviews];
   CAMetalLayer *metal_layer = (CAMetalLayer *)self.layer;
   CGFloat scale = self.window ? self.window.screen.nativeScale : UIScreen.mainScreen.nativeScale;
   metal_layer.contentsScale = scale;
   CGSize size = self.bounds.size;
   metal_layer.drawableSize = CGSizeMake(MAX(1.0, size.width * scale),
                                          MAX(1.0, size.height * scale));
}

@end

@interface KKSmokeViewController : UIViewController
@end

@implementation KKSmokeViewController

- (void)loadView
{
   KKSmokeView *view = [[KKSmokeView alloc] initWithFrame:UIScreen.mainScreen.bounds];
   view.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
   self.view = view;
   [view release];
}

- (BOOL)prefersStatusBarHidden
{
   return YES;
}

- (UIInterfaceOrientationMask)supportedInterfaceOrientations
{
   return UIInterfaceOrientationMaskAll;
}

@end

@interface KKAppDelegate : UIResponder <UIApplicationDelegate> {
   UIWindow *_window;
   KKSmokeViewController *_view_controller;
   UILabel *_status_label;
   CADisplayLink *_display_link;
   KKVulkanState _vk;
   BOOL _failed;
}
@end

@implementation KKAppDelegate

- (BOOL)application:(UIApplication *)application
   didFinishLaunchingWithOptions:(NSDictionary *)launchOptions
{
   (void)application;
   (void)launchOptions;

   NSArray *documents = NSSearchPathForDirectoriesInDomains(
      NSDocumentDirectory, NSUserDomainMask, YES);
   NSString *log_path =
      [[documents firstObject] stringByAppendingPathComponent:@"KosmicKrisp-M3B.log"];
   g_log_file = fopen(log_path.fileSystemRepresentation, "w");

   KKLog(@"PsTJon KosmicKrisp M3B START");
   KKLog(@"KintTany=%s", KK_KINTTANY_SHA);
   KKLog(@"Mesa/KosmicKrisp=%s", KK_MESA_SHA);
   KKLog(@"iOS=%@ device=%@", UIDevice.currentDevice.systemVersion,
         UIDevice.currentDevice.model);
   KKLog(@"log=%@", log_path);

   _window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
   _view_controller = [[KKSmokeViewController alloc] init];

   _status_label = [[UILabel alloc] initWithFrame:CGRectMake(12, 12, 350, 96)];
   _status_label.autoresizingMask =
      UIViewAutoresizingFlexibleRightMargin | UIViewAutoresizingFlexibleBottomMargin;
   _status_label.numberOfLines = 5;
   _status_label.font = [UIFont monospacedSystemFontOfSize:12 weight:UIFontWeightSemibold];
   _status_label.textColor = UIColor.whiteColor;
   _status_label.backgroundColor = [UIColor colorWithWhite:0 alpha:0.55];
   _status_label.text = @"KosmicKrisp M3B\ninicializando Vulkan/Metal…";
   [_view_controller.view addSubview:_status_label];

   _window.rootViewController = _view_controller;
   [_window makeKeyAndVisible];

   [self performSelector:@selector(startSmoke) withObject:nil afterDelay:0.25];
   return YES;
}

- (void)startSmoke
{
   KKSmokeView *view = (KKSmokeView *)_view_controller.view;
   [view setNeedsLayout];
   [view layoutIfNeeded];

   CAMetalLayer *metal_layer = (CAMetalLayer *)view.layer;
   if (!metal_layer.device)
      metal_layer.device = MTLCreateSystemDefaultDevice();
   metal_layer.opaque = YES;

   if (!metal_layer.device) {
      [self failWithMessage:@"MTLCreateSystemDefaultDevice falhou"];
      return;
   }

   KKLog(@"METAL DEVICE name=%@ registryID=%llu",
         metal_layer.device.name, metal_layer.device.registryID);

   if (!KKCreateVulkan(&_vk, metal_layer)) {
      [self failWithMessage:@"Falha ao inicializar KosmicKrisp/Vulkan"];
      return;
   }

   _status_label.text =
      [NSString stringWithFormat:@"KosmicKrisp M3B PASS inicial\n%@\n%ux%u • %u imagens\n0 frames",
       metal_layer.device.name,
       _vk.swapchain_extent.width, _vk.swapchain_extent.height,
       _vk.swapchain_image_count];

   [self startDisplayLink];
}

- (void)startDisplayLink
{
   if (_display_link || _failed || !_vk.ready)
      return;

   _display_link = [[CADisplayLink displayLinkWithTarget:self
                                                selector:@selector(displayTick:)] retain];
   _display_link.preferredFramesPerSecond = 60;
   [_display_link addToRunLoop:NSRunLoop.mainRunLoop forMode:NSRunLoopCommonModes];
   KKLog(@"DISPLAY LOOP START target=60Hz serialized smoke");
}

- (void)stopDisplayLink
{
   if (!_display_link)
      return;
   [_display_link invalidate];
   [_display_link release];
   _display_link = nil;
}

- (void)displayTick:(CADisplayLink *)displayLink
{
   (void)displayLink;
   if (_failed || !_vk.ready)
      return;

   CAMetalLayer *metal_layer = (CAMetalLayer *)_view_controller.view.layer;
   if (!KKRenderFrame(&_vk, metal_layer)) {
      [self failWithMessage:@"Falha durante acquire/submit/present"];
      return;
   }

   if ((_vk.frame_count % 60u) == 0u) {
      _status_label.text =
         [NSString stringWithFormat:
            @"KosmicKrisp M3B PRESENT PASS\n%@\n%ux%u • FIFO • 60Hz alvo\n%llu frames • %.1f MiB",
            metal_layer.device.name,
            _vk.swapchain_extent.width, _vk.swapchain_extent.height,
            _vk.frame_count, KKResidentMiB()];
   }

   if ((_vk.frame_count % 300u) == 0u) {
      KKLog(@"HEARTBEAT frames=%llu resident=%.1fMiB extent=%ux%u",
            _vk.frame_count, KKResidentMiB(),
            _vk.swapchain_extent.width, _vk.swapchain_extent.height);
   }
}

- (void)failWithMessage:(NSString *)message
{
   if (_failed)
      return;
   _failed = YES;
   [self stopDisplayLink];
   KKLog(@"M3B FAIL %@", message);
   _status_label.backgroundColor = [UIColor colorWithRed:0.55 green:0 blue:0 alpha:0.8];
   _status_label.text = [NSString stringWithFormat:
      @"KosmicKrisp M3B FAIL\n%@\nAbra Arquivos > app > KosmicKrisp-M3B.log", message];
}

- (void)applicationDidEnterBackground:(UIApplication *)application
{
   (void)application;
   KKLog(@"LIFECYCLE background frames=%llu", _vk.frame_count);
   [self stopDisplayLink];
   if (_vk.device && _vk.DeviceWaitIdle)
      _vk.DeviceWaitIdle(_vk.device);
   KKDestroySwapchain(&_vk);
}

- (void)applicationWillEnterForeground:(UIApplication *)application
{
   (void)application;
   if (_failed || !_vk.ready)
      return;

   KKLog(@"LIFECYCLE foreground");
   [self performSelector:@selector(resumeAfterForeground)
              withObject:nil
              afterDelay:0.15];
}

- (void)resumeAfterForeground
{
   if (_failed || !_vk.ready)
      return;
   CAMetalLayer *metal_layer = (CAMetalLayer *)_view_controller.view.layer;
   [_view_controller.view setNeedsLayout];
   [_view_controller.view layoutIfNeeded];
   if (!KKCreateSwapchain(&_vk, metal_layer)) {
      [self failWithMessage:@"Falha ao recriar swapchain após background"];
      return;
   }
   [self startDisplayLink];
}

- (void)applicationWillTerminate:(UIApplication *)application
{
   (void)application;
   KKLog(@"LIFECYCLE terminate frames=%llu", _vk.frame_count);
   [self stopDisplayLink];
   KKDestroyVulkan(&_vk);
   if (g_log_file) {
      fclose(g_log_file);
      g_log_file = NULL;
   }
}

- (void)dealloc
{
   [self stopDisplayLink];
   KKDestroyVulkan(&_vk);
   [_status_label release];
   [_view_controller release];
   [_window release];
   [super dealloc];
}

@end

int
main(int argc, char *argv[])
{
   @autoreleasepool {
      return UIApplicationMain(argc, argv, nil, NSStringFromClass([KKAppDelegate class]));
   }
}
