/* AscensionRecomp iPhone Metal diagnostic host. No commercial game code. */
#import <UIKit/UIKit.h>
#import <Metal/Metal.h>
#import <QuartzCore/QuartzCore.h>
#import "ARMetalView.h"
#import "ARGameFolderStore.h"
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>
#import <CommonCrypto/CommonDigest.h>
#include <unistd.h>
#include <stdlib.h>
#include <math.h>
#include "../ios-probe/ARBuildProvenance.h"
#include "../runtime/ppu_bridge.h"
#include "../runtime/ppu_guest_fs.h"
#include "../runtime/ppu_m756_stop_evidence.h"
#include "../runtime/ppu_m767_live_import.h"
extern void ar_m772_runtime_attest(uint64_t out[40]);
extern void ar_m772_runtime_begin(void);
extern uint32_t ar_m772_entry_state(void);
extern uint32_t ar_m772_copy_aot_trace(uint64_t *out, uint32_t capacity);
extern uint32_t ar_m772_copy_hle_trace(uint64_t *out, uint32_t capacity);
extern uint32_t ar_m772_copy_unresolved_hle_trace(uint64_t *out, uint32_t capacity);
extern void cellSpursResetAscensionMetrics(void);
extern void cellSpursCopyAscensionMetrics(uint64_t out[8]);
extern void cellSpursCopyAscensionPmDiagnostics(uint64_t out[32][7]);
extern void spu_workload_reset_ascension_job_metrics(void);
extern void spu_workload_copy_ascension_job_metrics(uint64_t out[8]);
extern void ar_m756_last_stop_evidence(ar_m756_stop_evidence*);
extern void ar_m756_last_origin_evidence(ar_m756_stop_evidence*);
extern void ar_m751_last_fs_trace(ar_fs_trace *);
#include "../runtime/ppu_m717_graph.h"
extern void ar_m717_last_aot_trace(ar_aot_trace *);
extern void ar_m769_last_install_stats(uint32_t out[5]);
extern int ar_private_elf_inspect(const unsigned char*,size_t,unsigned int[5]);
extern int ar_m70_native_runtime_probe(const unsigned char*,size_t,unsigned int,unsigned int[16]);
extern int ar_m712_exec_window(const unsigned char*,size_t,unsigned int,unsigned int[6]);
extern int ar_m714_frontier_inventory(const unsigned char*,size_t,unsigned int,unsigned int[32],unsigned int*,unsigned int*);
extern int ar_m716_verified_successors(const unsigned char*,size_t,unsigned int[2]);
extern int ar_m71_private_continuous_probe(const unsigned char*,size_t,
                        unsigned int,unsigned int,unsigned int[16]);
extern int ar_m73_private_import_probe(const unsigned char*,size_t,
                        unsigned int,unsigned int,unsigned int[16],
                        unsigned int[16],char[48]);
extern int ar_private_import_match(const unsigned char*,size_t,unsigned int,
                                  unsigned int[4],char[48]);
extern int ar_ppu_bootstrap_four(const unsigned char*,size_t,
                                const unsigned int[5],unsigned int[4]);
extern int ar_ppu_bootstrap_eight(const unsigned char*,size_t,
                                 const unsigned int[5],unsigned int[6]);
extern int ar_ppu_bootstrap_sixteen(const unsigned char*,size_t,
                                   const unsigned int[5],unsigned int[7]);
extern int ar_ppu_bootstrap_twentyfour(const unsigned char*,size_t,
                                      const unsigned int[5],unsigned int[9]);
extern int ar_ppu_bootstrap_thirtytwo(const unsigned char*,size_t,
                                     const unsigned int[5],unsigned int[10]);
extern int ar_ppu_bootstrap_forty(const unsigned char*,size_t,
                                 const unsigned int[5],unsigned int[16]);
extern int ar_ppu_bootstrap_fortyeight(const unsigned char*,size_t,
                                      const unsigned int[5],unsigned int[20]);
extern int ar_ppu_bootstrap_fortyeight_trace(const unsigned char*,size_t,
                      const unsigned int[5],unsigned int[20],unsigned int[24]);
extern int ar_ppu_bootstrap_fortyeight_trace_m672(const unsigned char*,size_t,
                      const unsigned int[5],unsigned int[20],unsigned int[24],unsigned int[24]);
extern int ar_ppu_bootstrap_fortyeight_trace_m674(const unsigned char*,size_t,
                      const unsigned int[5],unsigned int[20],unsigned int[24],
                      unsigned int[24],unsigned int[12]);

extern int rsx_metal_backend_init(unsigned int width, unsigned int height, const char* title);
extern void rsx_metal_backend_shutdown(void);
extern void rsx_metal_backend_present(void);
extern unsigned int rsx_metal_backend_guest_draws(void);
extern void cellGcmTickVBlank(void);
extern void cellGcmTickFlip(void);
extern void cellGcm_rsx_process_fifo(void);
extern int cellGcm_take_flip_pending_synced(void);
extern void cellPad_set_host_state(uint16_t buttons, uint8_t analog_lx,
                                   uint8_t analog_ly, uint8_t analog_rx,
                                   uint8_t analog_ry, uint8_t trigger_l2,
                                   uint8_t trigger_r2);
extern int ar_probe_vm_init(void);
extern int ar_probe_guest_shader_compile(char *details, size_t cap);
extern int ar_probe_m51_guest_textured_quad(unsigned swizzled, unsigned int pixels[4], unsigned *encoded, unsigned *guest_draws, unsigned int shader_state[4]);
extern int ar_probe_m52_guest_texture_mutation(unsigned swizzled,
    unsigned int pixels[4], unsigned *failed_phase, unsigned *uploads,
    unsigned *replacements, unsigned *guest_total, unsigned *metal_total);
extern int ar_probe_m53_guest_multipass(unsigned swizzled, unsigned int pixels[4],
    unsigned *phase, unsigned *guest_total, unsigned *metal_total,
    unsigned *surface_views, unsigned *new_uploads);
extern int ar_probe_m54_guest_depth_occlusion(unsigned swizzled,
    unsigned int pixels[4], unsigned *phase, unsigned *guest_total,
    unsigned *metal_total, unsigned *depth_draws);
extern int ar_probe_m55_guest_stencil_mask(unsigned swizzled,
    unsigned int pixels[4], unsigned *phase, unsigned *guest_total,
    unsigned *metal_total, unsigned *stencil_draws);
extern int ar_probe_m56_guest_stencil_bitmasks(unsigned swizzled,
    unsigned int pixels[4], unsigned *phase, unsigned *guest_total,
    unsigned *metal_total, unsigned *stencil_draws);
extern int ar_probe_m57_guest_blend_mask(unsigned swizzled,unsigned int pixels[4],
    unsigned *phase,unsigned *guest_total,unsigned *metal_total,
    unsigned *blend_draws,unsigned *red_draws);
extern int ar_probe_m58_guest_alpha_test(unsigned swizzled,unsigned int pixels[4],
    unsigned *phase,unsigned *guest_total,unsigned *metal_total,
    unsigned *alpha_draws);
extern void ar_probe_vm_shutdown(void);
extern int ar_probe_rsx_clear_flip(unsigned cycle, unsigned int *expected, unsigned int *observed);
extern int ar_probe_rsx_triangle(unsigned int *background, unsigned int *sample);
extern int ar_probe_rsx_fixed_stage(void);
extern int ar_probe_rsx_dma_triangle(unsigned int *background,unsigned int *sample);
extern int ar_probe_rsx_indexed_quad(unsigned use32,unsigned int *background,unsigned int *sample);
extern int ar_probe_rsx_texture(void *layer,unsigned swizzled,unsigned int out_pixels[4]);
extern int ar_probe_rsx_texture_registers(unsigned swizzled,unsigned int out_pixels[4]);
extern int ar_probe_rsx_texture_cache_mutation(unsigned swizzled,unsigned int out_pixels[4],unsigned *phase,unsigned *uploads,unsigned *replacements);

/* Display/export version comes from the installed IPA's Info.plist. */
static NSString *ARCurrentRelease(void){
 NSString *v=[[NSBundle mainBundle] objectForInfoDictionaryKey:@"CFBundleShortVersionString"];
 return v.length?[@"M" stringByAppendingString:v]:@"M-INDEFINIDA";
}
static NSString *ARVMReservationName(uint32_t kind){
 switch(kind){
  case 1u:return @"mmap anywhere · guest 3,5 GiB leitura/escrita";
  case 3u:return @"Mach VM_FLAGS_ANYWHERE · guest 3,5 GiB leitura/escrita";
  default:return @"sem reserva concluída";
 }
}
static NSString *ARVMReservationStageName(uint32_t stage){
 switch(stage){
  case AR_VM_STAGE_NEEDS_64BIT:return @"processo não é 64-bit";
  case AR_VM_STAGE_ALIGNED_HINT:return @"mmap do endereço alinhado";
  case AR_VM_STAGE_HINT_RELOCATED:return @"iOS realocou o endereço sugerido";
  case AR_VM_STAGE_HINT_CLEANUP:return @"liberação de endereço realocado";
  case AR_VM_STAGE_FALLBACK_MAP:return @"mmap guest anywhere (3,5 GiB RW)";
  case AR_VM_STAGE_TRIM:return @"ajuste do fallback alinhado";
  case AR_VM_STAGE_PROTECT_LOW:return @"habilitar memória baixa do guest";
  case AR_VM_STAGE_PROTECT_RSX:return @"habilitar memória local RSX";
  case AR_VM_STAGE_PROTECT_STACK:return @"habilitar pilhas do guest";
  case AR_VM_STAGE_RELEASE:return @"liberar região guest";
  case AR_VM_STAGE_MACH_ALLOCATE:return @"vm_allocate guest anywhere (3,5 GiB RW)";
  case AR_VM_STAGE_MACH_PROTECT_NONE:return @"proteger reserva Mach como PROT_NONE";
  case AR_VM_STAGE_MACH_PROTECT_COMMIT:return @"habilitar faixa guest pela API Mach";
  case AR_VM_STAGE_MACH_RELEASE:return @"liberar reserva Mach";
  default:return @"nenhuma";
 }
}
/* The iOS host must drive the same guest FIFO, vblank and flip loop as the
 * PS3Recomp desktop host. These counters are only incremented by that loop. */
static volatile uint32_t ARNativeRSXPumpActive;
static volatile uint32_t ARNativeRSXBackendReady;
static volatile uint64_t ARNativeRSXVBlanks;
static volatile uint64_t ARNativeRSXFIFODrains;
static volatile uint64_t ARNativeRSXPresentedFrames;
static volatile uint64_t ARNativeRSXLastGuestDraws;
static volatile uint32_t ARNativeRSXVBlankHz=60;
enum {
  ARPadSelect=0x0001, ARPadL3=0x0002, ARPadR3=0x0004, ARPadStart=0x0008,
  ARPadUp=0x0010, ARPadRight=0x0020, ARPadDown=0x0040, ARPadLeft=0x0080,
  ARPadL2=0x0100, ARPadR2=0x0200, ARPadL1=0x0400, ARPadR1=0x0800,
  ARPadTriangle=0x1000, ARPadCircle=0x2000, ARPadCross=0x4000, ARPadSquare=0x8000
};
static uint64_t ARRSXLoad(const volatile uint64_t *value){
 return __atomic_load_n(value,__ATOMIC_RELAXED);
}
static void ARRSXResetMetrics(void){
 __atomic_store_n(&ARNativeRSXVBlanks,UINT64_C(0),__ATOMIC_RELAXED);
 __atomic_store_n(&ARNativeRSXFIFODrains,UINT64_C(0),__ATOMIC_RELAXED);
 __atomic_store_n(&ARNativeRSXPresentedFrames,UINT64_C(0),__ATOMIC_RELAXED);
 __atomic_store_n(&ARNativeRSXLastGuestDraws,UINT64_C(0),__ATOMIC_RELAXED);
}
static NSString *ARFormatRunElapsed(CFTimeInterval startedAt,
                                    CFTimeInterval endedAt){
 if(startedAt<=0.0)return @"AINDA NÃO INICIADO";
 const CFTimeInterval now=endedAt>startedAt?endedAt:CACurrentMediaTime();
 const uint64_t seconds=(uint64_t)MAX(0.0,now-startedAt);
 return [NSString stringWithFormat:@"%02llu:%02llu:%02llu",
   (unsigned long long)(seconds/3600u),
   (unsigned long long)((seconds/60u)%60u),
   (unsigned long long)(seconds%60u)];
}
static BOOL ARIsValidatedAscensionELF(NSData *data){
 if(data.length!=8717136u)return NO;
 uint32_t info[5]={0};
 if(ar_private_elf_inspect(data.bytes,data.length,info)!=0 ||
    info[0]!=0x8283f8u || info[1]!=0x10410u || info[2]!=0x83f2b0u)return NO;
 unsigned char digest[CC_SHA256_DIGEST_LENGTH]={0};
 CC_SHA256(data.bytes,(CC_LONG)data.length,digest);
 static const unsigned char expected[32]={
   0x4b,0xf7,0x5c,0x89,0x7b,0x82,0xd1,0xbe,
   0xb2,0x55,0x14,0xcb,0xad,0xaf,0xf3,0xd0,
   0x3e,0x1b,0x0c,0x7b,0xf8,0x49,0xfa,0x5d,
   0x28,0x9b,0xe4,0xf9,0x18,0x34,0x62,0xb5};
 return memcmp(digest,expected,sizeof(expected))==0;
}
static BOOL ARGameManifestHasTitleUsrdir(NSDictionary *manifest){
 if(![[manifest[@"root_name"] description] isEqualToString:@"NPUA80918"])return NO;
 NSArray *files=[manifest[@"files"] isKindOfClass:NSArray.class]?manifest[@"files"]:@[];
 for(NSDictionary *entry in files){
   NSString *path=[entry[@"path"] isKindOfClass:NSString.class]?entry[@"path"]:@"";
   for(NSString *part in [path componentsSeparatedByString:@"/"])
     if([part caseInsensitiveCompare:@"USRDIR"]==NSOrderedSame)return YES;
 }
 return NO;
}
/* Use a native gradient layer so the game tile remains atmospheric even before
 * the user imports ICON0.PNG. This keeps the IPA free of game artwork. */
@interface ARLauncherHeroView : UIView @end
@implementation ARLauncherHeroView
+ (Class)layerClass { return CAGradientLayer.class; }
@end

@interface ARProbeDelegate : UIResponder <UIApplicationDelegate, UIDocumentPickerDelegate>
@property(nonatomic,strong) UIWindow *window;
@property(nonatomic,strong) UIView *launcherBrand;
@property(nonatomic,strong) UIView *launcherFooter;
@property(nonatomic,strong) UILabel *launcherReadinessLabel;
@property(nonatomic,strong) ARMetalView *metalView;
@property(nonatomic,strong) UILabel *status;
@property(nonatomic,strong) UIScrollView *gameList;
@property(nonatomic,strong) UIScrollView *graphicsList;
@property(nonatomic,strong) UIScrollView *settingsList;
@property(nonatomic,strong) UIScrollView *reportList;
@property(nonatomic,strong) UILabel *launcherReportLabel;
@property(nonatomic,strong) NSTimer *launcherReportRefreshTimer;
@property(nonatomic,strong) UIButton *ppuReportButton;
@property(nonatomic,strong) UIButton *ppuBatchButton;
@property(nonatomic,copy) NSString *ppuBatchReport;
@property(nonatomic,copy) NSString *ppuReport;
@property(nonatomic,copy) NSString *ppuProgress;
@property(nonatomic,copy) NSString *ppuSummary;
@property(nonatomic,copy) NSString *folderReport;
@property(nonatomic,strong) NSURL *latestSpuCaptureURL;
@property(nonatomic,strong) NSDictionary<NSString*,id> *m750Run;
@property(nonatomic,copy) NSString *m750HostObservation;
@property(nonatomic,strong) UIDocumentPickerViewController *folderPicker;
@property(nonatomic,strong) UIDocumentPickerViewController *rpcMarkerPicker;
@property(nonatomic,strong) UIButton *ppuAdvancedButton;
@property(nonatomic,strong) UIButton *ppuDiagnosticsButton;
@property(nonatomic,strong) NSTimer *ppuLiveRefreshTimer;
@property(nonatomic,strong) UITextView *ppuLiveReportView;
@property(nonatomic,strong) UIButton *nativeLaunchButton;
@property(nonatomic,strong) UILabel *gameInstallLabel;
@property(nonatomic,strong) UILabel *settingsGameInstallLabel;
@property(nonatomic,strong) UILabel *elfStatusLabel;
@property(nonatomic,strong) UILabel *settingsElfStatusLabel;
@property(nonatomic,strong) UILabel *bootMetricsLabel;
@property(nonatomic,strong) UIImageView *gameCoverView;
@property(nonatomic,strong) UIButton *graphicsDrawButton;
@property(nonatomic,strong) UIButton *graphicsCacheButton;
@property(nonatomic,strong) NSTimer *nativeRunRefreshTimer;
@property(nonatomic,strong) NSThread *nativeRunThread;
@property(nonatomic,strong) UILabel *nativeRunElapsedLabel;
@property(nonatomic,strong) NSThread *nativeRSXPumpThread;
@property(nonatomic,strong) UISegmentedControl *launcherTabs;
@property(nonatomic,strong) UISegmentedControl *presentationScaleControl;
@property(nonatomic,strong) UISegmentedControl *vblankRateControl;
@property(nonatomic,strong) UILabel *videoSettingsSummary;
@property(nonatomic,strong) UIView *nativeGameHUD;
@property(nonatomic,strong) UILabel *nativeGameHUDLabel;
@property(nonatomic,strong) UIView *nativeGameControls;
@property(nonatomic,strong) NSData *selectedElfData;
@property(nonatomic,copy) NSString *selectedElfPath;
@property(nonatomic,assign) CFAbsoluteTime nativeRunStartedAt;
@property(nonatomic,assign) CFAbsoluteTime nativeRunEndedAt;
@property(nonatomic,assign) BOOL ready;
@property(nonatomic,assign) BOOL shaderBusy;
@property(nonatomic,assign) BOOL graphicsReady;
@property(nonatomic,assign) BOOL gameDisplayActive;
@property(nonatomic,assign) uint16_t nativePadButtons;
@property(nonatomic,assign) BOOL hasGameInstallation;
@property(nonatomic,assign) NSUInteger m51Attempts;
@property(nonatomic,assign) NSUInteger m52Attempts;
@property(nonatomic,assign) NSUInteger m53Attempts;
@property(nonatomic,assign) NSUInteger m54Attempts;
@property(nonatomic,assign) NSUInteger m55Attempts;
@property(nonatomic,assign) NSUInteger m56Attempts;
@property(nonatomic,assign) NSUInteger m57Attempts;
@property(nonatomic,assign) NSUInteger m58Attempts;
@property(nonatomic,assign) NSUInteger successfulFrames;
@property(nonatomic,assign) NSUInteger guestAttempts;
@property(nonatomic,assign) NSUInteger indexedAttempts;
@property(nonatomic,assign) NSUInteger textureAttempts;
@property(nonatomic,assign) NSUInteger registerTextureAttempts;
@property(nonatomic,assign) NSUInteger cacheMutationAttempts;
- (BOOL)buildLauncherWithApplication:(UIApplication*)app options:(NSDictionary*)options;
- (NSData*)gameCoverDataFromManifest:(NSDictionary*)manifest;
- (void)startNativeGame:(UIButton*)sender;
- (void)runNativeRSXPump;
- (void)showNativeGameFrame;
- (void)showLauncherAfterNativeRun;
- (void)openLauncherSettings:(UIButton*)sender;
- (void)videoSettingChanged:(UISegmentedControl*)sender;
- (void)refreshVideoSettingsSummary;
- (void)showLauncherReport:(UIButton*)sender;
- (void)copyLauncherReport:(UIButton*)sender;
- (void)shareLauncherReport:(UIButton*)sender;
- (void)updateLauncherReport;
- (void)launcherReportRefreshTick:(NSTimer*)timer;
- (UIButton*)nativePadButton:(NSString*)title bit:(uint16_t)bit;
- (void)nativePadDown:(UIButton*)sender;
- (void)nativePadUp:(UIButton*)sender;
- (void)refreshNativeLaunchAvailability;
- (void)acceptELFAtURL:(NSURL*)url;
- (void)initializeGraphicsLab:(UIButton*)sender;
@end

