// Native Xenos color EDRAM surface cache and MSAA image resolve.
// All presented content originates in genuine guest vertex/pixel programs.
typedef struct {
  uint32_t tile,pitch,format;
  VkSampleCountFlagBits samples;
  VkImage color,resolved;
  VkDeviceMemory colorMemory,resolvedMemory;
  VkImageView view;
  VkRenderPass pass;
  VkFramebuffer framebuffer;
  VkExtent2D extent;
  bool resolvedLayoutReady;
} XDColorTarget;
static XDColorTarget g_xd_color[16]={0};
static uint32_t g_xd_color_count=0;
static void XDDestroyGuestColor(KKVulkanState* state) {
  if(!state->device)return;
  for(uint32_t i=0;i<g_xd_color_count;++i) {
    XDColorTarget *t=&g_xd_color[i];
    if(t->framebuffer)XD(DestroyFramebuffer)(state->device,t->framebuffer,NULL);
    if(t->pass)XD(DestroyRenderPass)(state->device,t->pass,NULL);
    if(t->view)XD(DestroyImageView)(state->device,t->view,NULL);
    if(t->color)XD(DestroyImage)(state->device,t->color,NULL);
    if(t->resolved)XD(DestroyImage)(state->device,t->resolved,NULL);
    if(t->colorMemory)state->FreeMemory(state->device,t->colorMemory,NULL);
    if(t->resolvedMemory)state->FreeMemory(state->device,t->resolvedMemory,NULL);
  }
  memset(g_xd_color,0,sizeof(g_xd_color));g_xd_color_count=0;
}
static bool XDCreateColorImage(KKVulkanState* state,VkFormat fmt,
                               VkExtent2D ext,VkSampleCountFlagBits samples,
                               VkImageUsageFlags usage,
                               VkImage* outImage,VkDeviceMemory* outMemory) {
  VkImageCreateInfo info={.sType=VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO,
    .imageType=VK_IMAGE_TYPE_2D,.format=fmt,.extent={ext.width,ext.height,1u},
    .mipLevels=1,.arrayLayers=1,.samples=samples,
    .tiling=VK_IMAGE_TILING_OPTIMAL,.usage=usage,
    .sharingMode=VK_SHARING_MODE_EXCLUSIVE,
    .initialLayout=VK_IMAGE_LAYOUT_UNDEFINED};
  if(XD(CreateImage)(state->device,&info,NULL,outImage)!=VK_SUCCESS)return false;
  VkMemoryRequirements req={0};
  XD(GetImageMemoryRequirements)(state->device,*outImage,&req);
  VkPhysicalDeviceMemoryProperties props={0};
  state->GetPhysicalDeviceMemoryProperties(state->physical_device,&props);
  uint32_t type=UINT32_MAX;
  for(uint32_t i=0;i<props.memoryTypeCount;++i)
    if((req.memoryTypeBits&(1u<<i)) &&
       (props.memoryTypes[i].propertyFlags&VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT)){
      type=i;break;
    }
  if(type==UINT32_MAX)for(uint32_t i=0;i<props.memoryTypeCount;++i)
    if(req.memoryTypeBits&(1u<<i)){type=i;break;}
  if(type==UINT32_MAX)return false;
  VkMemoryAllocateInfo alloc={.sType=VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
    .allocationSize=req.size,.memoryTypeIndex=type};
  return state->AllocateMemory(state->device,&alloc,NULL,outMemory)==VK_SUCCESS &&
    XD(BindImageMemory)(state->device,*outImage,*outMemory,0)==VK_SUCCESS;
}
static XDColorTarget* XDGetGuestColor(KKVulkanState* state,
                                     const XOWUEGuestDraw* draw) {
  const uint32_t tile=draw->rb_color_info[0]&0xFFFu;
  const uint32_t pitch=draw->rb_surface_info&0x3FFFu;
  const uint32_t fmt=(draw->rb_color_info[0]>>16u)&0xFu;
  const uint32_t msaa=(draw->rb_surface_info>>16u)&3u;
  if(!pitch||pitch>2048u||msaa>2u||g_xd_color_count>=16u)return NULL;
  const VkSampleCountFlagBits samples=(VkSampleCountFlagBits)(1u<<msaa);
  const VkFormat imageFormat=fmt==0u?VK_FORMAT_R8G8B8A8_UNORM:
                             fmt==2u?VK_FORMAT_A2B10G10R10_UNORM_PACK32:
                             fmt==3u?VK_FORMAT_R16G16B16A16_SFLOAT:
                             VK_FORMAT_UNDEFINED;
  if(imageFormat==VK_FORMAT_UNDEFINED)return NULL;
  for(uint32_t i=0;i<g_xd_color_count;++i)
    if(g_xd_color[i].tile==tile&&g_xd_color[i].pitch==pitch&&
       g_xd_color[i].format==fmt&&g_xd_color[i].samples==samples)return &g_xd_color[i];
  VkPhysicalDeviceProperties gpu={0};
  state->GetPhysicalDeviceProperties(state->physical_device,&gpu);
  if(!(gpu.limits.framebufferColorSampleCounts&samples))return NULL;
  XDColorTarget* t=&g_xd_color[g_xd_color_count];
  t->tile=tile;t->pitch=pitch;t->format=fmt;t->samples=samples;
  t->extent=(VkExtent2D){pitch,1024u};
  if(!XDCreateColorImage(state,imageFormat,t->extent,samples,
      VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT|VK_IMAGE_USAGE_TRANSFER_SRC_BIT,
      &t->color,&t->colorMemory))goto fail;
  if(samples!=VK_SAMPLE_COUNT_1_BIT &&
     !XDCreateColorImage(state,imageFormat,t->extent,VK_SAMPLE_COUNT_1_BIT,
       VK_IMAGE_USAGE_TRANSFER_DST_BIT|VK_IMAGE_USAGE_TRANSFER_SRC_BIT,
       &t->resolved,&t->resolvedMemory))goto fail;
  VkImageViewCreateInfo view={.sType=VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO,
    .image=t->color,.viewType=VK_IMAGE_VIEW_TYPE_2D,.format=imageFormat,
    .subresourceRange={.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT,
       .levelCount=1,.layerCount=1}};
  if(XD(CreateImageView)(state->device,&view,NULL,&t->view)!=VK_SUCCESS)goto fail;
  VkAttachmentDescription attachment={.format=imageFormat,.samples=samples,
    .loadOp=VK_ATTACHMENT_LOAD_OP_CLEAR,.storeOp=VK_ATTACHMENT_STORE_OP_STORE,
    .stencilLoadOp=VK_ATTACHMENT_LOAD_OP_DONT_CARE,
    .stencilStoreOp=VK_ATTACHMENT_STORE_OP_DONT_CARE,
    .initialLayout=VK_IMAGE_LAYOUT_UNDEFINED,
    .finalLayout=VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL};
  VkAttachmentReference ref={.attachment=0,
    .layout=VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL};
  VkSubpassDescription subpass={.pipelineBindPoint=VK_PIPELINE_BIND_POINT_GRAPHICS,
    .colorAttachmentCount=1,.pColorAttachments=&ref};
  VkRenderPassCreateInfo rp={.sType=VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO,
    .attachmentCount=1,.pAttachments=&attachment,.subpassCount=1,
    .pSubpasses=&subpass};
  if(XD(CreateRenderPass)(state->device,&rp,NULL,&t->pass)!=VK_SUCCESS)goto fail;
  VkFramebufferCreateInfo fb={.sType=VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO,
    .renderPass=t->pass,.attachmentCount=1,.pAttachments=&t->view,
    .width=t->extent.width,.height=t->extent.height,.layers=1u};
  if(XD(CreateFramebuffer)(state->device,&fb,NULL,&t->framebuffer)!=VK_SUCCESS)goto fail;
  ++g_xd_color_count;
  KKLog(@"XENOS_EDRAM_COLOR_NATIVE tile=%u pitch=%u format=%u samples=%u",
    tile,pitch,fmt,(unsigned)samples);
  return t;
fail:
  if(t->framebuffer)XD(DestroyFramebuffer)(state->device,t->framebuffer,NULL);
  if(t->pass)XD(DestroyRenderPass)(state->device,t->pass,NULL);
  if(t->view)XD(DestroyImageView)(state->device,t->view,NULL);
  if(t->color)XD(DestroyImage)(state->device,t->color,NULL);
  if(t->resolved)XD(DestroyImage)(state->device,t->resolved,NULL);
  if(t->colorMemory)state->FreeMemory(state->device,t->colorMemory,NULL);
  if(t->resolvedMemory)state->FreeMemory(state->device,t->resolvedMemory,NULL);
  memset(t,0,sizeof(*t));
  return NULL;
}
static bool XDResolveGuestColor(KKVulkanState* state,
                                const XOWUEGuestDraw* draw,
                                VkCommandBuffer cmd,uint32_t imageIndex,
                                bool swapchainInColorLayout) {
  // Only resolve existing guest EDRAM targets - never invent a color surface.
  const uint32_t sourceTile=draw->rb_color_info[0]&0xFFFu;
  XDColorTarget* t=NULL;
  for(uint32_t i=0;i<g_xd_color_count;++i)
    if(g_xd_color[i].tile==sourceTile){t=&g_xd_color[i];break;}
  if(!t)return false;
  VkImageMemoryBarrier fromColor={.sType=VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
    .srcAccessMask=VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT,
    .dstAccessMask=VK_ACCESS_TRANSFER_READ_BIT,
    .oldLayout=VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,
    .newLayout=VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
    .srcQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,
    .dstQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,.image=t->color,
    .subresourceRange={.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT,.levelCount=1,.layerCount=1}};
  state->CmdPipelineBarrier(cmd,VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT,
     VK_PIPELINE_STAGE_TRANSFER_BIT,0,0,NULL,0,NULL,1,&fromColor);
  VkImage image=t->color;
  if(t->samples!=VK_SAMPLE_COUNT_1_BIT) {
    VkImageMemoryBarrier toResolve={.sType=VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
      .srcAccessMask=0,.dstAccessMask=VK_ACCESS_TRANSFER_WRITE_BIT,
      .oldLayout=t->resolvedLayoutReady?VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL:VK_IMAGE_LAYOUT_UNDEFINED,
      .newLayout=VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
      .srcQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,
      .dstQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,.image=t->resolved,
      .subresourceRange={.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT,.levelCount=1,.layerCount=1}};
    state->CmdPipelineBarrier(cmd,VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,
      VK_PIPELINE_STAGE_TRANSFER_BIT,0,0,NULL,0,NULL,1,&toResolve);
    VkImageResolve region={.srcSubresource={.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT,.layerCount=1},
      .dstSubresource={.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT,.layerCount=1},
      .extent={t->extent.width,t->extent.height,1u}};
    XD(CmdResolveImage)(cmd,t->color,VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
      t->resolved,VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,1,&region);
    toResolve.srcAccessMask=VK_ACCESS_TRANSFER_WRITE_BIT;
    toResolve.dstAccessMask=VK_ACCESS_TRANSFER_READ_BIT;
    toResolve.oldLayout=VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
    toResolve.newLayout=VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
    state->CmdPipelineBarrier(cmd,VK_PIPELINE_STAGE_TRANSFER_BIT,
      VK_PIPELINE_STAGE_TRANSFER_BIT,0,0,NULL,0,NULL,1,&toResolve);
    t->resolvedLayoutReady=true;
    image=t->resolved;
  }
  if(swapchainInColorLayout) {
    VkImageMemoryBarrier toCopy={.sType=VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
      .srcAccessMask=VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT,
      .dstAccessMask=VK_ACCESS_TRANSFER_WRITE_BIT,
      .oldLayout=VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,
      .newLayout=VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
      .srcQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,
      .dstQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,
      .image=state->swapchain_images[imageIndex],
      .subresourceRange={.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT,
        .levelCount=1,.layerCount=1}};
    state->CmdPipelineBarrier(cmd,VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT,
      VK_PIPELINE_STAGE_TRANSFER_BIT,0,0,NULL,0,NULL,1,&toCopy);
  }
  // Native resolve to host presentation; guest physical writeback is separate.
  VkImageBlit region={.srcSubresource={.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT,.layerCount=1},
    .srcOffsets={{0,0,0},{(int32_t)t->extent.width,(int32_t)t->extent.height,1}},
    .dstSubresource={.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT,.layerCount=1},
    .dstOffsets={{0,0,0},{(int32_t)state->swapchain_extent.width,
                          (int32_t)state->swapchain_extent.height,1}}};
  XD(CmdBlitImage)(cmd,image,VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
    state->swapchain_images[imageIndex],VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
    1,&region,VK_FILTER_NEAREST);
  VkImageMemoryBarrier toAttachment={.sType=VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
    .srcAccessMask=VK_ACCESS_TRANSFER_WRITE_BIT,
    .dstAccessMask=VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT,
    .oldLayout=VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
    .newLayout=VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,
    .srcQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,
    .dstQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,
    .image=state->swapchain_images[imageIndex],
    .subresourceRange={.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT,.levelCount=1,.layerCount=1}};
  state->CmdPipelineBarrier(cmd,VK_PIPELINE_STAGE_TRANSFER_BIT,
    VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT,0,0,NULL,0,NULL,1,&toAttachment);
  KKLog(@"XENOS_EDRAM_RESOLVE_NATIVE source_tile=%u samples=%u pitch=%u copied_to_swapchain=1 guest_memory_commit=0",
    sourceTile,(unsigned)t->samples,t->pitch);
  return true;
}
