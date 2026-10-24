#import <UIKit/UIKit.h>
#import <QuartzCore/CAMetalLayer.h>
#import <Metal/Metal.h>
static void KKLog(NSString *format, ...);
#import <mach/mach.h>

#define VK_USE_PLATFORM_METAL_EXT 1
#include <vulkan/vulkan.h>

#define XOWUE_MESA_COMMIT "bfe063f723d436e5cdef8a98f058d4e44a64810c"

#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <math.h>
#include "Graphics/Xenos/XOWUEGuestDraw.h"

static _Atomic(uint32_t) g_xowue_guest_swap_count = 0;
static _Atomic(uint32_t) g_xowue_guest_width = 0;
static _Atomic(uint32_t) g_xowue_guest_height = 0;
static _Atomic(uint32_t) g_xowue_guest_frontbuffer = 0;
static _Atomic(uint64_t) g_xowue_guest_frame_count = 0;
static pthread_mutex_t g_xowue_guest_frame_mutex = PTHREAD_MUTEX_INITIALIZER;
static uint8_t *g_xowue_guest_frame = NULL;
static size_t g_xowue_guest_frame_bytes = 0;
static uint32_t g_xowue_guest_frame_width = 0;
static uint32_t g_xowue_guest_frame_height = 0;
static uint32_t g_xowue_guest_frame_address = 0;
static uint32_t g_xowue_guest_frame_format = 0;
static _Atomic uint64_t g_xowue_guest_nonblack = 0;
static _Atomic uint64_t g_xowue_guest_checksum = 0;

void xowue_vulkan_backend_guest_swap(uint32_t frontbuffer, uint32_t width, uint32_t height)
{
   atomic_store_explicit(&g_xowue_guest_frontbuffer, frontbuffer, memory_order_relaxed);
   atomic_store_explicit(&g_xowue_guest_width, width, memory_order_relaxed);
   atomic_store_explicit(&g_xowue_guest_height, height, memory_order_relaxed);
   atomic_fetch_add_explicit(&g_xowue_guest_swap_count, 1, memory_order_relaxed);
}

void xowue_vulkan_backend_guest_frame_rgba(uint32_t frontbuffer,
                                           uint32_t width, uint32_t height,
                                           uint32_t format,
                                           const uint8_t *rgba,
                                           size_t byte_count)
{
   if (!rgba || width == 0 || height == 0 ||
       (uint64_t)width * height * 4u > byte_count)
      return;

   const size_t required = (size_t)width * (size_t)height * 4u;
   uint8_t *copy = (uint8_t *)malloc(required);
   if (!copy)
      return;
   memcpy(copy, rgba, required);
   size_t nonblack = 0;
   uint64_t digest = 14695981039346656037ull;
   size_t pixelCount = (size_t)width * height;
   for (size_t k = 0; k < pixelCount; ++k) {
      const uint8_t *c = copy + k * 4u;
      if (c[0] || c[1] || c[2]) ++nonblack;
      digest = ((digest ^ c[0]) * 1099511628211ull)
               ^ ((uint64_t)c[1] << 8) ^ ((uint64_t)c[2] << 16);
   }
   atomic_store_explicit(&g_xowue_guest_nonblack,(uint64_t)nonblack,memory_order_relaxed);
   atomic_store_explicit(&g_xowue_guest_checksum,digest,memory_order_relaxed);
   KKLog(@"XENOS_GUEST_SWAP_RGBA nonblack=%zu total=%zu checksum=%016llX address=%08X format=%u",
         nonblack,pixelCount,(unsigned long long)digest,frontbuffer,format);
   pthread_mutex_lock(&g_xowue_guest_frame_mutex);
   uint8_t *previous = g_xowue_guest_frame;
   g_xowue_guest_frame = copy;
   g_xowue_guest_frame_bytes = required;
   g_xowue_guest_frame_width = width;
   g_xowue_guest_frame_height = height;
   g_xowue_guest_frame_address = frontbuffer;
   g_xowue_guest_frame_format = format;
   atomic_fetch_add_explicit(&g_xowue_guest_frame_count, 1, memory_order_relaxed);
   pthread_mutex_unlock(&g_xowue_guest_frame_mutex);
   free(previous);
}

void xowue_vulkan_backend_guest_frame_reset(void)
{
   pthread_mutex_lock(&g_xowue_guest_frame_mutex);
   uint8_t *previous = g_xowue_guest_frame;
   g_xowue_guest_frame = NULL;
   g_xowue_guest_frame_bytes = 0;
   g_xowue_guest_frame_width = 0;
   g_xowue_guest_frame_height = 0;
   g_xowue_guest_frame_address = 0;
   g_xowue_guest_frame_format = 0;
   atomic_store_explicit(&g_xowue_guest_frame_count, 0, memory_order_relaxed);
   atomic_store_explicit(&g_xowue_guest_nonblack,0,memory_order_relaxed);
   atomic_store_explicit(&g_xowue_guest_checksum,0,memory_order_relaxed);
   pthread_mutex_unlock(&g_xowue_guest_frame_mutex);
   free(previous);
}


extern VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL
vk_icdGetInstanceProcAddr(VkInstance instance, const char *pName);

