/* iOS rePOP native text for the diagnostics, backed by CoreGraphics/UIKit. */
#import <UIKit/UIKit.h>
#include <stdint.h>
void resot_host_draw_text(uint32_t *pixels, int width, int height,
                          int x, int y, const char *txt, uint32_t argb) {
    if (!pixels || width<=0 || height<=0 || !txt) return;
    CGColorSpaceRef color = CGColorSpaceCreateDeviceRGB();
    if (!color) return;
    CGContextRef context = CGBitmapContextCreate(pixels,(size_t)width,(size_t)height,
        8,(size_t)width*4,color,kCGImageAlphaPremultipliedFirst|kCGBitmapByteOrder32Little);
    CGColorSpaceRelease(color);
    if (!context) return;
    UIGraphicsPushContext(context);
    NSString *str=[NSString stringWithUTF8String:txt];
    UIColor *fg=[UIColor colorWithRed:((argb>>16)&255)/255.0 green:((argb>>8)&255)/255.0
                               blue:(argb&255)/255.0 alpha:((argb>>24)&255)/255.0];
    [str drawAtPoint:CGPointMake(x,y) withAttributes:@{
        NSFontAttributeName:[UIFont systemFontOfSize:16],NSForegroundColorAttributeName:fg}];
    UIGraphicsPopContext();
    CGContextRelease(context);
}