@implementation ARProbeDelegate
- (UIInterfaceOrientationMask)application:(UIApplication *)application
 supportedInterfaceOrientationsForWindow:(UIWindow *)window {
  (void)application; (void)window;
  return self.gameDisplayActive ? UIInterfaceOrientationMaskLandscape :
                                 UIInterfaceOrientationMaskPortrait;
}
- (void)requestGameOrientation:(UIInterfaceOrientationMask)orientations {
  [self.window.rootViewController setNeedsUpdateOfSupportedInterfaceOrientations];
  if (@available(iOS 16.0, *)) {
    UIWindowScene *scene=self.window.windowScene;
    if (!scene) return;
    UIWindowSceneGeometryPreferencesIOS *preferences=
      [[UIWindowSceneGeometryPreferencesIOS alloc] initWithInterfaceOrientations:orientations];
    [scene requestGeometryUpdateWithPreferences:preferences errorHandler:^(NSError *error) {
      dispatch_async(dispatch_get_main_queue(), ^{
        NSString *message=[NSString stringWithFormat:@"Orientação não aplicada: %@",
                           error.localizedDescription ?: @"iOS recusou a rotação"];
        self.status.text=message;
        if(self.gameDisplayActive)self.nativeGameHUDLabel.text=message;
      });
    }];
  }
}
- (BOOL)application:(UIApplication*)app didFinishLaunchingWithOptions:(NSDictionary*)options {
    return [self buildLauncherWithApplication:app options:options];
#if 0 /* Replaced by the game-first launcher below; legacy test dashboard retired. */
    (void)app; (void)options;
     /* Create app-owned Files/Documents folder, NOT RPCS3 folder access. */
     NSError *homeError=nil;
     if(!ARGameFolderPrepareDocumentsHome(&homeError)){
       self.folderReport=[NSString stringWithFormat:
         @"M7.47: Documents/AscensionRecomp indisponível (%@)",
         homeError.localizedDescription?:@"erro do iOS"];
     }
     self.window=[[UIWindow alloc] initWithFrame:[UIScreen mainScreen].bounds];
    UIViewController *controller=[UIViewController new];
    controller.view.backgroundColor=[UIColor blackColor];

    ARMetalView *view=[[ARMetalView alloc] initWithFrame:CGRectZero];
    view.translatesAutoresizingMaskIntoConstraints=NO;
    [controller.view addSubview:view];
    [NSLayoutConstraint activateConstraints:@[
        [view.leadingAnchor constraintEqualToAnchor:controller.view.leadingAnchor],
        [view.trailingAnchor constraintEqualToAnchor:controller.view.trailingAnchor],
        [view.topAnchor constraintEqualToAnchor:controller.view.topAnchor],
        [view.bottomAnchor constraintEqualToAnchor:controller.view.bottomAnchor]
    ]];
    self.metalView=view;
    /* The game launcher is the first screen. The Metal test surface is only
     * shown on its own tab; a diagnostic blue clear must never look like a
     * game frame. */
    self.metalView.hidden=YES;
    UITapGestureRecognizer *tap=[[UITapGestureRecognizer alloc]
                                 initWithTarget:self action:@selector(drawNextFrame:)];
    [view addGestureRecognizer:tap];
    UILongPressGestureRecognizer *longPress=[[UILongPressGestureRecognizer alloc]
                                           initWithTarget:self
                                           action:@selector(drawTriangle:)];
    longPress.minimumPressDuration=0.65;
    [view addGestureRecognizer:longPress];
    [tap requireGestureRecognizerToFail:longPress];
    UITapGestureRecognizer *doubleTap=[[UITapGestureRecognizer alloc]
                                     initWithTarget:self action:@selector(drawDMATriangle:)];
    doubleTap.numberOfTapsRequired=2;
    [view addGestureRecognizer:doubleTap];
    [tap requireGestureRecognizerToFail:doubleTap];
    UITapGestureRecognizer *tripleTap=[[UITapGestureRecognizer alloc]
                                    initWithTarget:self action:@selector(drawIndexedQuad:)];
    tripleTap.numberOfTapsRequired=3;
    [view addGestureRecognizer:tripleTap];
    [tap requireGestureRecognizerToFail:tripleTap];
    [doubleTap requireGestureRecognizerToFail:tripleTap];
    UITapGestureRecognizer *fourTap=[[UITapGestureRecognizer alloc]
                                    initWithTarget:self action:@selector(drawPS3Texture:)];
    fourTap.numberOfTapsRequired=4;
    [view addGestureRecognizer:fourTap];
    [tap requireGestureRecognizerToFail:fourTap];
    [doubleTap requireGestureRecognizerToFail:fourTap];
    [tripleTap requireGestureRecognizerToFail:fourTap];
    UITapGestureRecognizer *fiveTap=[[UITapGestureRecognizer alloc]
                  initWithTarget:self action:@selector(drawRSXBoundTexture:)];
    fiveTap.numberOfTapsRequired=5;
    [view addGestureRecognizer:fiveTap];
    [tap requireGestureRecognizerToFail:fiveTap];
    [doubleTap requireGestureRecognizerToFail:fiveTap];
    [tripleTap requireGestureRecognizerToFail:fiveTap];
    [fourTap requireGestureRecognizerToFail:fiveTap];

    UILabel *status=[[UILabel alloc] initWithFrame:CGRectZero];
    status.translatesAutoresizingMaskIntoConstraints=NO;
    status.numberOfLines=0;
    status.textAlignment=NSTextAlignmentCenter;
    status.textColor=[UIColor whiteColor];
    status.backgroundColor=[[UIColor blackColor] colorWithAlphaComponent:0.72];
    status.font=[UIFont systemFontOfSize:14 weight:UIFontWeightMedium];
    status.text=@"AscensionRecomp — iniciando backend Metal...";
    [controller.view addSubview:status];
    [NSLayoutConstraint activateConstraints:@[
        [status.centerXAnchor constraintEqualToAnchor:controller.view.centerXAnchor],
        [status.topAnchor constraintEqualToAnchor:controller.view.safeAreaLayoutGuide.topAnchor constant:24],
        [status.widthAnchor constraintLessThanOrEqualToAnchor:controller.view.widthAnchor constant:-24]
    ]];
    self.status=status;
    /* Visible hardware cache test button; all existing gesture probes stay. */
    UIButton *cacheButton=[UIButton buttonWithType:UIButtonTypeSystem];
    cacheButton.translatesAutoresizingMaskIntoConstraints=NO;
    [cacheButton setTitle:@"M4.10 · Atualização do cache RSX" forState:UIControlStateNormal];
    [cacheButton setTitleColor:[UIColor whiteColor] forState:UIControlStateNormal];
    cacheButton.backgroundColor=[[UIColor blackColor] colorWithAlphaComponent:0.82];
    cacheButton.titleLabel.font=[UIFont systemFontOfSize:14 weight:UIFontWeightSemibold];
    cacheButton.layer.cornerRadius=10;
    [cacheButton addTarget:self action:@selector(testRSXCache:) forControlEvents:UIControlEventTouchUpInside];
    [controller.view addSubview:cacheButton];
    [NSLayoutConstraint activateConstraints:@[
        [cacheButton.centerXAnchor constraintEqualToAnchor:controller.view.centerXAnchor],
        [cacheButton.bottomAnchor constraintEqualToAnchor:controller.view.safeAreaLayoutGuide.bottomAnchor constant:-20],
        [cacheButton.leadingAnchor constraintGreaterThanOrEqualToAnchor:controller.view.leadingAnchor constant:16],
        [cacheButton.trailingAnchor constraintLessThanOrEqualToAnchor:controller.view.trailingAnchor constant:-16],
        [cacheButton.widthAnchor constraintLessThanOrEqualToConstant:350],
        [cacheButton.heightAnchor constraintEqualToConstant:46]
    ]];
    /* M5.0: separate guest VP/FP shader compiler test; M4.10 stays intact. */
    UIButton *shaderButton=[UIButton buttonWithType:UIButtonTypeSystem];
    shaderButton.translatesAutoresizingMaskIntoConstraints=NO;
    [shaderButton setTitle:@"M5.0 · Shaders RSX VP/FP" forState:UIControlStateNormal];
    [shaderButton setTitleColor:[UIColor whiteColor] forState:UIControlStateNormal];
    shaderButton.backgroundColor=[[UIColor blackColor] colorWithAlphaComponent:0.82];
    shaderButton.titleLabel.font=[UIFont systemFontOfSize:14 weight:UIFontWeightSemibold];
    shaderButton.layer.cornerRadius=10;
    [shaderButton addTarget:self action:@selector(testGuestRSXShader:) forControlEvents:UIControlEventTouchUpInside];
    [controller.view addSubview:shaderButton];
    [NSLayoutConstraint activateConstraints:@[
        [shaderButton.centerXAnchor constraintEqualToAnchor:controller.view.centerXAnchor],
        [shaderButton.bottomAnchor constraintEqualToAnchor:cacheButton.topAnchor constant:-10],
        [shaderButton.widthAnchor constraintLessThanOrEqualToConstant:350],
        [shaderButton.leadingAnchor constraintGreaterThanOrEqualToAnchor:controller.view.leadingAnchor constant:16],
        [shaderButton.trailingAnchor constraintLessThanOrEqualToAnchor:controller.view.trailingAnchor constant:-16],
        [shaderButton.heightAnchor constraintEqualToConstant:46]
    ]];
    /* M5.1: REAL RSX guest TEX0 rasterization; older buttons remain. */
    UIButton *drawButton=[UIButton buttonWithType:UIButtonTypeSystem];
    drawButton.translatesAutoresizingMaskIntoConstraints=NO;
    [drawButton setTitle:@"M5.1 · DRAW RSX TEX0 real" forState:UIControlStateNormal];
    [drawButton setTitleColor:[UIColor whiteColor] forState:UIControlStateNormal];
    drawButton.backgroundColor=[[UIColor blackColor] colorWithAlphaComponent:0.82];
    drawButton.titleLabel.font=[UIFont systemFontOfSize:14 weight:UIFontWeightSemibold];
    drawButton.layer.cornerRadius=10;
    [drawButton addTarget:self action:@selector(testM51GuestDraw:)
         forControlEvents:UIControlEventTouchUpInside];
    [controller.view addSubview:drawButton];
    [NSLayoutConstraint activateConstraints:@[
        [drawButton.centerXAnchor constraintEqualToAnchor:controller.view.centerXAnchor],
        [drawButton.bottomAnchor constraintEqualToAnchor:shaderButton.topAnchor constant:-10],
        [drawButton.widthAnchor constraintLessThanOrEqualToConstant:350],
        [drawButton.leadingAnchor constraintGreaterThanOrEqualToAnchor:controller.view.leadingAnchor constant:16],
        [drawButton.trailingAnchor constraintLessThanOrEqualToAnchor:controller.view.trailingAnchor constant:-16],
        [drawButton.heightAnchor constraintEqualToConstant:46]
    ]];
    /* M5.2: three genuine guest draws and two live cache replacements. */
    UIButton *mutationButton=[UIButton buttonWithType:UIButtonTypeSystem];
    mutationButton.translatesAutoresizingMaskIntoConstraints=NO;
    [mutationButton setTitle:@"M5.2 · TEXTURA dinâmica RSX" forState:UIControlStateNormal];
    [mutationButton setTitleColor:[UIColor whiteColor] forState:UIControlStateNormal];
    mutationButton.backgroundColor=[[UIColor blackColor] colorWithAlphaComponent:0.82];
    mutationButton.titleLabel.font=[UIFont systemFontOfSize:14 weight:UIFontWeightSemibold];
    mutationButton.layer.cornerRadius=10;
    [mutationButton addTarget:self action:@selector(testM52TextureMutation:)
             forControlEvents:UIControlEventTouchUpInside];
    [controller.view addSubview:mutationButton];
    [NSLayoutConstraint activateConstraints:@[
        [mutationButton.centerXAnchor constraintEqualToAnchor:controller.view.centerXAnchor],
        [mutationButton.bottomAnchor constraintEqualToAnchor:drawButton.topAnchor constant:-10],
        [mutationButton.widthAnchor constraintLessThanOrEqualToConstant:350],
        [mutationButton.leadingAnchor constraintGreaterThanOrEqualToAnchor:controller.view.leadingAnchor constant:16],
        [mutationButton.trailingAnchor constraintLessThanOrEqualToAnchor:controller.view.trailingAnchor constant:-16],
        [mutationButton.heightAnchor constraintEqualToConstant:46]
    ]];
    /* M5.3: guest render target -> TEX0 -> second guest GPU render target. */
    UIButton *multipassButton=[UIButton buttonWithType:UIButtonTypeSystem];
    multipassButton.translatesAutoresizingMaskIntoConstraints=NO;
    [multipassButton setTitle:@"M5.3 · Multipass RSX → Metal"
                    forState:UIControlStateNormal];
    [multipassButton setTitleColor:[UIColor whiteColor] forState:UIControlStateNormal];
    multipassButton.backgroundColor=[[UIColor blackColor] colorWithAlphaComponent:0.82];
    multipassButton.titleLabel.font=[UIFont systemFontOfSize:14 weight:UIFontWeightSemibold];
    multipassButton.layer.cornerRadius=10;
    [multipassButton addTarget:self action:@selector(testM53Multipass:)
           forControlEvents:UIControlEventTouchUpInside];
    [controller.view addSubview:multipassButton];
    [NSLayoutConstraint activateConstraints:@[
        [multipassButton.centerXAnchor constraintEqualToAnchor:controller.view.centerXAnchor],
        [multipassButton.bottomAnchor constraintEqualToAnchor:mutationButton.topAnchor constant:-10],
        [multipassButton.widthAnchor constraintLessThanOrEqualToConstant:350],
        [multipassButton.leadingAnchor constraintGreaterThanOrEqualToAnchor:controller.view.leadingAnchor constant:16],
        [multipassButton.trailingAnchor constraintLessThanOrEqualToAnchor:controller.view.trailingAnchor constant:-16],
        [multipassButton.heightAnchor constraintEqualToConstant:46]
    ]];
    /* M5.4: depth occlusion using actual NV40 guest shader draws. */
    UIButton *depthButton=[UIButton buttonWithType:UIButtonTypeSystem];
    depthButton.translatesAutoresizingMaskIntoConstraints=NO;
    [depthButton setTitle:@"M5.4 · Profundidade RSX/Metal" forState:UIControlStateNormal];
    [depthButton setTitleColor:[UIColor whiteColor] forState:UIControlStateNormal];
    depthButton.backgroundColor=[[UIColor blackColor] colorWithAlphaComponent:0.82];
    depthButton.titleLabel.font=[UIFont systemFontOfSize:14 weight:UIFontWeightSemibold];
    depthButton.layer.cornerRadius=10;
    [depthButton addTarget:self action:@selector(testM54DepthOcclusion:)
                forControlEvents:UIControlEventTouchUpInside];
    [controller.view addSubview:depthButton];
    [NSLayoutConstraint activateConstraints:@[
        [depthButton.centerXAnchor constraintEqualToAnchor:controller.view.centerXAnchor],
        [depthButton.bottomAnchor constraintEqualToAnchor:multipassButton.topAnchor constant:-10],
        [depthButton.widthAnchor constraintLessThanOrEqualToConstant:350],
        [depthButton.leadingAnchor constraintGreaterThanOrEqualToAnchor:controller.view.leadingAnchor constant:16],
        [depthButton.trailingAnchor constraintLessThanOrEqualToAnchor:controller.view.trailingAnchor constant:-16],
        [depthButton.heightAnchor constraintEqualToConstant:46]
    ]];
    /* M5.5: stencil ALWAYS/REPLACE, EQUAL reject, EQUAL accept. */
    UIButton *stencilButton=[UIButton buttonWithType:UIButtonTypeSystem];
    stencilButton.translatesAutoresizingMaskIntoConstraints=NO;
    [stencilButton setTitle:@"M5.5 · Máscara STENCIL RSX" forState:UIControlStateNormal];
    [stencilButton setTitleColor:[UIColor whiteColor] forState:UIControlStateNormal];
    stencilButton.backgroundColor=[[UIColor blackColor] colorWithAlphaComponent:0.82];
    stencilButton.titleLabel.font=[UIFont systemFontOfSize:14 weight:UIFontWeightSemibold];
    stencilButton.layer.cornerRadius=10;
    [stencilButton addTarget:self action:@selector(testM55StencilMask:)
              forControlEvents:UIControlEventTouchUpInside];
    [controller.view addSubview:stencilButton];
    [NSLayoutConstraint activateConstraints:@[
        [stencilButton.centerXAnchor constraintEqualToAnchor:controller.view.centerXAnchor],
        [stencilButton.bottomAnchor constraintEqualToAnchor:depthButton.topAnchor constant:-10],
        [stencilButton.widthAnchor constraintLessThanOrEqualToConstant:350],
        [stencilButton.leadingAnchor constraintGreaterThanOrEqualToAnchor:controller.view.leadingAnchor constant:16],
        [stencilButton.trailingAnchor constraintLessThanOrEqualToAnchor:controller.view.trailingAnchor constant:-16],
        [stencilButton.heightAnchor constraintEqualToConstant:46]
    ]];
    /* M5.6: real stencil write/read bit masks, no host simulation. */
    UIButton *maskButton=[UIButton buttonWithType:UIButtonTypeSystem];
    maskButton.translatesAutoresizingMaskIntoConstraints=NO;
    [maskButton setTitle:@"M5.6 · STENCIL bitmask RSX" forState:UIControlStateNormal];
    [maskButton setTitleColor:[UIColor whiteColor] forState:UIControlStateNormal];
    maskButton.backgroundColor=[[UIColor blackColor] colorWithAlphaComponent:0.82];
    maskButton.titleLabel.font=[UIFont systemFontOfSize:14 weight:UIFontWeightSemibold];
    maskButton.layer.cornerRadius=10;
    [maskButton addTarget:self action:@selector(testM56StencilBitmasks:)
                 forControlEvents:UIControlEventTouchUpInside];
    [controller.view addSubview:maskButton];
    [NSLayoutConstraint activateConstraints:@[
        [maskButton.centerXAnchor constraintEqualToAnchor:controller.view.centerXAnchor],
        [maskButton.bottomAnchor constraintEqualToAnchor:stencilButton.topAnchor constant:-10],
        [maskButton.widthAnchor constraintLessThanOrEqualToConstant:350],
        [maskButton.leadingAnchor constraintGreaterThanOrEqualToAnchor:controller.view.leadingAnchor constant:16],
        [maskButton.trailingAnchor constraintLessThanOrEqualToAnchor:controller.view.trailingAnchor constant:-16],
        [maskButton.heightAnchor constraintEqualToConstant:46]
    ]];
    UIButton *blendButton=[UIButton buttonWithType:UIButtonTypeSystem];
    blendButton.translatesAutoresizingMaskIntoConstraints=NO;
    [blendButton setTitle:@"M5.7 · Blend e máscaras RSX" forState:UIControlStateNormal];
    [blendButton setTitleColor:[UIColor whiteColor] forState:UIControlStateNormal];
    blendButton.backgroundColor=[[UIColor blackColor] colorWithAlphaComponent:0.82];
    blendButton.titleLabel.font=[UIFont systemFontOfSize:14 weight:UIFontWeightSemibold];
    blendButton.layer.cornerRadius=10;
    [blendButton addTarget:self action:@selector(testM57BlendMask:)
          forControlEvents:UIControlEventTouchUpInside];
    [controller.view addSubview:blendButton];
    [NSLayoutConstraint activateConstraints:@[
        [blendButton.centerXAnchor constraintEqualToAnchor:controller.view.centerXAnchor],
        [blendButton.bottomAnchor constraintEqualToAnchor:maskButton.topAnchor constant:-10],
        [blendButton.widthAnchor constraintLessThanOrEqualToConstant:350],
        [blendButton.leadingAnchor constraintGreaterThanOrEqualToAnchor:controller.view.leadingAnchor constant:16],
        [blendButton.trailingAnchor constraintLessThanOrEqualToAnchor:controller.view.trailingAnchor constant:-16],
        [blendButton.heightAnchor constraintEqualToConstant:46]
    ]];
    UIButton *alphaButton=[UIButton buttonWithType:UIButtonTypeSystem];
    alphaButton.translatesAutoresizingMaskIntoConstraints=NO;
    [alphaButton setTitle:@"M5.8 · Transparência ALPHA RSX" forState:UIControlStateNormal];
    [alphaButton setTitleColor:[UIColor whiteColor] forState:UIControlStateNormal];
    alphaButton.backgroundColor=[[UIColor blackColor] colorWithAlphaComponent:0.82];
    alphaButton.titleLabel.font=[UIFont systemFontOfSize:14 weight:UIFontWeightSemibold];
    alphaButton.layer.cornerRadius=10;
    [alphaButton addTarget:self action:@selector(testM58AlphaTest:)
          forControlEvents:UIControlEventTouchUpInside];
    [controller.view addSubview:alphaButton];
    [NSLayoutConstraint activateConstraints:@[
        [alphaButton.centerXAnchor constraintEqualToAnchor:controller.view.centerXAnchor],
        [alphaButton.bottomAnchor constraintEqualToAnchor:blendButton.topAnchor constant:-10],
        [alphaButton.widthAnchor constraintLessThanOrEqualToConstant:350],
        [alphaButton.leadingAnchor constraintGreaterThanOrEqualToAnchor:controller.view.leadingAnchor constant:16],
        [alphaButton.trailingAnchor constraintLessThanOrEqualToAnchor:controller.view.trailingAnchor constant:-16],
        [alphaButton.heightAnchor constraintEqualToConstant:46]
    ]];
    /* M5.9: explicit private Files import; no title data in the IPA. */
    UIButton *elfButton=[UIButton buttonWithType:UIButtonTypeSystem];
    elfButton.translatesAutoresizingMaskIntoConstraints=NO;
    [elfButton setTitle:@"Selecionar GOWA.ELF · iniciar boot nativo" forState:UIControlStateNormal];
    [elfButton setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
    elfButton.backgroundColor=[UIColor.blackColor colorWithAlphaComponent:0.82];
    elfButton.titleLabel.font=[UIFont systemFontOfSize:14 weight:UIFontWeightSemibold];
    elfButton.layer.cornerRadius=10;
    [elfButton addTarget:self action:@selector(importM59ELF:)
             forControlEvents:UIControlEventTouchUpInside];
    [controller.view addSubview:elfButton];
    [NSLayoutConstraint activateConstraints:@[
      [elfButton.centerXAnchor constraintEqualToAnchor:controller.view.centerXAnchor],
      [elfButton.bottomAnchor constraintEqualToAnchor:alphaButton.topAnchor constant:-10],
      [elfButton.widthAnchor constraintLessThanOrEqualToConstant:350],
      [elfButton.heightAnchor constraintEqualToConstant:46],
      [elfButton.leadingAnchor constraintGreaterThanOrEqualToAnchor:controller.view.leadingAnchor constant:16],
      [elfButton.trailingAnchor constraintLessThanOrEqualToAnchor:controller.view.trailingAnchor constant:-16]
    ]];

    /* M6.2.3 — UI ONLY. Original gestures, GOWA.ELF import, all
     * handlers and the guest PPU / RSX engines remain unchanged.
     * Remove the old, unscrollable button-to-button constraints and
     * reparent the SAME buttons into two scrollable sections. */
    NSArray<UIButton *> *buttons=@[
        cacheButton,shaderButton,drawButton,mutationButton,multipassButton,
        depthButton,stencilButton,maskButton,blendButton,alphaButton,elfButton];
    NSMutableArray<NSLayoutConstraint *> *old=[NSMutableArray array];
    for(NSLayoutConstraint *c in controller.view.constraints)
        if([buttons containsObject:c.firstItem] ||
           [buttons containsObject:c.secondItem]) [old addObject:c];
    [NSLayoutConstraint deactivateConstraints:old];

    status.font=[UIFont systemFontOfSize:13 weight:UIFontWeightMedium];
    status.layer.cornerRadius=12;
    status.layer.masksToBounds=YES;

    UIView *panel=[UIView new];
    panel.translatesAutoresizingMaskIntoConstraints=NO;
    panel.backgroundColor=[[UIColor colorWithRed:0.035 green:0.06 blue:0.12 alpha:1]
                              colorWithAlphaComponent:0.94];
    panel.layer.cornerRadius=17;
    panel.layer.masksToBounds=YES;
    [controller.view addSubview:panel];
    UILabel *header=[UILabel new];
    header.translatesAutoresizingMaskIntoConstraints=NO;
    header.text=[NSString stringWithFormat:@"ASCENSIONRECOMP   ·   %@",ARCurrentRelease()];
    header.textColor=[UIColor colorWithRed:0.73 green:0.87 blue:1 alpha:1];
    header.font=[UIFont systemFontOfSize:12 weight:UIFontWeightBold];
    header.textAlignment=NSTextAlignmentCenter;
    [panel addSubview:header];
    UISegmentedControl *tabs=[[UISegmentedControl alloc]
                         initWithItems:@[@"Jogo / PPU", @"RSX / Metal"]];
    tabs.translatesAutoresizingMaskIntoConstraints=NO;
    tabs.selectedSegmentIndex=0;
    tabs.selectedSegmentTintColor=[UIColor colorWithRed:0.11 green:0.42 blue:0.75 alpha:1];
    [tabs setTitleTextAttributes:@{NSForegroundColorAttributeName:UIColor.whiteColor}
                       forState:UIControlStateSelected];
    [tabs addTarget:self action:@selector(arSwitchTab:)
                forControlEvents:UIControlEventValueChanged];
    [panel addSubview:tabs];
    UIScrollView *game=[UIScrollView new],*graphics=[UIScrollView new];
    for(UIScrollView *scroll in @[game,graphics]) {
        scroll.translatesAutoresizingMaskIntoConstraints=NO;
        scroll.alwaysBounceVertical=YES;
        [panel addSubview:scroll];
        [NSLayoutConstraint activateConstraints:@[
          [scroll.topAnchor constraintEqualToAnchor:tabs.bottomAnchor constant:12],
          [scroll.bottomAnchor constraintEqualToAnchor:panel.bottomAnchor constant:-12],
          [scroll.leadingAnchor constraintEqualToAnchor:panel.leadingAnchor constant:12],
          [scroll.trailingAnchor constraintEqualToAnchor:panel.trailingAnchor constant:-12]
        ]];
    }
    self.gameList=game; self.graphicsList=graphics; graphics.hidden=YES;
    UIButton *reportButton=[UIButton buttonWithType:UIButtonTypeSystem];
    [reportButton setTitle:@"Copiar status AOT" forState:UIControlStateNormal];
    [reportButton setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
    reportButton.backgroundColor=[UIColor colorWithRed:0.14 green:0.23 blue:0.35 alpha:1];
    reportButton.titleLabel.font=[UIFont systemFontOfSize:14 weight:UIFontWeightSemibold];
    reportButton.layer.cornerRadius=11;
    reportButton.enabled=NO;
    [reportButton.heightAnchor constraintEqualToConstant:42].active=YES;
    [reportButton addTarget:self action:@selector(copyPpuReport:)
            forControlEvents:UIControlEventTouchUpInside];
    self.ppuReportButton=reportButton;
    UIButton *batchButton=[UIButton buttonWithType:UIButtonTypeSystem];
    [batchButton setTitle:@"Copiar lote PPC (até 32 instruções)" forState:UIControlStateNormal];
    [batchButton setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
    batchButton.backgroundColor=[UIColor colorWithRed:0.14 green:0.23 blue:0.35 alpha:1];
    batchButton.titleLabel.font=[UIFont systemFontOfSize:13 weight:UIFontWeightSemibold];
    batchButton.layer.cornerRadius=11;
    batchButton.enabled=NO;
    [batchButton.heightAnchor constraintEqualToConstant:42].active=YES;
    [batchButton addTarget:self action:@selector(copyPpuBatch:)
        forControlEvents:UIControlEventTouchUpInside];
    self.ppuBatchButton=batchButton;
    UIButton *advancedButton=[UIButton buttonWithType:UIButtonTypeSystem];
    [advancedButton setTitle:@"Diagnóstico avançado · M6/M7" forState:UIControlStateNormal];
    [advancedButton setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
    advancedButton.backgroundColor=[UIColor colorWithRed:0.12 green:0.18 blue:0.27 alpha:1];
    advancedButton.titleLabel.font=[UIFont systemFontOfSize:13 weight:UIFontWeightMedium];
    advancedButton.layer.cornerRadius=11;
    [advancedButton.heightAnchor constraintEqualToConstant:40].active=YES;
    advancedButton.enabled=NO;
    advancedButton.accessibilityLabel=@"Copiar diagnóstico PPU completo e consultar detalhes";
    [advancedButton addTarget:self action:@selector(openAdvancedPpuReport:)
            forControlEvents:UIControlEventTouchUpInside];
    self.ppuAdvancedButton=advancedButton;
    /* M7.19: One consolidated diagnostics control replaces three
     * separate status/lote PPC/advanced buttons in the visible UI. */
    UIButton *diagnostics=[UIButton buttonWithType:UIButtonTypeSystem];
    [diagnostics setTitle:@"Relatório completo · visualizar / TXT" forState:UIControlStateNormal];
    [diagnostics setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
    diagnostics.backgroundColor=[UIColor colorWithRed:0.13 green:0.30 blue:0.48 alpha:1];
    diagnostics.titleLabel.font=[UIFont systemFontOfSize:14 weight:UIFontWeightSemibold];
    diagnostics.titleLabel.adjustsFontSizeToFitWidth=YES;
    diagnostics.titleLabel.minimumScaleFactor=0.8;
    diagnostics.layer.cornerRadius=11;
    diagnostics.accessibilityLabel=@"Relatório completo: status AOT, PPC, grafo, HLE e exportar TXT";
    [diagnostics.heightAnchor constraintEqualToConstant:46].active=YES;
    diagnostics.enabled=NO;
    [diagnostics addTarget:self action:@selector(openUnifiedPpuMenu:)
         forControlEvents:UIControlEventTouchUpInside];
    self.ppuDiagnosticsButton=diagnostics;
    self.ppuDiagnosticsButton.enabled=NO;
    /* M7.37 F0: user-selected game folder independent of guest sys_fs. */
    UIButton *folderButton=[UIButton buttonWithType:UIButtonTypeSystem];
    [folderButton setTitle:@"Selecionar pasta NPUA80918 · Abrir"
                forState:UIControlStateNormal];
    [folderButton setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
    folderButton.titleLabel.font=[UIFont systemFontOfSize:14 weight:UIFontWeightSemibold];
    folderButton.titleLabel.adjustsFontSizeToFitWidth=YES;
    folderButton.titleLabel.minimumScaleFactor=0.7;
    folderButton.layer.cornerRadius=11;
    [folderButton.heightAnchor constraintEqualToConstant:46].active=YES;
    [folderButton addTarget:self action:@selector(importGameFolder:)
         forControlEvents:UIControlEventTouchUpInside];
    /* F1: local Files Documents folder, independent of the iCloud picker. */
    UIButton *localFolderButton=[UIButton buttonWithType:UIButtonTypeSystem];
    [localFolderButton setTitle:@"Detectar arquivos locais · NPUA80918"
                     forState:UIControlStateNormal];
    [localFolderButton setTitleColor:UIColor.whiteColor
                           forState:UIControlStateNormal];
    localFolderButton.titleLabel.font=[UIFont systemFontOfSize:14
                                                         weight:UIFontWeightSemibold];
    localFolderButton.titleLabel.adjustsFontSizeToFitWidth=YES;
    localFolderButton.titleLabel.minimumScaleFactor=0.72;
    localFolderButton.layer.cornerRadius=11;
    [localFolderButton.heightAnchor constraintEqualToConstant:46].active=YES;
    [localFolderButton addTarget:self action:@selector(importGameFolderFromDocuments:)
             forControlEvents:UIControlEventTouchUpInside];
    /* M7.40: read-only existing RPCS3 PARAM.SFO picker; no copies. */
    UIButton *rpcMarkerButton=[UIButton buttonWithType:UIButtonTypeSystem];
    [rpcMarkerButton setTitle:@"Importar PARAM.SFO · cópia temporária"
                    forState:UIControlStateNormal];
    [rpcMarkerButton setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
    rpcMarkerButton.titleLabel.font=[UIFont systemFontOfSize:14
                                         weight:UIFontWeightSemibold];
    rpcMarkerButton.titleLabel.adjustsFontSizeToFitWidth=YES;
    rpcMarkerButton.titleLabel.minimumScaleFactor=0.66;
    rpcMarkerButton.layer.cornerRadius=11;
    [rpcMarkerButton.heightAnchor constraintEqualToConstant:46].active=YES;
    [rpcMarkerButton addTarget:self action:@selector(importRPCS3Marker:)
              forControlEvents:UIControlEventTouchUpInside];
    NSArray<UIScrollView *> *scrollers=@[game,graphics];
    for(NSUInteger i=0;i<scrollers.count;i++) {
        UIScrollView *scroll=scrollers[i];
        UIStackView *stack=[UIStackView new];
        stack.translatesAutoresizingMaskIntoConstraints=NO;
        stack.axis=UILayoutConstraintAxisVertical;
        stack.alignment=UIStackViewAlignmentFill;
        stack.spacing=10;
        [scroll addSubview:stack];
        UILabel *hint=[UILabel new];
        hint.numberOfLines=0;
        hint.textAlignment=NSTextAlignmentCenter;
        hint.font=[UIFont systemFontOfSize:13 weight:UIFontWeightMedium];
        hint.textColor=[UIColor colorWithWhite:0.83 alpha:1];
        hint.text=i==0 ?
             @"GOD OF WAR · ASCENSION\nNPUA80918 · runtime PS3Recomp recompilado para ARM64. Configure os arquivos e acompanhe cada etapa do boot." :
             @"Diagnósticos RSX → Metal, do mais recente ao legado. Role para encontrar os testes anteriores.";
        [stack addArrangedSubview:hint];
        NSArray<UIButton *> *ordered=i==0 ? @[elfButton,folderButton,localFolderButton,rpcMarkerButton] : @[
            alphaButton,blendButton,maskButton,stencilButton,depthButton,
            multipassButton,mutationButton,drawButton,shaderButton,cacheButton];
        for(UIButton *button in ordered) {
            button.backgroundColor=(i==0 && button==elfButton) ?
                [UIColor colorWithRed:0.12 green:0.48 blue:0.31 alpha:1] :
                [UIColor colorWithRed:0.11 green:0.18 blue:0.30 alpha:1];
            button.titleLabel.adjustsFontSizeToFitWidth=YES;
            button.titleLabel.minimumScaleFactor=0.76;
            [stack addArrangedSubview:button];
        }
        if(i==0) {
            [stack addArrangedSubview:diagnostics];
            UILabel *privacy=[UILabel new];
            privacy.numberOfLines=0;
            privacy.textAlignment=NSTextAlignmentCenter;
            privacy.textColor=[UIColor colorWithWhite:0.64 alpha:1];
            privacy.font=[UIFont systemFontOfSize:12];
            privacy.text=@"O GOWA.ELF fica no iPhone e não é incluído na IPA ou enviado ao GitHub.";
            [stack addArrangedSubview:privacy];
        }
        [NSLayoutConstraint activateConstraints:@[
            [stack.leadingAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.leadingAnchor],
            [stack.trailingAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.trailingAnchor],
            [stack.topAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.topAnchor],
            [stack.bottomAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.bottomAnchor],
            [stack.widthAnchor constraintEqualToAnchor:scroll.frameLayoutGuide.widthAnchor]
        ]];
    }
    [elfButton setTitle:@"Selecionar GOWA.ELF · iniciar boot nativo" forState:UIControlStateNormal];
    NSLayoutConstraint *height=[panel.heightAnchor
             constraintEqualToAnchor:controller.view.heightAnchor multiplier:0.60];
    height.priority=UILayoutPriorityDefaultHigh;
    [NSLayoutConstraint activateConstraints:@[
        [panel.leadingAnchor constraintEqualToAnchor:controller.view.safeAreaLayoutGuide.leadingAnchor constant:12],
        [panel.trailingAnchor constraintEqualToAnchor:controller.view.safeAreaLayoutGuide.trailingAnchor constant:-12],
        [panel.bottomAnchor constraintEqualToAnchor:controller.view.safeAreaLayoutGuide.bottomAnchor constant:-12],
        [panel.topAnchor constraintGreaterThanOrEqualToAnchor:status.bottomAnchor constant:12],
        height,
        [header.topAnchor constraintEqualToAnchor:panel.topAnchor constant:12],
        [header.leadingAnchor constraintEqualToAnchor:panel.leadingAnchor constant:12],
        [header.trailingAnchor constraintEqualToAnchor:panel.trailingAnchor constant:-12],
        [tabs.topAnchor constraintEqualToAnchor:header.bottomAnchor constant:12],
        [tabs.leadingAnchor constraintEqualToAnchor:panel.leadingAnchor constant:12],
        [tabs.trailingAnchor constraintEqualToAnchor:panel.trailingAnchor constant:-12],
        [tabs.heightAnchor constraintEqualToConstant:35]
    ]];
    self.window.rootViewController=controller;
    [self.window makeKeyAndVisible];

    dispatch_async(dispatch_get_main_queue(), ^{
        BOOL attached=[self.metalView bindToPS3MetalBackend];
        /* The test app has no game ELF; expose a genuine bounded scratch VM. */
        int memory_ready=attached ? ar_probe_vm_init() : -1;
        int initialized=memory_ready==0 ? rsx_metal_backend_init(960,540,"AscensionRecomp GPU Probe") : -1;
        self.ready=(initialized==0);
        if(self.ready) {
            /* The preceding empty backend_present could race the direct
             * Metal clear and leave BLACK on the first screen (seen in the
             * user's M4.3 video). Never report blue without GPU completion. */
            NSString *referenceError=nil;
            BOOL referenceOK=[self.metalView presentDiagnosticFrame:0
                                                             error:&referenceError];
            if(referenceOK) {
                self.successfulFrames=1;
                self.status.text=@"Referência Metal direta: AZUL\n"
                                  "1 toque: limpar pelo RSX NV4097\n"
                                  "Segure 1s: TRIÂNGULO INLINE (M4.5)\n"
                                  "2 toques: TRIÂNGULO DMA da memória PS3\n"
                                  "3 toques: QUAD indexado 16/32 bits\n"
                                  "4 toques: TEXTURA PS3 linear/swizzled\n"
                                  "5 toques: TEXTURA por NV4097/cache/Metal\n"
                                  "Sem arquivos do jogo.";
                self.status.text=@"ASCENSIONRECOMP · NPUA80918\n"
                                  "M7.72 · PPU recompilada estaticamente\n"
                                  "Importe GOWA.ELF e selecione a pasta do jogo.\n"
                                  "Boot e gameplay só são confirmados por execução guest e quadro RSX.\n"
                                  "Ferramentas RSX estão na aba RSX / Metal.";
            } else {
                self.status.text=[NSString stringWithFormat:
                     @"A referência Metal falhou: %@\n"
                      "Toque para tentar RSX NV4097.",
                     referenceError ?: @"sem detalhes"];
            }
        } else {
            ar_probe_vm_shutdown();
            self.status.text=@"Falha ao inicializar o backend RSX→Metal.\nEnvie uma captura de tela para diagnóstico.";
        }
    });
    /* Bookmark survives app restart; no file copied to the IPA/sandbox.
     * Manifest reconstruction is local-only and does not call guest sys_fs. */
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY,0),^{
       NSDictionary *prior=ARGameFolderRestore(NULL);
       if(!prior)return;
       dispatch_async(dispatch_get_main_queue(),^{
         if(!self.folderReport.length){
           self.folderReport=[NSString stringWithFormat:
              @"M7.37 F0 — Pasta anterior restaurada · %@ arquivo(s), %@ bytes.\n"
               "Manifesto privado local; cellFsOpen/Read ainda pendentes.\n",
               prior[@"file_count"],prior[@"total_bytes"]];
           self.ppuDiagnosticsButton.enabled=YES;
         }
       });
    });
    return YES;
#endif
    return NO;
}

- (UILabel*)arLauncherLabel:(NSString*)text size:(CGFloat)size weight:(UIFontWeight)weight
                      color:(UIColor*)color lines:(NSInteger)lines {
  UILabel *label=[UILabel new]; label.translatesAutoresizingMaskIntoConstraints=NO;
  label.text=text; label.font=[UIFont systemFontOfSize:size weight:weight];
  label.textColor=color; label.numberOfLines=lines;
  return label;
}
- (UIButton*)arLauncherButton:(NSString*)title background:(UIColor*)background action:(SEL)action {
  UIButton *button=[UIButton buttonWithType:UIButtonTypeSystem];
  button.translatesAutoresizingMaskIntoConstraints=NO;
  [button setTitle:title forState:UIControlStateNormal];
  [button setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
  button.titleLabel.font=[UIFont systemFontOfSize:14 weight:UIFontWeightBold];
  button.titleLabel.numberOfLines=2; button.titleLabel.textAlignment=NSTextAlignmentCenter;
  button.backgroundColor=background; button.layer.cornerRadius=12;
  button.contentEdgeInsets=UIEdgeInsetsMake(13,16,13,16);
  [button.heightAnchor constraintGreaterThanOrEqualToConstant:48].active=YES;
  [button addTarget:self action:action forControlEvents:UIControlEventTouchUpInside];
  return button;
}

- (BOOL)buildLauncherWithApplication:(UIApplication*)app options:(NSDictionary*)options {
  (void)app; (void)options;
  NSError *homeError=nil;
  if(!ARGameFolderPrepareDocumentsHome(&homeError))
    self.folderReport=[NSString stringWithFormat:@"Documents local indisponível: %@",
                       homeError.localizedDescription?:@"erro do iOS"];
  self.window=[[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
  UIViewController *controller=[UIViewController new];
  UIColor *background=[UIColor colorWithRed:0.035 green:0.039 blue:0.047 alpha:1];
  UIColor *panel=[UIColor colorWithRed:0.085 green:0.09 blue:0.10 alpha:1];
  UIColor *gold=[UIColor colorWithRed:0.84 green:0.68 blue:0.37 alpha:1];
  UIColor *muted=[UIColor colorWithRed:0.66 green:0.68 blue:0.70 alpha:1];
  controller.view.backgroundColor=background; self.window.rootViewController=controller;

  ARMetalView *metal=[[ARMetalView alloc] initWithFrame:CGRectZero];
  metal.translatesAutoresizingMaskIntoConstraints=NO; metal.hidden=YES; self.metalView=metal;
  [controller.view addSubview:metal];
  [NSLayoutConstraint activateConstraints:@[
    [metal.leadingAnchor constraintEqualToAnchor:controller.view.leadingAnchor],
    [metal.trailingAnchor constraintEqualToAnchor:controller.view.trailingAnchor],
    [metal.topAnchor constraintEqualToAnchor:controller.view.topAnchor],
    [metal.bottomAnchor constraintEqualToAnchor:controller.view.bottomAnchor]
  ]];

  UIStackView *brandBar=[UIStackView new]; brandBar.translatesAutoresizingMaskIntoConstraints=NO;
  brandBar.axis=UILayoutConstraintAxisHorizontal; brandBar.alignment=UIStackViewAlignmentCenter;
  brandBar.distribution=UIStackViewDistributionEqualSpacing; self.launcherBrand=brandBar;
  UIStackView *brandCopy=[UIStackView new]; brandCopy.axis=UILayoutConstraintAxisVertical; brandCopy.spacing=2;
  UILabel *brandTitle=[self arLauncherLabel:@"GOD OF WAR  ASCENSION" size:14 weight:UIFontWeightBlack color:UIColor.whiteColor lines:1];
  brandTitle.font=[UIFont fontWithName:@"Georgia-Bold" size:14] ?: brandTitle.font;
  [brandCopy addArrangedSubview:brandTitle];
  UILabel *brandSubtitle=[self arLauncherLabel:@"NPUA80918  ·  PS3 → iOS ARM64" size:9 weight:UIFontWeightMedium color:muted lines:1];
  brandSubtitle.font=[UIFont monospacedSystemFontOfSize:9 weight:UIFontWeightMedium];
  [brandCopy addArrangedSubview:brandSubtitle];
  UILabel *versionBadge=[self arLauncherLabel:ARCurrentRelease() size:10 weight:UIFontWeightBold color:gold lines:1];
  versionBadge.textAlignment=NSTextAlignmentCenter;
  versionBadge.backgroundColor=[UIColor colorWithRed:0.24 green:0.17 blue:0.08 alpha:1];
  versionBadge.layer.cornerRadius=10; versionBadge.layer.masksToBounds=YES;
  versionBadge.layer.borderWidth=1; versionBadge.layer.borderColor=[gold colorWithAlphaComponent:0.45].CGColor;
  versionBadge.text=[NSString stringWithFormat:@"  %@  ",ARCurrentRelease()];
  [versionBadge.heightAnchor constraintEqualToConstant:28].active=YES;
  [brandBar addArrangedSubview:brandCopy]; [brandBar addArrangedSubview:versionBadge];
  [controller.view addSubview:brandBar];
  [NSLayoutConstraint activateConstraints:@[
    [brandBar.topAnchor constraintEqualToAnchor:controller.view.safeAreaLayoutGuide.topAnchor constant:7],
    [brandBar.leadingAnchor constraintEqualToAnchor:controller.view.leadingAnchor constant:20],
    [brandBar.trailingAnchor constraintEqualToAnchor:controller.view.trailingAnchor constant:-20],
    [brandBar.heightAnchor constraintEqualToConstant:38]
  ]];

  UISegmentedControl *tabs=[[UISegmentedControl alloc] initWithItems:@[@"JOGAR",@"ARQUIVOS",@"AJUSTES",@"RELATÓRIO"]];
  tabs.translatesAutoresizingMaskIntoConstraints=NO; tabs.selectedSegmentIndex=0;
  self.launcherTabs=tabs;
  tabs.backgroundColor=panel;
  tabs.selectedSegmentTintColor=[UIColor colorWithRed:0.48 green:0.16 blue:0.11 alpha:1];
  [tabs setTitleTextAttributes:@{NSForegroundColorAttributeName:UIColor.whiteColor,
      NSFontAttributeName:[UIFont systemFontOfSize:11 weight:UIFontWeightBold]}
                       forState:UIControlStateNormal];
  [tabs addTarget:self action:@selector(arSwitchTab:) forControlEvents:UIControlEventValueChanged];
  [controller.view addSubview:tabs];
  [NSLayoutConstraint activateConstraints:@[
    [tabs.topAnchor constraintEqualToAnchor:brandBar.bottomAnchor constant:9],
    [tabs.leadingAnchor constraintEqualToAnchor:controller.view.leadingAnchor constant:18],
    [tabs.trailingAnchor constraintEqualToAnchor:controller.view.trailingAnchor constant:-18],
    [tabs.heightAnchor constraintEqualToConstant:40]
  ]];

  UIScrollView *(^makePage)(void)=^UIScrollView*{
    UIScrollView *page=[UIScrollView new]; page.translatesAutoresizingMaskIntoConstraints=NO;
    page.alwaysBounceVertical=YES; page.showsVerticalScrollIndicator=NO;
    page.backgroundColor=UIColor.clearColor; [controller.view addSubview:page];
    [NSLayoutConstraint activateConstraints:@[
      [page.topAnchor constraintEqualToAnchor:tabs.bottomAnchor constant:8],
      [page.leadingAnchor constraintEqualToAnchor:controller.view.leadingAnchor],
      [page.trailingAnchor constraintEqualToAnchor:controller.view.trailingAnchor],
      [page.bottomAnchor constraintEqualToAnchor:controller.view.safeAreaLayoutGuide.bottomAnchor]
    ]];
    return page;
  };
  UIStackView *(^makeContent)(UIScrollView*)=^UIStackView*(UIScrollView *page){
    UIStackView *stack=[UIStackView new]; stack.translatesAutoresizingMaskIntoConstraints=NO;
    stack.axis=UILayoutConstraintAxisVertical; stack.alignment=UIStackViewAlignmentFill;
    stack.spacing=13; [page addSubview:stack];
    [NSLayoutConstraint activateConstraints:@[
      [stack.leadingAnchor constraintEqualToAnchor:page.contentLayoutGuide.leadingAnchor constant:18],
      [stack.trailingAnchor constraintEqualToAnchor:page.contentLayoutGuide.trailingAnchor constant:-18],
      [stack.topAnchor constraintEqualToAnchor:page.contentLayoutGuide.topAnchor constant:10],
      [stack.bottomAnchor constraintEqualToAnchor:page.contentLayoutGuide.bottomAnchor constant:-18],
      [stack.widthAnchor constraintEqualToAnchor:page.frameLayoutGuide.widthAnchor constant:-36]
    ]];
    return stack;
  };
  UIScrollView *game=makePage(), *graphics=makePage(), *settingsPage=makePage(), *report=makePage();
  graphics.hidden=YES; settingsPage.hidden=YES; report.hidden=YES;
  self.gameList=game; self.graphicsList=graphics;
  self.settingsList=settingsPage; self.reportList=report;
  UIStackView *main=makeContent(game);

  [main addArrangedSubview:[self arLauncherLabel:@"SUA BIBLIOTECA" size:10 weight:UIFontWeightBold color:gold lines:1]];

  ARLauncherHeroView *hero=[ARLauncherHeroView new]; hero.translatesAutoresizingMaskIntoConstraints=NO;
  CAGradientLayer *heroGradient=(CAGradientLayer*)hero.layer;
  heroGradient.colors=@[(id)[UIColor colorWithRed:0.34 green:0.095 blue:0.055 alpha:1].CGColor,
                         (id)[UIColor colorWithRed:0.16 green:0.055 blue:0.050 alpha:1].CGColor,
                         (id)[UIColor colorWithRed:0.045 green:0.040 blue:0.052 alpha:1].CGColor];
  heroGradient.startPoint=CGPointMake(0,0); heroGradient.endPoint=CGPointMake(1,1);
  hero.layer.cornerRadius=19; hero.layer.borderWidth=1;
  hero.clipsToBounds=YES;
  hero.layer.borderColor=[[UIColor colorWithRed:0.42 green:0.22 blue:0.13 alpha:1] colorWithAlphaComponent:0.65].CGColor;
  [hero.heightAnchor constraintEqualToConstant:226].active=YES;
  UIImageView *cover=[UIImageView new]; cover.translatesAutoresizingMaskIntoConstraints=NO;
  cover.contentMode=UIViewContentModeScaleAspectFit; cover.alpha=1.0; cover.hidden=YES;
  cover.backgroundColor=[UIColor colorWithWhite:0.06 alpha:1];
  cover.layer.cornerRadius=12; cover.layer.masksToBounds=YES;
  cover.layer.borderWidth=1; cover.layer.borderColor=[gold colorWithAlphaComponent:0.65].CGColor;
  [hero addSubview:cover]; self.gameCoverView=cover;
  [NSLayoutConstraint activateConstraints:@[
    [cover.trailingAnchor constraintEqualToAnchor:hero.trailingAnchor constant:-14],
    [cover.topAnchor constraintEqualToAnchor:hero.topAnchor constant:14],
    [cover.widthAnchor constraintEqualToConstant:68],
    [cover.heightAnchor constraintEqualToConstant:68]
  ]];
  UIView *stripe=[UIView new]; stripe.translatesAutoresizingMaskIntoConstraints=NO;
  stripe.backgroundColor=gold; stripe.layer.cornerRadius=2; [hero addSubview:stripe];
  UIStackView *heroCopy=[UIStackView new]; heroCopy.translatesAutoresizingMaskIntoConstraints=NO;
  heroCopy.axis=UILayoutConstraintAxisVertical; heroCopy.spacing=7;
  [heroCopy addArrangedSubview:[self arLauncherLabel:@"RECOMPILAÇÃO NATIVA  ·  PLAYSTATION 3" size:9 weight:UIFontWeightBold color:[UIColor colorWithWhite:0.84 alpha:1] lines:1]];
  UILabel *heroTitle=[self arLauncherLabel:@"ASCENSION" size:33 weight:UIFontWeightBlack color:UIColor.whiteColor lines:1];
  heroTitle.font=[UIFont fontWithName:@"Georgia-Bold" size:33] ?: heroTitle.font;
  [heroCopy addArrangedSubview:heroTitle];
  UILabel *region=[self arLauncherLabel:@"NPUA80918   •   PLAYSTATION 3" size:10 weight:UIFontWeightMedium color:gold lines:1];
  region.font=[UIFont monospacedSystemFontOfSize:10 weight:UIFontWeightMedium];
  [heroCopy addArrangedSubview:region];
  [heroCopy addArrangedSubview:[self arLauncherLabel:@"PS3Recomp · guest ARM64 · renderização Metal" size:11 weight:UIFontWeightMedium color:[UIColor colorWithWhite:0.84 alpha:1] lines:1]];
  [hero addSubview:heroCopy];
  [NSLayoutConstraint activateConstraints:@[
    [stripe.leadingAnchor constraintEqualToAnchor:hero.leadingAnchor constant:17],
    [stripe.topAnchor constraintEqualToAnchor:hero.topAnchor constant:20],
    [stripe.widthAnchor constraintEqualToConstant:3],
    [stripe.heightAnchor constraintEqualToConstant:152],
    [heroCopy.leadingAnchor constraintEqualToAnchor:stripe.trailingAnchor constant:14],
    [heroCopy.trailingAnchor constraintEqualToAnchor:hero.trailingAnchor constant:-15],
    [heroCopy.bottomAnchor constraintEqualToAnchor:hero.bottomAnchor constant:-17]
  ]];
  [main addArrangedSubview:hero];

  UIView *library=[UIView new]; library.translatesAutoresizingMaskIntoConstraints=NO;
  library.backgroundColor=panel; library.layer.cornerRadius=15;
  library.layer.borderWidth=1; library.layer.borderColor=[UIColor colorWithWhite:0.20 alpha:1].CGColor;
  UIStackView *libraryRows=[UIStackView new]; libraryRows.translatesAutoresizingMaskIntoConstraints=NO;
  libraryRows.axis=UILayoutConstraintAxisVertical; libraryRows.spacing=8;
  [libraryRows addArrangedSubview:[self arLauncherLabel:@"ARQUIVOS DO JOGO" size:10 weight:UIFontWeightBold color:gold lines:1]];
  self.gameInstallLabel=[self arLauncherLabel:@"Pasta do jogo não selecionada" size:13 weight:UIFontWeightSemibold color:UIColor.whiteColor lines:2];
  [libraryRows addArrangedSubview:self.gameInstallLabel];
  UIView *separator=[UIView new]; separator.backgroundColor=[UIColor colorWithWhite:0.22 alpha:1];
  [separator.heightAnchor constraintEqualToConstant:1].active=YES; [libraryRows addArrangedSubview:separator];
  [libraryRows addArrangedSubview:[self arLauncherLabel:@"EXECUTÁVEL" size:10 weight:UIFontWeightBold color:gold lines:1]];
  self.elfStatusLabel=[self arLauncherLabel:@"GOWA.ELF não importado" size:13 weight:UIFontWeightSemibold color:UIColor.whiteColor lines:2];
  [libraryRows addArrangedSubview:self.elfStatusLabel]; [library addSubview:libraryRows];
  [NSLayoutConstraint activateConstraints:@[
    [libraryRows.leadingAnchor constraintEqualToAnchor:library.leadingAnchor constant:14],
    [libraryRows.trailingAnchor constraintEqualToAnchor:library.trailingAnchor constant:-14],
    [libraryRows.topAnchor constraintEqualToAnchor:library.topAnchor constant:13],
    [libraryRows.bottomAnchor constraintEqualToAnchor:library.bottomAnchor constant:-13]
  ]];
  [main addArrangedSubview:library];

  self.nativeLaunchButton=[self arLauncherButton:@"INICIAR JOGO" background:[UIColor colorWithRed:0.47 green:0.12 blue:0.10 alpha:1] action:@selector(startNativeGame:)];
  [self.nativeLaunchButton setTitle:@"▶   INICIAR ASCENSION" forState:UIControlStateNormal];
  [self.nativeLaunchButton.heightAnchor constraintEqualToConstant:54].active=YES;
  self.nativeLaunchButton.enabled=NO; self.nativeLaunchButton.alpha=0.52;
  UIView *footer=[UIView new]; footer.translatesAutoresizingMaskIntoConstraints=NO;
  footer.backgroundColor=[UIColor colorWithRed:0.055 green:0.058 blue:0.068 alpha:0.98];
  self.launcherFooter=footer; [controller.view addSubview:footer];
  UIView *footerRule=[UIView new]; footerRule.translatesAutoresizingMaskIntoConstraints=NO;
  footerRule.backgroundColor=[UIColor colorWithWhite:0.21 alpha:1]; [footer addSubview:footerRule];
  self.launcherReadinessLabel=[self arLauncherLabel:@"CONFIGURE OS ARQUIVOS PARA JOGAR" size:9 weight:UIFontWeightBold color:muted lines:1];
  self.launcherReadinessLabel.font=[UIFont monospacedSystemFontOfSize:9 weight:UIFontWeightBold];
  [footer addSubview:self.launcherReadinessLabel]; [footer addSubview:self.nativeLaunchButton];
  [NSLayoutConstraint activateConstraints:@[
    [footer.leadingAnchor constraintEqualToAnchor:controller.view.leadingAnchor],
    [footer.trailingAnchor constraintEqualToAnchor:controller.view.trailingAnchor],
    [footer.bottomAnchor constraintEqualToAnchor:controller.view.bottomAnchor],
    [footerRule.topAnchor constraintEqualToAnchor:footer.topAnchor],
    [footerRule.leadingAnchor constraintEqualToAnchor:footer.leadingAnchor],
    [footerRule.trailingAnchor constraintEqualToAnchor:footer.trailingAnchor],
    [footerRule.heightAnchor constraintEqualToConstant:1],
    [self.launcherReadinessLabel.topAnchor constraintEqualToAnchor:footer.topAnchor constant:8],
    [self.launcherReadinessLabel.leadingAnchor constraintEqualToAnchor:footer.leadingAnchor constant:20],
    [self.launcherReadinessLabel.trailingAnchor constraintEqualToAnchor:footer.trailingAnchor constant:-20],
    [self.nativeLaunchButton.topAnchor constraintEqualToAnchor:self.launcherReadinessLabel.bottomAnchor constant:6],
    [self.nativeLaunchButton.leadingAnchor constraintEqualToAnchor:footer.leadingAnchor constant:16],
    [self.nativeLaunchButton.trailingAnchor constraintEqualToAnchor:footer.trailingAnchor constant:-16],
    [self.nativeLaunchButton.bottomAnchor constraintEqualToAnchor:controller.view.safeAreaLayoutGuide.bottomAnchor constant:-8]
  ]];
  game.contentInset=UIEdgeInsetsMake(0,0,112,0); game.scrollIndicatorInsets=game.contentInset;
  graphics.contentInset=UIEdgeInsetsMake(0,0,12,0);

  UIView *activity=[UIView new]; activity.translatesAutoresizingMaskIntoConstraints=NO;
  activity.backgroundColor=[UIColor colorWithWhite:0.075 alpha:1]; activity.layer.cornerRadius=13;
  UIStackView *activityRows=[UIStackView new]; activityRows.translatesAutoresizingMaskIntoConstraints=NO;
  activityRows.axis=UILayoutConstraintAxisVertical; activityRows.spacing=8;
  [activityRows addArrangedSubview:[self arLauncherLabel:@"SESSÃO / ATIVIDADE" size:10 weight:UIFontWeightBold color:gold lines:1]];
  self.status=[self arLauncherLabel:@"Aguardando instalação e GOWA.ELF" size:12 weight:UIFontWeightMedium color:[UIColor colorWithWhite:0.86 alpha:1] lines:3];
  self.nativeRunElapsedLabel=[self arLauncherLabel:@"TEMPO DESDE INICIAR  AINDA NÃO INICIADO" size:10 weight:UIFontWeightSemibold color:gold lines:1];
  self.nativeRunElapsedLabel.font=[UIFont monospacedSystemFontOfSize:10 weight:UIFontWeightSemibold];
  self.bootMetricsLabel=[self arLauncherLabel:@"PPU AOT · ainda não iniciado\ncellFs · sem chamadas guest medidas" size:10 weight:UIFontWeightRegular color:muted lines:7];
  self.bootMetricsLabel.font=[UIFont monospacedSystemFontOfSize:10 weight:UIFontWeightRegular];
  [activityRows addArrangedSubview:self.status];
  [activityRows addArrangedSubview:self.nativeRunElapsedLabel];
  [activityRows addArrangedSubview:self.bootMetricsLabel];
  [activity addSubview:activityRows];
  [NSLayoutConstraint activateConstraints:@[
    [activityRows.leadingAnchor constraintEqualToAnchor:activity.leadingAnchor constant:13],
    [activityRows.trailingAnchor constraintEqualToAnchor:activity.trailingAnchor constant:-13],
    [activityRows.topAnchor constraintEqualToAnchor:activity.topAnchor constant:12],
    [activityRows.bottomAnchor constraintEqualToAnchor:activity.bottomAnchor constant:-12]
  ]];
  [main addArrangedSubview:activity];
  self.ppuDiagnosticsButton=[self arLauncherButton:@"PROGRESSO REAL DA EXECUÇÃO" background:[UIColor colorWithWhite:0.12 alpha:1] action:@selector(showLauncherReport:)];
  [main addArrangedSubview:self.ppuDiagnosticsButton];
  self.ppuReportButton=self.ppuDiagnosticsButton; self.ppuAdvancedButton=self.ppuDiagnosticsButton;

  UIStackView *files=makeContent(graphics);
  [files addArrangedSubview:[self arLauncherLabel:@"ARQUIVOS DO JOGO" size:20 weight:UIFontWeightBold color:UIColor.whiteColor lines:1]];
  [files addArrangedSubview:[self arLauncherLabel:@"Selecione a instalação NPUA80918 e o ELF recompilado. O acesso fica guardado neste app." size:13 weight:UIFontWeightMedium color:muted lines:0]];
  UIView *installCard=[UIView new]; installCard.translatesAutoresizingMaskIntoConstraints=NO;
  installCard.backgroundColor=panel; installCard.layer.cornerRadius=15;
  UIStackView *installRows=[UIStackView new]; installRows.translatesAutoresizingMaskIntoConstraints=NO;
  installRows.axis=UILayoutConstraintAxisVertical; installRows.spacing=8;
  [installRows addArrangedSubview:[self arLauncherLabel:@"PASTA DO JOGO" size:10 weight:UIFontWeightBold color:gold lines:1]];
  self.settingsGameInstallLabel=[self arLauncherLabel:self.gameInstallLabel.text size:13 weight:UIFontWeightSemibold color:UIColor.whiteColor lines:2];
  [installRows addArrangedSubview:self.settingsGameInstallLabel];
  UIView *installSeparator=[UIView new]; installSeparator.backgroundColor=[UIColor colorWithWhite:0.22 alpha:1];
  [installSeparator.heightAnchor constraintEqualToConstant:1].active=YES;
  [installRows addArrangedSubview:installSeparator];
  [installRows addArrangedSubview:[self arLauncherLabel:@"EXECUTÁVEL" size:10 weight:UIFontWeightBold color:gold lines:1]];
  self.settingsElfStatusLabel=[self arLauncherLabel:self.elfStatusLabel.text size:13 weight:UIFontWeightSemibold color:UIColor.whiteColor lines:2];
  [installRows addArrangedSubview:self.settingsElfStatusLabel];
  [installCard addSubview:installRows];
  [NSLayoutConstraint activateConstraints:@[
    [installRows.leadingAnchor constraintEqualToAnchor:installCard.leadingAnchor constant:14],
    [installRows.trailingAnchor constraintEqualToAnchor:installCard.trailingAnchor constant:-14],
    [installRows.topAnchor constraintEqualToAnchor:installCard.topAnchor constant:13],
    [installRows.bottomAnchor constraintEqualToAnchor:installCard.bottomAnchor constant:-13]
  ]];
  [files addArrangedSubview:installCard];
  [files addArrangedSubview:[self arLauncherLabel:@"PASTA DA INSTALAÇÃO" size:10 weight:UIFontWeightBold color:gold lines:1]];
  [files addArrangedSubview:[self arLauncherButton:@"ESCOLHER PASTA NPUA80918" background:[UIColor colorWithRed:0.40 green:0.13 blue:0.10 alpha:1] action:@selector(importGameFolder:)]];
  [files addArrangedSubview:[self arLauncherButton:@"LOCALIZAR EM DOCUMENTOS" background:[UIColor colorWithWhite:0.15 alpha:1] action:@selector(importGameFolderFromDocuments:)]];
  [files addArrangedSubview:[self arLauncherLabel:@"EXECUTÁVEL RECOMPILADO" size:10 weight:UIFontWeightBold color:gold lines:1]];
  [files addArrangedSubview:[self arLauncherButton:@"IMPORTAR GOWA.ELF" background:[UIColor colorWithWhite:0.18 alpha:1] action:@selector(importM59ELF:)]];
  [files addArrangedSubview:[self arLauncherLabel:@"O QUE ESTA BUILD ACEITA" size:10 weight:UIFontWeightBold color:gold lines:1]];
  [files addArrangedSubview:[self arLauncherLabel:@"A inicialização nativa exige a pasta NPUA80918 e o ELF GOWA.ELF validado. O botão Iniciar só é liberado quando os dois estão prontos." size:12 weight:UIFontWeightMedium color:muted lines:0]];

  UIStackView *preferences=makeContent(settingsPage);
  [preferences addArrangedSubview:[self arLauncherLabel:@"VÍDEO E DESEMPENHO" size:20 weight:UIFontWeightBold color:UIColor.whiteColor lines:1]];
  [preferences addArrangedSubview:[self arLauncherLabel:@"Controles aplicados ao backend Metal e ao relógio de VBlank do guest." size:13 weight:UIFontWeightMedium color:muted lines:0]];
  [preferences addArrangedSubview:[self arLauncherLabel:@"RESOLUÇÃO DE APRESENTAÇÃO" size:10 weight:UIFontWeightBold color:gold lines:1]];
  UISegmentedControl *scaleControl=[[UISegmentedControl alloc] initWithItems:@[@"0,5×",@"0,75×",@"1×"]];
  scaleControl.selectedSegmentIndex=2;
  scaleControl.backgroundColor=panel;
  scaleControl.selectedSegmentTintColor=[UIColor colorWithRed:0.48 green:0.16 blue:0.11 alpha:1];
  [scaleControl setTitleTextAttributes:@{NSForegroundColorAttributeName:UIColor.whiteColor,
      NSFontAttributeName:[UIFont systemFontOfSize:12 weight:UIFontWeightSemibold]}
                       forState:UIControlStateNormal];
  [scaleControl addTarget:self action:@selector(videoSettingChanged:) forControlEvents:UIControlEventValueChanged];
  scaleControl.accessibilityLabel=@"Resolução da imagem apresentada pelo Metal";
  self.presentationScaleControl=scaleControl;
  [preferences addArrangedSubview:scaleControl];
  [preferences addArrangedSubview:[self arLauncherLabel:@"Reduz somente o drawable que vai para a tela. O tamanho interno dos alvos RSX continua definido pelo jogo." size:11 weight:UIFontWeightRegular color:muted lines:0]];
  [preferences addArrangedSubview:[self arLauncherLabel:@"CADÊNCIA DO VBLANK GUEST" size:10 weight:UIFontWeightBold color:gold lines:1]];
  UISegmentedControl *rateControl=[[UISegmentedControl alloc] initWithItems:@[@"30 Hz",@"60 Hz"]];
  rateControl.selectedSegmentIndex=1;
  rateControl.backgroundColor=panel;
  rateControl.selectedSegmentTintColor=[UIColor colorWithRed:0.48 green:0.16 blue:0.11 alpha:1];
  [rateControl setTitleTextAttributes:@{NSForegroundColorAttributeName:UIColor.whiteColor,
      NSFontAttributeName:[UIFont systemFontOfSize:12 weight:UIFontWeightSemibold]}
                       forState:UIControlStateNormal];
  [rateControl addTarget:self action:@selector(videoSettingChanged:) forControlEvents:UIControlEventValueChanged];
  rateControl.accessibilityLabel=@"Cadência de VBlank do guest em 30 ou 60 hertz";
  self.vblankRateControl=rateControl;
  [preferences addArrangedSubview:rateControl];
  [preferences addArrangedSubview:[self arLauncherLabel:@"Isso regula o ritmo das interrupções de vídeo PS3. Não força o jogo a produzir 30 ou 60 quadros; o relatório mede os FPS guest separadamente." size:11 weight:UIFontWeightRegular color:muted lines:0]];
  self.videoSettingsSummary=[self arLauncherLabel:@"Configurações atuais: Metal 1× · VBlank 60 Hz" size:11 weight:UIFontWeightSemibold color:UIColor.whiteColor lines:2];
  self.videoSettingsSummary.font=[UIFont monospacedSystemFontOfSize:11 weight:UIFontWeightSemibold];
  [preferences addArrangedSubview:self.videoSettingsSummary];
  [self refreshVideoSettingsSummary];

  UIStackView *reportRows=makeContent(report);
  [reportRows addArrangedSubview:[self arLauncherLabel:@"PROGRESSO DA EXECUÇÃO" size:20 weight:UIFontWeightBold color:UIColor.whiteColor lines:1]];
  [reportRows addArrangedSubview:[self arLauncherLabel:@"Este painel acompanha o guest PS3Recomp. Atividade do host, importação de arquivos e bancada sintética não contam como avanço do jogo." size:12 weight:UIFontWeightMedium color:muted lines:0]];
  self.launcherReportLabel=[self arLauncherLabel:@"Aguardando a primeira execução." size:10 weight:UIFontWeightRegular color:[UIColor colorWithWhite:0.88 alpha:1] lines:0];
  self.launcherReportLabel.font=[UIFont monospacedSystemFontOfSize:10 weight:UIFontWeightRegular];
  self.launcherReportLabel.numberOfLines=0;
  self.launcherReportLabel.lineBreakMode=NSLineBreakByWordWrapping;
  [reportRows addArrangedSubview:self.launcherReportLabel];
  [reportRows addArrangedSubview:[self arLauncherButton:@"COPIAR RELATÓRIO COMPLETO" background:[UIColor colorWithWhite:0.15 alpha:1] action:@selector(copyLauncherReport:)]];
  [reportRows addArrangedSubview:[self arLauncherButton:@"COMPARTILHAR / EXPORTAR TXT" background:[UIColor colorWithWhite:0.15 alpha:1] action:@selector(shareLauncherReport:)]];
  [reportRows addArrangedSubview:[self arLauncherButton:@"EXPORTAR BINÁRIOS SPU AUSENTES" background:[UIColor colorWithWhite:0.15 alpha:1] action:@selector(shareSpuMissCapture:)]];

  UIView *gameHUD=[UIView new]; gameHUD.translatesAutoresizingMaskIntoConstraints=NO;
  gameHUD.hidden=YES; gameHUD.backgroundColor=[panel colorWithAlphaComponent:0.92];
  gameHUD.layer.cornerRadius=13; gameHUD.layer.borderWidth=1;
  gameHUD.layer.borderColor=[gold colorWithAlphaComponent:0.45].CGColor;
  UIStackView *hudRow=[UIStackView new]; hudRow.translatesAutoresizingMaskIntoConstraints=NO;
  hudRow.axis=UILayoutConstraintAxisHorizontal; hudRow.alignment=UIStackViewAlignmentCenter; hudRow.spacing=10;
  UIStackView *hudCopy=[UIStackView new]; hudCopy.axis=UILayoutConstraintAxisVertical; hudCopy.spacing=3;
  [hudCopy addArrangedSubview:[self arLauncherLabel:@"ASCENSION · RSX NATIVO" size:10 weight:UIFontWeightBold color:gold lines:1]];
  self.nativeGameHUDLabel=[self arLauncherLabel:@"Aguardando métricas do guest" size:10 weight:UIFontWeightMedium color:UIColor.whiteColor lines:2];
  self.nativeGameHUDLabel.font=[UIFont monospacedSystemFontOfSize:10 weight:UIFontWeightMedium];
  [hudCopy addArrangedSubview:self.nativeGameHUDLabel];
  [hudRow addArrangedSubview:hudCopy];
  UIButton *hudReport=[self arLauncherButton:@"RELATÓRIO" background:[UIColor colorWithRed:0.43 green:0.13 blue:0.10 alpha:1] action:@selector(openUnifiedPpuMenu:)];
  hudReport.titleLabel.font=[UIFont systemFontOfSize:10 weight:UIFontWeightBold];
  [hudReport.heightAnchor constraintEqualToConstant:38].active=YES;
  [hudRow addArrangedSubview:hudReport];
  [gameHUD addSubview:hudRow]; [controller.view addSubview:gameHUD]; self.nativeGameHUD=gameHUD;
  [NSLayoutConstraint activateConstraints:@[
    [gameHUD.topAnchor constraintEqualToAnchor:controller.view.safeAreaLayoutGuide.topAnchor constant:8],
    [gameHUD.leadingAnchor constraintEqualToAnchor:controller.view.leadingAnchor constant:12],
    [gameHUD.trailingAnchor constraintEqualToAnchor:controller.view.trailingAnchor constant:-12],
    [hudRow.leadingAnchor constraintEqualToAnchor:gameHUD.leadingAnchor constant:10],
    [hudRow.trailingAnchor constraintEqualToAnchor:gameHUD.trailingAnchor constant:-10],
    [hudRow.topAnchor constraintEqualToAnchor:gameHUD.topAnchor constant:8],
    [hudRow.bottomAnchor constraintEqualToAnchor:gameHUD.bottomAnchor constant:-8]
  ]];
  UIView *controls=[UIView new]; controls.translatesAutoresizingMaskIntoConstraints=NO;
  controls.hidden=YES; controls.multipleTouchEnabled=YES; self.nativeGameControls=controls;
  [controller.view addSubview:controls];
  [NSLayoutConstraint activateConstraints:@[
    [controls.leadingAnchor constraintEqualToAnchor:controller.view.leadingAnchor constant:8],
    [controls.trailingAnchor constraintEqualToAnchor:controller.view.trailingAnchor constant:-8],
    [controls.bottomAnchor constraintEqualToAnchor:controller.view.safeAreaLayoutGuide.bottomAnchor constant:-8],
    [controls.heightAnchor constraintEqualToConstant:132]
  ]];
  void (^placePadButton)(NSString*,uint16_t,NSLayoutXAxisAnchor*,CGFloat,NSLayoutYAxisAnchor*,CGFloat,CGFloat)=
    ^(NSString *title,uint16_t bit,NSLayoutXAxisAnchor *x,CGFloat dx,NSLayoutYAxisAnchor *y,CGFloat dy,CGFloat size){
      UIButton *button=[self nativePadButton:title bit:bit];
      [controls addSubview:button];
      [NSLayoutConstraint activateConstraints:@[
        [button.centerXAnchor constraintEqualToAnchor:x constant:dx],
        [button.centerYAnchor constraintEqualToAnchor:y constant:dy],
        [button.widthAnchor constraintEqualToConstant:size],
        [button.heightAnchor constraintEqualToConstant:size]
      ]];
    };
  placePadButton(@"▲",ARPadUp,controls.leadingAnchor,60,controls.topAnchor,22,44);
  placePadButton(@"◀",ARPadLeft,controls.leadingAnchor,16,controls.topAnchor,66,44);
  placePadButton(@"▼",ARPadDown,controls.leadingAnchor,60,controls.topAnchor,66,44);
  placePadButton(@"▶",ARPadRight,controls.leadingAnchor,104,controls.topAnchor,66,44);
  placePadButton(@"L1",ARPadL1,controls.leadingAnchor,22,controls.bottomAnchor,-22,40);
  placePadButton(@"L2",ARPadL2,controls.leadingAnchor,68,controls.bottomAnchor,-22,40);
  placePadButton(@"△",ARPadTriangle,controls.trailingAnchor,-60,controls.topAnchor,22,44);
  placePadButton(@"□",ARPadSquare,controls.trailingAnchor,-104,controls.topAnchor,66,44);
  placePadButton(@"✕",ARPadCross,controls.trailingAnchor,-60,controls.topAnchor,66,44);
  placePadButton(@"○",ARPadCircle,controls.trailingAnchor,-16,controls.topAnchor,66,44);
  placePadButton(@"R1",ARPadR1,controls.trailingAnchor,-22,controls.bottomAnchor,-22,40);
  placePadButton(@"R2",ARPadR2,controls.trailingAnchor,-68,controls.bottomAnchor,-22,40);
  placePadButton(@"SELECT",ARPadSelect,controls.centerXAnchor,-26,controls.bottomAnchor,-22,40);
  placePadButton(@"START",ARPadStart,controls.centerXAnchor,26,controls.bottomAnchor,-22,40);

  [self.window makeKeyAndVisible]; self.ready=YES;
  self.status.text=@"Pronto. Selecione a pasta do jogo e importe o ELF para habilitar Iniciar.";
  dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY,0),^{
    NSError *restoreError=nil;
    NSDictionary *prior=ARGameFolderRestore(&restoreError);
    NSURL *support=[[NSFileManager.defaultManager URLsForDirectory:NSApplicationSupportDirectory
                                              inDomains:NSUserDomainMask] firstObject];
    NSURL *dir=[[support URLByAppendingPathComponent:@"AscensionRecomp" isDirectory:YES]
                URLByAppendingPathComponent:@"Import" isDirectory:YES];
    NSData *stored=[NSData dataWithContentsOfURL:[dir URLByAppendingPathComponent:@"GOWA.ELF"]
                                          options:NSDataReadingMappedIfSafe error:NULL];
    NSData *coverData=ARGameManifestHasTitleUsrdir(prior)?[self gameCoverDataFromManifest:prior]:nil;
    dispatch_async(dispatch_get_main_queue(),^{
      if(ARGameManifestHasTitleUsrdir(prior)){
        self.hasGameInstallation=YES;
        self.folderReport=[NSString stringWithFormat:@"Pasta restaurada · %@ arquivos (HOST)",prior[@"file_count"]?:@"0"];
        self.gameInstallLabel.text=[NSString stringWithFormat:@"NPUA80918 · %@ arquivos (HOST)",prior[@"file_count"]?:@"?"];
      }else if(prior){
        self.gameInstallLabel.text=@"A pasta salva não é NPUA80918 com USRDIR";
      }
      UIImage *coverImage=coverData?[UIImage imageWithData:coverData]:nil;
      self.gameCoverView.image=coverImage;
      self.gameCoverView.hidden=(coverImage==nil);
      if(ARIsValidatedAscensionELF(stored)){
        self.selectedElfData=stored; self.selectedElfPath=[dir URLByAppendingPathComponent:@"GOWA.ELF"].path;
        self.elfStatusLabel.text=@"GOWA.ELF · SHA-256 validado neste dispositivo";
      }
      [self refreshNativeLaunchAvailability];
    });
  });
  return YES;
}

/* Use only the user's small ICON0.PNG from the authorized game folder. The
 * image stays in memory and is never copied into the app or the IPA. */
- (NSData*)gameCoverDataFromManifest:(NSDictionary*)manifest {
  NSArray *files=[manifest[@"files"] isKindOfClass:NSArray.class]?manifest[@"files"]:@[];
  NSString *selectedPath=nil; NSUInteger selectedSize=0;
  for(NSDictionary *entry in files){
    NSString *path=[entry[@"path"] isKindOfClass:NSString.class]?entry[@"path"]:@"";
    NSNumber *size=[entry[@"bytes"] isKindOfClass:NSNumber.class]?entry[@"bytes"]:nil;
    if([path.lastPathComponent caseInsensitiveCompare:@"ICON0.PNG"]==NSOrderedSame &&
       size.unsignedIntegerValue>0 && size.unsignedIntegerValue<=65536u){
      selectedPath=path; selectedSize=size.unsignedIntegerValue;
      if([path caseInsensitiveCompare:@"ICON0.PNG"]==NSOrderedSame)break;
    }
  }
  if(!selectedPath)return nil;
  NSError *error=nil;
  NSData *data=ARGameFolderReadPrefix(selectedPath,selectedSize,&error);
  return data.length==selectedSize?data:nil;
}

- (void)refreshNativeLaunchAvailability {
  self.settingsGameInstallLabel.text=self.gameInstallLabel.text;
  self.settingsElfStatusLabel.text=self.elfStatusLabel.text;
  self.gameInstallLabel.textColor=self.hasGameInstallation?UIColor.systemGreenColor:UIColor.whiteColor;
  self.elfStatusLabel.textColor=self.selectedElfData.length?UIColor.systemGreenColor:UIColor.whiteColor;
  self.settingsGameInstallLabel.textColor=self.gameInstallLabel.textColor;
  self.settingsElfStatusLabel.textColor=self.elfStatusLabel.textColor;
  BOOL enabled=self.ready && !self.shaderBusy;
  BOOL launchReady=self.hasGameInstallation && self.selectedElfData.length>0;
  self.nativeLaunchButton.enabled=enabled; self.nativeLaunchButton.alpha=enabled?1.0:0.52;
  if(self.shaderBusy){
    [self.nativeLaunchButton setTitle:@"EXECUÇÃO EM ANDAMENTO" forState:UIControlStateNormal];
    self.launcherReadinessLabel.text=@"AOT EM EXECUÇÃO · AGUARDANDO ATIVIDADE GUEST";
    self.launcherReadinessLabel.textColor=[UIColor colorWithRed:0.95 green:0.69 blue:0.38 alpha:1];
  }else if(launchReady){
    [self.nativeLaunchButton setTitle:@"▶   INICIAR ASCENSION" forState:UIControlStateNormal];
    self.launcherReadinessLabel.text=@"HOST VALIDADO · VFS GUEST MONTA NO BOOT DO RUNTIME";
    self.launcherReadinessLabel.textColor=[UIColor colorWithRed:0.95 green:0.69 blue:0.38 alpha:1];
  }else if(!self.hasGameInstallation && !self.selectedElfData.length){
    [self.nativeLaunchButton setTitle:@"CONFIGURAR ARQUIVOS" forState:UIControlStateNormal];
    self.launcherReadinessLabel.text=@"PRECISA DA PASTA NPUA80918 E DO GOWA.ELF";
    self.launcherReadinessLabel.textColor=[UIColor colorWithRed:0.95 green:0.69 blue:0.38 alpha:1];
  }else if(!self.hasGameInstallation){
    [self.nativeLaunchButton setTitle:@"SELECIONAR PASTA DO JOGO" forState:UIControlStateNormal];
    self.launcherReadinessLabel.text=@"GOWA.ELF VALIDADO  ·  FALTA A PASTA NPUA80918";
    self.launcherReadinessLabel.textColor=[UIColor colorWithRed:0.95 green:0.69 blue:0.38 alpha:1];
  }else{
    [self.nativeLaunchButton setTitle:@"IMPORTAR GOWA.ELF" forState:UIControlStateNormal];
    self.launcherReadinessLabel.text=@"PASTA HOST PRONTA · VFS GUEST AGUARDA O BOOT";
    self.launcherReadinessLabel.textColor=[UIColor colorWithRed:0.95 green:0.69 blue:0.38 alpha:1];
  }
}
- (void)acceptELFAtURL:(NSURL*)url {
  if(!url || self.shaderBusy)return;
  self.status.text=@"Validando GOWA.ELF; a importação não executa checkpoints legados.";
  dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{
    BOOL scoped=[url startAccessingSecurityScopedResource];
    NSError *error=nil;
    NSNumber *size=[[[NSFileManager defaultManager] attributesOfItemAtPath:url.path error:&error] objectForKey:NSFileSize];
    NSData *data=nil;
    if(!error && size && size.unsignedLongLongValue<=32u*1024u*1024u)
      data=[NSData dataWithContentsOfURL:url options:NSDataReadingMappedIfSafe error:&error];
    BOOL valid=ARIsValidatedAscensionELF(data);
    NSURL *destination=nil;
    if(valid){
      NSURL *support=[[NSFileManager.defaultManager URLsForDirectory:NSApplicationSupportDirectory
                                                inDomains:NSUserDomainMask] firstObject];
      NSURL *directory=[[support URLByAppendingPathComponent:@"AscensionRecomp" isDirectory:YES]
                        URLByAppendingPathComponent:@"Import" isDirectory:YES];
      if(![NSFileManager.defaultManager createDirectoryAtURL:directory
                           withIntermediateDirectories:YES attributes:nil error:&error]) valid=NO;
      else {
        destination=[directory URLByAppendingPathComponent:@"GOWA.ELF"];
        if(![data writeToURL:destination options:NSDataWritingAtomic error:&error]) valid=NO;
        else [destination setResourceValue:@YES forKey:NSURLIsExcludedFromBackupKey error:NULL];
      }
    }
    if(scoped)[url stopAccessingSecurityScopedResource];
    dispatch_async(dispatch_get_main_queue(),^{
      if(valid){
        self.selectedElfData=data; self.selectedElfPath=destination.path;
        self.elfStatusLabel.text=@"GOWA.ELF · SHA-256 e entry 0x10410 validados";
        self.ppuReport=[NSString stringWithFormat:
          @"ELF validado e salvo somente no iPhone.\n"
           "SHA-256 confirmado · %lu bytes · entry 0x00010410 · TOC 0x0083F2B0.\n"
           "Importar não iniciou o jogo.", (unsigned long)data.length];
        self.status.text=@"ELF pronto. Selecione a pasta do jogo e toque Iniciar.";
      }else{
        self.elfStatusLabel.text=@"ELF inválido ou inacessível";
        self.status.text=[NSString stringWithFormat:@"Importação recusada: %@",
          error.localizedDescription?:@"o arquivo não corresponde ao EBOOT validado de NPUA80918"];
      }
      [self refreshNativeLaunchAvailability];
    });
  });
}
- (void)updateNativeRunMetrics {
  uint64_t m772[40]={0}; ar_m772_runtime_attest(m772);
  uint32_t state=ar_m772_entry_state();
  NSString *elapsed=ARFormatRunElapsed(self.nativeRunStartedAt,self.nativeRunEndedAt);
  self.nativeRunElapsedLabel.text=[NSString stringWithFormat:@"TEMPO DESDE INICIAR  %@",elapsed];
  NSString *phase=state==0?@"PREPARANDO runtime / VFS":
                  state==1?@"ENTRY AOT EM EXECUÇÃO":
                  state==2?@"ENTRY RETORNOU":@"FALHA AO VINCULAR ENTRY";
  const uint64_t frames=ARRSXLoad(&ARNativeRSXPresentedFrames);
  const uint64_t draws=ARRSXLoad(&ARNativeRSXLastGuestDraws);
  self.bootMetricsLabel.text=[NSString stringWithFormat:
    @"%@\nGuest AOT: %llu chamadas · entry starts: %llu · última entrada: 0x%08llX\n"
     "Runtime PS3Recomp: %@ · raiz VFS: %@\n"
     "cellFs guest: %llu opens · %llu reads · %llu bytes\n"
     "RSX guest: %llu draws · %llu flips apresentados",
     phase,(unsigned long long)m772[5],(unsigned long long)m772[13],
     (unsigned long long)m772[6],m772[4]?@"PRONTO":@"AINDA NÃO INICIALIZADO",
     m772[8]?@"CONFIGURADA":@"NÃO CONFIGURADA",
     (unsigned long long)m772[10],(unsigned long long)m772[11],
     (unsigned long long)m772[12],(unsigned long long)draws,
     (unsigned long long)frames];
  self.nativeGameHUDLabel.text=[NSString stringWithFormat:
    @"Tempo %@\nGuest AOT %@ · FS %@ bytes\nGuest RSX %@ draws · %@ flips",
    elapsed,@(m772[5]),@(m772[12]),@(draws),@(frames)];
  if(state==1)self.status.text=[NSString stringWithFormat:
    @"PS3Recomp AOT ativo · funções %@ · HLE %@ · LV2 %@ · FS guest %@ bytes · frames guest %@.",
    @(m772[5]),@(m772[26]),@(m772[29]),@(m772[12]),@(frames)];
  if(state==1 && frames>0 && !self.gameDisplayActive)[self showNativeGameFrame];
}
- (void)runNativeRSXPump {
  CFTimeInterval nextVBlank=CACurrentMediaTime();
  while(__atomic_load_n(&ARNativeRSXPumpActive,__ATOMIC_ACQUIRE)){
    uint64_t live[40]={0}; ar_m772_runtime_attest(live);
    if(!live[4] || !__atomic_load_n(&ARNativeRSXBackendReady,__ATOMIC_ACQUIRE)){
      [NSThread sleepForTimeInterval:0.002];
      continue;
    }
    const CFTimeInterval now=CACurrentMediaTime();
    if(now>=nextVBlank){
      uint32_t hz=__atomic_load_n(&ARNativeRSXVBlankHz,__ATOMIC_RELAXED);
      if(hz!=30 && hz!=60)hz=60;
      const CFTimeInterval vblankInterval=1.0/(double)hz;
      cellGcmTickVBlank();
      cellGcmTickFlip();
      __atomic_add_fetch(&ARNativeRSXVBlanks,UINT64_C(1),__ATOMIC_RELAXED);
      nextVBlank+=vblankInterval;
      if(now-nextVBlank>0.100)nextVBlank=now+vblankInterval;
    }
    /* Match PS3Recomp's desktop frame clock: advance guest fences by draining
     * the real GCM FIFO, then present only after its pending flip is complete. */
    cellGcm_rsx_process_fifo();
    __atomic_add_fetch(&ARNativeRSXFIFODrains,UINT64_C(1),__ATOMIC_RELAXED);
    if(cellGcm_take_flip_pending_synced()){
      rsx_metal_backend_present();
      __atomic_add_fetch(&ARNativeRSXPresentedFrames,UINT64_C(1),__ATOMIC_RELAXED);
    }
    __atomic_store_n(&ARNativeRSXLastGuestDraws,
                     (uint64_t)rsx_metal_backend_guest_draws(),__ATOMIC_RELAXED);
    [NSThread sleepForTimeInterval:0.004];
  }
}
- (void)showNativeGameFrame {
  if(self.gameDisplayActive)return;
  self.gameDisplayActive=YES;
  [self requestGameOrientation:UIInterfaceOrientationMaskLandscape];
  self.launcherBrand.hidden=YES; self.launcherTabs.hidden=YES;
  self.launcherFooter.hidden=YES; self.gameList.hidden=YES;
  self.graphicsList.hidden=YES; self.settingsList.hidden=YES; self.reportList.hidden=YES;
  self.metalView.hidden=NO; self.nativeGameHUD.hidden=NO; self.nativeGameControls.hidden=NO;
  UIView *root=self.window.rootViewController.view;
  [root bringSubviewToFront:self.metalView];
  [root bringSubviewToFront:self.nativeGameHUD];
  [root bringSubviewToFront:self.nativeGameControls];
}
- (void)showLauncherAfterNativeRun {
  self.gameDisplayActive=NO;
  [self requestGameOrientation:UIInterfaceOrientationMaskPortrait];
  self.nativeGameHUD.hidden=YES;
  self.nativeGameControls.hidden=YES;
  self.nativePadButtons=0;
  cellPad_set_host_state(0,128,128,128,128,0,0);
  self.launcherBrand.hidden=NO; self.launcherTabs.hidden=NO;
  [self arSwitchTab:self.launcherTabs];
}
- (void)startNativeGame:(UIButton*)sender {
  (void)sender;
  if(self.shaderBusy)return;
  const CFTimeInterval tappedAt=CACurrentMediaTime();
  if(!self.hasGameInstallation){
    self.gameInstallLabel.text=@"Selecione NPUA80918 com a pasta USRDIR";
    self.status.text=@"Escolha uma pasta válida do jogo antes de iniciar.";
    [self refreshNativeLaunchAvailability];
    self.launcherTabs.selectedSegmentIndex=1; [self arSwitchTab:self.launcherTabs];
    return;
  }
  if(!self.selectedElfData.length){
    self.status.text=@"Importe e valide o GOWA.ELF antes de iniciar.";
    self.launcherTabs.selectedSegmentIndex=1; [self arSwitchTab:self.launcherTabs];
    return;
  }
  /* The bookmark and title manifest were checked when the user imported the
   * folder or during async startup restore. Do not reload a potentially large
   * JSON manifest on the UI thread. The guest session revalidates its security
   * scope in the background immediately before runtime initialization. */
  self.shaderBusy=YES;
  const BOOL labWasReady=self.graphicsReady;
  const BOOL layerAttached=labWasReady || [self.metalView bindToPS3MetalBackend];
  self.graphicsReady=NO;
  self.graphicsDrawButton.enabled=NO; self.graphicsCacheButton.enabled=NO;
  self.metalView.hidden=YES; self.nativeGameHUD.hidden=YES; self.gameDisplayActive=NO;
  ARRSXResetMetrics();
  __atomic_store_n(&ARNativeRSXBackendReady,0u,__ATOMIC_RELEASE);
  __atomic_store_n(&ARNativeRSXPumpActive,0u,__ATOMIC_RELEASE);
  self.nativeRunStartedAt=tappedAt;
  self.nativeRunEndedAt=0.0;
  self.ppuReport=nil; self.m750Run=nil; self.ppuProgress=@"Montando PS3Recomp e VFS guest.";
  /* These HLE switches are read once by PS3Recomp. Set them before the
   * runtime starts so Ascension uses the game-proven LFQueue and Edge paths. */
  setenv("PS3_EDGE_ZLIB_HLE","1",1);
  setenv("PS3_LFQUEUE_SDK_LAYOUT","1",1);
  /* Ascension's WWS policy keeps readyCount as a level and chooses by SPU. */
  setenv("SPURS_READY_LEVEL","1",1);
  /* Ascension patches its RSX FIFO park after SPU jobs build a frame. Use the
   * same bounded 2 s wait as the PC port; 50 ms can skip commands still being
   * written by the recompiled SPU jobs. */
  setenv("GCM_PARK_WAIT_MS","2000",1);
  /* Keep the RSX behind the frame label that Ascension's post-process jobs
   * release, instead of running past work the SPUs have not finished. */
  setenv("GCM_SEMA_ACQUIRE","1",1);
  /* Save exact unlifted WWS job binaries in Files so they can be lifted into
   * native ARM64 code. The files remain in the app's Documents sandbox. */
  NSURL *documents=[[[NSFileManager defaultManager]
      URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask] firstObject];
  NSString *captureUUID=[[[NSUUID UUID] UUIDString]
      stringByReplacingOccurrencesOfString:@"-" withString:@""];
  NSString *captureName=[NSString stringWithFormat:@"AscensionSPU-%@",captureUUID];
  self.latestSpuCaptureURL=[documents URLByAppendingPathComponent:captureName isDirectory:YES];
  NSError *captureError=nil;
  if(self.latestSpuCaptureURL)
    [[NSFileManager defaultManager] createDirectoryAtURL:self.latestSpuCaptureURL
                             withIntermediateDirectories:YES attributes:nil error:&captureError];
  if(self.latestSpuCaptureURL && !captureError)
    setenv("SPU_DUMP_MISS",self.latestSpuCaptureURL.path.UTF8String,1);
  else
    unsetenv("SPU_DUMP_MISS");
  spu_workload_reset_ascension_job_metrics();
  cellSpursResetAscensionMetrics();
  ar_m772_runtime_begin();
  [self arSetStatus:@"Preparando VM, PPU/SPU recompilados e acesso guest ao jogo…"];
  [self refreshNativeLaunchAvailability];
  self.nativeRunRefreshTimer=[NSTimer scheduledTimerWithTimeInterval:0.25
      target:self selector:@selector(nativeRunRefreshTick:) userInfo:nil repeats:YES];
  [[NSRunLoop mainRunLoop] addTimer:self.nativeRunRefreshTimer forMode:NSRunLoopCommonModes];
  NSData *elf=[self.selectedElfData copy];
  /* GoW2's iOS host gives the statically recompiled guest its own 64 MiB
   * native stack. The full PS3Recomp C-AOT entry can make deep native calls;
   * GCD's default worker stack is too small to treat as a safe game stack. */
  NSThread *worker=[[NSThread alloc] initWithBlock:^{
    unsigned int native[16]={0};
    int backendRC=-1;
    if(labWasReady){
      rsx_metal_backend_shutdown();
      ar_probe_vm_shutdown();
    }
    if(layerAttached)
      backendRC=rsx_metal_backend_init(1280,720,"God of War: Ascension");
    __atomic_store_n(&ARNativeRSXBackendReady,backendRC==0?1u:0u,__ATOMIC_RELEASE);
    int hostRC=layerAttached?(backendRC==0?0:-75):-74;
    if(hostRC==0){
      ARRSXResetMetrics();
      __atomic_store_n(&ARNativeRSXPumpActive,1u,__ATOMIC_RELEASE);
      NSThread *pump=[[NSThread alloc] initWithTarget:self
          selector:@selector(runNativeRSXPump) object:nil];
      pump.name=@"Ascension RSX GCM FIFO";
      pump.qualityOfService=NSQualityOfServiceUserInteractive;
      pump.stackSize=(NSUInteger)8u*1024u*1024u;
      self.nativeRSXPumpThread=pump;
      [pump start];
      hostRC=ar_m70_native_runtime_probe(elf.bytes,elf.length,0u,native);
      __atomic_store_n(&ARNativeRSXPumpActive,0u,__ATOMIC_RELEASE);
      const CFTimeInterval drainDeadline=CACurrentMediaTime()+1.0;
      while(!pump.finished && CACurrentMediaTime()<drainDeadline)
        [NSThread sleepForTimeInterval:0.002];
      if(pump.finished){
        self.nativeRSXPumpThread=nil;
        rsx_metal_backend_shutdown();
        __atomic_store_n(&ARNativeRSXBackendReady,0u,__ATOMIC_RELEASE);
      }
    }
    const CFTimeInterval runEndedAt=CACurrentMediaTime();
    const uint64_t vblanks=ARRSXLoad(&ARNativeRSXVBlanks);
    const uint64_t drains=ARRSXLoad(&ARNativeRSXFIFODrains);
    const uint64_t frames=ARRSXLoad(&ARNativeRSXPresentedFrames);
    const uint64_t draws=ARRSXLoad(&ARNativeRSXLastGuestDraws);
    ar_vm_reservation_status vmReservation={0};
    ar_bridge_vm_reservation_status(&vmReservation);
    uint64_t m772[40]={0}; ar_m772_runtime_attest(m772);
    uint32_t state=ar_m772_entry_state();
    NSDictionary *result=@{
      @"host_rc":@(hostRC), @"rc":@((int32_t)native[6]), @"entry":@(native[1]),
      @"toc":@(native[2]), @"vm_capacity":@(native[4]), @"loaded_bytes":@(native[13]),
      @"aot":@(m772[0]), @"aot_calls":@(m772[5]),
      @"entry_starts":@(m772[13]), @"unique":@0,
      @"fallback":@0, @"limit":@0, @"stop":@(native[7]), @"opcode":@(native[14]),
      @"last_aot":@(m772[6]), @"fs_open_calls":@(m772[9]), @"fs_opens":@(m772[10]),
      @"fs_read_calls":@(m772[11]), @"fs_reads":@(m772[11]), @"fs_bytes":@(m772[12]),
      @"last_aot_lr":@(m772[14]), @"last_aot_sp":@(m772[15]),
      @"last_aot_r3":@(m772[16]), @"last_aot_r4":@(m772[17]),
      @"last_aot_r5":@(m772[18]), @"last_aot_r6":@(m772[19]),
      @"last_aot_r7":@(m772[20]), @"last_aot_r8":@(m772[21]),
      @"last_aot_r9":@(m772[22]), @"last_aot_r10":@(m772[23]),
      @"last_hle_nid":@(m772[24]), @"last_hle_lr":@(m772[25]),
      @"hle_calls":@(m772[26]), @"last_syscall":@(m772[27]),
      @"last_syscall_lr":@(m772[28]), @"syscall_calls":@(m772[29]),
      @"hotloop_count":@(m772[30]), @"hotloop_pc":@(m772[31]),
      @"hotloop_r3":@(m772[32]), @"hotloop_r4":@(m772[33]),
      @"hotloop_r5":@(m772[34]), @"hotloop_r8":@(m772[35]),
      @"hotloop_r9":@(m772[36]), @"unresolved_hle_count":@(m772[37]),
      @"unresolved_hle_nid":@(m772[38]), @"unresolved_hle_lr":@(m772[39]),
      @"rsx_backend_rc":@(backendRC), @"rsx_vblank_ticks":@(vblanks),
      @"rsx_fifo_drains":@(drains), @"rsx_guest_frames":@(frames),
      @"rsx_guest_draws":@(draws),
      @"entry_state":@(state), @"spu_fingerprints_registered":@(m772[3]),
      @"runtime_initialized":@(m772[4]), @"when":[[NSDate date] description],
      @"vm_attempted":@(vmReservation.attempted),
      @"vm_reservation_kind":@(vmReservation.reservation_kind),
      @"vm_mmap_attempts":@(vmReservation.mmap_attempts),
      @"vm_failure_stage":@(vmReservation.failure_stage),
      @"vm_failure_errno":@(vmReservation.failure_errno),
      @"vm_mach_attempts":@(vmReservation.mach_attempts),
      @"vm_last_mach_kern_return":@(vmReservation.last_mach_kern_return),
      @"vm_reservation_base":@(vmReservation.reservation_base)
    };
    dispatch_async(dispatch_get_main_queue(),^{
      self.nativeRunEndedAt=runEndedAt;
      self.nativeRunThread=nil;
      [self.nativeRunRefreshTimer invalidate]; self.nativeRunRefreshTimer=nil;
      self.shaderBusy=NO; self.m750Run=result;
      [self showLauncherAfterNativeRun];
      BOOL returned=[result[@"entry_state"] unsignedIntValue]==2u;
      int runHostRC=[result[@"host_rc"] intValue];
      uint32_t runEntryState=[result[@"entry_state"] unsignedIntValue];
      NSString *status=nil;
      if(runHostRC==-72)
        status=@"Acesso à pasta do jogo expirou ou foi revogado. Selecione NPUA80918 novamente no app Arquivos.";
      else if(runHostRC==-73)
        status=@"Falha ao inicializar PS3Recomp/VFS. Abra o relatório para ver host_rc e estado do runtime.";
      else if(runHostRC==-74)
        status=@"Não foi possível associar o CAMetalLayer do launcher ao renderer do jogo.";
      else if(runHostRC==-75)
        status=[NSString stringWithFormat:@"O renderer Metal do jogo não inicializou (rc=%d). Abra o relatório técnico.",[result[@"rsx_backend_rc"] intValue]];
      else if(runHostRC==-7){
        uint32_t vmStage=[result[@"vm_failure_stage"] unsignedIntValue];
        int vmErrno=[result[@"vm_failure_errno"] intValue];
        status=[NSString stringWithFormat:
          @"A VM guest falhou antes de carregar o ELF; por isso o VFS guest ainda não foi montado. %@ · último Mach kr=%@ · errno=%d · Mach tentativas=%@ · mmap tentativas=%@. Veja o relatório.",
          ARVMReservationStageName(vmStage),result[@"vm_last_mach_kern_return"],vmErrno,
          result[@"vm_mach_attempts"],result[@"vm_mmap_attempts"]];
      }
      else if(runHostRC!=0)
        status=[NSString stringWithFormat:@"Loader/host encerrou · host_rc=%d · guest_rc=%@.",runHostRC,result[@"rc"]];
      else if(runEntryState==3u)
        status=[NSString stringWithFormat:@"A função de entrada 0x%08X não foi vinculada à tabela AOT. guest_rc=%@.",
          [result[@"entry"] unsignedIntValue],result[@"rc"]];
      else if(returned)
        status=@"A função AOT de entrada retornou. A sessão guest terminou; nenhum quadro do jogo foi apresentado.";
      else
        status=[NSString stringWithFormat:@"Sessão encerrada · entry_state=%@ · host_rc=%@ · guest_rc=%@.",
          result[@"entry_state"],result[@"host_rc"],result[@"rc"]];
      if([result[@"fs_bytes"] unsignedLongLongValue]>0)
        status=[status stringByAppendingFormat:@" Leitura guest comprovada: %@ bytes.",result[@"fs_bytes"]];
      self.status.text=status; self.ppuProgress=status;
      self.ppuReport=[self arUnifiedPpuText];
      [self updateNativeRunMetrics]; [self updateLauncherReport];
      [self refreshNativeLaunchAvailability];
    });
  }];
  worker.name=@"Ascension PS3Recomp guest";
  worker.qualityOfService=NSQualityOfServiceUserInitiated;
  worker.stackSize=(NSUInteger)64u*1024u*1024u;
  self.nativeRunThread=worker;
  [worker start];
}
- (void)nativeRunRefreshTick:(NSTimer*)timer {
  (void)timer; [self updateNativeRunMetrics];
}
- (void)initializeGraphicsLab:(UIButton*)sender {
  (void)sender;
  if(self.graphicsReady){self.metalView.hidden=NO;return;}
  self.status.text=@"Inicializando bancada sintética RSX/Metal. Isso não inicia Ascension.";
  BOOL attached=[self.metalView bindToPS3MetalBackend];
  dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{
    int memory=attached?ar_probe_vm_init():-1;
    int backend=memory==0?rsx_metal_backend_init(960,540,"AscensionRecomp RSX Lab"):-1;
    dispatch_async(dispatch_get_main_queue(),^{
      self.graphicsReady=(backend==0); self.metalView.hidden=!self.graphicsReady;
      self.graphicsDrawButton.enabled=self.graphicsReady; self.graphicsCacheButton.enabled=self.graphicsReady;
      self.status.text=self.graphicsReady?
        @"Laboratório sintético pronto. A superfície RSX/Metal não é gameplay.":
        [NSString stringWithFormat:@"Bancada RSX/Metal falhou: VM=%d · backend=%d",memory,backend];
    });
  });
}

- (void)refreshVideoSettingsSummary {
  NSUserDefaults *defaults=NSUserDefaults.standardUserDefaults;
  id savedScale=[defaults objectForKey:@"AscensionMetalOutputScale"];
  double scale=savedScale?[defaults doubleForKey:@"AscensionMetalOutputScale"]:1.0;
  if(fabs(scale-0.5)<0.01)self.presentationScaleControl.selectedSegmentIndex=0;
  else if(fabs(scale-0.75)<0.01)self.presentationScaleControl.selectedSegmentIndex=1;
  else {scale=1.0;self.presentationScaleControl.selectedSegmentIndex=2;}
  self.metalView.outputScale=(CGFloat)scale;

  NSInteger hz=[defaults integerForKey:@"AscensionGuestVBlankHz"];
  if(hz!=30 && hz!=60)hz=60;
  self.vblankRateControl.selectedSegmentIndex=(hz==30)?0:1;
  __atomic_store_n(&ARNativeRSXVBlankHz,(uint32_t)hz,__ATOMIC_RELEASE);
  self.videoSettingsSummary.text=[NSString stringWithFormat:
    @"Configurações atuais: Metal %.2g× · VBlank %ld Hz",scale,(long)hz];
}
- (void)videoSettingChanged:(UISegmentedControl*)sender {
  NSUserDefaults *defaults=NSUserDefaults.standardUserDefaults;
  if(sender==self.presentationScaleControl){
    static const double scales[]={0.5,0.75,1.0};
    NSInteger i=sender.selectedSegmentIndex;
    if(i<0 || i>=3)return;
    [defaults setDouble:scales[i] forKey:@"AscensionMetalOutputScale"];
  }else if(sender==self.vblankRateControl){
    NSInteger i=sender.selectedSegmentIndex;
    if(i<0 || i>=2)return;
    [defaults setInteger:(i==0?30:60) forKey:@"AscensionGuestVBlankHz"];
  }
  [self refreshVideoSettingsSummary];
}

/* M5.0: NV40 guest microcode is decoded, lowered and compiled on the iPhone.
 * Failures are shown; no draw/gameplay claim is made from shader compilation. */
- (void)arSwitchTab:(UISegmentedControl *)sender {
    NSInteger selected=sender.selectedSegmentIndex;
    BOOL showGame=selected==0, showFiles=selected==1;
    BOOL showSettings=selected==2, showReport=selected==3;
    self.gameList.hidden=!showGame;
    self.graphicsList.hidden=!showFiles;
    self.settingsList.hidden=!showSettings;
    self.reportList.hidden=!showReport;
    self.launcherFooter.hidden=!showGame;
    self.metalView.hidden=YES;
    if(showReport){
      [self updateLauncherReport];
      if(self.shaderBusy && !self.launcherReportRefreshTimer){
        self.launcherReportRefreshTimer=[NSTimer scheduledTimerWithTimeInterval:0.75
          target:self selector:@selector(launcherReportRefreshTick:) userInfo:nil repeats:YES];
        [[NSRunLoop mainRunLoop] addTimer:self.launcherReportRefreshTimer
                                 forMode:NSRunLoopCommonModes];
      }
    }else{
      [self.launcherReportRefreshTimer invalidate];
      self.launcherReportRefreshTimer=nil;
    }
}
- (void)showLauncherReport:(UIButton*)sender {
    (void)sender;
    if(self.gameDisplayActive){[self openAdvancedPpuReport:nil];return;}
    self.launcherTabs.selectedSegmentIndex=3;
    [self arSwitchTab:self.launcherTabs];
}
- (void)updateLauncherReport {
    if(self.launcherReportLabel)
      self.launcherReportLabel.text=[self arUnifiedPpuText];
}
- (void)launcherReportRefreshTick:(NSTimer*)timer {
    if(!self.shaderBusy || self.launcherTabs.selectedSegmentIndex!=3){
      [timer invalidate]; self.launcherReportRefreshTimer=nil; return;
    }
    [self updateLauncherReport];
}
- (void)copyLauncherReport:(UIButton*)sender {
    UIPasteboard.generalPasteboard.string=[self arUnifiedPpuText];
    [sender setTitle:@"RELATÓRIO COPIADO" forState:UIControlStateNormal];
}
- (void)shareLauncherReport:(UIButton*)sender {
    (void)sender;
    [self arExportPpuText];
}
- (void)shareSpuMissCapture:(UIButton*)sender {
    NSURL *directory=self.latestSpuCaptureURL;
    NSError *error=nil;
    NSArray<NSURL*> *files=directory ? [[NSFileManager defaultManager]
        contentsOfDirectoryAtURL:directory includingPropertiesForKeys:nil
        options:NSDirectoryEnumerationSkipsHiddenFiles error:&error] : @[];
    if(!files.count){
      UIAlertController *alert=[UIAlertController alertControllerWithTitle:
          @"Nenhum PM SPU sem lift capturado"
          message:error.localizedDescription ?: @"O jogo ainda não submeteu um PM sem associação nativa nesta execução. PMs e jobs são caminhos separados no relatório."
          preferredStyle:UIAlertControllerStyleAlert];
      [alert addAction:[UIAlertAction actionWithTitle:@"OK" style:UIAlertActionStyleCancel handler:nil]];
      [self.window.rootViewController presentViewController:alert animated:YES completion:nil];
      return;
    }
    UIActivityViewController *share=[[UIActivityViewController alloc]
        initWithActivityItems:files applicationActivities:nil];
    UIViewController *presenter=self.window.rootViewController.presentedViewController
                                ?: self.window.rootViewController;
    UIPopoverPresentationController *popover=share.popoverPresentationController;
    if(popover){popover.sourceView=sender ?: presenter.view;
      popover.sourceRect=sender ? sender.bounds : presenter.view.bounds;}
    [presenter presentViewController:share animated:YES completion:nil];
}
- (void)openLauncherSettings:(UIButton*)sender {
  (void)sender;
  self.launcherTabs.selectedSegmentIndex=2;
  [self arSwitchTab:self.launcherTabs];
}
- (UIButton*)nativePadButton:(NSString*)title bit:(uint16_t)bit {
  UIButton *button=[UIButton buttonWithType:UIButtonTypeSystem];
  button.translatesAutoresizingMaskIntoConstraints=NO; button.tag=bit;
  button.multipleTouchEnabled=YES;
  [button setTitle:title forState:UIControlStateNormal];
  [button setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
  button.titleLabel.font=[UIFont systemFontOfSize:title.length>2?9:14 weight:UIFontWeightBold];
  button.titleLabel.adjustsFontSizeToFitWidth=YES;
  button.backgroundColor=[[UIColor colorWithRed:0.12 green:0.13 blue:0.15 alpha:1] colorWithAlphaComponent:0.70];
  button.layer.cornerRadius=22; button.layer.borderWidth=1;
  button.layer.borderColor=[[UIColor colorWithWhite:1 alpha:0.55] CGColor];
  [button addTarget:self action:@selector(nativePadDown:) forControlEvents:UIControlEventTouchDown];
  [button addTarget:self action:@selector(nativePadUp:) forControlEvents:
       UIControlEventTouchUpInside|UIControlEventTouchUpOutside|UIControlEventTouchCancel];
  return button;
}
- (void)publishNativePadState {
  uint16_t b=self.nativePadButtons;
  uint8_t lx=(b&ARPadLeft)?0:((b&ARPadRight)?255:128);
  uint8_t ly=(b&ARPadUp)?0:((b&ARPadDown)?255:128);
  cellPad_set_host_state(b,lx,ly,128,128,
      (b&ARPadL2)?255:0,(b&ARPadR2)?255:0);
}
- (void)nativePadDown:(UIButton*)sender {
  self.nativePadButtons|=(uint16_t)sender.tag;
  [self publishNativePadState];
}
- (void)nativePadUp:(UIButton*)sender {
  self.nativePadButtons&=(uint16_t)~sender.tag;
  [self publishNativePadState];
}
- (void)copyPpuBatch:(UIButton *)sender {
    if(!self.ppuBatchReport.length)return;
    UIPasteboard.generalPasteboard.string=self.ppuBatchReport;
    [sender setTitle:@"Lote PPC copiado · cole no chat" forState:UIControlStateNormal];
}
- (void)copyPpuReport:(UIButton *)sender {
    if(!self.ppuSummary.length)return;
    UIPasteboard.generalPasteboard.string=self.ppuSummary;
    [sender setTitle:@"Status AOT copiado · cole no chat" forState:UIControlStateNormal];
}
- (void)copyAdvancedPpuReport:(UIBarButtonItem *)sender {
    (void)sender;
    if(self.shaderBusy)UIPasteboard.generalPasteboard.string=[self arUnifiedPpuText];
    else if(self.ppuReport.length)UIPasteboard.generalPasteboard.string=self.ppuReport;
    else UIPasteboard.generalPasteboard.string=[self arUnifiedPpuText];
}
- (void)closeAdvancedPpuReport:(UIBarButtonItem *)sender {
    (void)sender;
    [self.ppuLiveRefreshTimer invalidate];
    self.ppuLiveRefreshTimer=nil;
    self.ppuLiveReportView=nil;
    [self.window.rootViewController dismissViewControllerAnimated:YES completion:nil];
}
- (void)openAdvancedPpuReport:(UIButton *)sender {
    (void)sender;
    UIViewController *page=[UIViewController new];
    page.title=@"Execução PS3Recomp";
    page.view.backgroundColor=UIColor.systemBackgroundColor;
    UITextView *details=[UITextView new];
    details.translatesAutoresizingMaskIntoConstraints=NO;
    details.editable=NO;
    details.selectable=YES;
    details.font=[UIFont monospacedSystemFontOfSize:12 weight:UIFontWeightRegular];
    details.text=[self arUnifiedPpuText];
    self.ppuLiveReportView=details;
    [self.ppuLiveRefreshTimer invalidate];
    self.ppuLiveRefreshTimer=nil;
    if(self.shaderBusy){
      __weak typeof(self) weakSelf=self;
      self.ppuLiveRefreshTimer=[NSTimer scheduledTimerWithTimeInterval:0.5
        repeats:YES block:^(__unused NSTimer *timer){
          __strong typeof(weakSelf) strongSelf=weakSelf;
          if(!strongSelf)return;
          strongSelf.ppuLiveReportView.text=[strongSelf arUnifiedPpuText];
          if(!strongSelf.shaderBusy){
            [strongSelf.ppuLiveRefreshTimer invalidate];
            strongSelf.ppuLiveRefreshTimer=nil;
          }
        }];
      [[NSRunLoop mainRunLoop] addTimer:self.ppuLiveRefreshTimer
                               forMode:NSRunLoopCommonModes];
    }
    [page.view addSubview:details];
    [NSLayoutConstraint activateConstraints:@[
      [details.topAnchor constraintEqualToAnchor:page.view.safeAreaLayoutGuide.topAnchor],
      [details.leadingAnchor constraintEqualToAnchor:page.view.safeAreaLayoutGuide.leadingAnchor constant:12],
      [details.trailingAnchor constraintEqualToAnchor:page.view.safeAreaLayoutGuide.trailingAnchor constant:-12],
      [details.bottomAnchor constraintEqualToAnchor:page.view.safeAreaLayoutGuide.bottomAnchor]
    ]];
    page.navigationItem.leftBarButtonItem=[[UIBarButtonItem alloc]
       initWithTitle:@"Fechar" style:UIBarButtonItemStylePlain target:self
       action:@selector(closeAdvancedPpuReport:)];
    UIBarButtonItem *copy=[[UIBarButtonItem alloc]
       initWithTitle:@"Copiar" style:UIBarButtonItemStylePlain target:self
       action:@selector(copyAdvancedPpuReport:)];
    UIBarButtonItem *share=[[UIBarButtonItem alloc]
       initWithTitle:@"Compartilhar" style:UIBarButtonItemStylePlain target:self
       action:@selector(shareAdvancedPpuReport:)];
    page.navigationItem.rightBarButtonItems=@[share,copy];
    UINavigationController *nav=[[UINavigationController alloc] initWithRootViewController:page];
    [self.window.rootViewController presentViewController:nav animated:YES completion:nil];
}
/* This report describes the active PS3Recomp session only: host/guest result,
 * live AOT entries, VFS state and measured guest file operations. It never
 * converts file indexing or synthetic Metal tests into game progress. */
- (NSString *)arUnifiedPpuText {
  uint64_t live[40]={0}; ar_m772_runtime_attest(live);
  ar_fs_trace liveFs={0}; ar_fs_snapshot(&liveFs);
  uint64_t spursMetrics[8]={0}; cellSpursCopyAscensionMetrics(spursMetrics);
  uint64_t spuJobs[8]={0}; spu_workload_copy_ascension_job_metrics(spuJobs);
  uint64_t pmDiagnostics[32][7]={0}; cellSpursCopyAscensionPmDiagnostics(pmDiagnostics);
  NSString *spuCaptureName=self.latestSpuCaptureURL.lastPathComponent ?: @"não configurada";
  uint32_t state=ar_m772_entry_state();
  NSString *elapsed=ARFormatRunElapsed(self.nativeRunStartedAt,self.nativeRunEndedAt);
  /* A second boot must report its current counters, not the last completed
   * run retained by the launcher. */
  NSDictionary *run=self.shaderBusy?nil:self.m750Run;
  BOOL guestFSReadMeasured=
      (run?[run[@"fs_read_calls"] unsignedLongLongValue]:live[11])>0 &&
      (run?[run[@"fs_bytes"] unsignedLongLongValue]:live[12])>0;
  uint64_t trace[12]={0};
  uint32_t traceCount=ar_m772_copy_aot_trace(trace,12);
  NSMutableString *aotTraceText=[NSMutableString string];
  for(uint32_t i=0;i<traceCount;i++){
    uint32_t pc=(uint32_t)(trace[i]>>32),lr=(uint32_t)trace[i];
    [aotTraceText appendFormat:@"%@func_%08X <- LR 0x%08X",i?@"\n":@"",pc,lr];
  }
  if(!aotTraceText.length)[aotTraceText appendString:@"(amostra ainda não coletada; 1 em 4096 entradas AOT)"];
  uint64_t hleTrace[8]={0},missTrace[8]={0};
  uint32_t hleTraceCount=ar_m772_copy_hle_trace(hleTrace,8);
  uint32_t missTraceCount=ar_m772_copy_unresolved_hle_trace(missTrace,8);
  NSMutableString *hleTraceText=[NSMutableString string];
  for(uint32_t i=0;i<hleTraceCount;i++)
    [hleTraceText appendFormat:@"%@NID 0x%08X <- LR 0x%08X",i?@"\n":@"",
      (uint32_t)(hleTrace[i]>>32),(uint32_t)hleTrace[i]];
  if(!hleTraceText.length)[hleTraceText appendString:@"(nenhuma chamada HLE registrada ainda)"];
  NSMutableString *missTraceText=[NSMutableString string];
  for(uint32_t i=0;i<missTraceCount;i++)
    [missTraceText appendFormat:@"%@NID 0x%08X <- LR 0x%08X",i?@"\n":@"",
      (uint32_t)(missTrace[i]>>32),(uint32_t)missTrace[i]];
  if(!missTraceText.length)[missTraceText appendString:@"(nenhum HLE sem serviço registrado)"];
  NSString *hotloopAudit=(live[31]==0x003C4FA4u)?
    @"0x003C4FA4 é o marcador de backedge da busca em func_003C4F98, não o PC corrente.":
    @"PC do hook de loop observado; é um marcador e pode estar antigo.";
  NSString *lastSpursWid=spursMetrics[7]==UINT64_MAX?@"—":
    [NSString stringWithFormat:@"%llu",(unsigned long long)spursMetrics[7]];
  NSMutableString *pmDiagnosticsText=[NSMutableString string];
  for(NSUInteger wid=0;wid<32;wid++){
    const uint64_t *d=pmDiagnostics[wid];
    if(d[0]==UINT64_MAX)continue;
    [pmDiagnosticsText appendFormat:
      @"%@wid=%llu · EA=0x%08llX · size=%llu · FNV-1a64=0x%016llX · image=%llu%@ · faixa=%@ · EA original >32 bits=%@",
      pmDiagnosticsText.length?@"\n":@"",(unsigned long long)d[0],
      (unsigned long long)d[1],(unsigned long long)d[2],(unsigned long long)d[3],
      (unsigned long long)d[4],d[4]?@"":@" (sem registro)",
      d[5]?@"válida":@"INVÁLIDA",d[6]?@"SIM":@"NÃO"];
  }
  if(!pmDiagnosticsText.length)
    [pmDiagnosticsText appendString:@"(nenhum PM ainda examinado pelo scheduler)"];
  ar_vm_reservation_status vmReservation={0};
  ar_bridge_vm_reservation_status(&vmReservation);
  NSString *vmMode=vmReservation.attempted?
      ARVMReservationName(vmReservation.reservation_kind):@"NÃO TENTADA";
  NSString *vmMachAttempts=vmReservation.attempted?
      [NSString stringWithFormat:@"%u",vmReservation.mach_attempts]:@"NÃO MEDIDO";
  NSString *vmMachReturn=vmReservation.attempted?
      [NSString stringWithFormat:@"%d",vmReservation.last_mach_kern_return]:@"NÃO MEDIDO";
  NSString *vmMmapAttempts=vmReservation.attempted?
      [NSString stringWithFormat:@"%u",vmReservation.mmap_attempts]:@"NÃO MEDIDO";
  NSString *vmBase=vmReservation.reservation_base?
      [NSString stringWithFormat:@"0x%llX",(unsigned long long)vmReservation.reservation_base]:@"NENHUM";
  NSString *vmStage=vmReservation.attempted?
      ARVMReservationStageName(vmReservation.failure_stage):@"NÃO MEDIDO";
  NSString *vmErrno=vmReservation.attempted?
      [NSString stringWithFormat:@"%d",vmReservation.failure_errno]:@"NÃO MEDIDO";
  NSString *phase=state==0?@"PREPARANDO runtime/VFS":
                  state==1?@"EXECUTANDO entry AOT":
                  state==2?@"ENTRY RETORNOU":
                  state==3?@"ENTRY NÃO VINCULADA":@"SEM ENTRY AOT";
  NSString *stateText=self.shaderBusy?@"EM EXECUÇÃO":(run?@"CONCLUÍDO":@"SEM EXECUÇÃO");
  NSString *vfsRootState=guestFSReadMeasured?
      (live[8]?@"ROOT CONFIGURADA · cellFsRead guest comprovado; último caminho abaixo":
               @"cellFsRead guest comprovado · estado da raiz a revisar"):
      (live[8]?@"ROOT CONFIGURADA · FS ainda não comprovado":
       ((run && [run[@"host_rc"] intValue]==AR_NO_MEMORY)?
        @"NÃO MONTADA · VM falhou antes do runtime":
        (self.hasGameInstallation?@"PENDENTE · monta no início do boot":@"NÃO CONFIGURADA")));
  if(!self.shaderBusy && !run)phase=@"AGUARDANDO INICIAR";
  else if(!self.shaderBusy && run && [run[@"host_rc"] intValue]!=0)phase=@"FALHA NO HOST / LOADER";
  else if(!self.shaderBusy && run && state==3u)phase=@"ENTRY AOT NÃO VINCULADA";
  NSString *entry=[NSString stringWithFormat:@"0x%08llX",(unsigned long long)(run?[run[@"entry"] unsignedIntValue]:0x10410u)];
  NSString *hostRC=run?[run[@"host_rc"] description]:@"NÃO MEDIDO";
  NSString *rc=run?[run[@"rc"] description]:@"NÃO MEDIDO";
  NSString *entryStarts=run?[run[@"entry_starts"] description]:[NSString stringWithFormat:@"%llu",(unsigned long long)live[13]];
  NSString *aotCalls=run?[run[@"aot_calls"] description]:[NSString stringWithFormat:@"%llu",(unsigned long long)live[5]];
  NSString *fsOpen=run?[run[@"fs_open_calls"] description]:[NSString stringWithFormat:@"%llu",(unsigned long long)live[9]];
  NSString *fsOK=run?[run[@"fs_opens"] description]:[NSString stringWithFormat:@"%llu",(unsigned long long)live[10]];
  NSString *fsRead=run?[run[@"fs_read_calls"] description]:[NSString stringWithFormat:@"%llu",(unsigned long long)live[11]];
  NSString *fsBytes=run?[run[@"fs_bytes"] description]:[NSString stringWithFormat:@"%llu",(unsigned long long)live[12]];
  NSString *guestFsPath=liveFs.last_path[0]?
      [NSString stringWithUTF8String:liveFs.last_path]:@"(nenhum caminho guest ainda)";
  if([run[@"fs_path"] isKindOfClass:[NSString class]] && [run[@"fs_path"] length])
    guestFsPath=run[@"fs_path"];
  NSString *hleCalls=run?[run[@"hle_calls"] description]:[NSString stringWithFormat:@"%llu",(unsigned long long)live[26]];
  NSString *unresolvedHLE=run?[run[@"unresolved_hle_count"] description]:[NSString stringWithFormat:@"%llu",(unsigned long long)live[37]];
  NSString *hotloopCount=run?[run[@"hotloop_count"] description]:[NSString stringWithFormat:@"%llu",(unsigned long long)live[30]];
  uint32_t reportVBlankHz=__atomic_load_n(&ARNativeRSXVBlankHz,__ATOMIC_RELAXED);
  if(reportVBlankHz!=30 && reportVBlankHz!=60)reportVBlankHz=60;
  uint64_t guestDraws=run?[run[@"rsx_guest_draws"] unsignedLongLongValue]:ARRSXLoad(&ARNativeRSXLastGuestDraws);
  NSString *rsxBackend=run?([run[@"rsx_backend_rc"] intValue]==0?@"inicializado · sessão encerrada":@"falhou"):
       (__atomic_load_n(&ARNativeRSXBackendReady,__ATOMIC_RELAXED)?@"Metal inicializado":@"não inicializado");
  NSString *rsxVblanks=run?[run[@"rsx_vblank_ticks"] description]:[NSString stringWithFormat:@"%llu",(unsigned long long)ARRSXLoad(&ARNativeRSXVBlanks)];
  NSString *rsxDrains=run?[run[@"rsx_fifo_drains"] description]:[NSString stringWithFormat:@"%llu",(unsigned long long)ARRSXLoad(&ARNativeRSXFIFODrains)];
  NSString *rsxFrames=run?[run[@"rsx_guest_frames"] description]:[NSString stringWithFormat:@"%llu",(unsigned long long)ARRSXLoad(&ARNativeRSXPresentedFrames)];
  NSString *rsxDraws=run?[run[@"rsx_guest_draws"] description]:[NSString stringWithFormat:@"%llu",(unsigned long long)ARRSXLoad(&ARNativeRSXLastGuestDraws)];
  BOOL hasGuestFlip=(run?[run[@"rsx_guest_frames"] unsignedLongLongValue]:ARRSXLoad(&ARNativeRSXPresentedFrames))>0;
  return [NSString stringWithFormat:
    @"ASCENSIONRECOMP · LAUNCHER / EXECUÇÃO NATIVA\n"
     "Branch=%s · Commit=%s · Actions=%s · RunID=%s\n"
     "App=%@ · title=NPUA80918 · origem=ELF autenticado no iPhone\n\n"
     "SESSÃO\n"
     "Estado=%@ · fase=%@\n"
     "Tempo desde tocar Iniciar=%@\n"
     "ELF importado=%@ · entry=%@ · host rc=%@ · guest rc=%@\n"
     "VM guest virtual=%@ bytes (páginas sob demanda) · ELF PT_LOAD=%@ bytes · raiz VFS=%@\n\n"
     "Reserva VM=%@ · base=%@ · Mach tentativas=%@ (último kr=%@) · mmap tentativas=%@ · estágio=%@ · errno=%@\n\n"
     "PS3RECOMP / MÉTRICAS AO VIVO\n"
     "Tabela AOT=%llu funções · autocheck do catálogo SPU=%llu/5 (não confirma o PM recebido em runtime) · runtime inicializado=%@\n"
     "Chamadas de função AOT=%@ · início(s) da entry=%@ · último PC=0x%08llX (entrada AOT mais recente; PC atual da instrução NÃO MEDIDO)\n"
     "SPURS2 · instâncias=%llu · workloads=%llu (%llu IDs 16–31) · PMs encontrados/faltantes=%llu/%llu · admissões do WWS PM=%llu (%llu IDs 16–31) · último wid=%@\n"
     "Jobs de job-chain do título · solicitações=%llu · com lift=%llu · sem lift=%llu · retornos do runner=%llu · ativos=%llu · último FNV=0x%016llX · bytes=%llu · EA=0x%08llX\n"
     "Captura de módulos ausentes=Documents/%@ · botão EXPORTAR BINÁRIOS SPU AUSENTES\n"
     "PMs examinados (um registro por wid):\n%@\n"
     "Últimas amostras AOT (1/4096):\n%@\n"
     "Último evento rastreado: LR=0x%08llX · SP=0x%08llX · r3-r6=%08llX/%08llX/%08llX/%08llX\n"
     "Argumentos r7-r10=%08llX/%08llX/%08llX/%08llX\n"
     "HLE=%@ · último NID=0x%08llX · LR=0x%08llX\n"
     "Últimas chamadas HLE:\n%@\n"
     "HLE sem serviço registrado=%@ · último NID=0x%08llX · LR=0x%08llX\n"
     "Últimos HLE sem serviço:\n%@\n"
     "LV2 syscalls=%@ · último número=%@ · LR=0x%08llX\n"
     "Loop observado=%@ · marcador hotloop=0x%08llX (não é PC atual) · %@ · r3/r4/r5/r8/r9=%08llX/%08llX/%08llX/%08llX/%08llX\n"
     "cellFsOpen guest=%@ · opens OK=%@\n"
     "cellFsRead guest=%@ · bytes lidos pelo guest=%@\n"
     "Último caminho guest=%@\n"
     "RSX backend=%@ · GCM vblank=%@ · FIFO drains=%@\n"
     "Metal drawable=%.2gx · cadência VBlank guest=%u Hz\n"
     "Flips guest apresentados=%@ · draws guest no último frame=%@\n"
     "PSARC específico= consulte Último caminho guest; nenhum histórico adicional é coletado.\n"
     "PPC interpretado=0 · entradas HLE e LV2 contadas no runtime\n\n"
     "Auditoria M7.89: o PM bruto C8D774963A96DCF2 (12 KiB, LS 0xA00) foi levantado separadamente em 255 funções nativas; não é alias do PM NPUA CE052ACDA7412063. A entrada C8 está registrada como imagem SPU 6. Registro e compilação não provam que o iPhone executou jobs, draws ou flips; confirme estes contadores no próximo teste.\n\n"
     "Auditoria M7.90: os 31 overlays WWS do GOWA.ELF NPUA80918 foram extraídos pelo extractor do port de PC e recompilados para C nativo via ps3recomp. O registro é chamado na inicialização e as imagens PM NPUA=5/C8=6 são roteadas pela identidade do PM registrado. Sete finais de código e uma ilha de strings foram excluídos como dados embutidos; o build recusa qualquer instrução SPU sem tradução. Isto ainda não comprova job, draw, flip ou frame no iPhone.\n\nAuditoria M7.91: o HLE lwcond agora enfileira waiters, solta/reobtém o lwmutex e só acorda após signal/signal_all/signal_to ou timeout; isso corrige uma semântica ausente observada no caminho PPU, mas não comprova que houve job ou frame.\n\n"
     "MARCOS DE JOGO\n"
     "Pasta reconhecida pelo HOST=%@\n"
     "Leitura guest de arquivos do jogo= %@\n"
     "Comandos RSX do jogo= %@\n"
     "Primeiro flip guest apresentado= %@\n\n"
     "Host iOS: o contador de FIFO/vblank descreve o worker Metal; só draws e flips guest confirmam renderização do jogo.\n"
     "Controles: cellPad HLE via overlay tátil · cellAudio HLE ativo, saída de áudio iOS silenciosa nesta versão.\n"
     "Estado do jogo: menu/gameplay ainda não estão comprovados até o guest gerar draws e apresentar um flip.\n"
     "ELF, PSARC e conteúdo do jogo permanecem no dispositivo.",
     AR_M750_BUILD_BRANCH,AR_M750_BUILD_SHA,AR_M750_BUILD_RUN_NUMBER,AR_M750_BUILD_RUN_ID,
     ARCurrentRelease(),stateText,phase,elapsed,
     run?@"SIM":(self.selectedElfData?@"SIM · VALIDADO":@"NÃO"),entry,hostRC,rc,
     run?[run[@"vm_capacity"] description]:[NSString stringWithFormat:@"%llu",(unsigned long long)live[7]],
     run?[run[@"loaded_bytes"] description]:@"NÃO MEDIDO",
     vfsRootState,
     vmMode,vmBase,vmMachAttempts,vmMachReturn,vmMmapAttempts,vmStage,vmErrno,
     (unsigned long long)live[0],(unsigned long long)live[3],live[4]?@"SIM":@"NÃO",
     aotCalls,entryStarts,(unsigned long long)live[6],
     (unsigned long long)spursMetrics[0],(unsigned long long)spursMetrics[1],
     (unsigned long long)spursMetrics[2],(unsigned long long)spursMetrics[5],
     (unsigned long long)spursMetrics[6],(unsigned long long)spursMetrics[3],
     (unsigned long long)spursMetrics[4],lastSpursWid,
     (unsigned long long)spuJobs[0],(unsigned long long)spuJobs[1],
     (unsigned long long)spuJobs[2],(unsigned long long)spuJobs[3],
     (unsigned long long)spuJobs[4],(unsigned long long)spuJobs[5],
     (unsigned long long)spuJobs[6],(unsigned long long)spuJobs[7],
     spuCaptureName,pmDiagnosticsText,aotTraceText,
     (unsigned long long)live[14],(unsigned long long)live[15],
     (unsigned long long)live[16],(unsigned long long)live[17],
     (unsigned long long)live[18],(unsigned long long)live[19],
     (unsigned long long)live[20],(unsigned long long)live[21],
     (unsigned long long)live[22],(unsigned long long)live[23],
     hleCalls,(unsigned long long)live[24],(unsigned long long)live[25],hleTraceText,
     unresolvedHLE,(unsigned long long)live[38],(unsigned long long)live[39],missTraceText,
     run?run[@"syscall_calls"]:[NSString stringWithFormat:@"%llu",(unsigned long long)live[29]],
     run?run[@"last_syscall"]:[NSString stringWithFormat:@"%llu",(unsigned long long)live[27]],
     (unsigned long long)live[28],hotloopCount,(unsigned long long)live[31],hotloopAudit,
     (unsigned long long)live[32],(unsigned long long)live[33],
     (unsigned long long)live[34],(unsigned long long)live[35],
     (unsigned long long)live[36],fsOpen,fsOK,fsRead,fsBytes,
     guestFsPath,rsxBackend,rsxVblanks,rsxDrains,(double)self.metalView.outputScale,
     reportVBlankHz,rsxFrames,rsxDraws,
     self.hasGameInstallation?@"SIM (arquivos indexados no host; isso não prova cellFs)":@"NÃO" ,
     (run?[run[@"fs_bytes"] unsignedLongLongValue]:live[12])>0?
       @"ATIVIDADE COMPROVADA":@"NÃO COMPROVADA",
     hasGuestFlip?@"COMPROVADOS · pelo menos um flip do guest chegou ao Metal":@"NÃO COMPROVADOS · nenhum flip guest",
     hasGuestFlip?(guestDraws>0?@"APRESENTADO · draws guest medidos":@"APRESENTADO · sem draw guest medido"):@"NÃO APRESENTADO"];
}
- (void)arCopyAllPpuText {
    NSString *report=[self arUnifiedPpuText];
    if(report.length)UIPasteboard.generalPasteboard.string=report;
}
/* Store TXT persistently in the app's Documents folder. iOS exposes
 * Documents in Files (including Recents indexing) via Info.plist.
 * The OS, not the app, controls the selected Files Recents tab.
 * Share sheet is primary: direct ChatGPT send without iCloud folder browse.
 */
- (NSURL *)arCreatePpuTextFile {
    NSString *report=[self arUnifiedPpuText];
    if(!report.length)return nil;
    NSDateFormatter *date=[NSDateFormatter new];
    date.locale=[NSLocale localeWithLocaleIdentifier:@"en_US_POSIX"];
    date.dateFormat=@"yyyyMMdd-HHmmss";
    NSString *name=[NSString stringWithFormat:
       @"AscensionRecomp-%@-NPUA80918-%@.txt",
       ARCurrentRelease(),[date stringFromDate:[NSDate date]]];
    NSURL *docs=[[[NSFileManager defaultManager]
        URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask] firstObject];
    NSURL *url=[docs URLByAppendingPathComponent:name isDirectory:NO];
    NSError *error=nil;
    if(!url || ![report writeToURL:url atomically:YES
                  encoding:NSUTF8StringEncoding error:&error]){
        UIAlertController *alert=[UIAlertController alertControllerWithTitle:
          @"Falha ao gerar o TXT" message:error.localizedDescription ?:
          @"Não foi possível salvar o relatório." preferredStyle:UIAlertControllerStyleAlert];
        [alert addAction:[UIAlertAction actionWithTitle:@"OK"
                   style:UIAlertActionStyleCancel handler:nil]];
        [self.window.rootViewController presentViewController:alert
                                     animated:YES completion:nil];
        return nil;
    }
    return url;
}
- (void)arExportPpuText {
    NSURL *url=[self arCreatePpuTextFile];
    if(!url)return;
    UIActivityViewController *share=[[UIActivityViewController alloc]
                       initWithActivityItems:@[url] applicationActivities:nil];
    UIViewController *presenter=self.window.rootViewController.presentedViewController
                                ?: self.window.rootViewController;
    UIPopoverPresentationController *popover=share.popoverPresentationController;
    if(popover){popover.sourceView=presenter.view;popover.sourceRect=presenter.view.bounds;}
    [presenter presentViewController:share animated:YES completion:nil];
}
- (void)arSavePpuTextToFiles {
    NSURL *url=[self arCreatePpuTextFile];
    if(!url)return;
    UIDocumentPickerViewController *picker=[[UIDocumentPickerViewController alloc]
                           initForExportingURLs:@[url] asCopy:YES];
    /* Do not pin iCloud Drive. With nil, the system chooses its
     * last-used Files directory; the virtual Recents tab is OS-owned. */
    picker.directoryURL=nil;
    UIViewController *presenter=self.window.rootViewController.presentedViewController
                                ?: self.window.rootViewController;
    [presenter presentViewController:picker animated:YES completion:nil];
}
- (void)openUnifiedPpuMenu:(UIButton *)sender {
    if(![self arUnifiedPpuText].length)return;
    /* One tap opens a preflight, live, or completed execution report. */
    [self openAdvancedPpuReport:sender];
}
- (void)shareAdvancedPpuReport:(UIBarButtonItem *)sender {
    (void)sender;
    [self arExportPpuText];
}
- (void)testGuestRSXShader:(UIButton *)sender {
    if (!self.ready || self.shaderBusy) return;
    self.shaderBusy=YES;
    sender.enabled=NO;
    self.status.text=@"M5.0: compilando VP/FP RSX originais sintéticos...\nSem dados comerciais.";
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        char report[256]={0};
        int rc=ar_probe_guest_shader_compile(report,sizeof(report));
        NSString *details=[NSString stringWithUTF8String:report];
        dispatch_async(dispatch_get_main_queue(), ^{
            self.shaderBusy=NO;
            sender.enabled=YES;
            if(rc==0) {
                self.status.text=[NSString stringWithFormat:
                    @"M5.0 VP/FP RSX → Metal: OK\n%@\n"
                     "Microcódigo sintético; ainda NÃO roda Ascension.",
                    details];
            } else {
                self.status.text=[NSString stringWithFormat:
                    @"M5.0 SHADER RSX: FALHA %d\n%@\n"
                     "M4.10 continua testável.",
                    rc,details];
            }
        });
    });
}

/* M5.1: do not report OK from compilation alone. The test returns only
 * after a real NV4097 guest pipeline draw and GPU four-point readback. */
- (void)testM51GuestDraw:(UIButton *)sender {
    (void)sender;
    if(!self.ready || self.shaderBusy)return;
    unsigned sw=(unsigned)((self.m51Attempts++ & 1u)!=0u);
    unsigned int p[4]={0},encoded=0,guest=0,shader[4]={0};
    self.status.text=@"M5.1: NV4097 → VP/FP TEX0 → GPU raster...";
    const int rc=ar_probe_m51_guest_textured_quad(sw,p,&encoded,&guest,shader);
    if(!rc) {
        self.status.text=[NSString stringWithFormat:
            @"M5.1 RSX VP/FP TEX0 → Metal: OK\n"
             "DRAW convidado: %u · GPU codificou: %u\n"
             "Layout: %@ · 4 pixels distintos reais\n"
             "VP %u · FP %u · carregado %u\n"
             "%08X %08X %08X %08X\n"
             "Aperte novamente: outro layout. SEM jogo.",
             guest,encoded,sw?@"SWIZZLED":@"LINEAR",
             shader[1],shader[2],shader[0],p[0],p[1],p[2],p[3]];
    }else{
        self.status.text=[NSString stringWithFormat:
            @"M5.1 RSX TEX0: FALHA %d\n"
             "DRAW convidado: %u · GPU codificou: %u\n"
             "Layout: %@ · VP %u · FP %u · par %u\n"
             "RegFP %08X\nPixels: %08X %08X %08X %08X\n"
             "M5.0 e M4.10 permanecem disponíveis.",
             rc,guest,encoded,sw?@"SWIZZLED":@"LINEAR",
             shader[1],shader[2],shader[0],shader[3],
             p[0],p[1],p[2],p[3]];
    }
}

/* M5.2: three distinct PS3 guest writes to the same texture address,
 * each displayed through the real guest FP TEX0 program and Metal readback.
 * Retains all legacy gestures/buttons and requires measured hash replacements. */
- (void)testM52TextureMutation:(UIButton *)sender {
    (void)sender;
    if (!self.ready || self.shaderBusy) return;
    unsigned sw=(unsigned)((self.m52Attempts++ & 1u)!=0u);
    unsigned int p[4]={0},phase=0,uploads=0,replacements=0,guest=0,metal=0;
    self.status.text=@"M5.2: mutando textura PS3 entre 3 DRAWs convidados...";
    const int rc=ar_probe_m52_guest_texture_mutation(
       sw,p,&phase,&uploads,&replacements,&guest,&metal);
    if(rc==0) {
        self.status.text=[NSString stringWithFormat:
            @"M5.2 TEX0 dinâmica → Metal: OK\n"
             "Layout %@ · 3 quadros GPU verificados\n"
             "DRAW convidado/Metal: %u / %u\n"
             "Uploads: %u · substituições cache: %u\n"
             "Últimos pixels: %08X %08X %08X %08X\n"
             "Aperte novamente para alternar o layout.",
             sw?@"SWIZZLED":@"LINEAR",guest,metal,
             uploads,replacements,p[0],p[1],p[2],p[3]];
    } else {
        self.status.text=[NSString stringWithFormat:
            @"M5.2 TEX0 dinâmica: FALHA %d · fase %u\n"
             "Layout %@ · DRAW RSX/Metal %u / %u\n"
             "Uploads %u · substituições %u\n"
             "Pixels %08X %08X %08X %08X\n"
             "M5.1 e M4.10 continuam disponíveis.",
             rc,phase,sw?@"SWIZZLED":@"LINEAR",guest,metal,
             uploads,replacements,p[0],p[1],p[2],p[3]];
    }
}

/* The two guest passes are separately validated by genuine target readback.
 * A passing result also requires a backend-created render-target texture view.
 */
- (void)testM53Multipass:(UIButton *)sender {
    (void)sender;
    if(!self.ready || self.shaderBusy)return;
    unsigned sw=(unsigned)((self.m53Attempts++ & 1u)!=0u);
    unsigned int pixels[4]={0},phase=0,guest=0,metal=0,views=0,uploads=0;
    self.status.text=@"M5.3: render A RSX → TEXTURA0 → render B RSX...";
    const int rc=ar_probe_m53_guest_multipass(
        sw,pixels,&phase,&guest,&metal,&views,&uploads);
    if(rc==0) {
        self.status.text=[NSString stringWithFormat:
            @"M5.3 MULTIPASS RSX → Metal: OK\n"
             "Layout %@ · 2 passes GPU verificados\n"
             "DRAWs convidados/Metal: %u/%u\n"
             "Views Metal da superfície: %u · uploads novos: %u\n"
             "RT B: %08X %08X %08X %08X\n"
             "Aperte novamente para alternar o layout.",
            sw?@"SWIZZLED":@"LINEAR",guest,metal,views,uploads,
            pixels[0],pixels[1],pixels[2],pixels[3]];
    } else {
        self.status.text=[NSString stringWithFormat:
            @"M5.3 MULTIPASS: FALHA %d · passe %u\n"
             "Layout %@ · DRAWs RSX/Metal: %u/%u\n"
             "Views Metal: %u · uploads novos: %u\n"
             "RT: %08X %08X %08X %08X\n"
             "M5.2/M5.1/M4.10 continuam disponíveis.",
            rc,phase,sw?@"SWIZZLED":@"LINEAR",guest,metal,views,uploads,
            pixels[0],pixels[1],pixels[2],pixels[3]];
    }
}

/* M5.4: occluded fragment must not overwrite prior colour; a closer
 * fragment must overwrite it. All pixels are read after actual GPU work. */
- (void)testM54DepthOcclusion:(UIButton *)sender {
    (void)sender;
    if(!self.ready || self.shaderBusy)return;
    unsigned sw=(unsigned)((self.m54Attempts++ & 1u)!=0u);
    unsigned int p[4]={0},phase=0,guest=0,metal=0,depth=0;
    self.status.text=@"M5.4: 3 DRAWs com profundidade Z24S8...";
    const int rc=ar_probe_m54_guest_depth_occlusion(
          sw,p,&phase,&guest,&metal,&depth);
    if(!rc) {
        self.status.text=[NSString stringWithFormat:
            @"M5.4 PROFUNDIDADE RSX: OK\n"
             "Layout %@ · 3 quadros GPU verificados\n"
             "DRAW RSX/Metal/depth: %u/%u/%u\n"
             "Trás oculto: SIM · frente visível: SIM\n"
             "Pixéis: %08X %08X %08X %08X\n"
             "Aperte novamente para alternar layout.",
             sw?@"SWIZZLED":@"LINEAR",guest,metal,depth,
             p[0],p[1],p[2],p[3]];
    } else {
        self.status.text=[NSString stringWithFormat:
            @"M5.4 PROFUNDIDADE: FALHA %d · fase %u\n"
             "Layout %@ · DRAW RSX/Metal/depth %u/%u/%u\n"
             "Pixéis: %08X %08X %08X %08X\n"
             "M5.3/M5.2/M5.1/M4.10 seguem disponíveis.",
             rc,phase,sw?@"SWIZZLED":@"LINEAR",guest,metal,depth,
             p[0],p[1],p[2],p[3]];
    }
}

/* M5.5: real RSX stencil controls must persist and select GPU fragments
 * correctly. A passing label requires three GPU readbacks, not only state. */
- (void)testM55StencilMask:(UIButton *)sender {
    (void)sender;
    if(!self.ready || self.shaderBusy)return;
    unsigned sw=(unsigned)((self.m55Attempts++ & 1u)!=0u);
    unsigned int pixels[4]={0},phase=0,guest=0,metal=0,stencil=0;
    self.status.text=@"M5.5: 3 DRAWs com stencil RSX...";
    const int rc=ar_probe_m55_guest_stencil_mask(
         sw,pixels,&phase,&guest,&metal,&stencil);
    if(!rc) {
        self.status.text=[NSString stringWithFormat:
            @"M5.5 STENCIL RSX → Metal: OK\n"
             "Layout %@ · 3 quadros GPU verificados\n"
             "DRAW RSX/Metal/stencil: %u/%u/%u\n"
             "Ref 2 oculto: SIM · ref 1 visível: SIM\n"
             "Pixels: %08X %08X %08X %08X\n"
             "Aperte novamente para alternar layout.",
             sw?@"SWIZZLED":@"LINEAR",guest,metal,stencil,
             pixels[0],pixels[1],pixels[2],pixels[3]];
    } else {
        self.status.text=[NSString stringWithFormat:
            @"M5.5 STENCIL: FALHA %d · fase %u\n"
             "Layout %@ · DRAW RSX/Metal/stencil: %u/%u/%u\n"
             "Pixels: %08X %08X %08X %08X\n"
             "M5.4/M5.3/M5.2/M5.1 continuam disponíveis.",
             rc,phase,sw?@"SWIZZLED":@"LINEAR",guest,metal,stencil,
             pixels[0],pixels[1],pixels[2],pixels[3]];
    }
}

/* M5.6: bitwise stencil read/write masking must change REAL GPU colour. */
- (void)testM56StencilBitmasks:(UIButton *)sender {
    (void)sender;
    if(!self.ready || self.shaderBusy)return;
    unsigned sw=(unsigned)((self.m56Attempts++ & 1u)!=0u);
    unsigned int pixels[4]={0},phase=0,guest=0,metal=0,stencil=0;
    self.status.text=@"M5.6: 7 passes GPU com STENCIL 0F/F0...";
    const int rc=ar_probe_m56_guest_stencil_bitmasks(
        sw,pixels,&phase,&guest,&metal,&stencil);
    if(!rc) {
        self.status.text=[NSString stringWithFormat:
             @"M5.6 BITMASK STENCIL: OK\n"
              "Layout %@ · 7 quadros GPU verificados\n"
              "DRAW RSX/Metal/stencil: %u/%u/%u\n"
              "Escrita 0F/F0 · leitura FF/0F: OK\n"
              "Pixels: %08X %08X %08X %08X\n"
              "Aperte novamente para alternar layout.",
              sw?@"SWIZZLED":@"LINEAR",guest,metal,stencil,
              pixels[0],pixels[1],pixels[2],pixels[3]];
    } else {
        self.status.text=[NSString stringWithFormat:
             @"M5.6 BITMASK: FALHA %d · fase %u\n"
              "Layout %@ · DRAW RSX/Metal/stencil %u/%u/%u\n"
              "Pixels: %08X %08X %08X %08X\n"
              "M5.5/M5.4/M5.3 permanecem disponíveis.",
              rc,phase,sw?@"SWIZZLED":@"LINEAR",guest,metal,stencil,
              pixels[0],pixels[1],pixels[2],pixels[3]];
    }
}

- (void)testM57BlendMask:(UIButton *)sender {
    (void)sender;
    if(!self.ready || self.shaderBusy)return;
    unsigned sw=(unsigned)((self.m57Attempts++ & 1u)!=0u);
    unsigned int p[4]={0},phase=0,guest=0,metal=0,blend=0,masked=0;
    self.status.text=@"M5.7: 4 DRAWs com blend RSX...";
    const int rc=ar_probe_m57_guest_blend_mask(sw,p,&phase,&guest,&metal,&blend,&masked);
    if(!rc) {
        self.status.text=[NSString stringWithFormat:
            @"M5.7 BLEND RSX → Metal: OK\n"
             "Layout %@ · 4 quadros GPU verificados\n"
             "DRAW RSX/Metal/blend/red: %u/%u/%u/%u\n"
             "ADD + máscara R + ZERO/ONE: OK\n"
             "Pixels: %08X %08X %08X %08X\n"
             "Aperte novamente para alternar layout.",
             sw?@"SWIZZLED":@"LINEAR",guest,metal,blend,masked,p[0],p[1],p[2],p[3]];
    } else {
        self.status.text=[NSString stringWithFormat:
            @"M5.7 BLEND: FALHA %d · fase %u\n"
             "Layout %@ · DRAW RSX/Metal/blend/red %u/%u/%u/%u\n"
             "Pixels: %08X %08X %08X %08X\n"
             "M5.6/M5.5/M5.4 permanecem disponíveis.",
             rc,phase,sw?@"SWIZZLED":@"LINEAR",guest,metal,blend,masked,
             p[0],p[1],p[2],p[3]];
    }
}
- (void)testM58AlphaTest:(UIButton *)sender {
    (void)sender;
    if(!self.ready || self.shaderBusy)return;
    unsigned sw=(unsigned)((self.m58Attempts++ & 1u)!=0u);
    unsigned int p[4]={0},phase=0,guest=0,metal=0,alpha=0;
    self.status.text=@"M5.8: 5 DRAWs com alpha GREATER/LESS...";
    const int rc=ar_probe_m58_guest_alpha_test(
       sw,p,&phase,&guest,&metal,&alpha);
    if(!rc) {
        self.status.text=[NSString stringWithFormat:
            @"M5.8 ALPHA RSX → Metal: OK\n"
             "Layout %@ · 5 quadros GPU verificados\n"
             "DRAW RSX/Metal/alpha: %u/%u/%u\n"
             "GREATER/LESS e refs 0/128/255: OK\n"
             "Pixels: %08X %08X %08X %08X\n"
             "Aperte novamente para alternar layout.",
             sw?@"SWIZZLED":@"LINEAR",guest,metal,alpha,
             p[0],p[1],p[2],p[3]];
    } else {
        self.status.text=[NSString stringWithFormat:
            @"M5.8 ALPHA: FALHA %d · fase %u\n"
             "Layout %@ · DRAW RSX/Metal/alpha %u/%u/%u\n"
             "Pixels: %08X %08X %08X %08X\n"
             "M5.7/M5.6/M5.5 permanecem disponíveis.",
             rc,phase,sw?@"SWIZZLED":@"LINEAR",guest,metal,alpha,
             p[0],p[1],p[2],p[3]];
    }
}
/* Local read-only probe; data is temporary and never logged, persisted
 * into app storage, uploaded or packaged with its compiled code. */
/* F0: choose a folder in Files. No copy of GBs to sandbox; bookmarks,
 * manifest and first 4-byte host read remain strictly device-local.
 * A real LV2 sys_fs_open/read has NOT been observed yet. */
/* M7.39: fallback for folder-pickers whose "Abrir" never dispatches
 * didPickDocumentsAtURLs on this iPhone/file-provider combination.
 * Real native file enumeration stays off the main thread.
 */
- (void)importGameFolderFromDocuments:(UIButton *)sender {
  (void)sender;
  if(self.shaderBusy)return;
  self.status.text=@"Procurando NPUA80918 em Documentos do app; leitura somente…";
  dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{
    NSError *error=nil;
    NSDictionary *manifest=ARGameFolderImportLocalDocuments(&error);
    NSData *coverData=ARGameManifestHasTitleUsrdir(manifest)?[self gameCoverDataFromManifest:manifest]:nil;
    NSError *readError=nil;
    NSString *relative=manifest[@"probe_relative_path"];
    NSData *bytes=(manifest && relative.length>0u)?
        ARGameFolderReadPrefix(relative,4u,&readError):nil;
    NSString *report=manifest
      ? [NSString stringWithFormat:
         @"M7.50 F1 — PASTA LOCAL IMPORTADA / NO MEU IPHONE\n"
          "Raiz=%@ · arquivos=%@ · tamanho=%@ bytes\n"
          "Leitura nativa host=%lu byte(s) · %@\n"
          "Arquivo de amostra=%@\n"
          "NPUA80918 registrada no manifesto, sem cópia extra pelo app.\n"
          "cellFsOpen/cellFsRead do guest ainda NÃO demonstradas.\n",
           manifest[@"root_name"],manifest[@"file_count"],manifest[@"total_bytes"],
           (unsigned long)bytes.length,
           bytes.length?@"OK":readError.localizedDescription?:@"indisponível",
           relative?:@"não localizado"]
      : [NSString stringWithFormat:
         @"M7.50 F1 — PASTA LOCAL NÃO ENCONTRADA\n"
          "Erro (%@/%ld): %@\n"
          "Não mova a instalação original do RPCS3. Copie apenas os "
          "arquivos necessários para No Meu iPhone / AscensionRecomp Test / "
          "AscensionRecomp / NPUA80918. Depois toque Detectar pasta local.\n",
          error.domain?:@"local",(long)error.code,
          error.localizedDescription?:@"pasta ausente"];
    dispatch_async(dispatch_get_main_queue(),^{
      self.hasGameInstallation=ARGameManifestHasTitleUsrdir(manifest);
      self.m750HostObservation=(manifest && bytes.length)?
          [NSString stringWithFormat:
             @"comprovado: arquivo=%@; bytes_lidos_HOST=%lu; momento=%@; NOTA: NÃO é cellFsRead",
             relative?:@"NÃO MEDIDO",(unsigned long)bytes.length,
             [[NSDate date] description]]:nil;
      self.folderReport=report;
      self.gameInstallLabel.text=self.hasGameInstallation?
        [NSString stringWithFormat:@"NPUA80918 · %@ arquivos (HOST)",manifest[@"file_count"]?:@"?"]:
        @"Instalação não encontrada em Documents";
      UIImage *coverImage=coverData?[UIImage imageWithData:coverData]:nil;
      self.gameCoverView.image=coverImage;
      self.gameCoverView.hidden=(coverImage==nil);
      [self refreshNativeLaunchAvailability];
      self.status.text=report;
    });
  });
}
/* M7.47: import PARAM.SFO via GOWA.ELF's asCopy:YES mechanism.
 * Only a small, temporary user-selected metadata copy; NOT USRDIR access. */
- (void)importRPCS3Marker:(UIButton *)sender {
  (void)sender;
  self.status.text=@"M7.47: importe PARAM.SFO como o GOWA.ELF (uma cópia TEMPORÁRIA de até 64 KB). Selecione o arquivo e confirme Abrir; USRDIR continua protegido pelo iOS.";
  UIDocumentPickerViewController *picker=
       [[UIDocumentPickerViewController alloc]
             initForOpeningContentTypes:@[UTTypeItem] asCopy:YES];
  picker.delegate=self;
  /* User can explicitly select/mark one or more files in Files. */
  picker.allowsMultipleSelection=YES;
  picker.directoryURL=nil;
  self.rpcMarkerPicker=picker;
  [self.window.rootViewController presentViewController:picker
                                                animated:YES completion:nil];
}
- (void)importGameFolder:(UIButton *)sender {
  (void)sender;
  if(self.shaderBusy)return;
  self.status.text=@"Selecione a pasta NPUA80918 inteira no app Arquivos. O launcher salva apenas um manifesto local.";
  UIDocumentPickerViewController *picker=
    [[UIDocumentPickerViewController alloc]
      initForOpeningContentTypes:@[UTTypeFolder] asCopy:NO];
  picker.delegate=self;
  /* Explicit folder selection with Files multi-item selection. */
  picker.allowsMultipleSelection=YES;
  picker.directoryURL=nil; /* OS owns Recents: no hardcoded iCloud Drive. */
  self.folderPicker=picker;
  [self.window.rootViewController presentViewController:picker
                                                animated:YES completion:nil];
}
- (void)arPerformOnMain:(dispatch_block_t)block {
 if(!block)return;
 if([NSThread isMainThread])block();
 else dispatch_sync(dispatch_get_main_queue(),block);
}
- (void)arSetStatus:(NSString*)text {
 [self arPerformOnMain:^{
   self.status.text=text;
   self.ppuProgress=text?:@"";
   if(self.shaderBusy)self.ppuDiagnosticsButton.enabled=YES;
 }];
}
- (void)arPublishPpuSummary {
 [self arPerformOnMain:^{ self.status.text=self.ppuSummary; }];
}
- (void)importM59ELF:(UIButton*)sender {
 (void)sender;
 if(!self.ready||self.shaderBusy)return;
 self.status.text=@"Escolha o GOWA.ELF desta instalação. O app valida SHA-256 e metadados antes de habilitar Iniciar.";
 UIDocumentPickerViewController*picker=
   [[UIDocumentPickerViewController alloc] initForOpeningContentTypes:@[UTTypeData] asCopy:YES];
 picker.delegate=self;
 [self.window.rootViewController presentViewController:picker animated:YES completion:nil];
}
- (void)documentPicker:(UIDocumentPickerViewController*)controller
        didPickDocumentsAtURLs:(NSArray<NSURL*>*)urls {
 if(controller==self.rpcMarkerPicker){
    self.rpcMarkerPicker=nil;
    NSURL *marker=nil;
     for(NSURL *candidate in urls){
       if([candidate.lastPathComponent caseInsensitiveCompare:@"PARAM.SFO"]==NSOrderedSame){
         marker=candidate;break;
       }
     }
     if(!marker){
       self.status.text=@"M7.46.1: marque PARAM.SFO e confirme Abrir; nenhuma seleção válida foi recebida.";
       return;
     }
     self.status.text=@"M7.47: lendo PARAM.SFO pelo mecanismo de importação do GOWA.ELF…";
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{
      NSError *error=nil;
      NSDictionary *manifest=ARGameFolderInspectParamSFO(marker,&error);
       NSString *report=manifest
         ? [NSString stringWithFormat:
             @"M7.47 — PARAM.SFO IMPORTADO E VALIDADO\n"
              "TITLE_ID=%@ · %lu bytes\n"
              "Cópia temporária SOMENTE do PARAM.SFO, como GOWA.ELF.\n"
              "Arquivos grandes do jogo não foram copiados.\n"
              "Permissão USRDIR ainda NÃO obtida.\n"
              "cellFsOpen/cellFsRead ainda não demonstradas.\n",
              manifest[@"title_id"],(unsigned long)[manifest[@"file_bytes"] unsignedLongValue]]
         : [NSString stringWithFormat:
             @"M7.47 — FALHA NA IMPORTAÇÃO DO PARAM.SFO\n"
              "Erro (%@/%ld): %@\n",
              error.domain?:@"iOS",(long)error.code,
              error.localizedDescription?:@"arquivo indisponível"];
       dispatch_async(dispatch_get_main_queue(),^{
        self.folderReport=report;
        self.status.text=report;
        self.ppuDiagnosticsButton.enabled=YES;
      });
    });
    return;
 }
 if(controller==self.folderPicker){
    self.folderPicker=nil;
    NSURL *chosen=nil;
     for(NSURL *candidate in urls){
       if([candidate.lastPathComponent caseInsensitiveCompare:@"NPUA80918"]==NSOrderedSame){
         chosen=candidate;break;
       }
     }
     if(!chosen){
       self.status.text=@"Marque a pasta NPUA80918 inteira e confirme Abrir. Arquivos e pastas com outros nomes não são aceitos.";
       return;
     }
     self.status.text=@"M7.46.1: pasta marcada; verificando acesso somente leitura…";
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{
      NSError *error=nil;
      NSDictionary *manifest=ARGameFolderImport(chosen,&error);
      NSData *coverData=ARGameManifestHasTitleUsrdir(manifest)?[self gameCoverDataFromManifest:manifest]:nil;
      NSString *relative=manifest[@"probe_relative_path"];
      NSError *readError=nil;
      NSData *actual=(manifest && relative.length>0)?
          ARGameFolderReadPrefix(relative,4u,&readError):nil;
      NSString *report=nil;
      if(manifest){
        report=[NSString stringWithFormat:
           @"M7.37 F0 — PASTA DO JOGO IMPORTADA REALMENTE\n"
            "NPUA80918 · arquivos=%@ · bytes=%@\n"
            "Links simbólicos ignorados=%@\n"
            "Leitura HOST de prefixo=%lu byte(s) · %@\n"
            "Manifesto e bookmark SALVOS SOMENTE NO IPHONE.\n"
            "PS3 cellFsOpen/cellFsRead ainda NÃO executadas.\n",
            manifest[@"file_count"],manifest[@"total_bytes"],
            manifest[@"symlinks_skipped"],(unsigned long)actual.length,
            actual.length?@"OK":(readError.localizedDescription?:@"nenhum arquivo encontrado")];
      }
      dispatch_async(dispatch_get_main_queue(),^{
        if(report && ARGameManifestHasTitleUsrdir(manifest)){
          self.folderReport=report;
          self.hasGameInstallation=YES;
          UIImage *coverImage=coverData?[UIImage imageWithData:coverData]:nil;
          self.gameCoverView.image=coverImage;
          self.gameCoverView.hidden=(coverImage==nil);
          self.gameInstallLabel.text=[NSString stringWithFormat:@"NPUA80918 · %@ arquivos (HOST)",
                                      manifest[@"file_count"]?:@"?"];
          self.status.text=[NSString stringWithFormat:
                 @"Pasta de jogo selecionada.\n%@",report];
          [self refreshNativeLaunchAvailability];
        }else{
          self.gameCoverView.image=nil;
          self.gameCoverView.hidden=YES;
          NSString *detail=error.localizedDescription?:
              (manifest?@"A pasta escolhida precisa ser NPUA80918 e conter USRDIR.":@"sem acesso ao diretório");
          self.folderReport=[NSString stringWithFormat:
                @"M7.38 F0 — FALHA IMPORTAÇÃO PASTA\n"
                 "Erro (%@/%ld): %@\n"
                 "Selecione NPUA80918 e toque Abrir (azul) no topo.\n"
                 "Nenhum arquivo comercial foi enviado.\n",
                 error.domain?:@"sem domínio",(long)error.code,detail];
          self.status.text=[NSString stringWithFormat:
                 @"Importação da pasta falhou: %@\n"
                  "Tente selecionar NPUA80918 e toque Abrir.",detail];
          self.hasGameInstallation=NO;
          self.gameInstallLabel.text=@"Falha ao abrir a pasta do jogo";
          [self refreshNativeLaunchAvailability];
        }
      });
    });
    return;
 }
 (void)controller;
 NSURL*url=urls.firstObject;if(!url)return;
 [self acceptELFAtURL:url];
 return;
#if 0 /* Legacy M6 checkpoint chain was removed from the Play action. */
 self.shaderBusy=YES;
 ar_m772_runtime_begin();
 self.ppuReport=nil;self.ppuSummary=nil;self.ppuBatchReport=nil;self.m750Run=nil;
 self.ppuProgress=@"GOWA.ELF recebido; preparando leitura e validação.";
 self.ppuBatchButton.enabled=NO;
 [self.ppuBatchButton setTitle:@"Copiar lote PPC (até 32 instruções)" forState:UIControlStateNormal];
 self.ppuReportButton.enabled=NO;self.ppuAdvancedButton.enabled=NO;
 /* Keep live status/report available while native probes run off-main. */
 self.ppuDiagnosticsButton.enabled=YES;
 [self.ppuDiagnosticsButton setTitle:@"Relatório ao vivo · em execução"
                            forState:UIControlStateNormal];
 self.status.text=@"GOWA.ELF recebido · validando o executável e iniciando a prova de boot nativo em segundo plano…";
 dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{
   @try {
   NSError*err=nil;
   NSNumber*size=[[[NSFileManager defaultManager]
      attributesOfItemAtPath:url.path error:&err] objectForKey:NSFileSize];
   if(err||!size||size.unsignedLongLongValue>32u*1024u*1024u){
       [self arSetStatus:@"M5.9: Arquivo indisponível ou maior que 32 MB."];return;
   }
   NSData*data=[NSData dataWithContentsOfURL:url
       options:NSDataReadingMappedIfSafe error:&err];
   if(err||!data){[self arSetStatus:@"M5.9: Leitura falhou."];return;}
   uint32_t info[5]={0};
   int rc=ar_private_elf_inspect(data.bytes,data.length,info);
   if(rc){
       [self arSetStatus:[NSString stringWithFormat:
          @"M5.9: erro ELF %d. Use GOWA.ELF descriptografado.",rc]];return;
   }
   unsigned char hash[CC_SHA256_DIGEST_LENGTH]={0};
   CC_SHA256(data.bytes,(CC_LONG)data.length,hash);
   static const unsigned char expected[32]={
       0x4b,0xf7,0x5c,0x89,0x7b,0x82,0xd1,0xbe,
       0xb2,0x55,0x14,0xcb,0xad,0xaf,0xf3,0xd0,
       0x3e,0x1b,0x0c,0x7b,0xf8,0x49,0xfa,0x5d,
       0x28,0x9b,0xe4,0xf9,0x18,0x34,0x62,0xb5};
   if(data.length!=8717136u||memcmp(hash,expected,32)||
       info[0]!=0x8283f8u||info[1]!=0x10410u||info[2]!=0x83f2b0u){
       [self arSetStatus:@"M5.9: ELF não corresponde à NPUA80918 validada."];return;
   }
   unsigned int cpu[4]={0};
   const int cpu_rc=ar_ppu_bootstrap_four(data.bytes,data.length,info,cpu);
   if(cpu_rc){
      [self arSetStatus:[NSString stringWithFormat:
         @"M5.9 ELF VALIDADO; M6.0 PPU FALHA %d (%u/4).\n"
          "CPU interrompida antes de M6.1.",cpu_rc,cpu[0]]];
      return;
   }
   unsigned int eight[6]={0};
   const int rc8=ar_ppu_bootstrap_eight(data.bytes,data.length,info,eight);
   if(rc8) {
      [self arSetStatus:[NSString stringWithFormat:
         @"M5.9 NPUA80918: ELF REAL VALIDADO\n"
          "M6.0 PPU 4/4 OK · M6.1 PPU FALHA %d (%u/8).\n"
          "Parada segura, sem HLE nem gameplay.",rc8,eight[0]]];
      return;
   }
   if(eight[0]!=8u||eight[1]!=0x83f2b0u||eight[2]!=0x10534u||
      eight[3]!=0x10430u||eight[4]!=0x07000f90u||eight[5]!=2u) {
      [self arSetStatus:@"M6.1: estado PPU inesperado; execução interrompida."];
      return;
   }
   unsigned int cpu16[7]={0};
   const int rc16=ar_ppu_bootstrap_sixteen(data.bytes,data.length,info,cpu16);
   if(rc16){
      [self arSetStatus:[NSString stringWithFormat:
        @"M5.9 ELF VALIDADO · M6.0 4/4\n"
         "M6.1 PPU REAL 8/8: OK\n"
         "M6.2 PPU: FALHA %d (%u/16 instruções).\n"
         "Parada segura. HLE/SPU não iniciados.",
        rc16,cpu16[0]]];
      return;
   }
   if(cpu16[0]!=16u||cpu16[1]!=0x83f2b0u||
      cpu16[2]!=0x10554u||cpu16[3]!=0x10430u||
      cpu16[4]!=0x07000ef0u||cpu16[5]!=9u||
      cpu16[6]!=0x10430u){
      [self arSetStatus:@"M6.2: registradores ou pilha divergentes. Parada segura."];
      return;
   }
   [self arSetStatus:@"M6.2 PPU REAL 16/16: OK · M6.3 em execução..."];
    unsigned int cpu24[9]={0};
    const int rc24=ar_ppu_bootstrap_twentyfour(data.bytes,data.length,info,cpu24);
    if(rc24){
       [self arSetStatus:[NSString stringWithFormat:
          @"M5.9 NPUA80918: ELF REAL VALIDADO\n"
           "M6.2 PPU REAL 16/16: OK\n"
           "M6.3 PARADA SEGURA %d · %u/24\n"
           "PC=0x%X · opcode=0x%08X\n"
           "Sem HLE/SPU/gameplay; instrução não ignorada.",
           rc24,cpu24[0],cpu24[8],cpu24[7]]];
       return;
    }
    [self arSetStatus:@"M6.3 PPU REAL 24/24: OK · preparando continuação limitada M6.4..."];
    /* Do not start extra PPU instructions before M6.3 24/24 succeeds. */
    unsigned int cpu32[10]={0};
    const int rc32=ar_ppu_bootstrap_thirtytwo(data.bytes,data.length,info,cpu32);
    /* M6.5.3: the old M6.4 interpreter is stack-ONLY. Its -995 on
     * a valid stw must not block the NEW M6.5 guest PT_LOAD overlay.
     * Permit ONLY the diagnosed write-restriction case after the
     * proved 24-step checkpoint. Preserve all other fail-closed stops. */
    const BOOL legacyStackOnlyStop =
        rc32==-995 && cpu32[0]>=24u && (cpu32[7]>>26)==36u;
    if(rc32 && !legacyStackOnlyStop){
       [self arSetStatus:[NSString stringWithFormat:
          @"M5.9 NPUA80918: ELF REAL VALIDADO\n"
           "M6.3 PPU REAL 24/24: OK\n"
           "M6.4 PARADA SEGURA %d · %u/32\n"
           "PC=0x%X · opcode=0x%08X\n"
           "M6.5 não iniciada: erro não é de memória convidada.",
           rc32,cpu32[0],cpu32[8],cpu32[7]]];
       return;
    }
    NSString *legacyState=legacyStackOnlyStop
       ? [NSString stringWithFormat:@"M6.4 LEGADA: -995 (%u/32) · transferida à M6.5",
                                    cpu32[0]]
       : @"M6.4 PPU REAL 32/32: OK";
    [self arSetStatus:[NSString stringWithFormat:@"%@ · M6.5 em execução (40 instruções)...",legacyState]];
    unsigned int cpu40[16]={0};
    const int rc40=ar_ppu_bootstrap_forty(data.bytes,data.length,info,cpu40);
    /* M6.6: only the documented mtctr opcode missing in the M6.5
     * sandbox can be retried by the new 48-step CTR-aware sandbox.
     * Other unknown opcodes, guest memory faults, and invalid accesses
     * remain fail-closed. We must NOT pretend M6.5 achieved 40/40. */
    const unsigned sprField=(cpu40[7]>>11)&1023u;
    const unsigned guestSpr=((sprField&31u)<<5)|(sprField>>5);
    const BOOL knownMtctrStop =
        rc40==-990 && cpu40[0]>=32u && (cpu40[7]>>26)==31u &&
        ((cpu40[7]>>1)&1023u)==467u &&
        guestSpr==9u && !(cpu40[7]&1u);
    if(rc40 && !knownMtctrStop){
       [self arSetStatus:[NSString stringWithFormat:
           @"M5.9 NPUA80918: ELF REAL VALIDADO\n"
            "M6.3 PPU REAL 24/24: OK\n"
            "%@\n"
            "M6.5 PARADA SEGURA %d · %u/40\n"
            "PC=0x%X · opcode=0x%08X\n"
            "%@\n"
            "Sem HLE/SPU/gameplay.",
            legacyState,rc40,cpu40[0],cpu40[8],cpu40[7],
            ((rc40<=-1001 && rc40>=-1005) ? [NSString stringWithFormat:@"EA=0x%X · base=0x%X · valor=0x%X",
                          cpu40[10],cpu40[11],cpu40[12]] :
             @"Sem falha de memória nesta instrução")]];
       return;
    }
    NSString *old40State=knownMtctrStop ?
        [NSString stringWithFormat:@"M6.5 LEGADA: mtctr (%u/40) · transferida à M6.6",
                                   cpu40[0]] :
        @"M6.5 PPU REAL 40/40: OK";
    unsigned int cpu48[20]={0};
    unsigned int trace48[24]={0};
    unsigned int detail48[24]={0};
    unsigned int tls48[12]={0};
    [self arSetStatus:[NSString stringWithFormat:@"%@ · M6.6 em execução (48 instruções)...",old40State]];
    const int rc48=ar_ppu_bootstrap_fortyeight_trace_m674(
        data.bytes,data.length,info,cpu48,trace48,detail48,tls48);

    unsigned int native[16]={0};
    /* A PS3 title ELF is not a complete install. Starting the full 256 MiB
     * guest and native PPU entry with no authorized USRDIR gives the game no
     * files to open, and on LiveContainer can look like a frozen app. Check
     * the persisted Files.app grant and indexed title layout first. */
    NSError *gameFolderError=nil;
    NSDictionary *gameManifest=ARGameFolderRestore(&gameFolderError);
    NSArray<NSDictionary *> *gameFiles=[gameManifest[@"files"] isKindOfClass:NSArray.class]
        ? gameManifest[@"files"] : @[];
    NSString *gameRootName=[gameManifest[@"root_name"] isKindOfClass:NSString.class]
        ? gameManifest[@"root_name"] : @"";
    BOOL hasUSRDIR=([gameRootName caseInsensitiveCompare:@"USRDIR"]==NSOrderedSame);
    unsigned long long gameBytes=0;
    NSUInteger psarcCount=0;
    for(NSDictionary *entry in gameFiles){
      NSString *relative=[entry[@"path"] isKindOfClass:NSString.class]
          ? entry[@"path"] : @"";
      if([relative caseInsensitiveCompare:@"USRDIR"]==NSOrderedSame ||
         [relative.lowercaseString hasPrefix:@"usrdir/"])hasUSRDIR=YES;
      NSNumber *length=[entry[@"bytes"] isKindOfClass:NSNumber.class]
          ? entry[@"bytes"] : @0;
      gameBytes+=length.unsignedLongLongValue;
      if([relative.pathExtension.lowercaseString isEqualToString:@"psarc"])
        psarcCount++;
    }
    const BOOL gameReady=gameFiles.count>0 && hasUSRDIR;
    int nativeRC=-74; /* no selected/indexed NPUA80918 USRDIR */
    if(gameReady){
      [self arSetStatus:[NSString stringWithFormat:
        @"Instalação reconhecida: %@ · %lu arquivos · %.2f GiB · %lu PSARC. Preparando PS3Recomp nativo (29.849 PPU / 4 SPU ELFs + WWS PM NPUA); AOT legado fora do caminho desta execução...",
        gameRootName,(unsigned long)gameFiles.count,
        (double)gameBytes/(1024.0*1024.0*1024.0),(unsigned long)psarcCount]];
      nativeRC=ar_m70_native_runtime_probe(
         data.bytes,data.length,detail48[8],native);
      [self arSetStatus:[NSString stringWithFormat:@"Despacho AOT terminou (rc=%d) · reunindo evidências guest...",nativeRC]];
    }else{
      native[6]=(uint32_t)nativeRC;
      NSString *why=gameFolderError.localizedDescription?:
          @"A pasta selecionada não contém arquivos USRDIR reconhecíveis.";
      [self arSetStatus:[NSString stringWithFormat:
        @"ELF validado; runtime pesado pausado. %@ Selecione a pasta NPUA80918 do jogo (com USRDIR) em ‘Selecionar pasta’ e importe o ELF novamente.",why]];
    }
    ar_fs_trace fsMeasured={0};
    ar_m751_last_fs_trace(&fsMeasured);
    ar_m767_import_evidence importMeasured={0};
    ar_m767_last_import_evidence(&importMeasured);
    uint32_t m769Stats[5]={0};
    ar_m769_last_install_stats(m769Stats);
    ar_m756_stop_evidence ownerStop={0};
    ar_m756_last_stop_evidence(&ownerStop);
    ar_m756_stop_evidence origin={0};
    ar_m756_last_origin_evidence(&origin);
    NSMutableString *originElfHex=[NSMutableString string];
    NSMutableString *originGuestHex=[NSMutableString string];
    for(unsigned i=0;i<origin.count&&i<AR_M756_SAMPLE_BYTES;i++){
      [originElfHex appendFormat:@"%02X",origin.elf_bytes[i]];
      if(origin.guest_status==AR_OK)[originGuestHex appendFormat:@"%02X",origin.guest_bytes[i]];
    }
    NSMutableString *elfHex=[NSMutableString string];
    NSMutableString *guestHex=[NSMutableString string];
    for(unsigned i=0;i<ownerStop.count&&i<AR_M756_SAMPLE_BYTES;i++){
      [elfHex appendFormat:@"%02X",ownerStop.elf_bytes[i]];
      if(ownerStop.guest_status==AR_OK)
        [guestHex appendFormat:@"%02X",ownerStop.guest_bytes[i]];
    }
    NSString *nativeText=[NSString stringWithFormat:
       @"\nM7.0 — RUNTIME PPU NATIVO (ELF privado)\n"
       "Loader=%d · Entrada=0x%08X · TOC=0x%08X · segmentos=%u\n"
       "Capacidade VM=%u · arquivo mapeado=%u · funções AOT=%u\n"
       "Import PRX=%d · bind import=%d · bind HLE=%d\n"
       "Instalação reconhecida=%@ · arquivos=%lu · bytes=%llu · PSARC=%lu\n"
       "Teste HLE TLS nativa=%d · r13=0x%08X\n"
       "Despacho AOT nativo=%d · primeiro PC pendente=0x%08X\n"
       "ABI de processo PS3 (thread principal/TLS/argv)=%@\n"
       "Opcode inicial guest=0x%08X · evidências=0x%X\n"
       "AR_UNRESOLVED=-3: PC guest sem ARM64 registrado; AOT ONLY proíbe fallback.\n",
       nativeRC,native[1],native[2],native[3],
       native[4],native[13],native[5],
       (int)native[8],(int)native[9],(int)native[10],
       gameReady?@"SIM (USRDIR)":@"NÃO (M7.0 não iniciado)",
       (unsigned long)gameFiles.count,gameBytes,(unsigned long)psarcCount,
       (int)native[11],native[12],
       (int)native[6],native[7],(native[15]&0x4000u)?@"PREPARADO":@"AUSENTE",
       native[14],native[15]];

    unsigned int continuous[16]={0};
    unsigned int importEvidence[16]={0};
    char discoveredLibrary[48]={0};
    const int execRC=ar_m73_private_import_probe(
        data.bytes,data.length,detail48[8],4096u,continuous,
        importEvidence,discoveredLibrary);
    [self arSetStatus:@"Diagnóstico PPU/AOT finalizado · publicando relatório..."];
    NSString *lwMutexText=[NSString stringWithFormat:
       @"\nM7.7 — HLE PS3 / sys_lwmutex_create (NID 0x2F85C0EF)\n"
        "Import PRX reconhecido=%@ · HLE vinculado=%@\n"
        "Mutex LV2 big-endian; serviço não equivale a gameplay.\n",
        (native[15]&16u)?@"SIM":@"NÃO",
        (native[15]&32u)?@"SIM":@"NÃO"];
    NSString *continuousText=[NSString stringWithFormat:
       @"\nM7.2 — EXECUÇÃO PPU CONTÍNUA + CR/BRANCH (INTERPRETADOR NATIVO ASSINADO)\n"
        "Preparação=%d · resultado guest=%d · passos=%u / orçamento 4096\n"
        "Último PC=0x%08X · opcode=0x%08X · PC anterior=0x%08X\n"
        "HLEs reais=%u · r13=0x%08X · LR=0x%08X · CTR=0x%08X\n"
        "Falha EA/syscall=0x%08X · NID=0x%08X · stub=0x%08X\n"
        "Thread=%u · VM=%u · funções ARM64 AOT=%u\n"
        "Motivos: -1310 orçamento; -1311 ISA ausente; -1312 destino não executável;"
        " -1313 memória; -1314 HLE/indireto; -1315 HLE falhou.\n"
        "INTERPRETAÇÃO NÃO É RECOMPILAÇÃO AOT: esta trilha M7.2"
        " é interpretada, independentemente do AOT compilado na M7.6.\n",
        execRC,(int)continuous[0],continuous[1],
        continuous[2],continuous[3],continuous[10],
        continuous[5],continuous[6],continuous[7],continuous[8],
        continuous[9],continuous[12],continuous[13],
        continuous[14],continuous[15],continuous[11]];
    NSString *importReport=[NSString stringWithFormat:
       @"\nM7.3 — IMPORTAÇÃO PRX NA PARADA REAL\n"
        "Falha bctrl em PC=0x%08X · r12/stub candidato=0x%08X\n"
        "CTR=0x%08X · r2=0x%08X · r0=0x%08X\n"
        "Bytes do stub: palavra0=0x%08X · palavra1=0x%08X\n"
        "PRX status=%d · NID=0x%08X · biblioteca=%s\n"
        "Metadados: importações examinadas=%u · bibliotecas=%u\n"
        "Validação=0x%X (1=código ELF X, 2=CTR, 4=TOC, 8=PRX, 16=tudo)\n"
        "Argumentos reais: r3=0x%08X r4=0x%08X r5=0x%08X r6=0x%08X\n"
        "Somente leitura: importação desconhecida NÃO executada.\n",
        importEvidence[0],importEvidence[1],
        importEvidence[2],importEvidence[3],importEvidence[15],
        importEvidence[4],importEvidence[5],
        (int)importEvidence[7],importEvidence[6],
        discoveredLibrary[0]?discoveredLibrary:"(não identificada)",
        importEvidence[9],importEvidence[10],importEvidence[8],
        importEvidence[11],importEvidence[12],
        importEvidence[13],importEvidence[14]];
    /* Primary status is derived ONLY from actual signed ARM64 guest
     * AOT dispatch, not the older 48/108-step interpreter reports. */
    uint32_t pendingImport[4]={0};
    char pendingLibrary[48]={0};
    int pendingMatch=(((int)native[6]==-3 || (int)native[6]==-12 || (int)native[6]==-13) && native[7]) ?
       ar_private_import_match(data.bytes,data.length,native[7],
                               pendingImport,pendingLibrary) : -1;
    /* Real unresolved PPC instruction window, read-only (no fallback). */
    uint32_t missingWords[6]={0};
    const int missingRead=(((int)native[6]==-3 || (int)native[6]==-12 || (int)native[6]==-13) && pendingMatch!=0 && native[7]) ?
        ar_m712_exec_window(data.bytes,data.length,native[7],missingWords) : -1;
    NSString *pendingText=nil;
    BOOL needsAOT=((int)native[6]==-3 || (int)native[6]==-12 || (int)native[6]==-13);
    if(needsAOT && pendingMatch==0){
      pendingText=[NSString stringWithFormat:
        @"Import PRX pendente: %s · NID=0x%08X\nStub=0x%08X",
        pendingLibrary[0]?pendingLibrary:"(sem nome)",
        pendingImport[0],native[7]];
    } else if(needsAOT && missingRead==0) {
      pendingText=[NSString stringWithFormat:
        @"AOT pendente: 0x%08X · opcode PPC=0x%08X\n"
         "Sem ARM64 registrado; dispatcher=%d (NÃO é fallback).",
        native[7],missingWords[0],(int)native[6]];
    } else if(needsAOT) {
      pendingText=[NSString stringWithFormat:
        @"AOT pendente: 0x%08X · janela PPC indisponível (%d).",
        native[7],missingRead];
    } else {
      pendingText=[NSString stringWithFormat:
        @"Último resultado do despachante: %d",(int)native[6]];
    }
    /* M7.14: collect verified executable PPC words in the clipboard report
     * for a subsequent private AOT batch; this never executes guest code. */
    NSString *frontierReport=@"\nM7.14 · nenhum lote PPC coletado.";
    if(((int)native[6]==-3 || (int)native[6]==-12 || (int)native[6]==-13) && native[7] && pendingMatch!=0){
       unsigned int batchWords[32]={0},batchCount=0,batchEnd=0;
       int batchRC=ar_m714_frontier_inventory(
           data.bytes,data.length,native[7],batchWords,&batchCount,&batchEnd);
       NSMutableString *batch=[NSMutableString stringWithFormat:
           @"\nM7.14 — LOTE PPC somente leitura\n"
            "PC inicial=0x%08X · resultado=%d · palavras=%u/32\n"
            "Primeiro desvio/syscall=0x%08X (0=não encontrado)\n",
           native[7],batchRC,batchCount,batchEnd];
       for(unsigned int ix=0;ix<batchCount;ix++){
          [batch appendFormat:@"0x%08X: %08X\n",native[7]+4u*ix,batchWords[ix]];
       }
       /* Two successor addresses derived only from the authenticated BEQ
        * executable word; the alternate path is READ-ONLY, not executed. */
       unsigned int paths[2]={0};
       if(ar_m716_verified_successors(data.bytes,data.length,paths)==0 &&
          (native[7]==paths[0] || native[7]==paths[1])){
          unsigned int alternative=(native[7]==paths[0]) ? paths[1]:paths[0];
          unsigned int altWords[32]={0},altCount=0,altTerm=0;
          int altRC=ar_m714_frontier_inventory(data.bytes,data.length,
                                  alternative,altWords,&altCount,&altTerm);
          [batch appendFormat:
              @"\nM7.16 — RAMIFICAÇÃO AUTENTICADA\n"
               "Desvio original=0x003C4DFC · beq 0x41820018\n"
               "Caminho realmente escolhido pelo PPU=0x%08X\n"
               "Caminho alternativo SOMENTE LEITURA=0x%08X\n"
               "Resultado alternativo=%d · palavras=%u/32 · desvio=0x%08X\n",
                native[7],alternative,altRC,altCount,altTerm];
          for(unsigned int ax=0;ax<altCount;ax++){
             [batch appendFormat:@"0x%08X: %08X\n",
                    alternative+4u*ax,altWords[ax]];
          }
       }
       [batch appendString:
           @"Inventário PPC SOMENTE LEITURA; nenhuma instrução interpretada.\n"
            "Limite gráfico: PPU ainda sem comandos RSX reais do Ascension.\n"
            "M4/M5 são testes sintéticos Metal, não menu do jogo.\n"];
       frontierReport=batch;
    }
    /* M7.17: distinguish actually executed ARM64 AOT entrypoints from
     * possible static PPC edges. This operates on the locally imported,
     * already SHA-256-authenticated owner ELF. No code is executed here. */
    ar_aot_trace measured={0};
    ar_m717_last_aot_trace(&measured);
    if(nativeRC==AR_OK && native[5]>0u) {
      uint32_t lastAot=measured.trace_count?
          measured.trace_pcs[measured.trace_count-1u]:0u;
      self.m750Run=@{@"aot":@(native[5]),
          @"unique":@(measured.unique_aot),
          @"dispatches":@(measured.aot_dispatches),
          @"fallback":@(measured.fallback_steps),
          @"limit":@(measured.fallback_step_limit),
          @"stop":@(native[7]),
          @"m767_stop_reason":@(measured.m767_fail_reason),
          @"m767_fail_pc":@(measured.m767_fail_pc),
          @"m767_import_stub":@(importMeasured.stub),
          @"m767_import_nid":@(importMeasured.nid),
          @"m767_import_verified":@(importMeasured.matched),
          @"m767_import_pre_slot":@(importMeasured.slot_pre_be),
          @"m767_import_post_slot":@(importMeasured.slot_post_be),
          @"m767_import_hle_calls":@(measured.m767_hle_calls),
          @"m767_import_hle_success":@(measured.m767_hle_success),
          @"opcode":@(ownerStop.guest_word),
          @"origin_elf_rc":@(origin.elf_status),
          @"origin_guest_rc":@(origin.guest_status),
          @"origin_word":@(origin.elf_word),
          @"origin_ram_word":@(origin.guest_word),
          @"origin_offset":[NSString stringWithFormat:@"0x%llX",
                                       (unsigned long long)origin.file_offset],
          @"origin_match":(origin.elf_status==AR_OK&&origin.guest_status==AR_OK)?
                          (origin.match?@"IGUAIS":@"DIFERENTES"):@"NÃO MEDIDO",
          @"origin_elf_hex":origin.elf_status==AR_OK?originElfHex:@"NÃO MEDIDO",
          @"origin_ram_hex":origin.guest_status==AR_OK?originGuestHex:@"NÃO MEDIDO",
          @"stop_elf_rc":@(ownerStop.elf_status),
          @"stop_guest_rc":@(ownerStop.guest_status),
          @"stop_elf_word":@(ownerStop.elf_word),
          @"stop_seg_va":[NSString stringWithFormat:@"0x%llX",
                                 (unsigned long long)ownerStop.segment_va],
          @"stop_seg_offset":[NSString stringWithFormat:@"0x%llX",
                                 (unsigned long long)ownerStop.segment_file_offset],
          @"stop_seg_filesz":[NSString stringWithFormat:@"0x%llX",
                                 (unsigned long long)ownerStop.segment_file_size],
          @"stop_file_offset":[NSString stringWithFormat:@"0x%llX",
                                 (unsigned long long)ownerStop.file_offset],
          @"stop_count":@(ownerStop.count),
          @"stop_match":(ownerStop.elf_status==AR_OK &&
                          ownerStop.guest_status==AR_OK)?
                          (ownerStop.match?@"IGUAIS":@"DIFERENTES"):@"NÃO MEDIDO",
          @"stop_elf_hex":ownerStop.elf_status==AR_OK?elfHex:@"NÃO MEDIDO",
          @"stop_guest_hex":ownerStop.guest_status==AR_OK?guestHex:@"NÃO MEDIDO",
          @"last_aot":@(lastAot),
          @"fs_open_calls":@(fsMeasured.open_calls),
          @"fs_opens":@(fsMeasured.open_ok),
          @"fs_read_calls":@(fsMeasured.read_calls),
          @"fs_last_error":@(fsMeasured.last_error),
          @"fs_reads":@(fsMeasured.read_ok),
          @"fs_bytes":@(fsMeasured.bytes_read),
          @"fs_fd":@(fsMeasured.last_fd),
          @"fs_path":[NSString stringWithUTF8String:fsMeasured.last_path]?:@"",
          @"rc":@((int32_t)native[6]),
          @"when":[[NSDate date] description]};
    }
    uint32_t roots[10]={0},nr=0;
    if(native[7])roots[nr++]=native[7];
    if(native[1])roots[nr++]=native[1];
    for(uint32_t i=0;i<measured.trace_count && nr<10u;i++){
       const uint32_t at=measured.trace_count-1u-i;
       const uint32_t pc=measured.trace_pcs[at];
       BOOL seen=NO;
       for(uint32_t j=0;j<nr;j++)if(roots[j]==pc)seen=YES;
       if(pc && !seen)roots[nr++]=pc;
    }
    ar_m717_graph graph={0};
    int graphRC=(nr && nativeRC==0) ?
       ar_m717_walk(data.bytes,data.length,roots,nr,2048u,&graph):-1;
    NSMutableString *graphReport=[NSMutableString stringWithFormat:
      @"\nM7.17 — COBERTURA ARM64 REAL + GRAFO PPC ESTÁTICO\n"
       "Entradas vinculadas=%u · despachos ARM64 executados=%u\n"
       "Entradas ARM64 distintas executadas=%u · HLEs executadas=%u\n"
       "Último AOT sem tradução=0x%08X · orçamento nativo=%u\n"
       "Grafo PPC somente leitura: resultado=%d · nós=%u/2048\n"
       "Arestas possíveis=%u · chamadas diretas=%u · condicionais=%u\n"
       "Desvios indiretos=%u · syscalls=%u · PCs inválidos=%u · limite=%u\n"
       "Candidatos de chamadas diretas confirmados em PT_LOAD X=%u\n",
       native[5],measured.aot_dispatches,measured.unique_aot,
       measured.hle_dispatches,measured.unresolved_pc,
       measured.max_budget,graphRC,graph.inspected,graph.edges,
       graph.direct_calls,graph.conditional,graph.indirect,
       graph.syscalls,graph.invalid_pc,graph.saturated,graph.call_count];
    for(uint32_t gi=0;gi<graph.call_count;gi++){
       [graphReport appendFormat:@"CALL_CANDIDATE 0x%08X\n",graph.calls[gi]];
    }
    [graphReport appendString:
       @"CALL_CANDIDATE é um destino de salto observado no ELF, NÃO"
        " uma função recompilada ou executada. Cobertura percentual do"
        " jogo ainda desconhecida. Nenhum RSX real demonstrado.\n"];
    /* M7.61 trace productivity: first-visit order survives hot loops,
     * run-length recent trace records last transitions instead of last raw
     * 64 dispatches. All fields are copied from the iPhone PPU dispatcher. */
    [graphReport appendFormat:
       @"\nTELEMETRIA AOT ATUAL (IPHONE, SEM INTERPRETADOR)\n"
        "PC PENDENTE=0x%08X | AOT imediatamente anterior=0x%08X\n"
        "CR=0x%08X XER=0x%08X | LR=0x%llX CTR=0x%llX\n"
        "r1=0x%llX r2/TOC=0x%llX r3=0x%llX\n"
        "AOT primeiras visitas=%u/%u (capacidade %u)\n"
        "Transições compactadas=%u/%u (últimas %u)\n",
       measured.unresolved_pc,measured.stop_previous_aot,
       measured.stop_cr,measured.stop_xer,
       (unsigned long long)measured.stop_lr,
       (unsigned long long)measured.stop_ctr,
       (unsigned long long)measured.stop_r1,
       (unsigned long long)measured.stop_r2,
       (unsigned long long)measured.stop_r3,
       measured.first_count,measured.first_total,AR_AOT_TRIAGE_FIRST,
       measured.run_count,measured.run_total,AR_AOT_TRIAGE_RUNS];
    [graphReport appendFormat:
       @"AOT_TAIL ORIGEM=0x%08X DESTINO=0x%08X HANDLER_ARM64=%@ TRANSFERENCIAS=%u\n"
        "AOT_TAIL PRIMEIRO_DESTINO_SEM_HANDLER origem=0x%08X destino=0x%08X\n",
       measured.tail_source,measured.tail_target,
       measured.tail_target_has_native?@"SIM":@"NÃO",
       measured.tail_count,
       measured.first_unlinked_tail_source,measured.first_unlinked_tail_target];
    [graphReport appendFormat:
       @"M7.67 IMPORT PRX ORIGINAL stub=0x%08X module=%s NID=0x%08X "
        "ambos sentidos=%@ reverse_rc=%d forward_rc=%d vinculado=%d HLE_link=%d\n"
        "M7.67 SLOT GUEST 0x%08X BEFORE=0x%08X (rc=%d) AFTER=0x%08X (rc=%d)\n"
        "M7.67 HLE_EXEC chamadas=%u sucesso=%u stub=0x%08X nid=0x%08X result=%d "
        "guest_lr_pre=0x%llX guest_toc_pre=0x%llX r3_before=0x%llX r3_after=0x%llX\n"
        "M7.67 STOP PC_CONSERVADO=0x%08X motivo=%u handler_que_retorna_erro=0x%08X "
        "PC_NATIVE_OUT=0x%08X rc=%d\n",
       importMeasured.stub,importMeasured.module,importMeasured.nid,
       importMeasured.matched?@"SIM":@"NÃO",importMeasured.reverse_status,
       importMeasured.forward_status,importMeasured.bind_status,
       importMeasured.hle_status,
       importMeasured.slot_va,importMeasured.slot_pre_be,importMeasured.slot_pre_status,
       importMeasured.slot_post_be,importMeasured.slot_post_status,
       measured.m767_hle_calls,measured.m767_hle_success,measured.m767_hle_stub,
       measured.m767_hle_nid,measured.m767_hle_result,
       (unsigned long long)measured.m767_hle_pre_lr,
       (unsigned long long)measured.m767_hle_pre_toc,
       (unsigned long long)measured.m767_hle_pre_r3,
       (unsigned long long)measured.m767_hle_post_r3,
       measured.m767_fail_pc,measured.m767_fail_reason,
       measured.m767_failed_handler_pc,native[7],(int32_t)native[6]];
    [graphReport appendFormat:
       @"M7.68 HLE-RETORNO-NATIVO: origem tail HLE-lookups=%u encontrados=%u "
        "retornos ao LR do guest=%u ultimo_lr=0x%08X retorno_arm64=%@ "
        "ultima_entrada_por_tail=%u nested_depth=%u\n"
        "M7.68 PARADA PROFUNDA: PC=0x%08X motivo=%u, LR=0x%llX TOC=0x%llX "
        "CR=0x%08X CTR=0x%llX; distinguir retorno guest/erro após HLE\n",
       measured.m768_tail_hle_lookup_count,
       measured.m768_tail_hle_found_count,
       measured.m768_hle_return_count,
       measured.m768_last_hle_return_pc,
       measured.m768_hle_return_native?@"SIM":@"NÃO",
       measured.m768_last_hle_entry_from_tail,
       measured.m768_last_hle_depth,
       measured.m767_fail_pc,measured.m767_fail_reason,
       (unsigned long long)measured.stop_lr,
       (unsigned long long)measured.stop_r2,measured.stop_cr,
       (unsigned long long)measured.stop_ctr];
    [graphReport appendFormat:
       @"M7.69 ASCENSION CFG ESCALA: 5437 blocos originais C->ARM64 em lote; "
        "novos AOT autenticados e registrados=%u; duplicados prévios=%u; "
        "veneer PRX protegido=%u; RAM inacessível=%u; SHA RAM divergente=%u; "
        "AOT distintas realmente executadas=%u; sem fallback PPC=%u\n",
       m769Stats[0],m769Stats[1],m769Stats[2],m769Stats[3],
       m769Stats[4],measured.unique_aot,measured.fallback_steps];
    NSMutableArray *firstVisits=[NSMutableArray arrayWithCapacity:measured.first_count];
    for(uint32_t i=0;i<measured.first_count;i++){
       NSString *pc=[NSString stringWithFormat:@"0x%08X",measured.first_pcs[i]];
       [firstVisits addObject:pc];
       [graphReport appendFormat:@"AOT_FIRST %u %@\n",i,pc];
    }
    NSMutableArray *runs=[NSMutableArray arrayWithCapacity:measured.run_count];
    for(uint32_t i=0;i<measured.run_count;i++){
       NSString *pc=[NSString stringWithFormat:@"0x%08X",measured.run_pcs[i]];
       NSNumber *times=@(measured.run_repetitions[i]);
       [runs addObject:@{@"pc":pc,@"hits":times}];
       [graphReport appendFormat:@"AOT_RUN %@ x%@\n",pc,times];
    }
    NSDictionary *triage=@{
      @"schema":@"ascension-aot-triage-1",
      @"source":@"iphone-native-ppu-dispatcher",
      @"first_aot":firstVisits,@"recent_runs":runs,
      @"missing_pc":[NSString stringWithFormat:@"0x%08X",measured.unresolved_pc],
      @"previous_aot":[NSString stringWithFormat:@"0x%08X",measured.stop_previous_aot],
      @"cr":@(measured.stop_cr),@"xer":@(measured.stop_xer),
      @"lr":@(measured.stop_lr),@"ctr":@(measured.stop_ctr),
      @"r1":@(measured.stop_r1),@"r2":@(measured.stop_r2),
      @"r3":@(measured.stop_r3),
      @"linked_aot":@(native[5]),
      @"distinct_aot":@(measured.unique_aot),
      @"aot_dispatches":@(measured.aot_dispatches),
      @"tail_count":@(measured.tail_count),
      @"tail_source":[NSString stringWithFormat:@"0x%08X",measured.tail_source],
      @"tail_target":[NSString stringWithFormat:@"0x%08X",measured.tail_target],
      @"tail_target_native":@(measured.tail_target_has_native),
      @"first_unlinked_tail_target":[NSString stringWithFormat:@"0x%08X",measured.first_unlinked_tail_target],
      @"m767_fail_pc":[NSString stringWithFormat:@"0x%08X",measured.m767_fail_pc],
      @"m767_fail_reason":@(measured.m767_fail_reason),
      @"m769_offline_full_blocks":@5437,
      @"m769_authenticated_new":@(m769Stats[0]),
      @"m769_already_registered":@(m769Stats[1]),
      @"m769_prx_hle_protected":@(m769Stats[2]),
      @"m769_guest_ram_unreadable":@(m769Stats[3]),
      @"m769_guest_ram_sha_mismatch":@(m769Stats[4]),
      @"m768_hle_return_count":@(measured.m768_hle_return_count),
      @"m768_hle_return_native":@(measured.m768_hle_return_native),
      @"m768_last_hle_return_pc":[NSString stringWithFormat:@"0x%08X",measured.m768_last_hle_return_pc],
      @"m768_tail_hle_lookup_count":@(measured.m768_tail_hle_lookup_count),
      @"m768_tail_hle_found_count":@(measured.m768_tail_hle_found_count),
      @"m768_hle_entry_from_tail":@(measured.m768_last_hle_entry_from_tail),
      @"m768_hle_depth":@(measured.m768_last_hle_depth),
      @"m767_failed_handler_pc":[NSString stringWithFormat:@"0x%08X",measured.m767_failed_handler_pc],
      @"prx_module":[NSString stringWithUTF8String:importMeasured.module],
      @"prx_nid":[NSString stringWithFormat:@"0x%08X",importMeasured.nid],
      @"prx_stub":[NSString stringWithFormat:@"0x%08X",importMeasured.stub],
      @"prx_verified":@(importMeasured.matched),
      @"guest_slot_pre":[NSString stringWithFormat:@"0x%08X",importMeasured.slot_pre_be],
      @"guest_slot_post":[NSString stringWithFormat:@"0x%08X",importMeasured.slot_post_be],
      @"guest_slot_pre_rc":@(importMeasured.slot_pre_status),
      @"guest_slot_post_rc":@(importMeasured.slot_post_status),
      @"hle_call_count":@(measured.m767_hle_calls),
      @"hle_success_count":@(measured.m767_hle_success),
      @"hle_result":@(measured.m767_hle_result),
      @"hle_stub":[NSString stringWithFormat:@"0x%08X",measured.m767_hle_stub],
      @"hle_nid":[NSString stringWithFormat:@"0x%08X",measured.m767_hle_nid],
      @"fallback_steps":@(measured.fallback_steps),
      @"first_truncated":@(measured.first_total>measured.first_count),
      @"runs_truncated":@(measured.run_total>measured.run_count),
      @"guest_fs_open_calls":@(fsMeasured.open_calls),
      @"guest_fs_read_calls":@(fsMeasured.read_calls),
      @"guest_fs_positive_bytes":@(fsMeasured.bytes_read)};
    NSData *triageData=[NSJSONSerialization dataWithJSONObject:triage
                               options:NSJSONWritingSortedKeys error:NULL];
    if(triageData.length){
      NSString *oneLine=[[NSString alloc] initWithData:triageData
                                              encoding:NSUTF8StringEncoding];
      if(oneLine.length)[graphReport appendFormat:@"AOT_TRIAGE_JSON=%@\n",oneLine];
    }
    /* Keep a short raw tail solely for backward compatibility. */
    [graphReport appendString:@"Últimos até 16 despachos brutos de AOT:\n"];
    const uint32_t rawStart=measured.trace_count>16u?measured.trace_count-16u:0u;
    for(uint32_t ti=rawStart;ti<measured.trace_count;ti++)
       [graphReport appendFormat:@"AOT_EXEC 0x%08X\n",measured.trace_pcs[ti]];
    /* M7.20 separate experimental PPC fallback metrics; these do not
     * affect AOT registered/executed counters. Unknown ISA must stop. */
    [graphReport appendFormat:
      @"\nM7.20 — DESPACHO HÍBRIDO EXPERIMENTAL (SEM JIT)\n"
       "Despachos ARM64 executados=%u · passos PPC interpretados=%u/%u\n"
       "Último PPC interpretado=0x%08X · opcode=0x%08X\n"
       "Primeiro PPC não suportado=0x%08X · opcode=0x%08X\n"
       "Resultado híbrido=%d · próximo PC pendente=0x%08X\n"
       "M7.26: BL aninhado, primeira chamada falha PC=0x%08X -> 0x%08X\n"
       "Fallback NÃO é AOT; interpretação não aumenta contagem ARM64.\n"
       "Ainda sem comandos RSX reais do Ascension.\n",
       measured.aot_dispatches,measured.fallback_steps,
       measured.fallback_step_limit,measured.fallback_last_pc,
       measured.fallback_last_opcode,measured.fallback_unsupported_pc,
       measured.fallback_unsupported_word,(int)native[6],native[7],
       measured.fallback_callsite_pc,measured.fallback_call_target];
    /* M7.26 LV2 syscall evidence: exact number and guest source PC.
     * No ELF contents or user secrets written to TXT or actions. */
    [graphReport appendFormat:
       @"\nM7.26 — SYSCALLS LV2 OBSERVADAS\n"
        "Total chamadas LV2=%u · última=%u (0x%X) · PC=0x%08X\n"
        "Syscall ausente=%u (0x%X) · PC=0x%08X\n"
        "Syscall 147: sys_time_get_timebase_frequency (79.800.000 Hz) implementada.\n"
        "DIVDU PPC64: AOT e fallback com divisão por zero bloqueada.\n",
        measured.lv2_calls,measured.lv2_last_number,
        measured.lv2_last_number,measured.lv2_last_pc,
        measured.lv2_missing_number,measured.lv2_missing_number,
        measured.lv2_missing_pc];
    [graphReport appendFormat:
       @"\nM7.27 — BARREIRAS DE ORDENAÇÃO PPC EXECUTADAS (FALLBACK)\n"
        "EIEIO=%u · SYNC=%u · LWSYNC=%u · ISYNC=%u\n"
        "Última barreira PPC executada em 0x%08X\n"
        "Contagens do interpretador, NÃO de AOT; barreira host conservadora.\n",
        measured.eieio_steps, measured.sync_steps, measured.lwsync_steps,
        measured.isync_steps, measured.last_barrier_pc];
    /* M7.28: vectors are not fake scalar GPRs. Execution evidence is the
     * authenticated instruction stream and exact next failing PC. */
    [graphReport appendString:
      @"\nM7.28 — VMX / ALTIVEC DO CELL (CPU)\n"
       "Registradores PPU VR128 preservados em contexto compartilhado.\n"
       "VSPLTISW/VSPLTW/LVX/STVX/LVLX/LVRX/STVLX/STVRX: suporte genérico.\n"
       "Sem execução RSX real demonstrada; nenhum AOT privado adicional.\n"];
    [graphReport appendFormat:
        @"\nM7.29 — FPU PPC64 (OPERAÇÕES REAIS NO FALLBACK)\n"
         "Carregamentos FP=%u · gravações FP=%u · conversões FCFID=%u · FDIV=%u\n"
         "Última instrução FP executada=0x%08X\n"
         "FCFID e FDIV com FPSCR básico; modos arredondamento complexos bloqueados.\n"
         "Contadores pertencem à interpretação, NÃO são novas funções AOT.\n",
         measured.fp_loads,measured.fp_stores,measured.fp_converts,
         measured.fp_divides,measured.fp_last_pc];
    /* M7.30: this trace records real PPC interpreted instructions, NOT
     * translated AOT. Use it to select future private owner ELF AOT spans.
     * No ELF content is included in public CI or GitHub commits. */
    [graphReport appendFormat:
       @"\nM7.30 — DESTINOS REAIS PARA PRÓXIMA RECOMPILAÇÃO NATIVA\n"
        "Entradas ARM64 executadas=%u distintas=%u; PPC interpretado=%u\n"
        "Últimas %u instruções PPC autenticadas (NÃO AOT):\n",
        measured.aot_dispatches,measured.unique_aot,
        measured.fallback_steps,measured.fallback_trace_count];
    for(uint32_t fi=0;fi<measured.fallback_trace_count;fi++){
       [graphReport appendFormat:@"PPC_INTERP PC=0x%08X WORD=0x%08X\n",
          measured.fallback_trace_pcs[fi],measured.fallback_trace_words[fi]];
    }
    [graphReport appendString:
       @"MFCR r12 codificação exata implementada; LV2 #145 hora atual em"
        " segundos/nanosegundos BE na memória convidada.\n"
        "Gate: CI NÃO prova AOT integral. Filesystem, PSARC e RSX reais"
        " continuam SEM evidência neste relatório.\n"];
    uint32_t m731HitsRecent=0u;
    for(uint32_t at=0;at<measured.trace_count;at++)
       if(measured.trace_pcs[at]==UINT32_C(0x0052da5c))
          m731HitsRecent++;
    [graphReport appendFormat:
       @"\nM7.31 — NOVO BLOCO DO ELF RECOMPILADO NATIVAMENTE\n"
        "PC do bloco=0x0052DA5C · instruções MTOCRF 8,r12 + BLR\n"
        "AOT registrada após SHA privada e autenticação PT_LOAD X=%@\n"
        "AOT executada no anel de últimas 64 chamadas=%@ · ocorrências=%u\n"
        "AOT vinculadas=%u · distintas executadas=%u · PPC interpretadas=%u\n"
        "AOT não equivale a gameplay nem a quadro RSX real.\n",
        native[5]>=1420u?@"SIM":@"NÃO",
        m731HitsRecent?@"SIM":@"NÃO",
        m731HitsRecent,native[5],measured.unique_aot,measured.fallback_steps];
    uint32_t m732AOTRecent=0u;
    for(uint32_t at=0;at<measured.trace_count;at++)
       if(measured.trace_pcs[at]==UINT32_C(0x005230e0))m732AOTRecent++;
    [graphReport appendFormat:
       @"\nM7.32 — AOT DE 9 INSTRUÇÕES + FUSO HORÁRIO PS3\n"
        "Nova entrada AOT 0x005230E0: %@ (anel recente: %u)\n"
        "AOT vinculadas=%u · distintas executadas=%u · PPC interpretado=%u\n"
        "Syscall 144 é sys_time_get_timezone (2 x s32 BE).\n"
        "LV2 total=%u · última syscall=%u · PC=0x%08X · faltante=%u\n"
        "Próximo objetivo: verificar fluxo até filesystem/PSARC e RSX reais.\n",
        m732AOTRecent?@"EXECUTADA":@"NÃO OBSERVADA NO ANEL",
        m732AOTRecent,native[5],measured.unique_aot,measured.fallback_steps,
        measured.lv2_calls,measured.lv2_last_number,measured.lv2_last_pc,
        measured.lv2_missing_number];
    [graphReport appendFormat:
      @"\nM7.33 — VÍNCULO LV2 144 (TEMPO REAL)\n"
       "Syscall timezone concluída=%u (não somente encontrada)\n"
       "Última syscall=%u PC=0x%08X · ainda faltante=%u\n"
       "AOT originais 1421 preservadas; nenhuma função ARM64 nova.\n",
       measured.lv2_timezone_completed,measured.lv2_last_number,
       measured.lv2_last_pc,measured.lv2_missing_number];
    uint32_t recent734=0u;
    for(uint32_t ai=0;ai<measured.trace_count;ai++)
      if(measured.trace_pcs[ai]==UINT32_C(0x0052aa1c))recent734++;
    [graphReport appendFormat:
      @"\nM7.34 — BLOCO ORIGINAL DE LOTE DE 77 PPC RECOMPILADOS NATIVAMENTE\n"
       "AOT 0x0052AA1C ARM64: %@ · ocorrências recentes=%u\n"
       "Entradas AOT vinculadas=%u (meta M7.36: 1440) · AOT distintas=%u\n"
       "Passos PPC interpretados=%u · nenhum frame RSX original confirmado.\n"
       "Trecho atestado por SHA privada e checksum mais comparação ELF/VM.\n",
       recent734?@"EXECUTADA":@"NÃO OBSERVADA",recent734,
       native[5],measured.unique_aot,measured.fallback_steps];
    uint32_t recent736=0u;
    for(uint32_t ai=0;ai<measured.trace_count;ai++)
      if(measured.trace_pcs[ai]==UINT32_C(0x00524b8c))recent736++;
    [graphReport appendFormat:
      @"\nM7.36 — NOVA AOT ARM64 DE 9 PPC + MULHW ASSINADO\n"
       "AOT 0x00524B8C ARM64: %@ · ocorrências recentes=%u\n"
       "AOT vinculadas=%u (meta 1440) · AOT distintas=%u\n"
       "PPC interpretado=%u · nenhum cellFsOpen/Read ou RSX real presumido.\n"
       "ELF proprietário fica no iPhone; autenticação SHA + PT_LOAD X/VM.\n",
       recent736?@"EXECUTADA":@"NÃO OBSERVADA",recent736,
       native[5],measured.unique_aot,measured.fallback_steps];
    if((int)native[6]==AR_MISSING_LV2){
       pendingText=[NSString stringWithFormat:
          @"Serviço PS3 LV2 pendente: syscall %u (0x%X)\n"
           "Instrução guest: 0x%08X · interrupção segura.",
           measured.lv2_missing_number,measured.lv2_missing_number,
           measured.lv2_missing_pc];
    }
    frontierReport=[frontierReport stringByAppendingString:graphReport];
    /* M7.15: keep verified instruction batch available even when legacy
     * PPU48 returns success and skips the error-detail report branch. */
    self.ppuBatchReport=(((int)native[6]==-3 || (int)native[6]==-12 ||
                          (int)native[6]==-13) && native[7] && pendingMatch!=0)
                        ? frontierReport : nil;
    [self arPerformOnMain:^{ self.ppuBatchButton.enabled=(self.ppuBatchReport.length>0); }];
    /* Primary screen contains only live measured AOT, FS, and frontier. */
    self.ppuSummary=[NSString stringWithFormat:
      @"ASCENSIONRECOMP %@ · NPUA80918\n"
       "AOT ARM64 ONLY · PPC interpretadas=%u\n"
       "AOT: %u registradas · %u distintas · %u despachos\n"
       "ELF: %@ · entrada 0x%08X\n"
       "%@\n"
       "Guest FS: open=%u · read=%u · bytes=%llu\n"
       "Último AOT: 0x%08X · r13/TLS=0x%08X\n"
       "RSX do Ascension: não demonstrado · sem gameplay.",
       ARCurrentRelease(),measured.fallback_steps,
       native[5],measured.unique_aot,measured.aot_dispatches,
       nativeRC==0?@"VALIDADO":@"FALHOU",native[1],
       pendingText,fsMeasured.open_calls,fsMeasured.read_calls,
       (unsigned long long)fsMeasured.bytes_read,
       measured.stop_previous_aot,native[12]];
    if((int)continuous[0]!=-1314 || continuous[3]!=0x4e800421u)
       importReport=@"\nM7.3: nenhuma chamada bctrl desconhecida detectada nesta execução.\n";
    continuousText=[continuousText stringByAppendingString:importReport];
    if(rc48){
       NSMutableString *recent=[NSMutableString string];
       for(unsigned i=0;i<4u && i<trace48[15];i++){
          const unsigned slot=(trace48[15]-1u-i)&3u;
          [recent appendFormat:@"passo recente -%u: PC=0x%08X opcode=0x%08X\n",
             i,trace48[16u+2u*slot],trace48[17u+2u*slot]];
       }
       self.ppuReport=[NSString stringWithFormat:
          @"ASCENSIONRECOMP M6.7.6 / NPUA80918 / trace PPU privado\n"
           "Resultado=%d · passos=%u/48 · PC=0x%08X · opcode=0x%08X\n"
           "CTR=0x%08X%08X · saltos indiretos=%u\n"
           "r0 atual=0x%08X%08X · alterações=%u\n"
           "Última alteração r0: PC=0x%08X opcode=0x%08X\n"
           "r0 anterior=0x%08X · depois=0x%08X%08X\n"
           "Tipo opcode última alteração=%u · EA se leitura=%08X\n"
           "mtctr: PC=0x%08X · registrador-fonte=r%u\n"
           "bctr/bctrl: PC=0x%08X · alvo CTR baixo=%08X\n"
           "Indicador falha memória=%u · EA=0x%08X\n"
           "%@"
           "Dados são registradores e metadados PRX; bytes do ELF não incluídos.",
           rc48,cpu48[0],cpu48[8],cpu48[7],
           cpu48[18],cpu48[17],cpu48[19],
           trace48[6],trace48[5],trace48[7],
           trace48[0],trace48[1],
           trace48[2],trace48[4],trace48[3],
           trace48[9],trace48[8],
           trace48[10],trace48[11],trace48[14],trace48[12],
           cpu48[16],cpu48[10],recent];
       NSMutableString *extended=[self.ppuReport mutableCopy];
       [extended appendFormat:
        @"\nr12 atual=0x%08X%08X · alterações=%u\n"
         "Última mudança r12: PC=0x%08X opcode=0x%08X\n"
         "r12 anterior=0x%08X depois=0x%08X%08X tipo=%u\n"
         "r12 EA leitura=0x%08X regiao=%u flags=%u\n"
         "lwz r0 via r12: EA=0x%08X valor=0x%08X regiao=%u flags=%u\n"
         "lwz r2 via r12: EA=0x%08X valor=0x%08X regiao=%u flags=%u\n"
         "r12 na leitura r0=0x%08X%08X\n"
         "Regioes: 0=sem mapa 1=pilha 2=codigo ELF 3=dados ELF 4=BSS 5=BSS+X\n",
         detail48[19],detail48[18],detail48[5],
         detail48[0],detail48[1],
         detail48[2],detail48[4],detail48[3],detail48[6],
         detail48[7],detail48[16],detail48[17],
         detail48[8],detail48[9],detail48[10],detail48[11],
         detail48[12],detail48[13],detail48[14],detail48[15],
         detail48[21],detail48[20]];
       /* Inspect guest firmware metadata only after a failed indirect call
        * that read an instruction word from executable PT_LOAD.
        * This never patches imports, changes CTR, or claims HLE support. */
       if(rc48==-1007 && detail48[10]==2u && detail48[8]){
          unsigned int importInfo[4]={0};
          char importLibrary[48]={0};
          int importStatus=ar_private_import_match(
             data.bytes,data.length,detail48[8],importInfo,importLibrary);
          [extended appendFormat:
              @"PRX import: status=%d · stub=0x%08X · NID=0x%08X"
               " · biblioteca=%s · importações examinadas=%u · bibliotecas=%u\n",
               importStatus,importInfo[1],importInfo[0],
               importLibrary[0]?importLibrary:"(não identificada)",
               importInfo[2],importInfo[3]];
          if(importStatus==0)
            [extended appendString:
                @"Importação identificada, MAS serviço HLE ainda NÃO vinculado; -1007 preservado.\n"];
          else
            [extended appendString:
                @"Nenhuma importação associada comprovada; não executar este destino.\n"];
       }
       [extended appendFormat:
        @"TLS HLE M6.7.6: inicializado=%u · chamadas=%u · motivo=%u\n"
         "ABI: thread_id=0x%08X · seg=0x%08X · file=%u · mem=%u\n"
         "TLS: r13=0x%08X · bytes copiados=%u · retorno PC=0x%08X\n"
         "Entrada LV2: PT_TLS presente=%u · tamanho de página=0x%08X\n"
          "Último mtlr: PC=0x%08X · LR=0x%08X (retorno verificado por blr)\n",
         tls48[0],tls48[1],tls48[8],
         tls48[2],tls48[3],tls48[4],tls48[5],
         tls48[6],tls48[7],tls48[10],tls48[9],tls48[11],
          detail48[22],detail48[23]];
       if(tls48[0])
         [extended appendString:
           @"sys_initialize_tls HLE executada com imagem TLS copiada, BSS zerado e r13 configurado; não significa boot completo.\n"];
       else if(rc48==-1021)
         [extended appendString:
           @"Entrada ELF PT_TLS ausente/inválida ou fora dos limites; correção bloqueada com segurança.\n"];
       else if(rc48==-1022 || rc48==-1024)
          [extended appendString:
            @"Retorno LR/blr bloqueado: endereço fora do código executável ou branch condicional não suportado.\n"];
        else if(rc48==-1011 || rc48==-1012 || rc48==-1013)
         [extended appendString:
           @"TLS recusado: parâmetros, thread já inicializada ou leitura de memória inválida. Não houve sucesso artificial.\n"];
       [extended appendString:nativeText];
       [extended appendString:frontierReport];
       [extended appendString:lwMutexText];
       if(native[5]>0u){
         [extended appendFormat:
           @"\nM7.9 — SERVIÇOS DO INÍCIO AOT ARM64\n"
            "Thread get-id=%@ · mutex lock=%@ · mutex unlock=%@\n"
            "Todos são imports PS3 reais, vinculados por biblioteca/NID;\n"
            "HLE disponível não prova que a chamada foi executada.\n",
            (native[15]&0x100u)?@"VINCULADO":@"AUSENTE",
            (native[15]&0x200u)?@"VINCULADO":@"AUSENTE",
            (native[15]&0x400u)?@"VINCULADO":@"AUSENTE"];
       }

       if(native[5]>0u){
         [extended appendFormat:
           @"\nM7.8 — EXECUÇÃO DO ASCENSION RECOMPILADO ARM64\n"
            "Funções nativas=%u · despacho=%d · próximo PC faltante=0x%08X\n"
            "Import de tempo autenticado=%@ · HLE tempo vinculado=%@\n"
            "Syscall LV2 0x160=implementado; início PS3 parcial, SEM gameplay.\n",
            native[5],(int)native[6],native[7],
            (native[15]&64u)?@"SIM":@"NÃO",
            (native[15]&128u)?@"SIM":@"NÃO"];
       }

       /* M7.6: AOT count is native signed function count, never interpreter
        * steps. AR_UNRESOLVED -3 is genuine missing guest ARM64 coverage. */
       if(native[5]>0u){
         [extended appendFormat:
           @"\nM7.6 — AOT ARM64 REAL / NPUA80918\n"
            "Funções registradas=%u · resultado AOT=%d\n"
            "Próxima função ARM64 ausente=0x%08X · r13 AOT=0x%08X\n"
            "Entrada recompilada=0x%08X · bind PRX=%d / HLE=%d\n"
            "Ainda não é gameplay; -3 significa função sem recompilação.\n",
            native[5],(int)native[6],native[7],native[12],
            native[1],(int)native[9],(int)native[10]];
       } else {
         [extended appendString:
           @"\nM7.6 — AOT ARM64 NPUA80918 NÃO VINCULADO\n"
            "Funções AOT=0; é necessário o módulo AOT durante o Actions.\n"];
       }
       [extended appendString:continuousText];
       self.ppuReport=[NSString stringWithFormat:@"%@\n\n%@",self.ppuSummary,extended];
       [self arPerformOnMain:^{ self.ppuReportButton.enabled=YES; }];
       [self arPerformOnMain:^{ self.ppuAdvancedButton.enabled=YES; }];
       [self arPerformOnMain:^{ self.ppuDiagnosticsButton.enabled=(self.ppuReport.length>0); }];
       [self arPerformOnMain:^{ [self.ppuReportButton setTitle:@"Copiar status AOT" forState:UIControlStateNormal]; }];
       NSString *faultDetail=cpu48[16]
          ? [NSString stringWithFormat:@"EA=0x%X · base=0x%X · valor=0x%X",
                cpu48[10],cpu48[11],cpu48[12]]
          : [NSString stringWithFormat:@"CTR=0x%08X%08X · indiretos=%u",
                cpu48[18],cpu48[17],cpu48[19]];
       [self arSetStatus:[NSString stringWithFormat:
          @"M5.9 NPUA80918: ELF REAL VALIDADO\n"
           "%@\n"
           "%@\n"
           "M6.6 PARADA SEGURA %d · %u/48\n"
           "PC=0x%X · opcode=0x%08X\n"
           "%@\n"
           "Última escrita r0: PC=0x%X · word=%08X\n"
           "Use «Copiar diagnóstico PPU» para enviar a trilha.",
           legacyState,old40State,rc48,cpu48[0],cpu48[8],
           cpu48[7],faultDetail,trace48[0],trace48[1]]];
       [self arPublishPpuSummary];
       return;
    }
    self.ppuReport=[NSString stringWithFormat:
       @"ASCENSIONRECOMP M6.7.6 / NPUA80918\n"
        "Resultado=0 · passos=%u/48 · sys_initialize_tls=%u · r13=0x%08X\n"
        "TLS copiada=%u bytes; PPU48 ainda é um bootstrap limitado.\n",
        cpu48[0],tls48[0],tls48[6],tls48[7]];
    self.ppuReport=[self.ppuReport stringByAppendingString:nativeText];
    self.ppuReport=[self.ppuReport stringByAppendingString:frontierReport];
    self.ppuReport=[self.ppuReport stringByAppendingString:continuousText];
    self.ppuReport=[NSString stringWithFormat:@"%@\n\n%@",self.ppuSummary,self.ppuReport];
    [self arPerformOnMain:^{ self.ppuAdvancedButton.enabled=YES; }];
    [self arPerformOnMain:^{ self.ppuDiagnosticsButton.enabled=(self.ppuReport.length>0); }];
    [self arPerformOnMain:^{ [self.ppuReportButton setTitle:@"Copiar status AOT" forState:UIControlStateNormal]; }];
    [self arPerformOnMain:^{ self.ppuReportButton.enabled=YES; }];
    [self arSetStatus:[NSString stringWithFormat:
       @"M5.9 NPUA80918: ELF REAL VALIDADO\n"
        "%@\n"
        "%@\n"
        "M6.7.6 PPU REAL 48/48: OK · TLS=%u\n"
        "PC=0x%X · CTR=0x%08X%08X\n"
        "stores=%u · indiretos=%u · sombra=%u\n"
        "M7.9: código ARM64 recompilado vinculado; veja AOT e próximo PC no relatório.",
        legacyState,old40State,tls48[0],cpu48[2],cpu48[18],cpu48[17],
        cpu48[5],cpu48[19],cpu48[15]]];
    [self arPublishPpuSummary];
   } @finally {
     if(scoped)[url stopAccessingSecurityScopedResource];
     dispatch_async(dispatch_get_main_queue(),^{
       self.shaderBusy=NO;
       self.ppuBatchButton.enabled=(self.ppuBatchReport.length>0);
       self.ppuReportButton.enabled=(self.ppuReport.length>0);
       self.ppuAdvancedButton.enabled=(self.ppuReport.length>0);
       self.ppuDiagnosticsButton.enabled=YES;
       [self.ppuDiagnosticsButton setTitle:@"Relatórios · resumo / técnico"
                                  forState:UIControlStateNormal];
     });
   }
 });
 return;
}
#endif
}
- (void)documentPickerWasCancelled:(UIDocumentPickerViewController*)controller {
  if(controller==self.rpcMarkerPicker){
    self.rpcMarkerPicker=nil;
    self.status.text=@"M7.40: seleção cancelada, instalação RPCS3 intocada.";
    return;
  }
  if(controller==self.folderPicker){
    self.folderPicker=nil;
    self.status.text=@"Importação da pasta cancelada.";
    return;
  }
 (void)controller;
 self.status.text=@"M5.9 cancelado; M5.8.1 disponível.";
}
/* A tap submits another actual on-screen GPU clear pass.
 * Completion is checked; labels do not assert success on failed work. */