// Native Xenos microcode -> SPIR-V bridge, not fixed demo shaders.
extern bool xowue_xenos_active_shader_hashes(uint64_t *vertex, uint64_t *pixel);
extern size_t xowue_xenos_spirv_words(uint64_t hash, uint32_t *out, size_t capacity);

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
   #if !__has_feature(objc_arc)
   [message release];
#endif
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
   VkBuffer upload_buffer;
   VkDeviceMemory upload_memory;
   void *upload_mapped;
   VkDeviceSize upload_size;
   VkMemoryPropertyFlags upload_memory_flags;

   PFN_vkDestroyInstance DestroyInstance;
   PFN_vkEnumeratePhysicalDevices EnumeratePhysicalDevices;
   PFN_vkGetPhysicalDeviceProperties GetPhysicalDeviceProperties;
   PFN_vkGetPhysicalDeviceMemoryProperties GetPhysicalDeviceMemoryProperties;
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
   PFN_vkCmdCopyBufferToImage CmdCopyBufferToImage;
   PFN_vkCreateShaderModule CreateShaderModule;
   PFN_vkDestroyShaderModule DestroyShaderModule;
   VkShaderModule guest_vertex_module;
   VkShaderModule guest_pixel_module;
   uint64_t guest_vertex_hash;
   uint64_t guest_pixel_hash;
   PFN_vkCreateBuffer CreateBuffer;
   PFN_vkDestroyBuffer DestroyBuffer;
   PFN_vkGetBufferMemoryRequirements GetBufferMemoryRequirements;
   PFN_vkAllocateMemory AllocateMemory;
   PFN_vkFreeMemory FreeMemory;
   PFN_vkBindBufferMemory BindBufferMemory;
   PFN_vkMapMemory MapMemory;
   PFN_vkUnmapMemory UnmapMemory;
   PFN_vkFlushMappedMemoryRanges FlushMappedMemoryRanges;
   PFN_vkCreateSemaphore CreateSemaphore;
   PFN_vkDestroySemaphore DestroySemaphore;
   PFN_vkQueueSubmit QueueSubmit;
   PFN_vkQueueWaitIdle QueueWaitIdle;
   PFN_vkDeviceWaitIdle DeviceWaitIdle;

   uint64_t frame_count;
   uint64_t guest_frames_presented;
   uint64_t last_guest_decoded_serial;
   uint64_t guest_draws_submitted;
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

static void KKUpdateNativeShaderModule(KKVulkanState *state, uint64_t hash,
                                       VkShaderModule *module, uint64_t *loadedHash,
                                       const char *stage)
{
   if (!state->ready || hash == *loadedHash) return;
   if (*module && state->DestroyShaderModule) {
      state->DestroyShaderModule(state->device, *module, NULL);
      *module = VK_NULL_HANDLE;
   }
   *loadedHash = hash;
   if (!hash) return;
   size_t count = xowue_xenos_spirv_words(hash, NULL, 0);
   if (count < 5 || count > (1u << 20u)) {
      KKLog(@"XENOS_SPIRV_MISSING stage=%s hash=%016llX",
            stage, (unsigned long long)hash);
      return;
   }
   uint32_t *words = (uint32_t *)malloc(count * sizeof(uint32_t));
   if (!words) return;
   if (xowue_xenos_spirv_words(hash, words, count) != count ||
       words[0] != 0x07230203u) {
      free(words);
      KKLog(@"XENOS_SPIRV_INVALID stage=%s hash=%016llX",
            stage, (unsigned long long)hash);
      return;
   }
   VkShaderModuleCreateInfo info = {
      .sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO,
      .codeSize = count * sizeof(uint32_t),
      .pCode = words,
   };
   VkResult result = state->CreateShaderModule(state->device, &info, NULL, module);
   free(words);
   KKLog(@"XENOS_VULKAN_SHADER_MODULE stage=%s hash=%016llX words=%zu result=%d",
         stage, (unsigned long long)hash, count, result);
   // A shader module is not yet a guest pipeline or a PM4 draw submission.
}

static bool KKUpdateLinkedPixelShaderModule(
   KKVulkanState *state, uint64_t vertex, uint64_t pixel) {
   const uint64_t pairHash = pixel ^ (vertex * 0x9E3779B97F4A7C15ull);
   if (state->guest_pixel_module && state->guest_pixel_hash == pairHash)
      return true;
   size_t count=xowue_xenos_linked_fragment_spirv_words(vertex,pixel,NULL,0);
   if (count < 5u || count > (1u << 20u)) {
      KKLog(@"XENOS_LINKED_FRAGMENT_REJECT vs=%016llX ps=%016llX",
         (unsigned long long)vertex,(unsigned long long)pixel);
      return false;
   }
   uint32_t *words=(uint32_t*)malloc(count*sizeof(uint32_t));
   if (!words) return false;
   if (xowue_xenos_linked_fragment_spirv_words(vertex,pixel,words,count)!=count ||
       words[0]!=0x07230203u) { free(words); return false; }
   VkShaderModuleCreateInfo info={.sType=VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO,
      .codeSize=count*sizeof(uint32_t),.pCode=words};
   VkShaderModule module=VK_NULL_HANDLE;
   VkResult result=state->CreateShaderModule(state->device,&info,NULL,&module);
   free(words);
   if (result!=VK_SUCCESS) {
      KKLog(@"XENOS_LINKED_FRAGMENT_MODULE_REJECT vk=%d",result);
      return false;
   }
   if (state->guest_pixel_module)
      state->DestroyShaderModule(state->device,state->guest_pixel_module,NULL);
   state->guest_pixel_module=module;
   state->guest_pixel_hash=pairHash;
   KKLog(@"XENOS_FRAGMENT_COLOR_OUTPUT_LINKED vs=%016llX ps=%016llX words=%zu",
      (unsigned long long)vertex,(unsigned long long)pixel,count);
   return true;
}

