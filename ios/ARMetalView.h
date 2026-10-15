#import <UIKit/UIKit.h>

/* UIKit-provided CAMetalLayer host, independent of proprietary PS3 code. */
@interface ARMetalView : UIView
/* Call before RSX backend init, on the main thread. */
- (BOOL)bindToPS3MetalBackend;
@end
