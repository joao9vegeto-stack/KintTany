#import "ARMetalView.h"
#import <QuartzCore/CAMetalLayer.h>
#import <Metal/Metal.h>
extern int rsx_metal_backend_set_ios_layer(void *metal_layer);
extern int rsx_metal_backend_set_ios_output_scale(float scale);

@interface ARMetalView ()
@property(nonatomic,assign) BOOL ps3BackendBound;
@end

@implementation ARMetalView
+ (Class)layerClass {
    return [CAMetalLayer class];
}
- (instancetype)initWithFrame:(CGRect)frame {
    if ((self=[super initWithFrame:frame])) _outputScale=1.0;
    return self;
}
- (void)setOutputScale:(CGFloat)outputScale {
    if (!(outputScale>=0.5 && outputScale<=1.0)) outputScale=1.0;
    _outputScale=outputScale;
    (void)rsx_metal_backend_set_ios_output_scale((float)outputScale);
    [self setNeedsLayout];
}
- (BOOL)bindToPS3MetalBackend {
    if (![NSThread isMainThread]) return NO;
    CAMetalLayer *drawableLayer=(CAMetalLayer *)self.layer;
    if (![drawableLayer isKindOfClass:[CAMetalLayer class]]) return NO;
    drawableLayer.opaque=YES;
    drawableLayer.contentsScale=self.contentScaleFactor;
    [self layoutIfNeeded];
    self.ps3BackendBound=
      rsx_metal_backend_set_ios_layer((__bridge void *)drawableLayer)==0;
    return self.ps3BackendBound;
}
- (void)layoutSubviews {
    [super layoutSubviews];
    /* Once bound, PS3Recomp owns drawableSize: the guest chooses its display
     * target, and changing it on device rotation would mismatch the Metal
     * drawable and its depth attachment. UIKit still scales the layer to the
     * view's bounds. */
    if (self.ps3BackendBound) return;
    CAMetalLayer *drawableLayer=(CAMetalLayer *)self.layer;
    CGFloat scale=self.window.screen.scale;
    if (scale<=0) scale=self.contentScaleFactor;
    if (scale<=0) scale=1;
    drawableLayer.contentsScale=scale;
    CGFloat outputScale=self.outputScale;
    if (!(outputScale>=0.5 && outputScale<=1.0)) outputScale=1.0;
    drawableLayer.drawableSize=CGSizeMake(self.bounds.size.width*scale*outputScale,
                                          self.bounds.size.height*scale*outputScale);
}
/* Tests the actual iPhone drawable path with a completed GPU command buffer.
 * Produces a visibly colored frame; it deliberately does not issue RSX
 * guest commands or claim Ascension textures are rendering. */
- (BOOL)presentDiagnosticFrame:(NSUInteger)frame
                         error:(NSString * _Nullable * _Nullable)error {
    if (![NSThread isMainThread]) {
        if (error) *error=@"A apresentação precisa ocorrer na thread principal.";
        return NO;
    }
    CAMetalLayer *layer=(CAMetalLayer *)self.layer;
    id<MTLDevice> device=layer.device;
    if (!device) {
        if (error) *error=@"O backend não atribuiu um dispositivo Metal ao layer.";
        return NO;
    }
    if (layer.drawableSize.width < 1 || layer.drawableSize.height < 1) {
        if (error) *error=@"O CAMetalLayer ainda está sem tamanho.";
        return NO;
    }
    id<MTLCommandQueue> queue=[device newCommandQueue];
    if (!queue) {
        if (error) *error=@"Não foi possível criar a fila Metal.";
        return NO;
    }
    id<CAMetalDrawable> drawable=[layer nextDrawable];
    if (!drawable || !drawable.texture) {
        if (error) *error=@"CAMetalLayer não entregou um drawable válido.";
        return NO;
    }
    MTLRenderPassDescriptor *pass=[MTLRenderPassDescriptor renderPassDescriptor];
    pass.colorAttachments[0].texture=drawable.texture;
    pass.colorAttachments[0].loadAction=MTLLoadActionClear;
    pass.colorAttachments[0].storeAction=MTLStoreActionStore;
    const MTLClearColor colors[3]={
        {0.04, 0.36, 0.70, 1.0},  /* vivid blue */
        {0.03, 0.57, 0.41, 1.0},  /* green */
        {0.47, 0.14, 0.68, 1.0}   /* purple */
    };
    pass.colorAttachments[0].clearColor=colors[frame % 3];
    id<MTLCommandBuffer> buffer=[queue commandBuffer];
    if (!buffer) {
        if (error) *error=@"Não foi possível criar o command buffer Metal.";
        return NO;
    }
    id<MTLRenderCommandEncoder> encoder=[buffer renderCommandEncoderWithDescriptor:pass];
    if (!encoder) {
        if (error) *error=@"Não foi possível abrir um render pass Metal.";
        return NO;
    }
    [encoder endEncoding];
    [buffer presentDrawable:drawable];
    [buffer commit];
    [buffer waitUntilCompleted];
    if (buffer.status!=MTLCommandBufferStatusCompleted) {
        if (error) *error=[NSString stringWithFormat:@"Falha no command buffer: %@",
                            buffer.error.localizedDescription ?: @"sem detalhes"];
        return NO;
    }
    return YES;
}

@end