static void KKSyncNativeShaders(KKVulkanState *state)
{
   uint64_t vertex = 0, pixel = 0;
   if (!xowue_xenos_active_shader_hashes(&vertex, &pixel)) return;
   KKUpdateNativeShaderModule(state, vertex, &state->guest_vertex_module,
                              &state->guest_vertex_hash, "vertex");
   KKUpdateNativeShaderModule(state, pixel, &state->guest_pixel_module,
                              &state->guest_pixel_hash, "fragment");
}

static void
KKDestroyUploadBuffer(KKVulkanState *state)
{
   if (!state->device)
      return;
   if (state->upload_mapped && state->UnmapMemory)
      state->UnmapMemory(state->device, state->upload_memory);
   if (state->upload_buffer && state->DestroyBuffer)
      state->DestroyBuffer(state->device, state->upload_buffer, NULL);
   if (state->upload_memory && state->FreeMemory)
      state->FreeMemory(state->device, state->upload_memory, NULL);
   state->upload_buffer = VK_NULL_HANDLE;
   state->upload_memory = VK_NULL_HANDLE;
   state->upload_mapped = NULL;
   state->upload_size = 0;
   state->upload_memory_flags = 0;
}

static bool
KKEnsureUploadBuffer(KKVulkanState *state, uint32_t width, uint32_t height)
{
   const VkDeviceSize required = (VkDeviceSize)width * height * 4u;
   if (!state->device || width == 0 || height == 0 || required == 0)
      return false;
   if (state->upload_buffer && state->upload_mapped && state->upload_size >= required)
      return true;

   KKDestroyUploadBuffer(state);
   VkBufferCreateInfo buffer_info = {
      .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
      .size = required,
      .usage = VK_BUFFER_USAGE_TRANSFER_SRC_BIT,
      .sharingMode = VK_SHARING_MODE_EXCLUSIVE,
   };
   VkResult result = state->CreateBuffer(state->device, &buffer_info, NULL,
                                          &state->upload_buffer);
   if (result != VK_SUCCESS) {
      KKLog(@"FAIL guest-frame upload buffer = %d", result);
      return false;
   }

   VkMemoryRequirements requirements = {0};
   state->GetBufferMemoryRequirements(state->device, state->upload_buffer,
                                      &requirements);
   VkPhysicalDeviceMemoryProperties memory_properties = {0};
   state->GetPhysicalDeviceMemoryProperties(state->physical_device,
                                             &memory_properties);
   uint32_t memory_type = UINT32_MAX;
   uint32_t fallback_type = UINT32_MAX;
   VkMemoryPropertyFlags memory_flags = 0;
   VkMemoryPropertyFlags fallback_flags = 0;
   for (uint32_t i = 0; i < memory_properties.memoryTypeCount; ++i) {
      if ((requirements.memoryTypeBits & (1u << i)) == 0)
         continue;
      const VkMemoryPropertyFlags flags = memory_properties.memoryTypes[i].propertyFlags;
      if ((flags & VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT) == 0)
         continue;
      if (fallback_type == UINT32_MAX) {
         fallback_type = i;
         fallback_flags = flags;
      }
      if ((flags & VK_MEMORY_PROPERTY_HOST_COHERENT_BIT) != 0) {
         memory_type = i;
         memory_flags = flags;
         break;
      }
   }
   if (memory_type == UINT32_MAX) {
      memory_type = fallback_type;
      memory_flags = fallback_flags;
   }
   if (memory_type == UINT32_MAX) {
      KKLog(@"FAIL no host-visible memory for guest-frame upload");
      KKDestroyUploadBuffer(state);
      return false;
   }

   VkMemoryAllocateInfo allocation_info = {
      .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
      .allocationSize = requirements.size,
      .memoryTypeIndex = memory_type,
   };
   result = state->AllocateMemory(state->device, &allocation_info, NULL,
                                  &state->upload_memory);
   if (result != VK_SUCCESS) {
      KKLog(@"FAIL guest-frame upload memory = %d", result);
      KKDestroyUploadBuffer(state);
      return false;
   }
   result = state->BindBufferMemory(state->device, state->upload_buffer,
                                    state->upload_memory, 0);
   if (result != VK_SUCCESS) {
      KKLog(@"FAIL bind guest-frame upload memory = %d", result);
      KKDestroyUploadBuffer(state);
      return false;
   }
   result = state->MapMemory(state->device, state->upload_memory, 0,
                             VK_WHOLE_SIZE, 0, &state->upload_mapped);
   if (result != VK_SUCCESS || !state->upload_mapped) {
      KKLog(@"FAIL map guest-frame upload memory = %d", result);
      KKDestroyUploadBuffer(state);
      return false;
   }
   state->upload_size = requirements.size;
   state->upload_memory_flags = memory_flags;
   KKLog(@"GUEST_FRAME_UPLOAD ready %ux%u bytes=%llu coherent=%d",
         width, height, (unsigned long long)required,
         (memory_flags & VK_MEMORY_PROPERTY_HOST_COHERENT_BIT) != 0);
   return true;
}

