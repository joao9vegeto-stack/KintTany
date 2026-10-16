/* AscensionRecomp iPhone Metal diagnostic host. No commercial game code. */
#import <UIKit/UIKit.h>
#import <Metal/Metal.h>
#import "ARMetalView.h"
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>
#import <CommonCrypto/CommonDigest.h>
extern int ar_private_elf_inspect(const unsigned char*,size_t,unsigned int[5]);
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

@interface ARProbeDelegate : UIResponder <UIApplicationDelegate, UIDocumentPickerDelegate>
@property(nonatomic,strong) UIWindow *window;
@property(nonatomic,strong) ARMetalView *metalView;
@property(nonatomic,strong) UILabel *status;
@property(nonatomic,strong) UIScrollView *gameList;
@property(nonatomic,strong) UIScrollView *graphicsList;
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
    header.text=@"ASCENSIONRECOMP   ·   M6.6";
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
             @"NPUA80918 · M6.6: até 48 instruções PPU com registrador CTR, desvios indiretos validados e memória isolada. ELF privado no iPhone." :
             @"Diagnósticos RSX → Metal, do mais recente ao legado. Role para encontrar os testes anteriores.";
        [stack addArrangedSubview:hint];
        NSArray<UIButton *> *ordered=i==0 ? @[elfButton] : @[
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
    [elfButton setTitle:@"Importar GOWA.ELF · testar PPU" forState:UIControlStateNormal];
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
    return YES;
}


/* M5.0: NV40 guest microcode is decoded, lowered and compiled on the iPhone.
 * Failures are shown; no draw/gameplay claim is made from shader compilation. */