- (void)drawNextFrame:(UITapGestureRecognizer *)gesture {
    (void)gesture;
    if (!self.ready) return;

    /* The first screen remains the known-good direct Metal reference.
     * Every touch switches to the real NV4097 register-file route, with
     * GPU-synchronized readback before success is shown. */
    unsigned int expected=0, observed=0;
    const int rc=ar_probe_rsx_clear_flip((unsigned)self.guestAttempts++,
                                         &expected,&observed);
    if(rc==0) {
        self.successfulFrames++;
        self.status.text=[NSString stringWithFormat:
            @"NV4097 → RSX → Metal: OK\n"
             "Flip e pixel de GPU verificados\n"
             "Cor PS3: 0x%08X  Pixel: 0x%08X\n"
             "Toque para testar outra cor\n"
             "Sem jogo PS3 — não mede FPS",
             expected,observed];
    } else {
        self.status.text=[NSString stringWithFormat:
            @"Referência Metal direta funcionou.\n"
             "Falha no caminho NV4097 → RSX → Metal!\n"
             "Etapa %d · Esperado: 0x%08X · Lido: 0x%08X\n"
             "Envie uma captura para diagnóstico.",
             rc, expected, observed];
    }
}


/* Long press: independent geometry/shader/raster test, not the color clear. */
- (void)drawTriangle:(UILongPressGestureRecognizer *)gesture {
    if (gesture.state!=UIGestureRecognizerStateBegan || !self.ready) return;
    unsigned int bg=0,pixel=0;
    const int result=ar_probe_rsx_triangle(&bg,&pixel);
    if(result==0) {
        self.status.text=[NSString stringWithFormat:
            @"NV4097 → triângulo → Metal: OK\n"
             "Centro verde, fundo 0x%08X\n"
             "Pixel central 0x%08X\n"
             "Geometria sintética: sem jogo PS3.",
             bg,pixel];
    } else {
        self.status.text=[NSString stringWithFormat:
            @"GPU Metal continua inicializada.\n"
             "Triângulo NV4097 FALHOU: etapa %d\n"
             "Metal pipeline: %d (0 nenhum, 1 MSL, 2 PSO, 3 draw)\n"
             "Fundo: 0x%08X · Centro: 0x%08X\n"
             "Envie este resultado para corrigirmos a renderização.",
             result,ar_probe_rsx_fixed_stage(),bg,pixel];
    }
}