static bool
KKWriteGuestFrame(KKVulkanState *state)
{
   if (!state->upload_mapped || !state->upload_buffer ||
       state->upload_size < (VkDeviceSize)state->swapchain_extent.width *
                                state->swapchain_extent.height * 4u)
      return false;
   const uint32_t target_width = state->swapchain_extent.width;
   const uint32_t target_height = state->swapchain_extent.height;
   const size_t target_bytes = (size_t)target_width * target_height * 4u;
   uint8_t *destination = (uint8_t *)state->upload_mapped;
   memset(destination, 0, target_bytes);
   for (size_t i = 3; i < target_bytes; i += 4)
      destination[i] = 255;

   bool copied = false;
   pthread_mutex_lock(&g_xowue_guest_frame_mutex);
   const uint8_t *source = g_xowue_guest_frame;
   const uint32_t source_width = g_xowue_guest_frame_width;
   const uint32_t source_height = g_xowue_guest_frame_height;
   const size_t source_bytes = g_xowue_guest_frame_bytes;
   if (source && source_width && source_height &&
       (uint64_t)source_width * source_height * 4u <= source_bytes) {
      const bool rotate = target_height > target_width;
      const uint32_t rotated_width = rotate ? source_height : source_width;
      const uint32_t rotated_height = rotate ? source_width : source_height;
      const double scale_x = (double)target_width / rotated_width;
      const double scale_y = (double)target_height / rotated_height;
      const double scale = fmin(scale_x, scale_y);
      const uint32_t draw_width = (uint32_t)fmax(1.0, floor(rotated_width * scale));
      const uint32_t draw_height = (uint32_t)fmax(1.0, floor(rotated_height * scale));
      const uint32_t origin_x = (target_width - draw_width) / 2u;
      const uint32_t origin_y = (target_height - draw_height) / 2u;
      const bool target_bgra = state->swapchain_format == VK_FORMAT_B8G8R8A8_UNORM ||
                               state->swapchain_format == VK_FORMAT_B8G8R8A8_SRGB;
      for (uint32_t y = 0; y < draw_height; ++y) {
         const uint32_t rotated_y = (uint32_t)((uint64_t)y * rotated_height / draw_height);
         for (uint32_t x = 0; x < draw_width; ++x) {
            const uint32_t rotated_x = (uint32_t)((uint64_t)x * rotated_width / draw_width);
            const uint32_t source_x = rotate ? rotated_y : rotated_x;
            const uint32_t source_y = rotate ? source_height - 1u - rotated_x : rotated_y;
            const uint8_t *pixel = source + ((size_t)source_y * source_width + source_x) * 4u;
            uint8_t *output = destination + ((size_t)(origin_y + y) * target_width + origin_x + x) * 4u;
            output[0] = target_bgra ? pixel[2] : pixel[0];
            output[1] = pixel[1];
            output[2] = target_bgra ? pixel[0] : pixel[2];
            output[3] = pixel[3];
         }
      }
      copied = true;
   }
   pthread_mutex_unlock(&g_xowue_guest_frame_mutex);

   if ((state->upload_memory_flags & VK_MEMORY_PROPERTY_HOST_COHERENT_BIT) == 0) {
      VkMappedMemoryRange range = {
         .sType = VK_STRUCTURE_TYPE_MAPPED_MEMORY_RANGE,
         .memory = state->upload_memory,
         .offset = 0,
         .size = VK_WHOLE_SIZE,
      };
      VkResult result = state->FlushMappedMemoryRanges(state->device, 1, &range);
      if (result != VK_SUCCESS) {
         KKLog(@"FAIL flush guest-frame upload memory = %d", result);
         return false;
      }
   }
   return copied;
}

#include "XOWUENativeDraw.inc"

