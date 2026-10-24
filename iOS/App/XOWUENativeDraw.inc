// XOWUE native Xenos/PM4 Vulkan renderer. GPL-3.0-or-later.
// Executes real Xenos-translated shader modules on guest data. Supported
// draws are counted only after vkQueueSubmit succeeds; rejected combinations
// are visible in the diagnostic instead of being replaced by synthetic pixels.
#include "Graphics/Xenos/XOWUEGuestDraw.h"
#define XD(n) ((PFN_vk##n)state->GetDeviceProcAddr(state->device, "vk" #n))
enum { XD_GUEST_BYTES = 0x20000000u };
typedef struct {
   VkBuffer buffer;
   VkDeviceMemory memory;
   void *mapped;
   VkDeviceSize size;
   VkMemoryPropertyFlags flags;
} XDBuffer;
typedef struct {
   VkRenderPass render_pass;
   VkImageView views[8];
   VkFramebuffer framebuffers[8];
   VkDescriptorSetLayout descriptor_layout;
   VkPipelineLayout layout;
   VkDescriptorPool pool;
   VkDescriptorSet descriptors;
   VkPipeline pipeline;
   VkPipeline retired[128];
   uint32_t retired_count;
   VkPrimitiveTopology topology;
   uint64_t vs_hash, ps_hash;
   XDBuffer gpu_memory, constants, composited_frame;
   bool composed_valid;
   bool swapchain_transfer_src;
   uint64_t composed_frames;
   VkDeviceSize constant_stride;
   bool attachment_supported;
   uint64_t issued, rejected, rejected_texture, rejected_memory;
} XDRenderState;
static XDRenderState g_xd = {0};

static void XDDestroyBuffer(KKVulkanState *state, XDBuffer *buffer)
{
   if (!state->device) return;
   if (buffer->mapped) state->UnmapMemory(state->device, buffer->memory);
   if (buffer->buffer) state->DestroyBuffer(state->device, buffer->buffer, NULL);
   if (buffer->memory) state->FreeMemory(state->device, buffer->memory, NULL);
   memset(buffer, 0, sizeof(*buffer));
}

static bool XDCreateBuffer(KKVulkanState *state, XDBuffer *buffer,
                           VkDeviceSize bytes, VkBufferUsageFlags usage)
{
   VkBufferCreateInfo info = {.sType=VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
      .size=bytes, .usage=usage, .sharingMode=VK_SHARING_MODE_EXCLUSIVE};
   if (state->CreateBuffer(state->device, &info, NULL, &buffer->buffer) != VK_SUCCESS)
      return false;
   VkMemoryRequirements requirements={0};
   state->GetBufferMemoryRequirements(state->device, buffer->buffer, &requirements);
   VkPhysicalDeviceMemoryProperties properties={0};
   state->GetPhysicalDeviceMemoryProperties(state->physical_device, &properties);
   uint32_t best=UINT32_MAX;
   for (uint32_t i=0;i<properties.memoryTypeCount;++i) {
      VkMemoryPropertyFlags flags=properties.memoryTypes[i].propertyFlags;
      if (!(requirements.memoryTypeBits&(1u<<i)) ||
          !(flags&VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT)) continue;
      if (best==UINT32_MAX || (flags&VK_MEMORY_PROPERTY_HOST_COHERENT_BIT))
         best=i;
      if (flags&VK_MEMORY_PROPERTY_HOST_COHERENT_BIT) break;
   }
   if (best==UINT32_MAX) return false;
   VkMemoryAllocateInfo allocation={.sType=VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
      .allocationSize=requirements.size,.memoryTypeIndex=best};
   if (state->AllocateMemory(state->device,&allocation,NULL,&buffer->memory)!=VK_SUCCESS ||
       state->BindBufferMemory(state->device,buffer->buffer,buffer->memory,0)!=VK_SUCCESS ||
       state->MapMemory(state->device,buffer->memory,0,VK_WHOLE_SIZE,0,
                        &buffer->mapped)!=VK_SUCCESS) return false;
   buffer->size=bytes;
   buffer->flags=properties.memoryTypes[best].propertyFlags;
   return true;
}

