/* M7.39: exercise exact sandbox Documents import route on Mac using
 * synthetic mini game directory, not user's commercial game files.
 * Folder picker is deliberately NOT needed by this execution path.
 */
#import <Foundation/Foundation.h>
#include <stdio.h>
#import "../ios/ARGameFolderStore.h"
static int fail(int n,NSString *s) {NSLog(@"M7.39 fail %d %@",n,s);return n;}
int main(void) {
 @autoreleasepool {
  NSFileManager *fm=NSFileManager.defaultManager;
  NSURL *base=[[NSURL fileURLWithPath:NSTemporaryDirectory() isDirectory:YES]
       URLByAppendingPathComponent:[[NSUUID UUID] UUIDString] isDirectory:YES];
  NSURL *documents=[base URLByAppendingPathComponent:@"Documents" isDirectory:YES];
  NSError *error=nil;
  if(![fm createDirectoryAtURL:documents withIntermediateDirectories:YES
                    attributes:nil error:&error])return fail(1,error.description);
  if(ARGameFolderImportLocalAtURL(documents,&error))return fail(2,@"folder unexpectedly detected");
  if(error.code!=32)return fail(3,error.description);
  NSURL *title=[documents URLByAppendingPathComponent:@"NPUA80918" isDirectory:YES];
  NSURL *usrdir=[title URLByAppendingPathComponent:@"USRDIR" isDirectory:YES];
  if(![fm createDirectoryAtURL:usrdir withIntermediateDirectories:YES
                    attributes:nil error:&error])return fail(4,error.description);
  NSURL *file=[usrdir URLByAppendingPathComponent:@"TEST.PSARC"];
  NSData *data=[@"RSX123" dataUsingEncoding:NSUTF8StringEncoding];
  if(![data writeToURL:file atomically:YES])return fail(5,@"write synthetic file");
  NSDictionary *manifest=ARGameFolderImportLocalAtURL(documents,&error);
  if(!manifest)return fail(6,error.description?:@"no manifest");
  if(![manifest[@"root_name"] isEqualToString:@"NPUA80918"]
     || [manifest[@"file_count"] integerValue]!=1
     || [manifest[@"total_bytes"] unsignedLongLongValue]!=6)
    return fail(7,manifest.description);
  NSData *read=ARGameFolderReadPrefix(@"USRDIR/TEST.PSARC",4,&error);
  if(read.length!=4 ||
     ![read isEqualToData:[@"RSX1" dataUsingEncoding:NSUTF8StringEncoding]])
     return fail(8,error.description?:@"wrong read");
  NSDictionary *restored=ARGameFolderRestore(&error);
  if(!restored || [restored[@"file_count"] integerValue]!=1)
     return fail(9,error.description?:@"restore failed");
  [fm removeItemAtURL:base error:NULL];
  puts("M7.39 Files On My iPhone Documents route: missing-directory error, NPUA80918 manifest, actual 4-byte host read, restored bookmark PASS");
  return 0;
 }
}