static void
KKDestroySwapchain(KKVulkanState *state)
{
   if (state->device && state->DeviceWaitIdle)
      state->DeviceWaitIdle(state->device);

   XDDestroyFramebuffers(state);
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
   XDDestroyRenderer(state);
   KKDestroyUploadBuffer(state);
   if (state->device && state->DestroyShaderModule) {
      if (state->guest_vertex_module)
         state->DestroyShaderModule(state->device, state->guest_vertex_module, NULL);
      if (state->guest_pixel_module)
         state->DestroyShaderModule(state->device, state->guest_pixel_module, NULL);
   }

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
   g_xd.attachment_supported = (caps.supportedUsageFlags & VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT) != 0;
   g_xd.swapchain_transfer_src = (caps.supportedUsageFlags & VK_IMAGE_USAGE_TRANSFER_SRC_BIT) != 0;
   VkSwapchainCreateInfoKHR create_info = {
      .sType = VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR,
      .surface = state->surface,
      .minImageCount = image_count,
      .imageFormat = chosen.format,
      .imageColorSpace = chosen.colorSpace,
      .imageExtent = extent,
      .imageArrayLayers = 1,
      .imageUsage = VK_IMAGE_USAGE_TRANSFER_DST_BIT |
         (g_xd.attachment_supported ? VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT : 0) |
         (g_xd.swapchain_transfer_src ? VK_IMAGE_USAGE_TRANSFER_SRC_BIT : 0),
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

   if (old_swapchain) {
      XDDestroyFramebuffers(state);
      XDDestroyBuffer(state,&g_xd.composited_frame);
      g_xd.composed_valid=false;
      state->DestroySwapchainKHR(state->device, old_swapchain, NULL);
   }
   if (g_xd.render_pass && g_xd.attachment_supported &&
       !XDCreateFramebuffers(state))
      KKLog(@"XENOS_SWAPCHAIN_FRAMEBUFFER_REJECT");

   KKEnsureUploadBuffer(state, extent.width, extent.height);

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

   for (uint32_t i = 0; i < instance_extension_count; ++i)
      KKLog(@"INSTANCE_EXTENSION %s", instance_extensions[i].extensionName);

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
      .pApplicationName = "XOWUE",
      .applicationVersion = VK_MAKE_VERSION(0, 3, 2),
      .pEngineName = "XOWUE Xenos runtime",
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
   KK_LOAD_INSTANCE(state, GetPhysicalDeviceMemoryProperties, PFN_vkGetPhysicalDeviceMemoryProperties,
                    "vkGetPhysicalDeviceMemoryProperties");
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
   KKLog(@"GPU PASS name=%s vendor=0x%04x device=0x%04x driver=%u api=%u.%u.%u queueFamily=%u",
         properties.deviceName, properties.vendorID, properties.deviceID,
         properties.driverVersion,
         VK_VERSION_MAJOR(properties.apiVersion),
         VK_VERSION_MINOR(properties.apiVersion),
         VK_VERSION_PATCH(properties.apiVersion),
         state->queue_family);
   VkPhysicalDeviceMemoryProperties memory_properties = {0};
   state->GetPhysicalDeviceMemoryProperties(state->physical_device, &memory_properties);
   VkDeviceSize heap_bytes = 0;
   for (uint32_t i = 0; i < memory_properties.memoryHeapCount; ++i)
      heap_bytes += memory_properties.memoryHeaps[i].size;
   KKLog(@"GPU_MEMORY heaps=%u heap_bytes=%llu resident_mib=%.1f pipeline_cache=none(guest-frame-copy)",
         memory_properties.memoryHeapCount, (unsigned long long)heap_bytes, KKResidentMiB());

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

   for (uint32_t i = 0; i < device_extension_count; ++i)
      KKLog(@"DEVICE_EXTENSION %s", device_extensions[i].extensionName);

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
   KK_LOAD_DEVICE(state, CmdCopyBufferToImage, PFN_vkCmdCopyBufferToImage,
                  "vkCmdCopyBufferToImage");
   KK_LOAD_DEVICE(state, CreateShaderModule, PFN_vkCreateShaderModule, "vkCreateShaderModule");
   KK_LOAD_DEVICE(state, DestroyShaderModule, PFN_vkDestroyShaderModule, "vkDestroyShaderModule");
   KK_LOAD_DEVICE(state, CreateBuffer, PFN_vkCreateBuffer, "vkCreateBuffer");
   KK_LOAD_DEVICE(state, DestroyBuffer, PFN_vkDestroyBuffer, "vkDestroyBuffer");
   KK_LOAD_DEVICE(state, GetBufferMemoryRequirements,
                  PFN_vkGetBufferMemoryRequirements, "vkGetBufferMemoryRequirements");
   KK_LOAD_DEVICE(state, AllocateMemory, PFN_vkAllocateMemory, "vkAllocateMemory");
   KK_LOAD_DEVICE(state, FreeMemory, PFN_vkFreeMemory, "vkFreeMemory");
   KK_LOAD_DEVICE(state, BindBufferMemory, PFN_vkBindBufferMemory, "vkBindBufferMemory");
   KK_LOAD_DEVICE(state, MapMemory, PFN_vkMapMemory, "vkMapMemory");
   KK_LOAD_DEVICE(state, UnmapMemory, PFN_vkUnmapMemory, "vkUnmapMemory");
   KK_LOAD_DEVICE(state, FlushMappedMemoryRanges,
                  PFN_vkFlushMappedMemoryRanges, "vkFlushMappedMemoryRanges");
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

   // Create actual native Vulkan modules from the translated guest shaders.
   // Xenos EDRAM/pipelines/draws are tracked separately, never fabricated.
   KKSyncNativeShaders(state);

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

   const bool guest_frame_ready = KKWriteGuestFrame(state);
   const uint64_t currentGuestSerial = atomic_load_explicit(
      &g_xowue_guest_frame_count, memory_order_relaxed);
   const bool reuseComposed = g_xd.composed_valid && g_xd.composited_frame.buffer &&
      currentGuestSerial == state->last_guest_decoded_serial;

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

   VkImageSubresourceRange range = {
      .aspectMask = VK_IMAGE_ASPECT_COLOR_BIT,
      .baseMipLevel = 0,
      .levelCount = 1,
      .baseArrayLayer = 0,
      .layerCount = 1,
   };
   if (guest_frame_ready || reuseComposed) {
      if (reuseComposed) XDReuseComposedFrameBarrier(state,state->command_buffer);
      VkBufferImageCopy copy = {
         .bufferOffset = 0,
         .bufferRowLength = 0,
         .bufferImageHeight = 0,
         .imageSubresource = {
            .aspectMask = VK_IMAGE_ASPECT_COLOR_BIT,
            .mipLevel = 0,
            .baseArrayLayer = 0,
            .layerCount = 1,
         },
         .imageOffset = {0, 0, 0},
         .imageExtent = {state->swapchain_extent.width,
                         state->swapchain_extent.height, 1},
      };
      state->CmdCopyBufferToImage(
         state->command_buffer,
         reuseComposed ? g_xd.composited_frame.buffer : state->upload_buffer,
         state->swapchain_images[image_index],
         VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &copy);
   } else {
      VkClearColorValue color = {
         .float32 = {0.0f, 0.0f, 0.0f, 1.0f},
      };
      state->CmdClearColorImage(
         state->command_buffer, state->swapchain_images[image_index],
         VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, &color, 1, &range);
   }

   const uint32_t issuedGuestDraws = XDProcessDraws(state, image_index, state->command_buffer);
   const bool capturedComposed = issuedGuestDraws && XDCacheComposedFrame(
      state,image_index,state->command_buffer);
   if (!issuedGuestDraws && currentGuestSerial != state->last_guest_decoded_serial)
      g_xd.composed_valid=false;

   VkImageMemoryBarrier to_present = {
      .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
      .srcAccessMask = capturedComposed ? VK_ACCESS_TRANSFER_READ_BIT :
         issuedGuestDraws ? VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT : VK_ACCESS_TRANSFER_WRITE_BIT,
      .dstAccessMask = 0,
      .oldLayout = capturedComposed ? VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL :
         issuedGuestDraws ? VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL : VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
      .newLayout = VK_IMAGE_LAYOUT_PRESENT_SRC_KHR,
      .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
      .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
      .image = state->swapchain_images[image_index],
      .subresourceRange = range,
   };
   state->CmdPipelineBarrier(
      state->command_buffer,
      capturedComposed ? VK_PIPELINE_STAGE_TRANSFER_BIT :
         issuedGuestDraws ? VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT : VK_PIPELINE_STAGE_TRANSFER_BIT,
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
   if (result == VK_SUCCESS && issuedGuestDraws) {
      xowue_xenos_record_submitted(issuedGuestDraws);
      state->guest_draws_submitted += issuedGuestDraws;
      KKLog(@"XENOS_GPU_DRAWS_SUBMITTED=%u total=%llu",issuedGuestDraws,
            (unsigned long long)state->guest_draws_submitted);
   }
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
   if (result == VK_SUCCESS && capturedComposed && g_xd.composited_frame.mapped) {
      VkResult invalidateResult=VK_SUCCESS;
      if (!(g_xd.composited_frame.flags&VK_MEMORY_PROPERTY_HOST_COHERENT_BIT)) {
         VkMappedMemoryRange mapped={.sType=VK_STRUCTURE_TYPE_MAPPED_MEMORY_RANGE,
            .memory=g_xd.composited_frame.memory,.offset=0,.size=VK_WHOLE_SIZE};
         PFN_vkInvalidateMappedMemoryRanges invalidateMapped =
            (PFN_vkInvalidateMappedMemoryRanges)state->GetDeviceProcAddr(
               state->device,"vkInvalidateMappedMemoryRanges");
         invalidateResult = invalidateMapped ? invalidateMapped(state->device,1,&mapped)
                                             : VK_ERROR_EXTENSION_NOT_PRESENT;
      }
      if (invalidateResult == VK_SUCCESS) {
      // Actual GPU readback after queue completion, not a draw-call counter.
      // BGRA/RGBA swapchain formats both have first three color bytes.
      const uint8_t *pixels=(const uint8_t*)g_xd.composited_frame.mapped;
      const size_t total=(size_t)state->swapchain_extent.width *
                         (size_t)state->swapchain_extent.height;
      size_t samples=0, nonblack=0;
      uint64_t checksum=14695981039346656037ull;
      const size_t interval=total>8192u?total/8192u:1u;
      for (size_t k=0;k<total;k+=interval) {
         const uint8_t *c=pixels+k*4u;
         if (c[0] || c[1] || c[2]) ++nonblack;
         checksum=((checksum ^ c[0]) * 1099511628211ull ^
                   ((uint64_t)c[1]<<8) ^ ((uint64_t)c[2]<<16));
         ++samples;
      }
      size_t actualColored=0;
       uint32_t minX=UINT32_MAX,minY=UINT32_MAX,maxX=0,maxY=0;
       const uint32_t stride=state->swapchain_extent.width;
       for (size_t k=0;k<total;++k) {
          const uint8_t *c=pixels+k*4u;
          if (!(c[0] || c[1] || c[2])) continue;
          ++actualColored;
          uint32_t x=(uint32_t)(k%stride), y=(uint32_t)(k/stride);
          if (x<minX) minX=x;
          if (y<minY) minY=y;
          if (x>maxX) maxX=x;
          if (y>maxY) maxY=y;
       }
       KKLog(@"XENOS_COMPOSITED_GPU_READBACK nonblack=%zu samples=%zu checksum=%016llX full_nonblack=%zu full_pixels=%zu bbox=%u,%u..%u,%u",
            nonblack,samples,(unsigned long long)checksum,
            actualColored,total,minX==UINT32_MAX?0:minX,
            minY==UINT32_MAX?0:minY,maxX,maxY);
      } else {
         KKLog(@"XENOS_COMPOSITED_GPU_READBACK_INVALIDATE_FAILED code=%d",invalidateResult);
      }
   }
   if (result == VK_SUCCESS) XDCollectPipelines(state);
   if (result != VK_SUCCESS) {
      KKLog(@"FAIL vkQueueWaitIdle = %d", result);
      return false;
   }

   state->frame_count++;
   // Re-presenting an old framebuffer is not another game frame.
   const uint64_t decodedSerial = atomic_load_explicit(
       &g_xowue_guest_frame_count, memory_order_relaxed);
   if (guest_frame_ready && decodedSerial > state->last_guest_decoded_serial) {
      state->guest_frames_presented += decodedSerial - state->last_guest_decoded_serial;
      state->last_guest_decoded_serial = decodedSerial;
   }
   return true;
}


@interface XOWUEVulkanView : UIView {
   KKVulkanState _vk;
   CADisplayLink *_displayLink;
   UILabel *_statusLabel;
   id _backgroundObserver;
   id _foregroundObserver;
   BOOL _attempted;
   BOOL _failed;
}
@end

@implementation XOWUEVulkanView

+ (Class)layerClass
{
   return [CAMetalLayer class];
}

- (instancetype)initWithFrame:(CGRect)frame
{
   self = [super initWithFrame:frame];
   if (!self)
      return nil;

   self.backgroundColor = [UIColor colorWithWhite:0.055 alpha:1.0];
   self.clipsToBounds = YES;
   self.layer.cornerRadius = 14.0;

   _statusLabel = [[UILabel alloc] initWithFrame:CGRectZero];
   _statusLabel.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleBottomMargin;
   _statusLabel.numberOfLines = 3;
   _statusLabel.font = [UIFont monospacedSystemFontOfSize:10 weight:UIFontWeightSemibold];
   _statusLabel.textColor = UIColor.whiteColor;
   _statusLabel.backgroundColor = [UIColor colorWithWhite:0 alpha:0.62];
   _statusLabel.text = @"KOSMICKRISP / METAL\nInicializando backend gráfico…";
   [self addSubview:_statusLabel];
   _statusLabel.hidden = YES;

   __weak XOWUEVulkanView *weakSelf = self;
   NSNotificationCenter *notifications = NSNotificationCenter.defaultCenter;
   _backgroundObserver = [notifications addObserverForName:UIApplicationDidEnterBackgroundNotification
      object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note) {
         (void)note;
         XOWUEVulkanView *strongSelf = weakSelf;
         if (!strongSelf) return;
         strongSelf->_displayLink.paused = YES;
         if (strongSelf->_vk.device && strongSelf->_vk.DeviceWaitIdle) {
            VkResult result = strongSelf->_vk.DeviceWaitIdle(strongSelf->_vk.device);
            KKLog(@"LIFECYCLE background wait_idle=%d", result);
         }
      }];
   _foregroundObserver = [notifications addObserverForName:UIApplicationWillEnterForegroundNotification
      object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note) {
         (void)note;
         XOWUEVulkanView *strongSelf = weakSelf;
         if (!strongSelf || !strongSelf.window || !strongSelf->_vk.ready) return;
         CAMetalLayer *layer = (CAMetalLayer *)strongSelf.layer;
         if (!KKCreateSwapchain(&strongSelf->_vk, layer)) {
            [strongSelf failWithMessage:@"Falha ao recriar a swapchain após voltar do background"];
            return;
         }
         strongSelf->_displayLink.paused = NO;
         KKLog(@"LIFECYCLE foreground swapchain_ready=1 resident_mib=%.1f", KKResidentMiB());
      }];

   return self;
}

