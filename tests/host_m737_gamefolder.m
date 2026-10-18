/* M7.37 native Foundation host proof: actual read-only folder traversal
 * with synthetic files. No commercial PS3 assets in repository or logs.
 */
#import <Foundation/Foundation.h>
#include <stdio.h>
#import "../ios/ARGameFolderStore.h"
static int check(BOOL ok,int status,NSString *message) {
 if(!ok)NSLog(@"M7.37 FAIL %d: %@",status,message);
 return ok?0:status;
}
int main(void) {
 @autoreleasepool {
  NSFileManager *fm=NSFileManager.defaultManager;
  NSURL *root=[[NSURL fileURLWithPath:NSTemporaryDirectory() isDirectory:YES]
    URLByAppendingPathComponent:[[NSUUID UUID] UUIDString] isDirectory:YES];
  NSURL *dir=[root URLByAppendingPathComponent:@"USRDIR" isDirectory:YES];
  NSError *e=nil;
  if(![fm createDirectoryAtURL:dir withIntermediateDirectories:YES
                    attributes:nil error:&e])return 1;
  NSURL *psarc=[dir URLByAppendingPathComponent:@"core.psarc"];
  NSURL *param=[dir URLByAppendingPathComponent:@"params.bin"];
  NSData *expected=[@"ABCD1234" dataUsingEncoding:NSUTF8StringEncoding];
  if(![expected writeToURL:psarc atomically:YES] ||
     ![[@"Z" dataUsingEncoding:NSUTF8StringEncoding]
       writeToURL:param atomically:YES])return 2;
  NSURL *link=[dir URLByAppendingPathComponent:@"escape"];
  [fm createSymbolicLinkAtPath:link.path withDestinationPath:@"/etc/passwd"
                        error:NULL];
  NSDictionary *manifest=ARGameFolderImport(root,&e);
  if(check(manifest!=nil,3,e.localizedDescription?:@"no manifest"))return 3;
  if(check([manifest[@"file_count"] unsignedIntegerValue]==2,4,@"count")||
     check([manifest[@"total_bytes"] unsignedLongLongValue]==9,5,@"bytes")||
     check([manifest[@"symlinks_skipped"] unsignedIntegerValue]==1,6,@"symlink"))
   return 4;
  NSMutableSet *names=[NSMutableSet set];
  for(NSDictionary *f in manifest[@"files"]){
   if([f[@"path"] hasPrefix:@"/"])return 7;
   [names addObject:f[@"path"]];
  }
  if(check([names containsObject:@"USRDIR/core.psarc"] &&
           [names containsObject:@"USRDIR/params.bin"],8,@"manifest entries"))
      return 8;
  NSDictionary *restored=ARGameFolderRestore(&e);
  if(check([restored[@"file_count"] unsignedIntegerValue]==2,9,
           e.localizedDescription?:@"restore"))return 9;
  NSData *four=ARGameFolderReadPrefix(@"USRDIR/core.psarc",4,&e);
  if(check(four.length==4,10,e.localizedDescription?:@"read") ||
     check([four isEqualToData:[@"ABCD" dataUsingEncoding:NSUTF8StringEncoding]],
           11,@"bytes"))return 10;
  for(NSString *bad in @[@"../etc/passwd",@"/etc/passwd",
                         @"USRDIR/../params.bin",@"USRDIR/escape"]){
    NSError *badError=nil;
    if(ARGameFolderReadPrefix(bad,4,&badError)!=nil || !badError)return 12;
  }
  if(ARGameFolderReadPrefix(@"USRDIR/core.psarc",65537,&e)!=nil)return 13;
  [fm removeItemAtURL:root error:NULL];
  puts("M7.37 F0 local game folder: 2 manifest files, 9 bytes, 1 symlink skipped, bookmark restore, real 4-byte read, traversal denied PASS");
  return 0;
 }
}
