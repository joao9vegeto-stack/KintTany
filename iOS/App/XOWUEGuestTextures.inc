// Genuine Xenos 2D texture fetch descriptors; unsupported encodings reject.
typedef struct { VkImage image; VkDeviceMemory memory; VkImageView view;
                 XDBuffer staging; } XDTexture;
typedef struct {
   VkDescriptorSetLayout layout;
   VkDescriptorPool pool;
   VkSampler sampler;
   VkDescriptorSet sets[XOWUE_GPU_MAX_DRAWS];
   XDTexture slots[XOWUE_GPU_MAX_DRAWS][32];
} XDTextureState;
static XDTextureState g_xt={0};

static void XDDestroyTextureSlot(KKVulkanState *state, XDTexture *tx) {
   if (tx->view) XD(DestroyImageView)(state->device,tx->view,NULL);
   if (tx->image) XD(DestroyImage)(state->device,tx->image,NULL);
   if (tx->memory) state->FreeMemory(state->device,tx->memory,NULL);
   XDDestroyBuffer(state,&tx->staging);
   memset(tx,0,sizeof(*tx));
}
static void XDRecycleFrameTextures(KKVulkanState *state) {
   for (uint32_t i=0;i<XOWUE_GPU_MAX_DRAWS;++i) {
      for (uint32_t slot=0;slot<32;++slot) {
         if (g_xt.slots[i][slot].image || g_xt.slots[i][slot].staging.buffer)
            XDDestroyTextureSlot(state,&g_xt.slots[i][slot]);
      }
      g_xt.sets[i]=VK_NULL_HANDLE;
   }
   if (g_xt.pool) XD(ResetDescriptorPool)(state->device,g_xt.pool,0);
}
static void XDDestroyTextureBackend(KKVulkanState *state) {
   XDRecycleFrameTextures(state);
   if (g_xt.sampler) XD(DestroySampler)(state->device,g_xt.sampler,NULL);
   if (g_xt.pool) XD(DestroyDescriptorPool)(state->device,g_xt.pool,NULL);
   if (g_xt.layout) XD(DestroyDescriptorSetLayout)(state->device,g_xt.layout,NULL);
   memset(&g_xt,0,sizeof(g_xt));
}
static bool XDInitTextureBackend(KKVulkanState *state) {
   if (g_xt.layout) return g_xt.pool && g_xt.sampler;
   VkDescriptorSetLayoutBinding binds[32]={0};
   for (uint32_t i=0;i<32;++i) {
      binds[i]=(VkDescriptorSetLayoutBinding){.binding=i,
         .descriptorType=VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER,
         .descriptorCount=1,.stageFlags=VK_SHADER_STAGE_VERTEX_BIT|VK_SHADER_STAGE_FRAGMENT_BIT};
   }
   VkDescriptorSetLayoutCreateInfo layout={.sType=VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO,
      .bindingCount=32,.pBindings=binds};
   if (XD(CreateDescriptorSetLayout)(state->device,&layout,NULL,&g_xt.layout)!=VK_SUCCESS) return false;
   VkDescriptorPoolSize size={.type=VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER,
      .descriptorCount=32*XOWUE_GPU_MAX_DRAWS};
   VkDescriptorPoolCreateInfo pool={.sType=VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO,
      .maxSets=XOWUE_GPU_MAX_DRAWS,.poolSizeCount=1,.pPoolSizes=&size};
   if (XD(CreateDescriptorPool)(state->device,&pool,NULL,&g_xt.pool)!=VK_SUCCESS) return false;
   VkSamplerCreateInfo sampler={.sType=VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO,
      .magFilter=VK_FILTER_LINEAR,.minFilter=VK_FILTER_LINEAR,
      .mipmapMode=VK_SAMPLER_MIPMAP_MODE_NEAREST,
      .addressModeU=VK_SAMPLER_ADDRESS_MODE_REPEAT,
      .addressModeV=VK_SAMPLER_ADDRESS_MODE_REPEAT,
      .addressModeW=VK_SAMPLER_ADDRESS_MODE_REPEAT,.maxLod=1.0f};
   return XD(CreateSampler)(state->device,&sampler,NULL,&g_xt.sampler)==VK_SUCCESS;
}
static bool XDCreate2DTexture(KKVulkanState *state, XDTexture *tx,
                               const uint32_t fetch[6], VkCommandBuffer cmd) {
   const uint32_t width=(fetch[2]&0x1FFFu)+1u;
   const uint32_t height=((fetch[2]>>13u)&0x1FFFu)+1u;
   const VkDeviceSize bytes=(VkDeviceSize)width*height*4u;
   const uint32_t format=fetch[1]&0x3Fu;
   const bool supported=(format==2u||format==6u||format==7u||
       format==8u||format==9u||format==10u||format==25u||
       format==32u||format==54u);
   if (!width || !height || width>2048u || height>2048u ||
       !supported || bytes>16u*1024u*1024u) return false;
   if (!XDCreateBuffer(state,&tx->staging,bytes,VK_BUFFER_USAGE_TRANSFER_SRC_BIT)) return false;
   if (!xowue_xenos_copy_guest_texture2d(fetch,tx->staging.mapped,(size_t)bytes)) return false;
   XDFlush(state,&tx->staging);
   VkImageCreateInfo image={.sType=VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO,
      .imageType=VK_IMAGE_TYPE_2D,.format=VK_FORMAT_R8G8B8A8_UNORM,
      .extent={.width=width,.height=height,.depth=1},
      .mipLevels=1,.arrayLayers=1,.samples=VK_SAMPLE_COUNT_1_BIT,
      .tiling=VK_IMAGE_TILING_OPTIMAL,
      .usage=VK_IMAGE_USAGE_SAMPLED_BIT|VK_IMAGE_USAGE_TRANSFER_DST_BIT,
      .sharingMode=VK_SHARING_MODE_EXCLUSIVE,.initialLayout=VK_IMAGE_LAYOUT_UNDEFINED};
   if (XD(CreateImage)(state->device,&image,NULL,&tx->image)!=VK_SUCCESS) return false;
   VkMemoryRequirements requirements={0};
   XD(GetImageMemoryRequirements)(state->device,tx->image,&requirements);
   VkPhysicalDeviceMemoryProperties props={0};
   state->GetPhysicalDeviceMemoryProperties(state->physical_device,&props);
   uint32_t memoryType=UINT32_MAX;
   for (uint32_t i=0;i<props.memoryTypeCount;++i) {
      if (!(requirements.memoryTypeBits&(1u<<i))) continue;
      if (memoryType==UINT32_MAX) memoryType=i;
      if (props.memoryTypes[i].propertyFlags&VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT) {
         memoryType=i; break;
      }
   }
   if (memoryType==UINT32_MAX) return false;
   VkMemoryAllocateInfo alloc={.sType=VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
      .allocationSize=requirements.size,.memoryTypeIndex=memoryType};
   if (state->AllocateMemory(state->device,&alloc,NULL,&tx->memory)!=VK_SUCCESS ||
       XD(BindImageMemory)(state->device,tx->image,tx->memory,0)!=VK_SUCCESS) return false;
   VkImageViewCreateInfo view={.sType=VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO,
      .image=tx->image,.viewType=VK_IMAGE_VIEW_TYPE_2D,
      .format=VK_FORMAT_R8G8B8A8_UNORM,
      .subresourceRange={.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT,.levelCount=1,.layerCount=1}};
   if (XD(CreateImageView)(state->device,&view,NULL,&tx->view)!=VK_SUCCESS) return false;
   VkImageMemoryBarrier barrier={.sType=VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
      .srcAccessMask=0,.dstAccessMask=VK_ACCESS_TRANSFER_WRITE_BIT,
      .oldLayout=VK_IMAGE_LAYOUT_UNDEFINED,
      .newLayout=VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
      .srcQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,
      .dstQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,
      .image=tx->image,
      .subresourceRange={.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT,.levelCount=1,.layerCount=1}};
   state->CmdPipelineBarrier(cmd,VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,VK_PIPELINE_STAGE_TRANSFER_BIT,
       0,0,NULL,0,NULL,1,&barrier);
   VkBufferImageCopy copy={.bufferOffset=0,.imageSubresource={
      .aspectMask=VK_IMAGE_ASPECT_COLOR_BIT,.layerCount=1},
      .imageExtent={width,height,1}};
   state->CmdCopyBufferToImage(cmd,tx->staging.buffer,tx->image,
      VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,1,&copy);
   barrier.srcAccessMask=VK_ACCESS_TRANSFER_WRITE_BIT;
   barrier.dstAccessMask=VK_ACCESS_SHADER_READ_BIT;
   barrier.oldLayout=VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
   barrier.newLayout=VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;
   state->CmdPipelineBarrier(cmd,VK_PIPELINE_STAGE_TRANSFER_BIT,
      VK_PIPELINE_STAGE_VERTEX_SHADER_BIT|VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT,
      0,0,NULL,0,NULL,1,&barrier);
   return true;
}
static bool XDPrepare2DTextures(KKVulkanState *state, const XOWUEGuestDraw *draw,
                                VkCommandBuffer cmd, uint32_t drawSlot) {
   if (!draw->texture_2d_mask) return true;
   if (!g_xt.pool || drawSlot>=XOWUE_GPU_MAX_DRAWS) return false;
   VkDescriptorSetAllocateInfo allocate={.sType=VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO,
      .descriptorPool=g_xt.pool,.descriptorSetCount=1,.pSetLayouts=&g_xt.layout};
   if (XD(AllocateDescriptorSets)(state->device,&allocate,&g_xt.sets[drawSlot])!=VK_SUCCESS)
      return false;
   for (uint32_t slot=0;slot<32;++slot) {
      if (!(draw->texture_2d_mask&(1u<<slot))) continue;
      const uint32_t *fetch=draw->constants+2048u+slot*6u;
      XDTexture *texture=&g_xt.slots[drawSlot][slot];
      if (!XDCreate2DTexture(state,texture,fetch,cmd)) return false;
      VkDescriptorImageInfo image={.sampler=g_xt.sampler,.imageView=texture->view,
         .imageLayout=VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL};
      VkWriteDescriptorSet write={.sType=VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET,
         .dstSet=g_xt.sets[drawSlot],.dstBinding=slot,.descriptorCount=1,
         .descriptorType=VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER,.pImageInfo=&image};
      XD(UpdateDescriptorSets)(state->device,1,&write,0,NULL);
   }
   return true;
}