- (void)layoutSubviews
{
   [super layoutSubviews];
   CAMetalLayer *metalLayer = (CAMetalLayer *)self.layer;
   CGFloat scale = self.window ? self.window.screen.nativeScale : UIScreen.mainScreen.nativeScale;
   metalLayer.contentsScale = scale;
   metalLayer.drawableSize = CGSizeMake(MAX(1.0, self.bounds.size.width * scale),
                                         MAX(1.0, self.bounds.size.height * scale));
   _statusLabel.frame = CGRectMake(10, 10, MAX(0.0, self.bounds.size.width - 20), 56);
   if (self.window && !_attempted)
      [self performSelector:@selector(startBackend) withObject:nil afterDelay:0.15];
}

- (void)didMoveToWindow
{
   [super didMoveToWindow];
   if (!self.window) {
      _displayLink.paused = YES;
      if (_vk.device && _vk.DeviceWaitIdle)
         KKLog(@"LIFECYCLE view_detached wait_idle=%d", _vk.DeviceWaitIdle(_vk.device));
      return;
   }
   if (_vk.ready) {
      CAMetalLayer *metalLayer = (CAMetalLayer *)self.layer;
      if (!KKCreateSwapchain(&_vk, metalLayer)) {
         [self failWithMessage:@"Falha ao recriar a swapchain ao anexar a tela"];
         return;
      }
      _displayLink.paused = NO;
      return;
   }
   if (self.window && !_attempted)
      [self performSelector:@selector(startBackend) withObject:nil afterDelay:0.15];
}

