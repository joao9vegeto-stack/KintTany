/* PoPTST/reSOT: SDL3 3.4.18 Metal native occlusion query extension.
 * This file is injected inside SDL_gpu_metal.m by patch_sdl_metal_query.py.
 * Same ResotGpuQueryAPI ABI as reSOT's Vulkan extension. MIT.
 * IMPORTANT: limited to ONE visibility query per render pass, matching the
 * verified retail ng_flush_draws() call sequence. Unsupported usage fails.
 * Unlike a software stand-in, all sample counts are written by the GPU.
 */
#include "resot_gpu_query.h"

typedef struct ResotMetalQuery {
    id<MTLBuffer> buffer;
    id<MTLCommandBuffer> commandBuffer;
    bool begun;
    bool ended;
    bool failed;
} ResotMetalQuery;

static void SDLCALL resot_metal_destroy(SDL_GPUDevice *device, void *opaque)
{
    (void)device;
    ResotMetalQuery *q = (ResotMetalQuery *)opaque;
    if (!q) return;
    /* Safe only after reSOT's retirement fence, identical to Vulkan ABI. */
    q->buffer = nil;
    q->commandBuffer = nil;
    SDL_free(q);
}

static void *SDLCALL resot_metal_create(SDL_GPUDevice *device)
{
    MetalRenderer *r = (MetalRenderer *)device->driverData;
    if (!r || !r->device) return NULL;
    ResotMetalQuery *q = SDL_calloc(1, sizeof *q);
    if (!q) return NULL;
    q->buffer = [r->device newBufferWithLength:sizeof(Uint64)
                                      options:MTLResourceStorageModeShared];
    if (!q->buffer || !q->buffer.contents) {
        SDL_SetError("PoPTST Metal: cannot allocate shared query result buffer");
        resot_metal_destroy(device, q);
        return NULL;
    }
    return q;
}

static void SDLCALL resot_metal_reset(SDL_GPUCommandBuffer *cmd, void *opaque)
{
    MetalCommandBuffer *c = (MetalCommandBuffer *)cmd;
    ResotMetalQuery *q = (ResotMetalQuery *)opaque;
    if (!c || !q || !c->handle || c->resotPendingQuery || c->resotActiveQuery ||
        q->begun || q->ended || q->commandBuffer) {
        if (q) q->failed = true;
        SDL_SetError("PoPTST Metal: invalid query reset or multiple queries per pass");
        return;
    }
    /* This 0 is only buffer initialization. A guest-visible result is never
     * taken from it until the native command buffer completes successfully. */
    SDL_memset(q->buffer.contents, 0, sizeof(Uint64));
    c->resotPendingQuery = q;
    q->commandBuffer = c->handle; // hold native completion status beyond SDL recycling
}

/* Called from SDL's METAL_BeginRenderPass BEFORE creating its encoder. */
static void resot_metal_attach_query(MetalCommandBuffer *c, MTLRenderPassDescriptor *d)
{
    if (!c->resotPendingQuery) return;
    ResotMetalQuery *q = c->resotPendingQuery;
    c->resotPendingQuery = NULL;
    if (c->resotActiveQuery || q->failed || !q->buffer) {
        q->failed = true;
        SDL_SetError("PoPTST Metal: query render pass attachment failed");
        return;
    }
    d.visibilityResultBuffer = q->buffer;
    c->resotActiveQuery = q;
}

static void SDLCALL resot_metal_begin(SDL_GPUCommandBuffer *cmd, void *opaque)
{
    MetalCommandBuffer *c = (MetalCommandBuffer *)cmd;
    ResotMetalQuery *q = (ResotMetalQuery *)opaque;
    if (!c || !q || !c->renderEncoder || c->resotActiveQuery != q ||
        q->failed || q->begun) {
        if (q) q->failed = true;
        SDL_SetError("PoPTST Metal: invalid query begin");
        return;
    }
    [c->renderEncoder setVisibilityResultMode:MTLVisibilityResultModeCounting offset:0];
    q->begun = true;
}

static void SDLCALL resot_metal_end(SDL_GPUCommandBuffer *cmd, void *opaque)
{
    MetalCommandBuffer *c = (MetalCommandBuffer *)cmd;
    ResotMetalQuery *q = (ResotMetalQuery *)opaque;
    if (!c || !q || !c->renderEncoder || c->resotActiveQuery != q ||
        !q->begun || q->ended || q->failed) {
        if (q) q->failed = true;
        SDL_SetError("PoPTST Metal: invalid query end");
        return;
    }
    [c->renderEncoder setVisibilityResultMode:MTLVisibilityResultModeDisabled offset:0];
    q->ended = true;
}

static void SDLCALL resot_metal_resolve(SDL_GPUCommandBuffer *cmd, void *opaque)
{
    (void)cmd;
    ResotMetalQuery *q = (ResotMetalQuery *)opaque;
    /* Metal writes the shared visibility buffer during render pass execution;
     * no explicit vkCmdCopyQueryPoolResults analogue is needed. */
    if (!q || !q->begun || !q->ended || q->failed)
        SDL_SetError("PoPTST Metal: failed or incomplete query resolution");
}

static bool SDLCALL resot_metal_read(SDL_GPUDevice *device, void *opaque, Uint64 *samples)
{
    (void)device;
    ResotMetalQuery *q = (ResotMetalQuery *)opaque;
    if (!q || !samples || !q->begun || !q->ended || q->failed || !q->commandBuffer)
        return SDL_SetError("PoPTST Metal: query missing, failed or incomplete");
    if (q->commandBuffer.status != MTLCommandBufferStatusCompleted)
        return SDL_SetError("PoPTST Metal: native GPU command buffer did not complete");
    if (!q->buffer.contents) return SDL_SetError("PoPTST Metal: no query result memory");
    SDL_memcpy(samples, q->buffer.contents, sizeof *samples);
    return true;
}

static bool SDLCALL resot_metal_healthy(SDL_GPUDevice *device)
{
    MetalRenderer *r = (MetalRenderer *)device->driverData;
    if (!r) return SDL_SetError("PoPTST Metal: GPU renderer unavailable");
    /* The reSOT controller also checks every query command buffer on read;
     * actively submitted buffers are checked here without blocking. */
    SDL_LockMutex(r->submitLock);
    for (Uint32 i = 0; i < r->submittedCommandBufferCount; i++) {
        MetalFence *f = r->submittedCommandBuffers[i]->fence;
        if (f && f->commandBuffer.status == MTLCommandBufferStatusError) {
            SDL_UnlockMutex(r->submitLock);
            return SDL_SetError("PoPTST Metal: native command buffer failed");
        }
    }
    SDL_UnlockMutex(r->submitLock);
    return true;
}

__attribute__((visibility("default")))
const ResotGpuQueryAPI *SDLCALL RESOT_GetMetalQueryAPI(Uint32 version)
{
    static const ResotGpuQueryAPI api = {
        RESOT_GPU_QUERY_ABI, sizeof(ResotGpuQueryAPI), "metal",
        resot_metal_create, resot_metal_destroy, resot_metal_reset,
        resot_metal_begin, resot_metal_end, resot_metal_resolve,
        resot_metal_read, resot_metal_healthy
    };
    return version == RESOT_GPU_QUERY_ABI ? &api : NULL;
}