/* Unlike M4.5's inline FIFO attributes, this fetches 3 PS3 big-endian
 * float4 vertices from the bounds-checked virtual memory probe. */
- (void)drawDMATriangle:(UITapGestureRecognizer *)tap {
    (void)tap;
    if (!self.ready) return;
    unsigned int bg=0,center=0;
    int result=ar_probe_rsx_dma_triangle(&bg,&center);
    if(result==0) {
        self.status.text=[NSString stringWithFormat:
             @"NV4097 → DMA de vértices → Metal: OK\n"
              "Memória PS3 BE → triângulo magenta\n"
              "Fundo: 0x%08X · Centro: 0x%08X\n"
              "Dados sintéticos, sem código do jogo.",
              bg,center];
    } else {
        self.status.text=[NSString stringWithFormat:
             @"DMA NV4097 falhou: etapa %d\n"
              "Pipeline básico Metal: %d (0–3)\n"
              "Fundo: 0x%08X · Centro: 0x%08X\n"
              "Testes M4.5 continuam disponíveis.",
              result,ar_probe_rsx_fixed_stage(),bg,center];
    }
}

/* M4.7: indexed 4-vertex / 6-index quad; alternates u16 and u32. */
- (void)drawIndexedQuad:(UITapGestureRecognizer *)gesture {
    (void)gesture;
    if(!self.ready)return;
    unsigned use32=(unsigned)((self.indexedAttempts++ & 1u)!=0);
    unsigned int bg=0,pixel=0;
    const int rc=ar_probe_rsx_indexed_quad(use32,&bg,&pixel);
    if(rc==0){
        self.status.text=[NSString stringWithFormat:
          @"NV4097 → ÍNDICES → Metal: OK\n"
           "4 vértices, 6 índices %u-bit\n"
           "2 triângulos formando quadrilátero dourado\n"
           "Centro: 0x%08X Fundo: 0x%08X\n"
           "3 toques novamente: alternar 16/32",
           use32 ? 32u : 16u,pixel,bg];
    } else {
        self.status.text=[NSString stringWithFormat:
          @"ÍNDICES NV4097: FALHA %d\n"
           "Tipo: %u-bit Pipeline: %d\n"
           "Centro: 0x%08X Fundo: 0x%08X\n"
           "Testes anteriores preservados.",
           rc,use32?32u:16u,ar_probe_rsx_fixed_stage(),pixel,bg];
    }
}


