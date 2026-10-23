#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

/// Full-screen iOS game viewport backed by KosmicKrisp Vulkan/Metal WSI.
/// The runtime must translate Xenos draws before a game frame can appear.
@interface XOWUEVulkanView : UIView
@end

NS_ASSUME_NONNULL_END