static void XDFlush(KKVulkanState *state, const XDBuffer *buffer) {
   if (!buffer->mapped || (buffer->flags&VK_MEMORY_PROPERTY_HOST_COHERENT_BIT)) return;
   VkMappedMemoryRange flush={.sType=VK_STRUCTURE_TYPE_MAPPED_MEMORY_RANGE,
      .memory=buffer->memory,.offset=0,.size=VK_WHOLE_SIZE};
   state->FlushMappedMemoryRanges(state->device,1,&flush);
}

static void XDDestroyFramebuffers(KKVulkanState *state) {
   if (!state->device) return;
   for (uint32_t i=0;i<8;++i) {
      if (g_xd.framebuffers[i]) XD(DestroyFramebuffer)(state->device,g_xd.framebuffers[i],NULL);
      if (g_xd.views[i]) XD(DestroyImageView)(state->device,g_xd.views[i],NULL);
      g_xd.framebuffers[i]=VK_NULL_HANDLE;
      g_xd.views[i]=VK_NULL_HANDLE;
   }
}

#include "XOWUEGuestTextures.inc"

static void XDCollectPipelines(KKVulkanState *state) {
   for (uint32_t i=0;i<g_xd.retired_count;++i)
      if (g_xd.retired[i]) XD(DestroyPipeline)(state->device,g_xd.retired[i],NULL);
   g_xd.retired_count=0;
   XDRecycleFrameTextures(state);
}
static void XDDestroyRenderer(KKVulkanState *state) {
   if (!state->device) return;
   XDDestroyFramebuffers(state);
   if (g_xd.pipeline) XD(DestroyPipeline)(state->device,g_xd.pipeline,NULL);
   XDCollectPipelines(state);
   XDDestroyTextureBackend(state);
   if (g_xd.pool) XD(DestroyDescriptorPool)(state->device,g_xd.pool,NULL);
   if (g_xd.layout) XD(DestroyPipelineLayout)(state->device,g_xd.layout,NULL);
   if (g_xd.descriptor_layout) XD(DestroyDescriptorSetLayout)(state->device,g_xd.descriptor_layout,NULL);
   if (g_xd.render_pass) XD(DestroyRenderPass)(state->device,g_xd.render_pass,NULL);
   XDDestroyBuffer(state,&g_xd.gpu_memory);
   XDDestroyBuffer(state,&g_xd.constants);
   XDDestroyBuffer(state,&g_xd.composited_frame);
   memset(&g_xd,0,sizeof(g_xd));
}

static bool XDCreateFramebuffers(KKVulkanState *state) {
   if (!g_xd.render_pass || !g_xd.attachment_supported) return false;
   XDDestroyFramebuffers(state);
   for (uint32_t i=0;i<state->swapchain_image_count;++i) {
      VkImageViewCreateInfo view={.sType=VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO,
         .image=state->swapchain_images[i],.viewType=VK_IMAGE_VIEW_TYPE_2D,
         .format=state->swapchain_format,
         .subresourceRange={.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT,.levelCount=1,
                            .layerCount=1}};
      if (XD(CreateImageView)(state->device,&view,NULL,&g_xd.views[i])!=VK_SUCCESS)
         return false;
      VkFramebufferCreateInfo fb={.sType=VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO,
         .renderPass=g_xd.render_pass,.attachmentCount=1,.pAttachments=&g_xd.views[i],
         .width=state->swapchain_extent.width,.height=state->swapchain_extent.height,.layers=1};
      if (XD(CreateFramebuffer)(state->device,&fb,NULL,&g_xd.framebuffers[i])!=VK_SUCCESS)
         return false;
   }
   return true;
}

