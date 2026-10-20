/* AscensionRecomp iPhone Metal diagnostic host. No commercial game code. */
#import <UIKit/UIKit.h>
#import <Metal/Metal.h>
#import "ARMetalView.h"
#import "ARGameFolderStore.h"
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>
#import <CommonCrypto/CommonDigest.h>
#include "../ios-probe/ARBuildProvenance.h"
#include "../runtime/ppu_bridge.h"
#include "../runtime/ppu_guest_fs.h"
#include "../runtime/ppu_m756_stop_evidence.h"
#include "../runtime/ppu_m767_live_import.h"
extern void ar_m772_runtime_attest(uint64_t out[8]);
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
@interface ARProbeDelegate : UIResponder <UIApplicationDelegate, UIDocumentPickerDelegate>
@property(nonatomic,strong) UIWindow *window;
@property(nonatomic,strong) ARMetalView *metalView;
@property(nonatomic,strong) UILabel *status;
@property(nonatomic,strong) UIScrollView *gameList;
@property(nonatomic,strong) UIScrollView *graphicsList;
@property(nonatomic,strong) UIButton *ppuReportButton;
@property(nonatomic,strong) UIButton *ppuBatchButton;
@property(nonatomic,copy) NSString *ppuBatchReport;
@property(nonatomic,copy) NSString *ppuReport;
@property(nonatomic,copy) NSString *ppuProgress;
@property(nonatomic,copy) NSString *ppuSummary;
@property(nonatomic,copy) NSString *folderReport;
@property(nonatomic,strong) NSDictionary<NSString*,id> *m750Run;
@property(nonatomic,copy) NSString *m750HostObservation;
@property(nonatomic,strong) UIDocumentPickerViewController *folderPicker;
@property(nonatomic,strong) UIDocumentPickerViewController *rpcMarkerPicker;
@property(nonatomic,strong) UIButton *ppuAdvancedButton;
@property(nonatomic,strong) UIButton *ppuDiagnosticsButton;
@property(nonatomic,assign) BOOL ready;
@property(nonatomic,assign) BOOL shaderBusy;
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
@end