/* Four taps: check RSX A8R8G8B8 channel reorder/swizzle, a native
 * Metal texture upload, actual fragment sampling and GPU readback.
 * This deliberately does NOT claim arbitrary Ascension FP/VP support. */
- (void)drawPS3Texture:(UITapGestureRecognizer *)gesture {
    (void)gesture;
    if(!self.ready)return;
    unsigned swizzled=(unsigned)((self.textureAttempts++&1u)!=0);
    unsigned int colors[4]={0};
    int rc=ar_probe_rsx_texture((__bridge void *)self.metalView.layer,
                                 swizzled,colors);
    if(rc==0){
        self.status.text=[NSString stringWithFormat:
            @"TEXTURA PS3 → METAL: OK\n"
             "A8R8G8B8 %@ → RGBA8\n"
             "GPU amostrou 4 quadrantes diferentes\n"
             "Pixels: %08X %08X %08X %08X\n"
             "4 toques: alternar linear/swizzled",
             swizzled?@"SWIZZLED":@"LINEAR",
             colors[0],colors[1],colors[2],colors[3]];
    }else{
        self.status.text=[NSString stringWithFormat:
            @"TESTE TEXTURA PS3: FALHA %d\n"
             "Formato: %@\n"
             "Leitura: %08X %08X %08X %08X\n"
             "Demais testes RSX continuam disponíveis.",
             rc,swizzled?@"SWIZZLED":@"LINEAR",
             colors[0],colors[1],colors[2],colors[3]];
    }
}