- (void)startBackend
{
   if (_attempted || !self.window)
      return;
   _attempted = YES;

   NSArray *documents = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES);
   NSString *build = [[NSBundle mainBundle] objectForInfoDictionaryKey:@"CFBundleVersion"] ?: @"unknown";
   NSString *logName = [NSString stringWithFormat:@"diagnostico-build-%@.txt", build];
   NSString *logPath = [[documents firstObject] stringByAppendingPathComponent:logName];
   if (!g_log_file && logPath)
      g_log_file = fopen(logPath.fileSystemRepresentation, "a");
   KKLog(@"XENOS_GUEST_SWAP_PRESTART decoded=%llu nonblack=%llu checksum=%016llX",
      (unsigned long long)atomic_load_explicit(&g_xowue_guest_frame_count,memory_order_relaxed),
      (unsigned long long)atomic_load_explicit(&g_xowue_guest_nonblack,memory_order_relaxed),
      (unsigned long long)atomic_load_explicit(&g_xowue_guest_checksum,memory_order_relaxed));

   CAMetalLayer *metalLayer = (CAMetalLayer *)self.layer;
   metalLayer.device = MTLCreateSystemDefaultDevice();
   metalLayer.pixelFormat = MTLPixelFormatBGRA8Unorm;
   metalLayer.opaque = YES;
   if (!metalLayer.device) {
      [self failWithMessage:@"MTLCreateSystemDefaultDevice falhou"];
      return;
   }

   KKLog(@"KOSMICKRISP_BACKEND_START build=%@ mesa_commit=%s os=%@ model=%@",
         build, XOWUE_MESA_COMMIT, UIDevice.currentDevice.systemVersion,
         UIDevice.currentDevice.model);
   KKLog(@"METAL_DEVICE name=%@ registryID=%llu", metalLayer.device.name, metalLayer.device.registryID);

   if (!KKCreateVulkan(&_vk, metalLayer)) {
      [self failWithMessage:@"KosmicKrisp não criou instância, surface, device e swapchain Metal"];
      return;
   }

   _statusLabel.text = [NSString stringWithFormat:
      @"KOSMICKRISP ATIVO · %@\nCAMetalLayer %ux%u\nXenos → Vulkan → Metal",
      metalLayer.device.name, _vk.swapchain_extent.width, _vk.swapchain_extent.height];
   KKLog(@"KOSMICKRISP_BACKEND_READY extent=%ux%u images=%u",
         _vk.swapchain_extent.width, _vk.swapchain_extent.height, _vk.swapchain_image_count);

   _displayLink = [CADisplayLink displayLinkWithTarget:self selector:@selector(displayTick:)];
   _displayLink.preferredFramesPerSecond = 60;
   [_displayLink addToRunLoop:NSRunLoop.mainRunLoop forMode:NSRunLoopCommonModes];
}