static bool XDInit(KKVulkanState *state) {
   if (!g_xd.attachment_supported) return false;
   if (g_xd.descriptors) return g_xd.gpu_memory.mapped && g_xd.constants.mapped &&
      g_xd.render_pass && g_xd.framebuffers[0];
   VkAttachmentDescription color={.format=state->swapchain_format,.samples=VK_SAMPLE_COUNT_1_BIT,
      .loadOp=VK_ATTACHMENT_LOAD_OP_LOAD,.storeOp=VK_ATTACHMENT_STORE_OP_STORE,
      .stencilLoadOp=VK_ATTACHMENT_LOAD_OP_DONT_CARE,
      .stencilStoreOp=VK_ATTACHMENT_STORE_OP_DONT_CARE,
      .initialLayout=VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,
      .finalLayout=VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL};
   VkAttachmentReference ref={.attachment=0,.layout=VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL};
   VkSubpassDescription sub={.pipelineBindPoint=VK_PIPELINE_BIND_POINT_GRAPHICS,
      .colorAttachmentCount=1,.pColorAttachments=&ref};
   VkRenderPassCreateInfo rp={.sType=VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO,
      .attachmentCount=1,.pAttachments=&color,.subpassCount=1,.pSubpasses=&sub};
   if (XD(CreateRenderPass)(state->device,&rp,NULL,&g_xd.render_pass)!=VK_SUCCESS) return false;
   VkDescriptorSetLayoutBinding bindings[3]={
      {.binding=0,.descriptorType=VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,.descriptorCount=1,
       .stageFlags=VK_SHADER_STAGE_VERTEX_BIT|VK_SHADER_STAGE_FRAGMENT_BIT},
      {.binding=1,.descriptorType=VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER_DYNAMIC,.descriptorCount=1,
       .stageFlags=VK_SHADER_STAGE_VERTEX_BIT|VK_SHADER_STAGE_FRAGMENT_BIT},
      {.binding=2,.descriptorType=VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,.descriptorCount=1,
       .stageFlags=VK_SHADER_STAGE_VERTEX_BIT|VK_SHADER_STAGE_FRAGMENT_BIT}
   };
   VkDescriptorSetLayoutCreateInfo dl={.sType=VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO,
      .bindingCount=3,.pBindings=bindings};
   if (XD(CreateDescriptorSetLayout)(state->device,&dl,NULL,&g_xd.descriptor_layout)!=VK_SUCCESS)
      return false;
   VkPushConstantRange pc={.stageFlags=VK_SHADER_STAGE_VERTEX_BIT|VK_SHADER_STAGE_FRAGMENT_BIT,
      .offset=0,.size=112};
   if (!XDInitTextureBackend(state)) return false;
   VkDescriptorSetLayout layouts[2]={g_xd.descriptor_layout,g_xt.layout};
   VkPipelineLayoutCreateInfo pl={.sType=VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO,
      .setLayoutCount=2,.pSetLayouts=layouts,
      .pushConstantRangeCount=1,.pPushConstantRanges=&pc};
   if (XD(CreatePipelineLayout)(state->device,&pl,NULL,&g_xd.layout)!=VK_SUCCESS)
      return false;
   VkDescriptorPoolSize sizes[]={
      {.type=VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,.descriptorCount=2},
      {.type=VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER_DYNAMIC,.descriptorCount=1}};
   VkDescriptorPoolCreateInfo dp={.sType=VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO,
      .maxSets=1,.poolSizeCount=2,.pPoolSizes=sizes};
   if (XD(CreateDescriptorPool)(state->device,&dp,NULL,&g_xd.pool)!=VK_SUCCESS)
      return false;
   VkDescriptorSetAllocateInfo di={.sType=VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO,
      .descriptorPool=g_xd.pool,.descriptorSetCount=1,.pSetLayouts=&g_xd.descriptor_layout};
   if (XD(AllocateDescriptorSets)(state->device,&di,&g_xd.descriptors)!=VK_SUCCESS)
      return false;
   VkPhysicalDeviceProperties properties={0};
   state->GetPhysicalDeviceProperties(state->physical_device,&properties);
   const VkDeviceSize align=properties.limits.minUniformBufferOffsetAlignment
      ? properties.limits.minUniformBufferOffsetAlignment : 256;
   g_xd.constant_stride=((sizeof(((XOWUEGuestDraw*)0)->constants)+align-1)/align)*align;
   if (!XDCreateBuffer(state,&g_xd.constants,g_xd.constant_stride*XOWUE_GPU_MAX_DRAWS,
                       VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT))
      return false;
   if (!XDCreateBuffer(state,&g_xd.gpu_memory,XD_GUEST_BYTES,
                       VK_BUFFER_USAGE_STORAGE_BUFFER_BIT))
      return false;
   // The guest shader accesses its actual 512 MiB Xenos physical address space
   // by address; only fetch-covered regions are copied per draw.
   VkDescriptorBufferInfo data[]={ 
      {.buffer=g_xd.gpu_memory.buffer,.offset=0,.range=XD_GUEST_BYTES},
      {.buffer=g_xd.constants.buffer,.offset=0,
       .range=sizeof(((XOWUEGuestDraw*)0)->constants)},
      {.buffer=g_xd.gpu_memory.buffer,.offset=0,.range=XD_GUEST_BYTES}};
   VkWriteDescriptorSet writes[3]={0};
   for (uint32_t i=0;i<3;++i) {
      writes[i]=(VkWriteDescriptorSet){.sType=VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET,
         .dstSet=g_xd.descriptors,.dstBinding=i,.descriptorCount=1,
         .descriptorType=i==1?VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER_DYNAMIC:
                              VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,.pBufferInfo=&data[i]};
   }
   XD(UpdateDescriptorSets)(state->device,3,writes,0,NULL);
   if (!XDCreateFramebuffers(state)) return false;
   KKLog(@"XENOS_NATIVE_RESOURCES renderpass=1 descriptor_set=1 physical_ssbo_mib=512 ubo_bytes=%llu",
         (unsigned long long)(g_xd.constant_stride*XOWUE_GPU_MAX_DRAWS));
   return true;
}

