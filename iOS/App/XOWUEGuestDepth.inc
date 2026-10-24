// Native guest Xenos depth-only EDRAM attachments (Metal via Vulkan).
// Every target carries the guest EDRAM tile, pitch and actual sample count.
typedef struct {
  uint32_t tile,pitch;
  VkSampleCountFlagBits samples;
  VkImage image;
  VkDeviceMemory memory;
  VkImageView view;
  VkRenderPass pass;
  VkFramebuffer framebuffer;
  VkExtent2D extent;
} XDDepthTarget;
static XDDepthTarget g_xd_depth[8]={0};
static uint32_t g_xd_depth_count=0;
static void XDDestroyGuestDepth(KKVulkanState* state) {
  if(!state->device)return;
  for(uint32_t i=0;i<g_xd_depth_count;++i) {
    XDDepthTarget* t=&g_xd_depth[i];
    if(t->framebuffer)XD(DestroyFramebuffer)(state->device,t->framebuffer,NULL);
    if(t->pass)XD(DestroyRenderPass)(state->device,t->pass,NULL);
    if(t->view)XD(DestroyImageView)(state->device,t->view,NULL);
    if(t->image)XD(DestroyImage)(state->device,t->image,NULL);
    if(t->memory)state->FreeMemory(state->device,t->memory,NULL);
  }
  memset(g_xd_depth,0,sizeof(g_xd_depth));g_xd_depth_count=0;
}
static XDDepthTarget* XDGetGuestDepth(KKVulkanState* state,
                                      const XOWUEGuestDraw* draw) {
  const uint32_t tile=draw->rb_depth_info&0xFFFu;
  const uint32_t pitch=draw->rb_surface_info&0x3FFFu;
  const uint32_t mode=(draw->rb_surface_info>>16u)&3u;
  if(!pitch||pitch>2048u||mode>2u)return NULL;
  VkSampleCountFlagBits samples=(VkSampleCountFlagBits)(1u<<mode);
  for(uint32_t i=0;i<g_xd_depth_count;++i)
    if(g_xd_depth[i].tile==tile&&g_xd_depth[i].pitch==pitch&&
       g_xd_depth[i].samples==samples)return &g_xd_depth[i];
  if(g_xd_depth_count==8u)return NULL;
  VkPhysicalDeviceProperties props={0};
  state->GetPhysicalDeviceProperties(state->physical_device,&props);
  if(!(props.limits.framebufferDepthSampleCounts&samples))return NULL;
  XDDepthTarget* t=&g_xd_depth[g_xd_depth_count];
  t->tile=tile;t->pitch=pitch;t->samples=samples;
  t->extent=(VkExtent2D){pitch,1024u};
  VkImageCreateInfo image={.sType=VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO,
    .imageType=VK_IMAGE_TYPE_2D,.format=VK_FORMAT_D32_SFLOAT,
    .extent={pitch,1024u,1u},.mipLevels=1u,.arrayLayers=1u,
    .samples=samples,.tiling=VK_IMAGE_TILING_OPTIMAL,
    .usage=VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT,
    .sharingMode=VK_SHARING_MODE_EXCLUSIVE,
    .initialLayout=VK_IMAGE_LAYOUT_UNDEFINED};
  if(XD(CreateImage)(state->device,&image,NULL,&t->image)!=VK_SUCCESS)goto fail;
  VkMemoryRequirements req={0};XD(GetImageMemoryRequirements)(state->device,t->image,&req);
  VkPhysicalDeviceMemoryProperties propsMem={0};
  state->GetPhysicalDeviceMemoryProperties(state->physical_device,&propsMem);
  uint32_t memoryType=UINT32_MAX;
  for(uint32_t i=0;i<propsMem.memoryTypeCount;++i)
    if((req.memoryTypeBits&(1u<<i))&&
       (propsMem.memoryTypes[i].propertyFlags&VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT)){
      memoryType=i;break;
    }
  if(memoryType==UINT32_MAX) {
    for(uint32_t i=0;i<propsMem.memoryTypeCount;++i)
      if(req.memoryTypeBits&(1u<<i)){memoryType=i;break;}
  }
  if(memoryType==UINT32_MAX)goto fail;
  VkMemoryAllocateInfo alloc={.sType=VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
    .allocationSize=req.size,.memoryTypeIndex=memoryType};
  if(state->AllocateMemory(state->device,&alloc,NULL,&t->memory)!=VK_SUCCESS||
     XD(BindImageMemory)(state->device,t->image,t->memory,0)!=VK_SUCCESS)goto fail;
  VkImageViewCreateInfo view={.sType=VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO,
    .image=t->image,.viewType=VK_IMAGE_VIEW_TYPE_2D,
    .format=VK_FORMAT_D32_SFLOAT,
    .subresourceRange={.aspectMask=VK_IMAGE_ASPECT_DEPTH_BIT,
      .levelCount=1,.layerCount=1}};
  if(XD(CreateImageView)(state->device,&view,NULL,&t->view)!=VK_SUCCESS)goto fail;
  VkAttachmentDescription attachment={.format=VK_FORMAT_D32_SFLOAT,
    .samples=samples,.loadOp=VK_ATTACHMENT_LOAD_OP_CLEAR,
    .storeOp=VK_ATTACHMENT_STORE_OP_STORE,
    .stencilLoadOp=VK_ATTACHMENT_LOAD_OP_DONT_CARE,
    .stencilStoreOp=VK_ATTACHMENT_STORE_OP_DONT_CARE,
    .initialLayout=VK_IMAGE_LAYOUT_UNDEFINED,
    .finalLayout=VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL};
  VkAttachmentReference ref={.attachment=0,
    .layout=VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL};
  VkSubpassDescription subpass={.pipelineBindPoint=VK_PIPELINE_BIND_POINT_GRAPHICS,
    .colorAttachmentCount=0,.pDepthStencilAttachment=&ref};
  VkRenderPassCreateInfo rp={.sType=VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO,
    .attachmentCount=1,.pAttachments=&attachment,.subpassCount=1,.pSubpasses=&subpass};
  if(XD(CreateRenderPass)(state->device,&rp,NULL,&t->pass)!=VK_SUCCESS)goto fail;
  VkFramebufferCreateInfo fb={.sType=VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO,
    .renderPass=t->pass,.attachmentCount=1,.pAttachments=&t->view,
    .width=pitch,.height=1024u,.layers=1u};
  if(XD(CreateFramebuffer)(state->device,&fb,NULL,&t->framebuffer)!=VK_SUCCESS)goto fail;
  ++g_xd_depth_count;
  KKLog(@"XENOS_EDRAM_DEPTH_NATIVE tile=%u pitch=%u samples=%u",
    tile,pitch,(unsigned)samples);
  return t;
fail:
  if(t->framebuffer)XD(DestroyFramebuffer)(state->device,t->framebuffer,NULL);
  if(t->pass)XD(DestroyRenderPass)(state->device,t->pass,NULL);
  if(t->view)XD(DestroyImageView)(state->device,t->view,NULL);
  if(t->image)XD(DestroyImage)(state->device,t->image,NULL);
  if(t->memory)state->FreeMemory(state->device,t->memory,NULL);
  memset(t,0,sizeof(*t));
  KKLog(@"GRAPHICS_BLOCKER reason=EDRAM_DEPTH_RESOURCE_CREATE tile=%u pitch=%u samples=%u",
    tile,pitch,(unsigned)samples);
  return NULL;
}