- (void)arSwitchTab:(UISegmentedControl *)sender {
    BOOL showGame=sender.selectedSegmentIndex==0;
    self.gameList.hidden=!showGame;
    self.graphicsList.hidden=showGame;
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
 (void)controller;
 NSURL*url=urls.firstObject;if(!url)return;
 BOOL scoped=[url startAccessingSecurityScopedResource];
 @try {
   NSError*err=nil;
   NSNumber*size=[[[NSFileManager defaultManager]
      attributesOfItemAtPath:url.path error:&err] objectForKey:NSFileSize];
   if(err||!size||size.unsignedLongLongValue>32u*1024u*1024u){
       self.status.text=@"M5.9: Arquivo indisponível ou maior que 32 MB.";return;
   }
   NSData*data=[NSData dataWithContentsOfURL:url
       options:NSDataReadingMappedIfSafe error:&err];
   if(err||!data){self.status.text=@"M5.9: Leitura falhou.";return;}
   uint32_t info[5]={0};
   int rc=ar_private_elf_inspect(data.bytes,data.length,info);
   if(rc){
       self.status.text=[NSString stringWithFormat:
          @"M5.9: erro ELF %d. Use GOWA.ELF descriptografado.",rc];return;
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
       self.status.text=@"M5.9: ELF não corresponde à NPUA80918 validada.";return;
   }
   unsigned int cpu[4]={0};
   const int cpu_rc=ar_ppu_bootstrap_four(data.bytes,data.length,info,cpu);
   if(cpu_rc){
      self.status.text=[NSString stringWithFormat:
         @"M5.9 ELF VALIDADO; M6.0 PPU FALHA %d (%u/4).\n"
          "CPU interrompida antes de M6.1.",cpu_rc,cpu[0]];
      return;
   }
   unsigned int eight[6]={0};
   const int rc8=ar_ppu_bootstrap_eight(data.bytes,data.length,info,eight);
   if(rc8) {
      self.status.text=[NSString stringWithFormat:
         @"M5.9 NPUA80918: ELF REAL VALIDADO\n"
          "M6.0 PPU 4/4 OK · M6.1 PPU FALHA %d (%u/8).\n"
          "Parada segura, sem HLE nem gameplay.",rc8,eight[0]];
      return;
   }
   if(eight[0]!=8u||eight[1]!=0x83f2b0u||eight[2]!=0x10534u||
      eight[3]!=0x10430u||eight[4]!=0x07000f90u||eight[5]!=2u) {
      self.status.text=@"M6.1: estado PPU inesperado; execução interrompida.";
      return;
   }
   unsigned int cpu16[7]={0};
   const int rc16=ar_ppu_bootstrap_sixteen(data.bytes,data.length,info,cpu16);
   if(rc16){
      self.status.text=[NSString stringWithFormat:
        @"M5.9 ELF VALIDADO · M6.0 4/4\n"
         "M6.1 PPU REAL 8/8: OK\n"
         "M6.2 PPU: FALHA %d (%u/16 instruções).\n"
         "Parada segura. HLE/SPU não iniciados.",
        rc16,cpu16[0]];
      return;
   }
   if(cpu16[0]!=16u||cpu16[1]!=0x83f2b0u||
      cpu16[2]!=0x10554u||cpu16[3]!=0x10430u||
      cpu16[4]!=0x07000ef0u||cpu16[5]!=9u||
      cpu16[6]!=0x10430u){
      self.status.text=@"M6.2: registradores ou pilha divergentes. Parada segura.";
      return;
   }
   self.status.text=@"M6.2 PPU REAL 16/16: OK · M6.3 em execução...";
    unsigned int cpu24[9]={0};
    const int rc24=ar_ppu_bootstrap_twentyfour(data.bytes,data.length,info,cpu24);
    if(rc24){
       self.status.text=[NSString stringWithFormat:
          @"M5.9 NPUA80918: ELF REAL VALIDADO\n"
           "M6.2 PPU REAL 16/16: OK\n"
           "M6.3 PARADA SEGURA %d · %u/24\n"
           "PC=0x%X · opcode=0x%08X\n"
           "Sem HLE/SPU/gameplay; instrução não ignorada.",
           rc24,cpu24[0],cpu24[8],cpu24[7]];
       return;
    }
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
       self.status.text=[NSString stringWithFormat:
          @"M5.9 NPUA80918: ELF REAL VALIDADO\n"
           "M6.3 PPU REAL 24/24: OK\n"
           "M6.4 PARADA SEGURA %d · %u/32\n"
           "PC=0x%X · opcode=0x%08X\n"
           "M6.5 não iniciada: erro não é de memória convidada.",
           rc32,cpu32[0],cpu32[8],cpu32[7]];
       return;
    }
    NSString *legacyState=legacyStackOnlyStop
       ? [NSString stringWithFormat:@"M6.4 LEGADA: -995 (%u/32) · transferida à M6.5",
                                    cpu32[0]]
       : @"M6.4 PPU REAL 32/32: OK";
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
       self.status.text=[NSString stringWithFormat:
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
             @"Sem falha de memória nesta instrução")];
       return;
    }
    NSString *old40State=knownMtctrStop ?
        [NSString stringWithFormat:@"M6.5 LEGADA: mtctr (%u/40) · transferida à M6.6",
                                   cpu40[0]] :
        @"M6.5 PPU REAL 40/40: OK";
    unsigned int cpu48[20]={0};
    const int rc48=ar_ppu_bootstrap_fortyeight(data.bytes,data.length,info,cpu48);
    if(rc48){
       NSString *faultDetail=cpu48[16]
          ? [NSString stringWithFormat:@"EA=0x%X · base=0x%X · valor=0x%X",
                cpu48[10],cpu48[11],cpu48[12]]
          : [NSString stringWithFormat:@"CTR=0x%08X%08X · indiretos=%u",
                cpu48[18],cpu48[17],cpu48[19]];
       self.status.text=[NSString stringWithFormat:
          @"M5.9 NPUA80918: ELF REAL VALIDADO\n"
           "%@\n"
           "%@\n"
           "M6.6 PARADA SEGURA %d · %u/48\n"
           "PC=0x%X · opcode=0x%08X\n"
           "%@\n"
           "Sem HLE/SPU ou gameplay.",
           legacyState,old40State,rc48,cpu48[0],cpu48[8],
           cpu48[7],faultDetail];
       return;
    }
    self.status.text=[NSString stringWithFormat:
       @"M5.9 NPUA80918: ELF REAL VALIDADO\n"
        "%@\n"
        "%@\n"
        "M6.6 PPU REAL 48/48: OK\n"
        "PC=0x%X · CTR=0x%08X%08X\n"
        "stores=%u · indiretos=%u · sombra=%u\n"
        "Execução limitada; SEM HLE/SPU/gameplay.",
        legacyState,old40State,cpu48[2],cpu48[18],cpu48[17],
        cpu48[5],cpu48[19],cpu48[15]];
  } @finally {
    if(scoped)[url stopAccessingSecurityScopedResource];
 }
}
- (void)documentPickerWasCancelled:(UIDocumentPickerViewController*)controller {
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