static VkPrimitiveTopology XDTopology(uint32_t primitive) {
   switch (primitive&0x3Fu) {
      case 1: return VK_PRIMITIVE_TOPOLOGY_POINT_LIST;
      case 2: return VK_PRIMITIVE_TOPOLOGY_LINE_LIST;
      case 3: return VK_PRIMITIVE_TOPOLOGY_LINE_STRIP;
      case 4: case 7: case 8: case 13: return VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST;
      case 5: return VK_PRIMITIVE_TOPOLOGY_TRIANGLE_FAN;
      case 6: case 14: return VK_PRIMITIVE_TOPOLOGY_TRIANGLE_STRIP;
      default: return VK_PRIMITIVE_TOPOLOGY_MAX_ENUM;
   }
}

static bool XDGetPipeline(KKVulkanState *state, const XOWUEGuestDraw *draw,
                          VkPrimitiveTopology topology) {
   if (g_xd.pipeline && g_xd.vs_hash==draw->vertex_hash &&
       g_xd.ps_hash==draw->pixel_hash && g_xd.topology==topology)
      return true;
   if (g_xd.pipeline) {
      if (g_xd.retired_count < 128u) g_xd.retired[g_xd.retired_count++] = g_xd.pipeline;
      else return false;
      g_xd.pipeline=VK_NULL_HANDLE;
   }
   KKUpdateNativeShaderModule(state,draw->vertex_hash,&state->guest_vertex_module,
                              &state->guest_vertex_hash,"vertex");
   KKUpdateNativeShaderModule(state,draw->pixel_hash,&state->guest_pixel_module,
                              &state->guest_pixel_hash,"fragment");
   if (!state->guest_vertex_module || !state->guest_pixel_module) return false;
   VkPipelineShaderStageCreateInfo stages[2]={
      {.sType=VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,
       .stage=VK_SHADER_STAGE_VERTEX_BIT,.module=state->guest_vertex_module,.pName="main"},
      {.sType=VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,
       .stage=VK_SHADER_STAGE_FRAGMENT_BIT,.module=state->guest_pixel_module,.pName="main"}};
   VkPipelineVertexInputStateCreateInfo vertex={.sType=VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO};
   VkPipelineInputAssemblyStateCreateInfo assembly={.sType=VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO,
      .topology=topology};
   VkPipelineViewportStateCreateInfo viewport={.sType=VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO,
      .viewportCount=1,.scissorCount=1};
   VkPipelineRasterizationStateCreateInfo raster={.sType=VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO,
      .polygonMode=VK_POLYGON_MODE_FILL,.cullMode=VK_CULL_MODE_NONE,
      .frontFace=VK_FRONT_FACE_CLOCKWISE,.lineWidth=1.0f};
   VkPipelineMultisampleStateCreateInfo ms={.sType=VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO,
      .rasterizationSamples=VK_SAMPLE_COUNT_1_BIT};
   VkPipelineColorBlendAttachmentState attachment={.colorWriteMask=0xFu};
   VkPipelineColorBlendStateCreateInfo blend={.sType=VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO,
      .attachmentCount=1,.pAttachments=&attachment};
   VkDynamicState dynamic_states[]={VK_DYNAMIC_STATE_VIEWPORT,VK_DYNAMIC_STATE_SCISSOR};
   VkPipelineDynamicStateCreateInfo dynamic={.sType=VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO,
      .dynamicStateCount=2,.pDynamicStates=dynamic_states};
   VkGraphicsPipelineCreateInfo info={.sType=VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO,
      .stageCount=2,.pStages=stages,.pVertexInputState=&vertex,
      .pInputAssemblyState=&assembly,.pViewportState=&viewport,
      .pRasterizationState=&raster,.pMultisampleState=&ms,
      .pColorBlendState=&blend,.pDynamicState=&dynamic,
      .layout=g_xd.layout,.renderPass=g_xd.render_pass,.subpass=0};
   VkResult result=XD(CreateGraphicsPipelines)(state->device,VK_NULL_HANDLE,1,&info,NULL,
                                                &g_xd.pipeline);
   if (result!=VK_SUCCESS) {
      KKLog(@"XENOS_PIPELINE_REJECT result=%d vertex=%016llX pixel=%016llX topology=%u",
            result,(unsigned long long)draw->vertex_hash,
            (unsigned long long)draw->pixel_hash,(unsigned)topology);
      return false;
   }
   g_xd.vs_hash=draw->vertex_hash;
   g_xd.ps_hash=draw->pixel_hash;
   g_xd.topology=topology;
   KKLog(@"XENOS_NATIVE_PIPELINE_CREATED vertex=%016llX pixel=%016llX topology=%u",
         (unsigned long long)g_xd.vs_hash,(unsigned long long)g_xd.ps_hash,
         (unsigned)topology);
   return true;
}
typedef struct {
   uint32_t vsBase,psBase,indexAddress,indexInfo,indexOffset,alphaTest;
   float alphaRef;
   uint32_t flags;
   float posScale[4];
   uint32_t redirect[4][4];
} XDPush;
_Static_assert(sizeof(XDPush)==112, "Xenos shader push constant layout changed");

