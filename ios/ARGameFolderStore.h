/* M7.37: read-only local game folder importer, no assets in IPA or GitHub.
 * All paths and bookmark bytes remain on the user's iPhone.
 */
#import <Foundation/Foundation.h>
NS_ASSUME_NONNULL_BEGIN
FOUNDATION_EXPORT NSDictionary<NSString*,id> * _Nullable
ARGameFolderImport(NSURL *folder, NSError **error);
/* M7.40: read-only existing RPCS3 installation probe. PARAM.SFO is opened
 * in place; never copied, moved, modified or re-saved. Only works if
 * the iOS URL security scope also allows the original NPUA80918 folder.
 * Failure is explicit and must not be bypassed with sandbox traversal.
 */
FOUNDATION_EXPORT NSDictionary<NSString*,id> * _Nullable
ARGameFolderProbeRPCS3Marker(NSURL *paramSfo, NSError **error);
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
/* Small copy-mode import, independent of parent folder access. */
FOUNDATION_EXPORT NSDictionary<NSString*,id> * _Nullable
ARGameFolderInspectParamSFO(NSURL *url, NSError **error);
/* Visible Documents home, no game payload. */
FOUNDATION_EXPORT BOOL ARGameFolderPrepareDocumentsHome(NSError **error);
FOUNDATION_EXPORT NSData * _Nullable
ARGameFolderReadPrefix(NSString *relativePath, NSUInteger maxLength,
                       NSError **error);
/* M7.51 guest I/O: only real guest HLE/syscall execution invokes this.
 * Returns no file bytes without validating the stored local manifest. */
FOUNDATION_EXPORT int ARGameFolderGuestIO(const char *relative,uint64_t offset,
                                            void *dst,size_t count,size_t *actual,
                                            uint64_t *size);
NS_ASSUME_NONNULL_END
