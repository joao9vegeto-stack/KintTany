#import "ARMetalView.h"
#import <QuartzCore/CAMetalLayer.h>
extern int rsx_metal_backend_set_ios_layer(void *metal_layer);

@implementation ARMetalView
+ (Class)layerClass {
    return [CAMetalLayer class];
}
- (BOOL)bindToPS3MetalBackend {
    if (![NSThread isMainThread]) return NO;
    CAMetalLayer *drawableLayer=(CAMetalLayer *)self.layer;
    if (![drawableLayer isKindOfClass:[CAMetalLayer class]]) return NO;
    drawableLayer.opaque=YES;
    drawableLayer.contentsScale=self.contentScaleFactor;
    [self layoutIfNeeded];
    return rsx_metal_backend_set_ios_layer((__bridge void *)drawableLayer)==0;
}
- (void)layoutSubviews {
    [super layoutSubviews];
    CAMetalLayer *drawableLayer=(CAMetalLayer *)self.layer;
    CGFloat scale=self.window.screen.scale;
    if (scale<=0) scale=self.contentScaleFactor;
    if (scale<=0) scale=1;
    drawableLayer.contentsScale=scale;
    drawableLayer.drawableSize=CGSizeMake(self.bounds.size.width*scale,
                                          self.bounds.size.height*scale);
}
@end
