/* M7.37: read-only local game folder importer, no assets in IPA or GitHub.
 * All paths and bookmark bytes remain on the user's iPhone.
 */
#import <Foundation/Foundation.h>
NS_ASSUME_NONNULL_BEGIN
FOUNDATION_EXPORT NSDictionary<NSString*,id> * _Nullable
ARGameFolderImport(NSURL *folder, NSError **error);
FOUNDATION_EXPORT NSDictionary<NSString*,id> * _Nullable
ARGameFolderRestore(NSError **error);
/* M7.39: independent local Files -> On My iPhone -> App Documents route.
 * User moves/copies the NPUA80918 folder into the app's Files container.
 * No document picker, security scope or cloud directory selection needed.
 */
FOUNDATION_EXPORT NSDictionary<NSString*,id> * _Nullable
ARGameFolderImportLocalDocuments(NSError **error);
/* Injected Documents root for synthetic Mac tests only; same production path. */
FOUNDATION_EXPORT NSDictionary<NSString*,id> * _Nullable
ARGameFolderImportLocalAtURL(NSURL *documents, NSError **error);
FOUNDATION_EXPORT NSData * _Nullable
ARGameFolderReadPrefix(NSString *relativePath, NSUInteger maxLength,
                       NSError **error);
NS_ASSUME_NONNULL_END
