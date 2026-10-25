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
typedef struct {
  XDBuffer readback;
  uint32_t dest,pitch,height,info;
  bool pending;
} XDGuestResolve;
static XDGuestResolve g_xd_guest_resolves[16]={0};
static uint32_t g_xd_guest_resolves_count=0;
static void XDCommitGuestResolves(KKVulkanState* state) {
  for(uint32_t i=0;i<g_xd_guest_resolves_count;++i) {
    XDGuestResolve* r=&g_xd_guest_resolves[i];
    if(!r->pending || !r->readback.mapped)continue;
    VkResult invalidate=VK_SUCCESS;
    if(!(r->readback.flags&VK_MEMORY_PROPERTY_HOST_COHERENT_BIT)){
      VkMappedMemoryRange range={.sType=VK_STRUCTURE_TYPE_MAPPED_MEMORY_RANGE,
         .memory=r->readback.memory,.offset=0,.size=VK_WHOLE_SIZE};
      PFN_vkInvalidateMappedMemoryRanges fn=
          (PFN_vkInvalidateMappedMemoryRanges)state->GetDeviceProcAddr(
              state->device,"vkInvalidateMappedMemoryRanges");
      invalidate=fn?fn(state->device,1,&range):VK_ERROR_EXTENSION_NOT_PRESENT;
    }
    const size_t size=(size_t)r->pitch*r->height*4u;
    const bool ok=invalidate==VK_SUCCESS &&
       xowue_xenos_commit_resolved_rgba(r->dest,r->pitch,r->height,
                                        r->info,(const uint8_t*)r->readback.mapped,size);
    KKLog(@"XENOS_GUEST_RESOLVE_WRITEBACK addr=%08X pitch=%u height=%u status=%u vk=%d",
          r->dest,r->pitch,r->height,ok?1u:0u,invalidate);
    r->pending=false;
    XDDestroyBuffer(state,&r->readback);
  }
  memset(g_xd_guest_resolves,0,sizeof(g_xd_guest_resolves));
  g_xd_guest_resolves_count=0;
}

