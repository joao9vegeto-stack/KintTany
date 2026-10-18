/* M7.37: iOS security-scoped folder picker backing store (F0).
 * Never uploads or copies commercial game files. The manifest contains
 * relative paths, file sizes and zero file contents; stored ONLY on device.
 * Does NOT claim sys_fs_open or sys_fs_read from the PS3 game.
 */
#import "ARGameFolderStore.h"
#include <limits.h>
static NSString * const kGameBookmarkKey=@"ARGameFolderBookmarkM737";
static NSString * const kGameErrorDomain=@"AscensionRecomp.GameFolder";
static NSError *gameError(NSInteger code,NSString *detail) {
 return [NSError errorWithDomain:kGameErrorDomain code:code
   userInfo:@{NSLocalizedDescriptionKey:detail}];
}
static NSURL *manifestLocation(void) {
 NSFileManager *fm=NSFileManager.defaultManager;
 NSURL *base=[[fm URLsForDirectory:NSApplicationSupportDirectory
                        inDomains:NSUserDomainMask] firstObject];
 NSURL *directory=[base URLByAppendingPathComponent:@"AscensionRecomp"
                                       isDirectory:YES];
 [fm createDirectoryAtURL:directory withIntermediateDirectories:YES
              attributes:nil error:NULL];
 return [directory URLByAppendingPathComponent:@"game-folder-manifest.json"
                                   isDirectory:NO];
}
static BOOL safeRelativePath(NSString *path) {
 if(!path.length||[path hasPrefix:@"/"]||[path containsString:@"\\"]||
    [path containsString:@"://"])return NO;
 for(NSString *part in [path componentsSeparatedByString:@"/"])
   if(!part.length||[part isEqualToString:@"."]||
      [part isEqualToString:@".."])return NO;
 return YES;
}
static BOOL isRegular(NSURL *url,NSNumber **length) {
 NSNumber *regular=nil,*symbolic=nil,*bytes=nil;
 NSError *error=nil;
 if(![url getResourceValue:&symbolic forKey:NSURLIsSymbolicLinkKey error:&error]
    || symbolic.boolValue)return NO;
 if(![url getResourceValue:&regular forKey:NSURLIsRegularFileKey error:&error]
    || !regular.boolValue)return NO;
 if(![url getResourceValue:&bytes forKey:NSURLFileSizeKey error:&error]
    || !bytes)return NO;
 if(length)*length=bytes;
 return YES;
}
static NSDictionary<NSString*,id> *loadManifest(NSError **error) {
 NSData *json=[NSData dataWithContentsOfURL:manifestLocation()
                                    options:0 error:error];
 if(!json)return nil;
 id item=[NSJSONSerialization JSONObjectWithData:json options:0 error:error];
 if(![item isKindOfClass:NSDictionary.class]){
   if(error)*error=gameError(5,@"Manifesto local inválido.");
   return nil;
 }
 return item;
}
static NSURL *restoreRoot(NSError **error) {
 NSData *bookmark=[NSUserDefaults.standardUserDefaults
                      dataForKey:kGameBookmarkKey];
 if(!bookmark.length){
   if(error)*error=gameError(4,@"Nenhuma pasta do jogo foi selecionada.");
   return nil;
 }
 BOOL stale=NO;
 NSURL *url=[NSURL URLByResolvingBookmarkData:bookmark options:0
               relativeToURL:nil bookmarkDataIsStale:&stale error:error];
 if(!url||stale){
   if(error && !*error)*error=gameError(6,
                         @"Pasta movida: selecione-a novamente no Arquivos.");
   return nil;
 }
 return url;
}
/* Maximum of 200,000 metadata records, no unbounded directory recursion.
 * Symlinks are excluded and cannot escape the selected folder.
 */