@implementation ARProbeDelegate
- (BOOL)application:(UIApplication*)app didFinishLaunchingWithOptions:(NSDictionary*)options {
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
    [elfButton setTitle:@"M5.9 · Importar GOWA.ELF" forState:UIControlStateNormal];
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
             @"NPUA80918 · AOT ARM64 do Ascension. Importe o ELF para acompanhar a inicialização nativa." :
             @"Diagnósticos RSX → Metal, do mais recente ao legado. Role para encontrar os testes anteriores.";
        [stack addArrangedSubview:hint];
        NSArray<UIButton *> *ordered=i==0 ? @[rpcMarkerButton,localFolderButton,folderButton,elfButton] : @[
            alphaButton,blendButton,maskButton,stencilButton,depthButton,
            multipassButton,mutationButton,drawButton,shaderButton,cacheButton];
        for(UIButton *button in ordered) {
            button.backgroundColor=i==0 ?
                [UIColor colorWithRed:0.10 green:0.40 blue:0.73 alpha:1] :
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
    [elfButton setTitle:@"Importar GOWA.ELF · executar AOT" forState:UIControlStateNormal];
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
                                  "M7.43 · 6.251 AOT nativas em lote\n"
                                  "Importe GOWA.ELF para executar o código recompilado.\n"
                                  "Inicialização parcial, ainda sem gameplay.\n"
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
}


/* M5.0: NV40 guest microcode is decoded, lowered and compiled on the iPhone.
 * Failures are shown; no draw/gameplay claim is made from shader compilation. */
- (void)arSwitchTab:(UISegmentedControl *)sender {
    BOOL showGame=sender.selectedSegmentIndex==0;
    self.gameList.hidden=!showGame;
    self.graphicsList.hidden=showGame;
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
    if(self.ppuReport.length)UIPasteboard.generalPasteboard.string=self.ppuReport;
    else UIPasteboard.generalPasteboard.string=[self arUnifiedPpuText];
}
- (void)closeAdvancedPpuReport:(UIBarButtonItem *)sender {
    (void)sender;
    [self.window.rootViewController dismissViewControllerAnimated:YES completion:nil];
}
- (void)openAdvancedPpuReport:(UIButton *)sender {
    (void)sender;
    if(!self.ppuReport.length&&!self.shaderBusy)return;
    UIViewController *page=[UIViewController new];
    page.title=@"Diagnóstico avançado PPU";
    page.view.backgroundColor=UIColor.systemBackgroundColor;
    UITextView *details=[UITextView new];
    details.translatesAutoresizingMaskIntoConstraints=NO;
    details.editable=NO;
    details.selectable=YES;
    details.font=[UIFont monospacedSystemFontOfSize:12 weight:UIFontWeightRegular];
    details.text=self.ppuReport.length?self.ppuReport:[self arUnifiedPpuText];
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
    page.navigationItem.rightBarButtonItem=[[UIBarButtonItem alloc]
       initWithTitle:@"Copiar tudo" style:UIBarButtonItemStylePlain target:self
       action:@selector(copyAdvancedPpuReport:)];
    UINavigationController *nav=[[UINavigationController alloc] initWithRootViewController:page];
    [self.window.rootViewController presentViewController:nav animated:YES completion:nil];
}
/* The full report already contains summary + BE PPC batch + static callgraph
 * + measured AOT dispatches + HLE + M6 legacy diagnostics; don't duplicate
 * any section when exporting. No ELF or commercial assets leave the phone. */
- (NSString *)arUnifiedPpuText {
  /* M7.52-v3: freshly imported ELF run, measured guest counters only.
   * Do not derive device evidence from offline symbols or historical TXT. */
  NSDictionary *e=self.shaderBusy?nil:self.m750Run;
  NSString *(^val)(NSString *)=^NSString*(NSString *k){
     return e[k]?[e[k] description]:@"NÃO MEDIDO";
  };
  NSString *(^hexval)(NSString *)=^NSString*(NSString *k){
     return e[k]?[NSString stringWithFormat:@"0x%08X",
       [e[k] unsignedIntValue]]:@"NÃO MEDIDO";
  };
  NSString *last=(e&&[e[@"last_aot"] unsignedIntValue])?
     hexval(@"last_aot"):@"NÃO MEDIDO";
  NSString *realOpcode=(e && [e[@"stop_guest_rc"] intValue]==0)?hexval(@"opcode"):@"NÃO MEDIDO";
  NSString *fsOpen=([e[@"fs_opens"] unsignedIntValue]>0u)?
    [NSString stringWithFormat:@"COMPROVADO no guest · opens=%@/%@ · FD=%@ · caminho=%@",
      val(@"fs_opens"),val(@"fs_open_calls"),val(@"fs_fd"),
      e[@"fs_path"]?:@"NÃO MEDIDO"]:
      ([e[@"fs_open_calls"] unsignedIntValue]>0u)?
    [NSString stringWithFormat:@"tentativa guest=%@, sem FD válido · último erro=0x%08X",
      val(@"fs_open_calls"),[e[@"fs_last_error"] unsignedIntValue]]:
    @"não comprovado (nenhuma chamada open originada no guest)";
  NSString *fsRead=([e[@"fs_bytes"] unsignedLongLongValue]>0u)?
    [NSString stringWithFormat:@"COMPROVADO no guest · leituras=%@/%@ · bytes=%@",
      val(@"fs_reads"),val(@"fs_read_calls"),val(@"fs_bytes")]:
      ([e[@"fs_read_calls"] unsignedIntValue]>0u)?
    [NSString stringWithFormat:@"tentativa guest=%@, sem leitura positiva · erro=0x%08X",
       val(@"fs_read_calls"),[e[@"fs_last_error"] unsignedIntValue]]:
    @"não comprovado (nenhuma chamada read originada no guest)";
  NSString *origin=e?@"execução real no iPhone":@"NÃO MEDIDO";
  NSString *elf=e?@"comprovado":@"não comprovado";
  NSString *native=e&&[e[@"dispatches"] unsignedIntValue]?
    @"comprovado":@"não comprovado";
  NSMutableString *report=[NSMutableString stringWithFormat:
    @"ASCENSIONRECOMP — ESQUEMA AOT-v12\n"
     "EXECUÇÃO ATUAL\n"
     "Branch=%s | Commit=%s | Build Actions=%s | Workflow ID=%s\n"
     "App=%@ (CFBundleVersion=%@) | Runtime AOT ONLY | Relatório=v12\n"
     "Tipo teste=%@ | Momento=%@\n"
     "Estado atual=%@ · %@\n"
     "ELF carregado=%@ | origem=%@\n"
     "AOT vinculadas=%@ entradas | origem=%@\n"
     "AOT distintas executadas=%@ entradas | origem=%@\n"
     "Despachos ARM64=%@ despachos | origem=%@\n"
     "PPC interpretadas=%@ instruções (exigência AOT ONLY: 0) | origem=%@\n"
     "Limite de interpretação PPC=%@ instruções | origem=%@\n"
     "Resultado guest=%@ | origem=%@\n"
     "PC de parada=%@ | opcode=%@ | origem=%@\n"
     "Último PC AOT executado=%@ | origem=%@\n"
     "Compilador OFFLINE M7.43=6251 funções / 221061 PPC"
     " | origem: lote AOT histórico, NÃO dados desta execução.\n\n"
     "QUADRO DE MARCOS\n"
     "ELF carregado: %@\n"
     "AOT executado no caminho atual: %@\n"
     "USRDIR detectado pelo HOST (NÃO guest): %@\n"
     "cellFsOpen: %@\n"
     "cellFsRead com bytes positivos: %@\n"
     "PSARC aberto/analisado no guest: não comprovado\n"
     "Primeiro comando RSX real: não comprovado\n"
     "Primeiro quadro original do jogo: não comprovado\n\n",
     AR_M750_BUILD_BRANCH,AR_M750_BUILD_SHA,
     AR_M750_BUILD_RUN_NUMBER,AR_M750_BUILD_RUN_ID,
     ARCurrentRelease(),[[NSBundle mainBundle] objectForInfoDictionaryKey:@"CFBundleVersion"],
     e?@"teste físico iPhone / PPU guest":@"NÃO MEDIDO",
     e?val(@"when"):@"NÃO MEDIDO",
     self.shaderBusy?@"EM EXECUÇÃO":(e?@"CONCLUÍDO":@"SEM EXECUÇÃO"),
     self.ppuProgress?:@"sem status recente",elf,origin,
     val(@"aot"),e?@"tabela AOT carregada no app":origin,
     val(@"unique"),origin,val(@"dispatches"),origin,
     val(@"fallback"),origin,val(@"limit"),origin,
     val(@"rc"),origin,hexval(@"stop"),realOpcode,origin,
     last,origin,elf,native,
     self.m750HostObservation?:@"não comprovado",
     fsOpen,fsRead];
  /* Device baselines below are historical, never invented for a new run. */
  [report appendFormat:
    @"COMPARAÇÃO COM TESTES FÍSICOS ANTERIORES\n"
     "M7.61.3 (teste físico): AOT=7726; distintas=128; despachos=1859; parada=0x002C53B0.\n"
     "M7.62.1 (teste físico): AOT=7821; distintas=132; despachos=1890; parada=0x002C53BC.\n"
     "M7.63.1 (teste físico, commit 73959e4, Actions #244): AOT=8417; distintas=134;"
     " despachos=1892; PPC=0; parada=0x00539378.\n"
     "EXECUÇÃO ATUAL %@: AOT=%@; distintas=%@; despachos=%@; PPC=%@;"
     " limite=%@; parada=%@; opcode=%@; último AOT=%@.\n",
     ARCurrentRelease(),val(@"aot"),val(@"unique"),val(@"dispatches"),
     val(@"fallback"),val(@"limit"),hexval(@"stop"),realOpcode,last];
  if(e) [report appendFormat:
    @"DELTA FÍSICO vs M7.63.1: AOT=%+lld; distintas=%+lld; despachos=%+lld."
     " Símbolos compilados NÃO representam execução no iPhone.\n\n",
    (long long)[e[@"aot"] longLongValue]-8417LL,
    (long long)[e[@"unique"] longLongValue]-134LL,
    (long long)[e[@"dispatches"] longLongValue]-1892LL];
  else [report appendString:@"DELTA FÍSICO vs M7.63.1: NÃO MEDIDO.\n\n"];
  /* ELF versus RAM guest: independent read on-device before the VM is freed.
   * No fallback opcode or HOST Files sample may populate these fields. */
  [report appendFormat:
    @"ELF versus RAM guest | PC=%@ | ELF status=%@ | RAM status=%@\n"
     "segmento X VA=%@ | p_offset=%@ | tamanho arquivo=%@ | offset físico=%@\n"
     "opcode ELF=%@ | opcode RAM=%@ | bytes=%@ | comparação=%@\n"
     "ELF HEX=%@\nRAM HEX=%@\n"
     "Origem: ELF original + leitura real da memória guest ANTES do shutdown.\n\n",
     hexval(@"stop"),val(@"stop_elf_rc"),val(@"stop_guest_rc"),
     val(@"stop_seg_va"),val(@"stop_seg_offset"),val(@"stop_seg_filesz"),
     val(@"stop_file_offset"),
     ([e[@"stop_elf_rc"] intValue]==0)?hexval(@"stop_elf_word"):@"NÃO MEDIDO",
     realOpcode,val(@"stop_count"),val(@"stop_match"),
     e[@"stop_elf_hex"]?:@"NÃO MEDIDO",e[@"stop_guest_hex"]?:@"NÃO MEDIDO"];
  [report appendFormat:
    @"ELF versus RAM guest — ORIGEM FIXA 0x003C4FC4\n"
     "ELF status=%@ | RAM status=%@ | arquivo offset=%@ | iguais=%@\n"
     "opcode ELF=%@ | opcode RAM=%@\nELF HEX=%@\nRAM HEX=%@\n\n",
     val(@"origin_elf_rc"),val(@"origin_guest_rc"),
     val(@"origin_offset"),val(@"origin_match"),
     ([e[@"origin_elf_rc"] intValue]==0)?hexval(@"origin_word"):@"NÃO MEDIDO",
     ([e[@"origin_guest_rc"] intValue]==0)?hexval(@"origin_ram_word"):@"NÃO MEDIDO",
     e[@"origin_elf_hex"]?:@"NÃO MEDIDO",e[@"origin_ram_hex"]?:@"NÃO MEDIDO"];
  [report appendString:
    @"HISTÓRICO — LEGADOS, NÃO EXECUÇÃO ATUAL\n"
     "Os blocos anteriores M6.7.6, M7.0, M7.14, M7.17, M7.20,"
     " M7.26–M7.49 são diagnósticos de subsistemas antigos."
     " A etiqueta M7.44 é do runtime legado e não representa a versão"
     " do app. Nenhuma cifra antiga altera EXECUÇÃO ATUAL.\n"];
  NSString *body=self.ppuReport.length?self.ppuReport:self.ppuSummary;
  if(self.shaderBusy)body=nil;
  if(body.length)[report appendFormat:
    @"\n--- Histórico PPU com origem dos testes no texto ---\n%@\n",body];
  if(self.folderReport.length)[report appendFormat:
    @"\n--- Evento HOST Files separado (não cellFsOpen/Read) ---\n%@\n",
      self.folderReport];
  uint64_t m772[8]={0};
  if(!self.shaderBusy)ar_m772_runtime_attest(m772);
  [report appendFormat:
    @"\nM7.72 — TABELAS DO LIFT PS3RECOMP NO RUNTIME\n"
     "Entradas PPU registradas=%llu\n"
     "0x0052A740=%@ · chamada 0x0052E3F4=%@\n"
     "Imagens SPU registradas=%llu\n"
     "Runtime inicializado antes do guest=%@\n"
     "Despachos PPU PS3Recomp executados=%llu · último PC=0x%08llX\n"
     "VM guest ligada ao runtime=%llu bytes\n"
     "Despachos nativos não provam gameplay, HLE completo ou frame RSX.\n",
     (unsigned long long)m772[0],m772[1]?@"SIM":@"NÃO",
     m772[2]?@"SIM":@"NÃO",(unsigned long long)m772[3],
     m772[4]?@"SIM":@"NÃO",(unsigned long long)m772[5],
     (unsigned long long)m772[6],(unsigned long long)m772[7]];
  [report appendString:
    @"\nRelatório sem bytes de ELF, PSARC ou arquivos comerciais.\n"];
  return report;
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
    UIAlertController *menu=[UIAlertController alertControllerWithTitle:
          @"Relatório completo do Ascension"
          message:@"Status, lote PPC, AOT_EXEC, grafo e diagnósticos em um só lugar."
          preferredStyle:UIAlertControllerStyleActionSheet];
    [menu addAction:[UIAlertAction actionWithTitle:@"Visualizar relatório"
          style:UIAlertActionStyleDefault handler:^(__unused UIAlertAction *a){
          [self openAdvancedPpuReport:sender];
    }]];
    [menu addAction:[UIAlertAction actionWithTitle:@"Compartilhar TXT · direto ao ChatGPT"
          style:UIAlertActionStyleDefault handler:^(__unused UIAlertAction *a){
          [self arExportPpuText];
    }]];
    [menu addAction:[UIAlertAction actionWithTitle:@"Salvar TXT · Arquivos"
          style:UIAlertActionStyleDefault handler:^(__unused UIAlertAction *a){
          [self arSavePpuTextToFiles];
    }]];
    [menu addAction:[UIAlertAction actionWithTitle:@"Copiar tudo"
          style:UIAlertActionStyleDefault handler:^(__unused UIAlertAction *a){
          [self arCopyAllPpuText];
    }]];
    [menu addAction:[UIAlertAction actionWithTitle:@"Cancelar"
          style:UIAlertActionStyleCancel handler:nil]];
    UIPopoverPresentationController *popover=menu.popoverPresentationController;
    if(popover){popover.sourceView=sender;popover.sourceRect=sender.bounds;}
    [self.window.rootViewController presentViewController:menu animated:YES completion:nil];
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
  self.status.text=@"M7.50: verificando arquivos em AscensionRecomp/NPUA80918; leitura somente, sem alteração…";
  dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{
    NSError *error=nil;
    NSDictionary *manifest=ARGameFolderImportLocalDocuments(&error);
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
      self.m750HostObservation=(manifest && bytes.length)?
          [NSString stringWithFormat:
             @"comprovado: arquivo=%@; bytes_lidos_HOST=%lu; momento=%@; NOTA: NÃO é cellFsRead",
             relative?:@"NÃO MEDIDO",(unsigned long)bytes.length,
             [[NSDate date] description]]:nil;
      self.folderReport=report;
      self.ppuDiagnosticsButton.enabled=YES;
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
  self.status.text=@"M7.46.1: volte à pasta ACIMA de NPUA80918, use Selecionar, MARQUE a pasta NPUA80918 e confirme Abrir. Não marque USRDIR nem arquivos individuais.";
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
     if(!chosen && urls.count==1)chosen=urls.firstObject;
     if(!chosen){
       self.status.text=@"M7.46.1: marque somente NPUA80918 no diretório acima para autorizar a pasta inteira.";
       return;
     }
     self.status.text=@"M7.46.1: pasta marcada; verificando acesso somente leitura…";
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{
      NSError *error=nil;
      NSDictionary *manifest=ARGameFolderImport(chosen,&error);
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
        if(report){
          self.folderReport=report;
          self.status.text=[NSString stringWithFormat:
                 @"Pasta de jogo selecionada.\n%@",report];
          self.ppuDiagnosticsButton.enabled=YES;
        }else{
          NSString *detail=error.localizedDescription?:@"sem acesso ao diretório";
          self.folderReport=[NSString stringWithFormat:
                @"M7.38 F0 — FALHA IMPORTAÇÃO PASTA\n"
                 "Erro (%@/%ld): %@\n"
                 "Selecione NPUA80918 e toque Abrir (azul) no topo.\n"
                 "Nenhum arquivo comercial foi enviado.\n",
                 error.domain?:@"sem domínio",(long)error.code,detail];
          self.status.text=[NSString stringWithFormat:
                 @"Importação da pasta falhou: %@\n"
                  "Tente selecionar NPUA80918 e toque Abrir.",detail];
          self.ppuDiagnosticsButton.enabled=YES;
        }
      });
    });
    return;
 }
 (void)controller;
 NSURL*url=urls.firstObject;if(!url)return;
 BOOL scoped=[url startAccessingSecurityScopedResource];
 self.shaderBusy=YES;
 self.ppuReport=nil;self.ppuSummary=nil;self.ppuBatchReport=nil;self.m750Run=nil;
 self.ppuProgress=@"GOWA.ELF recebido; preparando leitura e validação.";
 self.ppuBatchButton.enabled=NO;
 [self.ppuBatchButton setTitle:@"Copiar lote PPC (até 32 instruções)" forState:UIControlStateNormal];
 self.ppuReportButton.enabled=NO;self.ppuAdvancedButton.enabled=NO;
 /* Keep live status/report available while native probes run off-main. */
 self.ppuDiagnosticsButton.enabled=YES;
 [self.ppuDiagnosticsButton setTitle:@"Relatório ao vivo · em execução"
                            forState:UIControlStateNormal];
 self.status.text=@"GOWA.ELF recebido. Leitura e execução PPU/AOT em segundo plano…";
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
        @"Instalação reconhecida: %@ · %lu arquivos · %.2f GiB · %lu PSARC. Preparando runtime PPU nativo...",
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
       "Opcode inicial guest=0x%08X · evidências=0x%X\n"
       "AR_UNRESOLVED=-3: PC guest sem ARM64 registrado; AOT ONLY proíbe fallback.\n",
       nativeRC,native[1],native[2],native[3],
       native[4],native[13],native[5],
       (int)native[8],(int)native[9],(int)native[10],
       gameReady?@"SIM (USRDIR)":@"NÃO (M7.0 não iniciado)",
       (unsigned long)gameFiles.count,gameBytes,(unsigned long)psarcCount,
       (int)native[11],native[12],
       (int)native[6],native[7],native[14],native[15]];

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
