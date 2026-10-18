/* M7.48 synthetic Documents home path: no commercial game assets.
 * The app CREATED the folder in 7.47 but forgot to scan its path. */
#import <Foundation/Foundation.h>
#import "../ios/ARGameFolderStore.h"
#include <stdio.h>
int main(void){
 @autoreleasepool{
  NSFileManager *fm=NSFileManager.defaultManager;NSError *err=nil;
  NSURL *base=[[NSURL fileURLWithPath:NSTemporaryDirectory() isDirectory:YES]
              URLByAppendingPathComponent:NSUUID.UUID.UUIDString isDirectory:YES];
  NSURL *docs=[base URLByAppendingPathComponent:@"Documents" isDirectory:YES];
  NSURL *title=[[docs URLByAppendingPathComponent:@"AscensionRecomp" isDirectory:YES]
               URLByAppendingPathComponent:@"NPUA80918" isDirectory:YES];
  if(![fm createDirectoryAtURL:title withIntermediateDirectories:YES attributes:nil error:&err])return 1;
  if(ARGameFolderImportLocalAtURL(docs,&err)!=nil || err.code!=32)return 2;
  NSURL *assets=[title URLByAppendingPathComponent:@"USRDIR" isDirectory:YES];
  if(![fm createDirectoryAtURL:assets withIntermediateDirectories:YES attributes:nil error:&err])return 3;
  NSURL *asset=[assets URLByAppendingPathComponent:@"GAME.DAT"];
  NSData *original=[@"SYNTHETIC-ONLY" dataUsingEncoding:NSUTF8StringEncoding];
  if(![original writeToURL:asset atomically:YES])return 4;
  NSDictionary *m=ARGameFolderImportLocalAtURL(docs,&err);
  if(!m || [m[@"file_count"] integerValue]!=1 ||
     ![m[@"root_name"] isEqualToString:@"NPUA80918"])return 5;
  NSData *read=ARGameFolderReadPrefix(@"USRDIR/GAME.DAT",4u,&err);
  if(![read isEqualToData:[@"SYNT" dataUsingEncoding:NSUTF8StringEncoding]])return 6;
  NSData *after=[NSData dataWithContentsOfURL:asset];
  if(![original isEqualToData:after])return 7;
  [fm removeItemAtURL:base error:NULL];
  puts("M7.48 local app Documents/AscensionRecomp/NPUA80918: empty home rejected; real synthetic file discovered READ-ONLY; unchanged contents PASS");
 }
 return 0;
}