static bool XDCopyGuestRange(KKVulkanState *state, uint32_t address, uint32_t bytes) {
   (void)state;
   if (!bytes) return true;
   if (address>=XD_GUEST_BYTES || bytes>XD_GUEST_BYTES-address) return false;
   return xowue_xenos_copy_guest_physical(address,
      (uint8_t*)g_xd.gpu_memory.mapped+address,bytes);
}

static bool XDUploadGuestDraw(KKVulkanState *state, const XOWUEGuestDraw *draw) {
   const uint32_t *fetch=draw->constants+2048u;
   for (uint32_t slot=0;slot<32u;++slot) {
      if (!(draw->vertex_fetch_mask&(1u<<slot))) continue;
      for (uint32_t sub=0;sub<3u;++sub) {
         const uint32_t entry=slot*3u+sub;
         if (!(draw->fetch_used[entry/32u]&(1u<<(entry%32u)))) continue;
         const uint32_t address=fetch[slot*6u+sub*2u]&0x1FFFFFFCu;
         if (!address) return false;
         uint64_t size=(uint64_t)(draw->index_count+4u)*
               (draw->fetch_strides[entry]?draw->fetch_strides[entry]:16u)*4u+
               (draw->fetch_extents[entry]+32u)*4u;
         if (size>(1u<<22u)) size=1u<<22u;
         if (!XDCopyGuestRange(state,address,(uint32_t)size)) return false;
      }
   }
   if (draw->index_address) {
      uint32_t width=(draw->index_info&1u)?4u:2u;
      uint32_t length=draw->index_count*width;
      if (!XDCopyGuestRange(state,draw->index_address,length)) return false;
   }
   return true;
}

