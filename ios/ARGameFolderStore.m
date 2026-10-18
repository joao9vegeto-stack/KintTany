/* M7.37: iOS security-scoped folder picker backing store (F0).
 * Never uploads or copies commercial game files. The manifest contains
 * relative paths, file sizes and zero file contents; stored ONLY on device.
 * Does NOT claim sys_fs_open or sys_fs_read from the PS3 game.
 */
#import "ARGameFolderStore.h"
#include <limits.h>
#include <sys/stat.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
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
 BOOL scoped=[folder startAccessingSecurityScopedResource];
 @try {
   /* M7.45: activate File Provider's scoped grant BEFORE stat. */
   BOOL folderFlag=NO;
   if(![NSFileManager.defaultManager fileExistsAtPath:folder.path
                                          isDirectory:&folderFlag]||!folderFlag){
     if(error)*error=gameError(2,@"iOS não autorizou a leitura da pasta, ou item escolhido não é pasta.");
     return nil;
   }
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
   /* NSURL directory.path may already end in "/". Never form "//" here. */
   NSString *root=[folder.path stringByStandardizingPath];
   NSString *prefix=[root hasSuffix:@"/"]?root:
                       [root stringByAppendingString:@"/"];
   for(NSURL *file in enumerator){
     NSNumber *symbolic=nil;
     /* File-provider resource keys can follow symlinks on macOS.
      * POSIX lstat is the authoritative fallback for file:// providers. */
     struct stat mode={0};
     const BOOL isLink=(lstat(file.fileSystemRepresentation,&mode)==0 &&
                       S_ISLNK(mode.st_mode));
     if(isLink||([file getResourceValue:&symbolic
                       forKey:NSURLIsSymbolicLinkKey error:NULL]&&symbolic.boolValue)){
       [enumerator skipDescendants];
       skippedLinks++;
       continue;
     }
     NSNumber *bytes=nil;
     if(!isRegular(file,&bytes))continue;
     NSString *path=[file.path stringByStandardizingPath];
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
   /* An empty app-created folder is NOT proof of installed game assets. */
   if(!files.count){
     if(error)*error=gameError(35,
       @"A pasta do jogo está vazia. Não mova o original do RPCS3; "
        "use uma cópia dos arquivos para testes.");
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
/* M7.39: Guaranteed local alternative when the iCloud/File Provider
 * document picker shows an inert "Abrir" button. Users move/copy the
 * directory into the app Documents (visible in Files > On My iPhone).
 * Zero recursion outside an exact well-known title directory.
 */
NSDictionary<NSString*,id> *ARGameFolderImportLocalAtURL(NSURL *documents,
                                                         NSError **error) {
 if(!documents.isFileURL) {
   if(error)*error=gameError(30,@"A pasta Documentos local não está acessível.");
   return nil;
 }
 NSFileManager *fm=NSFileManager.defaultManager;
 BOOL isDir=NO;
 if(![fm fileExistsAtPath:documents.path isDirectory:&isDir]||!isDir) {
   if(error)*error=gameError(31,@"A pasta Documentos local não existe.");
   return nil;
 }
 /* No broad scan of all files in Documents: never index TXT, logs or
  * unrelated personal documents. Only the exact user game directory.
  * An optional Games or Jogos container is allowed for organization. */
 NSArray<NSArray<NSString*> *> *locations=@[
   @[@"NPUA80918"],@[@"Jogos",@"NPUA80918"],
   @[@"Games",@"NPUA80918"],@[@"USRDIR"],
   /* M7.48: scan the exact app-owned folder created by M7.47,
    * including accidental nesting if a whole folder is pasted inside. */
   @[@"AscensionRecomp",@"NPUA80918",@"NPUA80918"],
   @[@"AscensionRecomp",@"NPUA80918"]
 ];
 for(NSArray<NSString*> *parts in locations) {
   NSURL *folder=documents;
   BOOL bad=NO;
   for(NSString *part in parts) {
     folder=[folder URLByAppendingPathComponent:part isDirectory:YES];
     struct stat metadata={0};
     if(lstat(folder.fileSystemRepresentation,&metadata)!=0 ||
        !S_ISDIR(metadata.st_mode)) {
       bad=YES;break;
     }
   }
   if(bad)continue;
   NSError *indexError=nil;
   NSDictionary *manifest=ARGameFolderImport(folder,&indexError);
   if(manifest)return manifest;
   if(indexError.code==35)continue; /* skip precreated empty title home */
   if(error)*error=indexError ?: gameError(33,@"Falha no manifesto local.");
   return nil;
 }
 if(error)*error=gameError(32,
     @"Nenhuma cópia válida dos arquivos do jogo foi encontrada. Não mova o "
      "original do RPCS3. Para testar, COPIE os arquivos para Arquivos > "
      "No Meu iPhone > AscensionRecomp Test > AscensionRecomp > "
      "NPUA80918, e toque Detectar pasta local.");
 return nil;
}
NSDictionary<NSString*,id> *ARGameFolderImportLocalDocuments(NSError **error) {
 NSURL *documents=[[NSFileManager.defaultManager
    URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask]
    firstObject];
 return ARGameFolderImportLocalAtURL(documents,error);
}

/* M7.47: import a SMALL user-selected PARAM.SFO like arquivo ELF
 * (document picker asCopy:YES). System-provided temporary file ONLY;
 * no game data copied by this app, no claim of parent-directory access.
 * Validate the real PSF index and the TITLE_ID key, never just the name. */
static uint32_t psf32(const uint8_t *p){
 return (uint32_t)p[0]|((uint32_t)p[1]<<8)|
        ((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static uint16_t psf16(const uint8_t *p){
 return (uint16_t)((uint16_t)p[0]|((uint16_t)p[1]<<8));
}
NSDictionary<NSString*,id> *ARGameFolderInspectParamSFO(NSURL *url,NSError **error){
 if(!url.isFileURL || [url.lastPathComponent caseInsensitiveCompare:@"PARAM.SFO"]!=NSOrderedSame){
   if(error)*error=gameError(47,@"Escolha PARAM.SFO, não outro arquivo.");
   return nil;
 }
 BOOL scoped=[url startAccessingSecurityScopedResource];
 @try {
   NSFileCoordinator *coord=[[NSFileCoordinator alloc]initWithFilePresenter:nil];
   __block NSData *data=nil;
   __block NSError *readError=nil;
   NSError *coordError=nil;
   [coord coordinateReadingItemAtURL:url options:NSFileCoordinatorReadingWithoutChanges
         error:&coordError byAccessor:^(NSURL *candidate){
     NSNumber *size=nil;
     [candidate getResourceValue:&size forKey:NSURLFileSizeKey error:&readError];
     if(!size||size.unsignedLongLongValue>65536u){
       readError=gameError(48,@"PARAM.SFO muito grande ou inacessível (máximo 64 KB).");
       return;
     }
     NSFileHandle *fh=[NSFileHandle fileHandleForReadingFromURL:candidate error:&readError];
     if(!fh)return;
     @try {data=[fh readDataUpToLength:65537u error:&readError];}
     @finally {[fh closeFile];}
   }];
   if(coordError||readError||data.length<20u||data.length>65536u){
     if(error)*error=coordError?:readError?:gameError(49,@"Falha ao ler o PARAM.SFO selecionado.");
     return nil;
   }
   const uint8_t*p=data.bytes;
   if(p[0]!=0u||p[1]!='P'||p[2]!='S'||p[3]!='F'){
     if(error)*error=gameError(50,@"Arquivo selecionado não tem cabeçalho PSF.");
     return nil;
   }
   const uint32_t key=psf32(p+8),values=psf32(p+12),n=psf32(p+16);
   if(n>512u||key>=data.length||values>=data.length||
      n>(data.length-20u)/16u||20u+n*16u>key){
     if(error)*error=gameError(51,@"Índice do PARAM.SFO inválido.");
     return nil;
   }
   NSString *title=nil;
   for(uint32_t i=0;i<n;i++){
     const uint8_t *entry=p+20u+16u*i;
     const uint32_t kp=key+(uint32_t)psf16(entry);
     const uint32_t len=psf32(entry+4),maxlen=psf32(entry+8);
     const uint32_t vp=values+psf32(entry+12);
     if(kp>=data.length||len>maxlen||vp>data.length||
         len>data.length-vp){
       if(error)*error=gameError(52,@"Valores do PARAM.SFO fora dos limites.");
       return nil;
     }
     const uint8_t *end=memchr(p+kp,0u,data.length-kp);
     if(!end){
       if(error)*error=gameError(52,@"Chave de PARAM.SFO sem terminador.");
       return nil;
     }
     if((size_t)(end-(p+kp))==8u && memcmp(p+kp,"TITLE_ID",8u)==0){
       const uint8_t *zero=memchr(p+vp,0u,(size_t)len);
       const NSUInteger count=zero?(NSUInteger)(zero-(p+vp)):(NSUInteger)len;
       title=[[NSString alloc]initWithBytes:p+vp length:count
                                     encoding:NSUTF8StringEncoding];
       title=[title stringByTrimmingCharactersInSet:
         [NSCharacterSet whitespaceAndNewlineCharacterSet]];
       break;
     }
   }
   if(![title isEqualToString:@"NPUA80918"]){
     if(error)*error=gameError(53,@"O PARAM.SFO não contém TITLE_ID=NPUA80918.");
     return nil;
   }
   return @{@"title_id":title,@"file_bytes":@(data.length),
            @"metadata_only":@YES,@"folder_access_verified":@NO,
            @"original_modified":@NO};
 } @finally {
   if(scoped)[url stopAccessingSecurityScopedResource];
 }
}
/* Create visible, app-owned Documents structure without copying a game.
 * These folders are NOT paths into the sandbox of the separate RPCS3 app. */
BOOL ARGameFolderPrepareDocumentsHome(NSError **error){
 NSURL *docs=[[NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory
                                 inDomains:NSUserDomainMask] firstObject];
 if(!docs){if(error)*error=gameError(54,@"Documentos do app indisponíveis.");return NO;}
 NSFileManager *fm=NSFileManager.defaultManager;
 NSURL *app=[docs URLByAppendingPathComponent:@"AscensionRecomp" isDirectory:YES];
 NSURL *title=[app URLByAppendingPathComponent:@"NPUA80918" isDirectory:YES];
 if(![fm createDirectoryAtURL:title withIntermediateDirectories:YES
                  attributes:nil error:error])return NO;
 NSURL *readme=[app URLByAppendingPathComponent:@"LEIA-ME.txt"];
 if(![fm fileExistsAtPath:readme.path]){
    NSString *message=@"AscensionRecomp — pasta local do aplicativo.\n"
       "NPUA80918 aqui é apenas um diretório vazio de organização.\n"
       "Os arquivos do RPCS3 NÃO são copiados e permanecem protegidos pelo iOS.\n"
       "Para importar PARAM.SFO, use o botão próprio; somente os metadados serão lidos.\n";
    if(![message writeToURL:readme atomically:YES
              encoding:NSUTF8StringEncoding error:error])return NO;
 }
 return YES;
}

/* M7.40: permissioned no-copy test of the RPCS3 Documents installation.
 * User chooses .../data/dev_hdd0/game/NPUA80918/PARAM.SFO in the Apple
 * document picker asCopy:NO. Reading this small marker does not grant
 * access to its 20+ GB siblings by itself. We test that separately and
 * fail closed if the File Provider supplies only a file-level grant.
 */
NSDictionary<NSString*,id> *ARGameFolderProbeRPCS3Marker(NSURL *paramSfo,
                                                         NSError **error) {
 if(!paramSfo.isFileURL) {
  if(error)*error=gameError(40,@"A seleção não retornou uma URL de arquivo local.");
  return nil;
 }
 NSArray<NSString*> *pieces=paramSfo.path.pathComponents;
 NSArray<NSString*> *suffix=@[@"data",@"dev_hdd0",@"game",
                              @"NPUA80918",@"PARAM.SFO"];
 if(pieces.count<suffix.count) {
  if(error)*error=gameError(41,@"Selecione PARAM.SFO dentro de "
                   "rpcs3/data/dev_hdd0/game/NPUA80918.");
  return nil;
 }
 for(NSUInteger i=0;i<suffix.count;i++) {
  if(![pieces[pieces.count-suffix.count+i] isEqualToString:suffix[i]]) {
   if(error)*error=gameError(41,@"Arquivo fora da instalação NPUA80918 "
                     "(rpcs3/data/dev_hdd0/game/NPUA80918/PARAM.SFO).");
   return nil;
  }
 }
 BOOL fileScope=[paramSfo startAccessingSecurityScopedResource];
 @try {
  NSFileCoordinator *coordinator=[[NSFileCoordinator alloc]
                                       initWithFilePresenter:nil];
  __block NSData *prefix=nil;
  __block NSError *readError=nil;
  NSError *coordError=nil;
  [coordinator coordinateReadingItemAtURL:paramSfo
                    options:NSFileCoordinatorReadingWithoutChanges
                      error:&coordError
                 byAccessor:^(NSURL *readURL) {
    NSFileHandle *h=[NSFileHandle fileHandleForReadingFromURL:readURL
                                                       error:&readError];
    if(!h)return;
    @try {prefix=[h readDataUpToLength:4u error:&readError];}
    @finally {[h closeFile];}
  }];
  if(!prefix.length||coordError||readError) {
   if(error)*error=coordError?:readError?:
      gameError(42,@"O iOS não autorizou ler o PARAM.SFO sem cópia.");
   return nil;
  }
  NSURL *root=[paramSfo URLByDeletingLastPathComponent];
  BOOL dir=NO;
  if(![NSFileManager.defaultManager fileExistsAtPath:root.path
                                         isDirectory:&dir]||!dir) {
   if(error)*error=gameError(43,@"PARAM.SFO autorizado, mas a pasta "
         "NPUA80918 está fora do escopo concedido pelo iOS.");
   return nil;
  }
  NSURL *usrdir=[root URLByAppendingPathComponent:@"USRDIR" isDirectory:YES];
  BOOL filesDir=NO;
  if(![NSFileManager.defaultManager fileExistsAtPath:usrdir.path
                                         isDirectory:&filesDir]||!filesDir) {
   if(error)*error=gameError(44,@"PARAM.SFO acessível; o iOS não liberou "
        "USRDIR. Autorizar um arquivo não autoriza a pasta inteira.");
   return nil;
  }
  /* Only read directory metadata. No writes, deletes, renames or copies
   * are ever performed under the RPCS3 container. */
  NSError *importError=nil;
  NSDictionary *manifest=ARGameFolderImport(root,&importError);
  if(!manifest) {
   if(error)*error=importError?:
     gameError(45,@"Permissão insuficiente para ler os arquivos de USRDIR.");
   return nil;
  }
  BOOL hasUSRDIR=NO;
  for(NSDictionary *entry in manifest[@"files"]) {
   NSString *relative=entry[@"path"];
   if([relative hasPrefix:@"USRDIR/"]){hasUSRDIR=YES;break;}
  }
  if(!hasUSRDIR) {
   if(error)*error=gameError(46,@"O seletor autorizou PARAM.SFO, mas "
      "não comprovou leitura dos arquivos em USRDIR.");
   return nil;
  }
  NSMutableDictionary *verified=[manifest mutableCopy];
  verified[@"source"]=@"rpcs3/data/dev_hdd0/game/NPUA80918";
  verified[@"param_sfo_prefix_bytes"]=@(prefix.length);
  verified[@"read_only"]=@YES;
  verified[@"no_copy"]=@YES;
  verified[@"folder_access_verified"]=@YES;
  verified[@"permission_kind"]=fileScope?@"security-scoped file":@"local";
  return verified;
 } @finally {
  if(fileScope)[paramSfo stopAccessingSecurityScopedResource];
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

/* M7.51: guest FS calls enter here ONLY through signed owner PPU HLE.
 * Local Files bookmark + exact relative manifest entry + no-symlink openat.
 * No game contents/logs in repository, and no copying into IPA. */
int ARGameFolderGuestIO(const char *relative,uint64_t offset,void *dst,
                         size_t count,size_t *actual,uint64_t *outsize){
 if(actual)*actual=0;
 if(outsize)*outsize=0;
 if(!relative||!actual||!outsize||(count&&!dst)||offset>LLONG_MAX)
   return -1;
 NSString *rel=[NSString stringWithUTF8String:relative];
 if(!safeRelativePath(rel))return -1;
 NSURL *root=restoreRoot(NULL);
 if(!root)return -1;
 BOOL scoped=[root startAccessingSecurityScopedResource];
 @try {
   NSDictionary *manifest=loadManifest(NULL);
   if(!manifest)return -1;
   NSNumber *expected=nil;
   for(NSDictionary *item in manifest[@"files"]){
     if([item[@"path"] isEqualToString:rel]){
       expected=item[@"bytes"];break;
     }
   }
   if(!expected)return -1;
   int current=open(root.fileSystemRepresentation,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
   if(current<0)return -1;
   NSArray<NSString*> *parts=[rel componentsSeparatedByString:@"/"];
   BOOL ok=YES;
   for(NSUInteger i=0;i<parts.count;i++){
     const int flags=O_RDONLY|O_NOFOLLOW|O_CLOEXEC|
                       (i+1<parts.count?O_DIRECTORY:0);
     int next=openat(current,parts[i].UTF8String,flags);
     close(current);
     current=next;
     if(current<0){ok=NO;break;}
   }
   if(!ok)return -1;
   struct stat st={0};
   if(fstat(current,&st)!=0||!S_ISREG(st.st_mode)||st.st_size<0||
      (uint64_t)st.st_size!=expected.unsignedLongLongValue){
     close(current);return -1;
   }
   *outsize=(uint64_t)st.st_size;
   if(count && offset<(uint64_t)st.st_size){
     const uint64_t remaining=(uint64_t)st.st_size-offset;
     const size_t n=(size_t)(remaining<count?remaining:count);
     ssize_t got=pread(current,dst,n,(off_t)offset);
     if(got<0){close(current);return -1;}
     *actual=(size_t)got;
   }
   close(current);
   return 0;
 } @finally {
   if(scoped)[root stopAccessingSecurityScopedResource];
 }
}