/* Five taps: vertex draw loads native RSX texture unit 0 from PS3 guest
 * registers; the GPU samples the bound Metal object in an isolated
 * compute diagnostic (NOT the game's RSX fragment program). */
- (void)drawRSXBoundTexture:(UITapGestureRecognizer *)gesture {
    (void)gesture;
    if(!self.ready)return;
    unsigned swizzled=(unsigned)((self.registerTextureAttempts++&1u)!=0);
    unsigned int samples[4]={0,0,0,0};
    int rc=ar_probe_rsx_texture_registers(swizzled,samples);
    if(rc==0) {
        self.status.text=[NSString stringWithFormat:
            @"NV4097 → TEXTURA0 → METAL: OK\n"
             "Origem: registrador RSX + cache/decoder\n"
             "Formato: %@ · GPU amostrou vínculo real\n"
             "Pixels: %08X %08X %08X %08X\n"
             "Amostrador de diagnóstico, sem shader PS3",
             swizzled?@"SWIZZLED":@"LINEAR",
             samples[0],samples[1],samples[2],samples[3]];
    } else {
        self.status.text=[NSString stringWithFormat:
            @"NV4097 TEXTURA0 FALHOU: %d\n"
             "Formato: %@\n"
             "Pixels: %08X %08X %08X %08X\n"
             "M4.8 e anteriores preservados.",
             rc,swizzled?@"SWIZZLED":@"LINEAR",
             samples[0],samples[1],samples[2],samples[3]];
    }
}

