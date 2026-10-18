/* M7.47 host-only test: valid PSF1 TITLE_ID, wrong ID and corrupt index.
 * The picker-selected file is temporary; never grant USRDIR permission. */
#import <Foundation/Foundation.h>
#import "../ios/ARGameFolderStore.h"
static void le16(uint8_t*p,uint16_t v){p[0]=v&255;p[1]=(v>>8)&255;}
static void le32(uint8_t*p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(i*8));}
int main(void){
 @autoreleasepool {
  NSString *tmp=[NSTemporaryDirectory() stringByAppendingPathComponent:
       [NSString stringWithFormat:@"m747-%@",NSUUID.UUID.UUIDString]];
  NSURL *folder=[NSURL fileURLWithPath:tmp isDirectory:YES];
  NSError *e=nil;
  if(![NSFileManager.defaultManager createDirectoryAtURL:folder
        withIntermediateDirectories:YES attributes:nil error:&e])return 1;
  NSURL *file=[folder URLByAppendingPathComponent:@"PARAM.SFO"];
  uint8_t d[58]={0,'P','S','F'};
  le32(d+4,0x101u);le32(d+8,36u);le32(d+12,48u);le32(d+16,1u);
  le16(d+20,0u);le16(d+22,0x204u);
  le32(d+24,10u);le32(d+28,10u);le32(d+32,0u);
  memcpy(d+36,"TITLE_ID",9u);memcpy(d+48,"NPUA80918",10u);
  if(![[NSData dataWithBytes:d length:sizeof(d)]
       writeToURL:file options:NSDataWritingAtomic error:&e])return 2;
  NSDictionary*result=ARGameFolderInspectParamSFO(file,&e);
  if(!result||![result[@"title_id"] isEqual:@"NPUA80918"]||
      [result[@"folder_access_verified"] boolValue]||
      [result[@"file_bytes"] integerValue]!=58)return 3;
  /* Invalid / untrusted data is never mistaken for a usable game folder. */
  d[48]='X';
  [[NSData dataWithBytes:d length:sizeof(d)]writeToURL:file atomically:YES];
  if(ARGameFolderInspectParamSFO(file,&e)!=nil)return 4;
  d[48]='N';le32(d+12,UINT32_MAX);
  [[NSData dataWithBytes:d length:sizeof(d)]writeToURL:file atomically:YES];
  if(ARGameFolderInspectParamSFO(file,&e)!=nil)return 5;
  if(ARGameFolderInspectParamSFO(
       [folder URLByAppendingPathComponent:@"PIC1.PNG"],&e)!=nil)return 6;
  [NSFileManager.defaultManager removeItemAtURL:folder error:NULL];
  puts("M7.47 small PARAM.SFO Files import: synthetic PSF TITLE_ID NPUA80918 parsed; bad title/index rejected, no USRDIR permission asserted PASS");
 }
 return 0;
}
