/* M7.40 noncopy in-place PARAM.SFO capability probe under a fake RPCS3
 * Files hierarchy. Reads (never writes) the original marker and existing
 * game payload. The runtime may fail closed on device if iOS only grants
 * the selected file, which this host fixture cannot simulate.
 */
#import <Foundation/Foundation.h>
#include <stdio.h>
#import "../ios/ARGameFolderStore.h"
static int check(BOOL ok,int code,NSString *why) {
 if(!ok)NSLog(@"M7.40 error %d %@",code,why);
 return ok?0:code;
}
int main(void) {
 @autoreleasepool {
  NSFileManager *fm=NSFileManager.defaultManager;
  NSURL *tmp=[[NSURL fileURLWithPath:NSTemporaryDirectory() isDirectory:YES]
      URLByAppendingPathComponent:[[NSUUID UUID] UUIDString] isDirectory:YES];
  NSURL *dir=tmp;
  for(NSString *component in @[@"rpcs3",@"data",@"dev_hdd0",
                               @"game",@"NPUA80918"]) {
   dir=[dir URLByAppendingPathComponent:component isDirectory:YES];
  }
  NSURL *usrdir=[dir URLByAppendingPathComponent:@"USRDIR" isDirectory:YES];
  NSError *err=nil;
  if(![fm createDirectoryAtURL:usrdir withIntermediateDirectories:YES
                    attributes:nil error:&err])return check(NO,1,err.description);
  NSURL *marker=[dir URLByAppendingPathComponent:@"PARAM.SFO" isDirectory:NO];
  NSURL *asset=[usrdir URLByAppendingPathComponent:@"test.bin"];
  NSData *sfo=[@"PSF-HEADER" dataUsingEncoding:NSUTF8StringEncoding];
  NSData *payload=[@"SYNTHETIC-ASSET" dataUsingEncoding:NSUTF8StringEncoding];
  if(![sfo writeToURL:marker atomically:YES] ||
     ![payload writeToURL:asset atomically:YES])return 2;
  NSDictionary *manifest=ARGameFolderProbeRPCS3Marker(marker,&err);
  if(!manifest)return check(NO,3,err.description?:@"nil marker result");
  if(check([manifest[@"folder_access_verified"] boolValue],4,@"scope")||
     check([manifest[@"read_only"] boolValue]&&
           [manifest[@"no_copy"] boolValue],5,@"read-only")||
     check([manifest[@"file_count"] intValue]==2,6,@"count")||
     check([manifest[@"param_sfo_prefix_bytes"] intValue]==4,7,@"prefix"))
     return 4;
  /* Original files must be byte-for-byte unchanged after the probe. */
  NSData *sfoAfter=[NSData dataWithContentsOfURL:marker];
  NSData *assetAfter=[NSData dataWithContentsOfURL:asset];
  if(check([sfoAfter isEqualToData:sfo],8,@"modified PARAM.SFO")||
     check([assetAfter isEqualToData:payload],9,@"modified USRDIR"))
     return 8;
  NSURL *wrong=[dir URLByAppendingPathComponent:@"SND0.AT3"];
  [sfo writeToURL:wrong atomically:YES];
  err=nil;
  if(ARGameFolderProbeRPCS3Marker(wrong,&err)!=nil ||
     err.code!=41)return 10;
  NSURL *missing=[dir URLByAppendingPathComponent:@"USRDIR"];
  if(![fm removeItemAtURL:missing error:&err])return 11;
  err=nil;
  if(ARGameFolderProbeRPCS3Marker(marker,&err)!=nil ||
     err.code!=44)return check(NO,12,err.description?:@"failed closed");
  [fm removeItemAtURL:tmp error:NULL];
  puts("M7.40 read-only RPCS3 PARAM.SFO in-place: exact path, 4-byte coordinated read, original files unchanged, USRDIR manifest, invalid marker denied, unavailable directory denied PASS");
  return 0;
 }
}
