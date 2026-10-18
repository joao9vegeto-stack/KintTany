/* M7.37: read-only local game folder importer, no assets in IPA or GitHub.
 * All paths and bookmark bytes remain on the user's iPhone.
 */
#import <Foundation/Foundation.h>
NS_ASSUME_NONNULL_BEGIN
FOUNDATION_EXPORT NSDictionary<NSString*,id> * _Nullable
ARGameFolderImport(NSURL *folder, NSError **error);
FOUNDATION_EXPORT NSDictionary<NSString*,id> * _Nullable
ARGameFolderRestore(NSError **error);
FOUNDATION_EXPORT NSData * _Nullable
ARGameFolderReadPrefix(NSString *relativePath, NSUInteger maxLength,
                       NSError **error);
NS_ASSUME_NONNULL_END