static uint32_t XDProcessDraws(KKVulkanState *state, uint32_t image_index,
                               VkCommandBuffer command) {
   XOWUEGuestDraw *draws=(XOWUEGuestDraw*)calloc(XOWUE_GPU_MAX_DRAWS,sizeof(XOWUEGuestDraw));
   if (!draws) return 0;
   const size_t total=xowue_xenos_take_draws(draws,XOWUE_GPU_MAX_DRAWS);
   if (!total) { free(draws); return 0; }
   if (!g_xd.attachment_supported || !XDInit(state) || !g_xd.framebuffers[image_index]) {
      xowue_xenos_record_rejected((uint32_t)total,"XENOS_VULKAN_RESOURCES_UNAVAILABLE");
      free(draws);
      return 0;
   }
   // Upload and barrier real guest textures before beginning any render pass.
   bool textureReady[XOWUE_GPU_MAX_DRAWS]={0};
   for (size_t i=0;i<total;++i) {
      if (draws[i].texture_3d_mask || draws[i].texture_cube_mask) continue;
      if (!draws[i].texture_2d_mask) { textureReady[i]=true; continue; }
      textureReady[i]=XDPrepare2DTextures(state,&draws[i],command,(uint32_t)i);
   }
   bool began=false;
   uint32_t queued=0;
   for (size_t i=0;i<total;++i) {
      const XOWUEGuestDraw *draw=&draws[i];
      const uint32_t primitive=draw->initiator&0x3Fu;
      VkPrimitiveTopology topology=XDTopology(primitive);
      if (topology==VK_PRIMITIVE_TOPOLOGY_MAX_ENUM || !draw->index_count ||
          draw->index_count>65535u) {
         ++g_xd.rejected;
         xowue_xenos_record_rejected(1,"XENOS_UNSUPPORTED_PRIMITIVE");
         continue;
      }
      if (!textureReady[i]) {
         ++g_xd.rejected_texture;
         xowue_xenos_record_rejected(1,"XENOS_TEXTURE_FORMAT_OR_FETCH_UNSUPPORTED");
         continue;
      }
      if (!XDUploadGuestDraw(state,draw)) {
         ++g_xd.rejected_memory;
         xowue_xenos_record_rejected(1,"XENOS_GUEST_VERTEX_OR_INDEX_MEMORY_INVALID");
         continue;
      }
      const uint32_t count=(primitive==8u)?(draw->index_count/3u)*6u:
                           (primitive==13u)?(draw->index_count/4u)*6u:
                           draw->index_count;
      if (!count || count>131072u || !XDGetPipeline(state,draw,topology)) {
         xowue_xenos_record_rejected(1,"XENOS_PIPELINE_CREATION_FAILED");
         continue;
      }
      const VkDeviceSize offset=g_xd.constant_stride*(VkDeviceSize)i;
      memcpy((uint8_t*)g_xd.constants.mapped+offset,draw->constants,
             sizeof(draw->constants));
      XDPush push={0};
      push.vsBase=0;
      push.psBase=256;
      push.indexAddress=draw->index_address;
      push.indexInfo=draw->index_info & 7u;
      if (primitive==8u) push.indexInfo |= 1u<<3u;
      if (primitive==13u) push.indexInfo |= 2u<<3u;
      push.indexOffset=draw->index_offset;
      push.alphaTest=7u;
      push.posScale[0]=1.0f;
      push.posScale[1]=1.0f;
      if (!began) {
         VkImageMemoryBarrier to_color={.sType=VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
            .srcAccessMask=VK_ACCESS_TRANSFER_WRITE_BIT,
            .dstAccessMask=VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT,
            .oldLayout=VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
            .newLayout=VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,
            .srcQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,
            .dstQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,
            .image=state->swapchain_images[image_index],
            .subresourceRange={.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT,.levelCount=1,.layerCount=1}};
         state->CmdPipelineBarrier(command,VK_PIPELINE_STAGE_TRANSFER_BIT,
            VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT,0,0,NULL,0,NULL,1,&to_color);
         VkRenderPassBeginInfo render={.sType=VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO,
            .renderPass=g_xd.render_pass,.framebuffer=g_xd.framebuffers[image_index],
            .renderArea={.offset={0,0},.extent=state->swapchain_extent}};
         XD(CmdBeginRenderPass)(command,&render,VK_SUBPASS_CONTENTS_INLINE);
         began=true;
      }
      VkViewport viewport={.x=0,.y=0,.width=(float)state->swapchain_extent.width,
         .height=(float)state->swapchain_extent.height,.minDepth=0,.maxDepth=1};
      VkRect2D scissor={.offset={0,0},.extent=state->swapchain_extent};
      XD(CmdSetViewport)(command,0,1,&viewport);
      XD(CmdSetScissor)(command,0,1,&scissor);
      XD(CmdBindPipeline)(command,VK_PIPELINE_BIND_POINT_GRAPHICS,g_xd.pipeline);
      uint32_t dynamic=(uint32_t)offset;
      XD(CmdBindDescriptorSets)(command,VK_PIPELINE_BIND_POINT_GRAPHICS,
         g_xd.layout,0,1,&g_xd.descriptors,1,&dynamic);
      if (draw->texture_2d_mask)
         XD(CmdBindDescriptorSets)(command,VK_PIPELINE_BIND_POINT_GRAPHICS,
            g_xd.layout,1,1,&g_xt.sets[i],0,NULL);
      XD(CmdPushConstants)(command,g_xd.layout,
         VK_SHADER_STAGE_VERTEX_BIT|VK_SHADER_STAGE_FRAGMENT_BIT,0,sizeof(push),&push);
      XD(CmdDraw)(command,count,1,0,0);
      ++queued;
   }
   if (began) {
      XD(CmdEndRenderPass)(command);
      XDFlush(state,&g_xd.constants);
      XDFlush(state,&g_xd.gpu_memory);
   }
   free(draws);
   return queued;
}