NSDictionary<NSString*,id> *ARGameFolderImport(NSURL *folder,NSError **error) {
 if(!folder.isFileURL){
   if(error)*error=gameError(1,@"Selecione uma pasta local do aplicativo Arquivos.");
   return nil;
 }
 BOOL folderFlag=NO;
 if(![NSFileManager.defaultManager fileExistsAtPath:folder.path
                                        isDirectory:&folderFlag]||!folderFlag){
   if(error)*error=gameError(2,@"O item escolhido não é uma pasta.");
   return nil;
 }
 BOOL scoped=[folder startAccessingSecurityScopedResource];
 @try {
   static const NSUInteger cap=200000u;
   NSArray<NSURLResourceKey> *keys=@[NSURLIsRegularFileKey,
                 NSURLIsSymbolicLinkKey,NSURLFileSizeKey];
   __block NSError *walkError=nil;
   NSDirectoryEnumerator<NSURL *> *enumerator=
     [NSFileManager.defaultManager enumeratorAtURL:folder
                 includingPropertiesForKeys:keys options:0
                 errorHandler:^BOOL(NSURL *bad,NSError *problem){
                   (void)bad;walkError=problem;return NO;
                 }];
   NSMutableArray<NSDictionary*> *files=[NSMutableArray array];
   unsigned long long total=0;
   NSString *firstRelative=nil;
   unsigned long long skippedLinks=0;
   NSString *prefix=[folder.path stringByAppendingString:@"/"];
   for(NSURL *file in enumerator){
     NSNumber *symbolic=nil;
     if([file getResourceValue:&symbolic
                       forKey:NSURLIsSymbolicLinkKey error:NULL]&&symbolic.boolValue){
       [enumerator skipDescendants];
       skippedLinks++;
       continue;
     }
     NSNumber *bytes=nil;
     if(!isRegular(file,&bytes))continue;
     NSString *path=file.path;
     if(![path hasPrefix:prefix])continue;
     NSString *relative=[path substringFromIndex:prefix.length];
     if(!safeRelativePath(relative))continue;
     if(files.count>=cap){
       if(error)*error=gameError(3,
               @"Mais de 200 mil arquivos: selecione a subpasta USRDIR.");
       return nil;
     }
     unsigned long long size=bytes.unsignedLongLongValue;
     if(ULLONG_MAX-total<size){
       if(error)*error=gameError(7,@"Tamanho total dos arquivos inválido.");
       return nil;
     }
     total+=size;
     [files addObject:@{@"path":relative,@"bytes":@(size)}];
     if(!firstRelative.length&&size>0u)firstRelative=relative;
   }
   if(walkError){
     if(error)*error=walkError;
     return nil;
   }
   /* A manifest is not proof of a guest LV2 sys_fs call. */
   NSDictionary *manifest=@{
      @"format":@1,@"title_id":@"NPUA80918",
      @"root_name":folder.lastPathComponent?:@"pasta",
      @"files":files,@"file_count":@(files.count),@"total_bytes":@(total),
      @"symlinks_skipped":@(skippedLinks),
      @"probe_relative_path":firstRelative?:@""
   };
   NSError *writeError=nil;
   NSData *json=[NSJSONSerialization dataWithJSONObject:manifest
                                               options:0 error:&writeError];
   if(!json){
     if(error)*error=writeError;
     return nil;
   }
   NSData *bookmark=[folder bookmarkDataWithOptions:NSURLBookmarkCreationMinimalBookmark
                              includingResourceValuesForKeys:nil
                                               relativeToURL:nil error:&writeError];
   if(!bookmark){
     if(error)*error=writeError;
     return nil;
   }
   NSURL *location=manifestLocation();
   if(![json writeToURL:location options:NSDataWritingAtomic error:&writeError]){
     if(error)*error=writeError;
     return nil;
   }
   [location setResourceValue:@YES forKey:NSURLIsExcludedFromBackupKey error:NULL];
   [NSUserDefaults.standardUserDefaults setObject:bookmark forKey:kGameBookmarkKey];
   return manifest;
 } @finally {
   if(scoped)[folder stopAccessingSecurityScopedResource];
 }
}
NSDictionary<NSString*,id> *ARGameFolderRestore(NSError **error) {
 NSURL *root=restoreRoot(error);
 if(!root)return nil;
 BOOL scoped=[root startAccessingSecurityScopedResource];
 @try {
  BOOL folderFlag=NO;
  if(![NSFileManager.defaultManager fileExistsAtPath:root.path
                                         isDirectory:&folderFlag]||!folderFlag){
   if(error)*error=gameError(8,@"Pasta indisponível; importe novamente.");
   return nil;
  }
  return loadManifest(error);
 } @finally {if(scoped)[root stopAccessingSecurityScopedResource];}
}
/* Real, bounded host read of an explicitly selected file, NOT cellFsRead.
 * No absolute path and no directory traversal. Files are never copied.
 */
NSData *ARGameFolderReadPrefix(NSString *relativePath,NSUInteger maxLength,
                              NSError **error){
 if(!safeRelativePath(relativePath)||maxLength>65536u){
   if(error)*error=gameError(9,@"Caminho ou limite de leitura inválido.");
   return nil;
 }
 NSURL *folder=restoreRoot(error);
 if(!folder)return nil;
 BOOL scoped=[folder startAccessingSecurityScopedResource];
 @try {
   NSDictionary *manifest=loadManifest(error);
   if(!manifest)return nil;
   BOOL permitted=NO;
   for(NSDictionary *entry in manifest[@"files"]){
     if([entry[@"path"] isEqualToString:relativePath]){
       permitted=YES;break;
     }
   }
   if(!permitted){
     if(error)*error=gameError(10,@"Arquivo fora do manifesto autorizado.");
     return nil;
   }
   NSURL *file=folder;
   for(NSString *part in [relativePath componentsSeparatedByString:@"/"]){
     file=[file URLByAppendingPathComponent:part isDirectory:NO];
     NSNumber *symbolic=nil;
     if(![file getResourceValue:&symbolic forKey:NSURLIsSymbolicLinkKey
                         error:error]||symbolic.boolValue){
       if(error && !*error)*error=gameError(11,@"Links simbólicos não são permitidos.");
       return nil;
     }
   }
   NSNumber *size=nil;
   if(!isRegular(file,&size)){
     if(error)*error=gameError(12,@"Arquivo não é regular.");
     return nil;
   }
   NSFileHandle *handle=[NSFileHandle fileHandleForReadingFromURL:file error:error];
   if(!handle)return nil;
   NSData *data=nil;
   @try{
     data=[handle readDataUpToLength:maxLength error:error];
   } @finally { [handle closeFile]; }
   return data;
 } @finally {if(scoped)[folder stopAccessingSecurityScopedResource];}
}