/* 3 GPU draws at identical guest texture address, with changed pixels
 * each frame. Repeat the button to test swizzled after linear. */
- (void)testRSXCache:(UIButton *)sender {
    (void)sender;
    if(!self.ready)return;
    unsigned sw=(unsigned)((self.cacheMutationAttempts++&1u)!=0);
    unsigned int samples[4]={0},phase=0,uploads=0,replacements=0;
    const int rc=ar_probe_rsx_texture_cache_mutation(sw,samples,
                                               &phase,&uploads,&replacements);
    if(rc==0){
        self.status.text=[NSString stringWithFormat:
          @"CACHE RSX → GPU METAL: OK\n"
           "Formato: %@ · mesmo endereço, 3 quadros\n"
           "Uploads: %u  Substituições: %u\n"
           "Pixels finais: %08X %08X %08X %08X\n"
           "Repita para testar o outro layout",
           sw?@"SWIZZLED":@"LINEAR",uploads,replacements,
           samples[0],samples[1],samples[2],samples[3]];
    } else {
        self.status.text=[NSString stringWithFormat:
          @"CACHE RSX → GPU: FALHA %d fase %u/3\n"
           "Layout: %@ · uploads %u · substituições %u\n"
           "Pixels: %08X %08X %08X %08X\n"
           "M4.9 e testes anteriores preservados.",
           rc,phase,sw?@"SWIZZLED":@"LINEAR",uploads,replacements,
           samples[0],samples[1],samples[2],samples[3]];
    }
}

- (void)applicationWillTerminate:(UIApplication*)app {
    (void)app;
    if(self.ready) {
        rsx_metal_backend_shutdown();
        ar_probe_vm_shutdown();
        self.ready=NO;
    }
}
@end

int main(int argc,char *argv[]) {
    @autoreleasepool {
        return UIApplicationMain(argc,argv,nil,NSStringFromClass([ARProbeDelegate class]));
    }
}