static void XDDestroyGuestColor(KKVulkanState* state) {
  if(!state->device)return;
  for(uint32_t i=0;i<g_xd_guest_resolves_count;++i)
     XDDestroyBuffer(state,&g_xd_guest_resolves[i].readback);
  memset(g_xd_guest_resolves,0,sizeof(g_xd_guest_resolves));
  g_xd_guest_resolves_count=0;
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
  if(!pitch||pitch>2048u||msaa>2u)return NULL;
  const VkSampleCountFlagBits samples=(VkSampleCountFlagBits)(1u<<msaa);
  const VkFormat imageFormat=fmt==0u?VK_FORMAT_R8G8B8A8_UNORM:
                             fmt==2u?VK_FORMAT_A2B10G10R10_UNORM_PACK32:
                             fmt==3u?VK_FORMAT_R16G16B16A16_SFLOAT:
                             VK_FORMAT_UNDEFINED;
  if(imageFormat==VK_FORMAT_UNDEFINED)return NULL;
  for(uint32_t i=0;i<g_xd_color_count;++i)
    if(g_xd_color[i].tile==tile&&g_xd_color[i].pitch==pitch&&
       g_xd_color[i].format==fmt&&g_xd_color[i].samples==samples)return &g_xd_color[i];
  if(g_xd_color_count>=16u)return NULL;
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
  // RB_COPY_CONTROL bits 0:2 select one of four color render targets,
  // or depth at index 4. Bits 20:21 specify the copy command. Do not
  // read color target 0 when the guest selected another surface / depth.
  // Xenia registers.h / RB_COPY_CONTROL (Xbox Xenos layout).
  const uint32_t sourceIndex=draw->rb_copy_control&7u;
  const uint32_t command=(draw->rb_copy_control>>20u)&3u;
  if(sourceIndex>=4u || command>1u) {
    KKLog(@"XENOS_COPY_SOURCE_UNSUPPORTED src=%u command=%u control=%08X",
       sourceIndex,command,draw->rb_copy_control);
    return false;
  }
  // Only resolve EDRAM surfaces actually written by real guest color draws.
  // The game's boot copied color target 0, tile 720; the prior draws had
  // created only a depth image, so producing arbitrary pixels is invalid.
  const uint32_t sourceTile=draw->rb_color_info[sourceIndex]&0xFFFu;
  XDColorTarget* t=NULL;
  for(uint32_t i=0;i<g_xd_color_count;++i)
    if(g_xd_color[i].tile==sourceTile){t=&g_xd_color[i];break;}
  if(!t) {
    KKLog(@"XENOS_COPY_MISSING_GUEST_COLOR src=%u command=%u tile=%u available_color=%u",
      sourceIndex,command,sourceTile,g_xd_color_count);
    return false;
  }
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
  // Write back the original GPU-produced color to Xbox guest memory.
  // Readback is queued in the same command buffer as the resolve; the CPU
  // commits it only *after* QueueWaitIdle, never before GPU completion.
  const uint32_t copyPitch=draw->rb_copy_dest_pitch&0x3FFFu;
  const uint32_t copyHeight=(draw->rb_copy_dest_pitch>>16u)&0x3FFFu;
  const uint32_t copyFormat=(draw->rb_copy_dest_info>>7u)&63u;
  if(t->format==0u && copyFormat==6u && copyPitch>0u && copyHeight>0u &&
     copyPitch<=t->extent.width && copyHeight<=t->extent.height &&
     g_xd_guest_resolves_count<16u) {
      XDGuestResolve* record=&g_xd_guest_resolves[g_xd_guest_resolves_count];
      const VkDeviceSize size=(VkDeviceSize)copyPitch*copyHeight*4u;
      if(XDCreateBuffer(state,&record->readback,size,
                        VK_BUFFER_USAGE_TRANSFER_DST_BIT)) {
         VkBufferImageCopy toBuffer={
           .bufferOffset=0u,.bufferRowLength=0u,.bufferImageHeight=0u,
           .imageSubresource={.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT,.layerCount=1u},
           .imageExtent={copyPitch,copyHeight,1u}};
         XD(CmdCopyImageToBuffer)(cmd,image,VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
                                 record->readback.buffer,1u,&toBuffer);
         record->dest=draw->rb_copy_dest_base;
         record->pitch=copyPitch;record->height=copyHeight;
         record->info=draw->rb_copy_dest_info;record->pending=true;
         ++g_xd_guest_resolves_count;
         KKLog(@"XENOS_GPU_RESOLVE_READBACK_QUEUED addr=%08X %ux%u bytes=%llu",
               record->dest,copyPitch,copyHeight,(unsigned long long)size);
      } else {
         XDDestroyBuffer(state,&record->readback);
         KKLog(@"GRAPHICS_BLOCKER reason=GUEST_RESOLVE_STAGING_CREATE_FAILED bytes=%llu",
               (unsigned long long)size);
      }
  } else {
    KKLog(@"XENOS_GUEST_RESOLVE_WRITEBACK_UNSUPPORTED edramfmt=%u destfmt=%u pitch=%u height=%u capacity=%u",
      t->format,copyFormat,copyPitch,copyHeight,g_xd_guest_resolves_count);
  }
  // Native resolve to host presentation after guest writeback copy request.
  // Letterbox the 1280x720 (16:9) Xbox 360 frame like XOWUENativeDraw.inc
  // instead of stretching it over the whole swapchain extent.
  const float swapW=(float)state->swapchain_extent.width;
  const float swapH=(float)state->swapchain_extent.height;
  const float fit=fminf(swapW/1280.0f,swapH/720.0f);
  const float fittedW=1280.0f*fit, fittedH=720.0f*fit;
  const int32_t dstX0=(int32_t)((swapW-fittedW)*0.5f);
  const int32_t dstY0=(int32_t)((swapH-fittedH)*0.5f);
  const int32_t dstX1=dstX0+(int32_t)fittedW;
  const int32_t dstY1=dstY0+(int32_t)fittedH;
  VkImageBlit region={.srcSubresource={.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT,.layerCount=1},
    .srcOffsets={{0,0,0},{(int32_t)t->extent.width,(int32_t)t->extent.height,1}},
    .dstSubresource={.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT,.layerCount=1},
    .dstOffsets={{dstX0,dstY0,0},{dstX1,dstY1,1}}};
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