static bool XDCacheComposedFrame(KKVulkanState *state,
                                 uint32_t imageIndex,
                                 VkCommandBuffer command) {
   if (!g_xd.swapchain_transfer_src) return false;
   VkDeviceSize bytes=(VkDeviceSize)state->swapchain_extent.width *
                      state->swapchain_extent.height * 4u;
   if (!g_xd.composited_frame.buffer) {
      if (!XDCreateBuffer(state,&g_xd.composited_frame,bytes,
                          VK_BUFFER_USAGE_TRANSFER_DST_BIT |
                          VK_BUFFER_USAGE_TRANSFER_SRC_BIT)) {
         KKLog(@"XENOS_COMPOSED_CACHE_ALLOCATION_FAILED bytes=%llu",
               (unsigned long long)bytes);
         return false;
      }
   }
   if (g_xd.composited_frame.size < bytes) return false;
   VkImageMemoryBarrier barrier={.sType=VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
      .srcAccessMask=VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT,
      .dstAccessMask=VK_ACCESS_TRANSFER_READ_BIT,
      .oldLayout=VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,
      .newLayout=VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
      .srcQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,
      .dstQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,
      .image=state->swapchain_images[imageIndex],
      .subresourceRange={.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT,
                         .levelCount=1,.layerCount=1}};
   state->CmdPipelineBarrier(command,VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT,
      VK_PIPELINE_STAGE_TRANSFER_BIT,0,0,NULL,0,NULL,1,&barrier);
   VkBufferImageCopy region={.bufferOffset=0,.imageSubresource={
      .aspectMask=VK_IMAGE_ASPECT_COLOR_BIT,.layerCount=1},
      .imageExtent={state->swapchain_extent.width,state->swapchain_extent.height,1}};
   XD(CmdCopyImageToBuffer)(command,state->swapchain_images[imageIndex],
      VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,g_xd.composited_frame.buffer,1,&region);
   g_xd.composed_valid=true;
   ++g_xd.composed_frames;
   return true;
}
static void XDReuseComposedFrameBarrier(KKVulkanState *state,VkCommandBuffer command) {
   VkBufferMemoryBarrier barrier={.sType=VK_STRUCTURE_TYPE_BUFFER_MEMORY_BARRIER,
      .srcAccessMask=VK_ACCESS_TRANSFER_WRITE_BIT,
      .dstAccessMask=VK_ACCESS_TRANSFER_READ_BIT,
      .srcQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,
      .dstQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,
      .buffer=g_xd.composited_frame.buffer,.offset=0,
      .size=g_xd.composited_frame.size};
   state->CmdPipelineBarrier(command,VK_PIPELINE_STAGE_TRANSFER_BIT,
      VK_PIPELINE_STAGE_TRANSFER_BIT,0,0,NULL,1,&barrier,0,NULL);
}

#undef XD