- (void)displayTick:(CADisplayLink *)displayLink
{
   (void)displayLink;
   if (_failed || !_vk.ready)
      return;

   CAMetalLayer *metalLayer = (CAMetalLayer *)self.layer;
   if (!KKRenderFrame(&_vk, metalLayer)) {
      NSString *build = [[NSBundle mainBundle] objectForInfoDictionaryKey:@"CFBundleVersion"] ?: @"unknown";
      NSString *logName = [NSString stringWithFormat:@"diagnostico-build-%@.txt", build];
      [self failWithMessage:[NSString stringWithFormat:@"Falha acquire/submit/present; veja %@", logName]];
      return;
   }

   if ((_vk.frame_count % 60u) == 0u) {
      const uint32_t swaps = atomic_load_explicit(&g_xowue_guest_swap_count, memory_order_relaxed);
      const uint32_t width = atomic_load_explicit(&g_xowue_guest_width, memory_order_relaxed);
      const uint32_t height = atomic_load_explicit(&g_xowue_guest_height, memory_order_relaxed);
      const uint64_t decodedFrames = atomic_load_explicit(&g_xowue_guest_frame_count, memory_order_relaxed);
      _statusLabel.text = [NSString stringWithFormat:
         @"METAL PRESENT PASS · %@\nVulkan presents %llu · distinct guest uploads %llu\nVdSwap Xenos: %u · %ux%u",
         metalLayer.device.name, _vk.frame_count, _vk.guest_frames_presented,
         swaps, width, height];
      KKLog(@"KOSMICKRISP_PRESENT host_presents=%llu unique_guest_uploads=%llu decoded_frames=%llu guest_swaps=%u guest_extent=%ux%u guest_vk_draws=%llu composed_frames=%llu cache=%d resident_mib=%.1f",
            _vk.frame_count, _vk.guest_frames_presented, decodedFrames,
            swaps, width, height, (unsigned long long)_vk.guest_draws_submitted,
            (unsigned long long)g_xd.composed_frames,g_xd.composed_valid,KKResidentMiB());
   }
}

- (void)failWithMessage:(NSString *)message
{
   _failed = YES;
   [_displayLink invalidate];
   _displayLink = nil;
   _statusLabel.hidden = NO;
   _statusLabel.text = [NSString stringWithFormat:@"KOSMICKRISP BLOQUEADO\n%@", message];
   _statusLabel.textColor = [UIColor colorWithRed:1.0 green:0.42 blue:0.36 alpha:1.0];
   KKLog(@"KOSMICKRISP_BACKEND_FAIL %@", message);
}

- (void)dealloc
{
   [_displayLink invalidate];
   if (_backgroundObserver)
      [NSNotificationCenter.defaultCenter removeObserver:_backgroundObserver];
   if (_foregroundObserver)
      [NSNotificationCenter.defaultCenter removeObserver:_foregroundObserver];
   KKDestroyVulkan(&_vk);
}

@end
