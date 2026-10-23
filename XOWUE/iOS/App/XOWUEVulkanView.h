#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

/// iOS CAMetalLayer host for the KosmicKrisp Vulkan/Metal WSI backend.
/// It currently renders an explicit diagnostic clear frame, not an Xenos scene.
@interface XOWUEVulkanView : UIView
@end

NS_ASSUME_NONNULL_END
