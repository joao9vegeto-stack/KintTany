/* AscensionRecomp iPhone Metal diagnostic host. No commercial game code. */
#import <UIKit/UIKit.h>
#import <Metal/Metal.h>
#import "ARMetalView.h"

extern int rsx_metal_backend_init(unsigned int width, unsigned int height, const char* title);
extern void rsx_metal_backend_shutdown(void);
extern void rsx_metal_backend_present(void);
extern int ar_probe_vm_init(void);
extern void ar_probe_vm_shutdown(void);
extern int ar_probe_rsx_clear_flip(unsigned cycle, unsigned int *expected, unsigned int *observed);
extern int ar_probe_rsx_triangle(unsigned int *background, unsigned int *sample);
extern int ar_probe_rsx_fixed_stage(void);
extern int ar_probe_rsx_dma_triangle(unsigned int *background,unsigned int *sample);
extern int ar_probe_rsx_indexed_quad(unsigned use32,unsigned int *background,unsigned int *sample);
extern int ar_probe_rsx_texture(void *layer,unsigned swizzled,unsigned int out_pixels[4]);
extern int ar_probe_rsx_texture_registers(unsigned swizzled,unsigned int out_pixels[4]);

@interface ARProbeDelegate : UIResponder <UIApplicationDelegate>
@property(nonatomic,strong) UIWindow *window;
@property(nonatomic,strong) ARMetalView *metalView;
@property(nonatomic,strong) UILabel *status;
@property(nonatomic,assign) BOOL ready;
@property(nonatomic,assign) NSUInteger successfulFrames;
@property(nonatomic,assign) NSUInteger guestAttempts;
@property(nonatomic,assign) NSUInteger indexedAttempts;
@property(nonatomic,assign) NSUInteger textureAttempts;
@property(nonatomic,assign) NSUInteger registerTextureAttempts;
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
