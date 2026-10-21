#import <UIKit/UIKit.h>

/* UIKit-provided CAMetalLayer host, independent of proprietary PS3 code. */
@interface ARMetalView : UIView
/* Relative size of the Metal presentation drawable (0.5...1.0). This scales
 * output pixels only; the game's RSX render targets remain game-controlled. */
@property(nonatomic,assign) CGFloat outputScale;
/* Call before RSX backend init, on the main thread. */
- (BOOL)bindToPS3MetalBackend;
/* Submit a real Metal clear pass to this CAMetalLayer on main thread.
 * This is a GPU/onscreen diagnostic, NOT a PS3 RSX draw command. */
- (BOOL)presentDiagnosticFrame:(NSUInteger)frame
                         error:(NSString * _Nullable * _Nullable)error;
@end
