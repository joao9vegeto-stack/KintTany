/* AscensionRecomp iPhone Metal diagnostic host. No commercial game code. */
#import <UIKit/UIKit.h>
#import <Metal/Metal.h>
#import "ARMetalView.h"

extern int rsx_metal_backend_init(unsigned int width, unsigned int height, const char* title);
extern void rsx_metal_backend_shutdown(void);
extern void rsx_metal_backend_present(void);
extern int ar_probe_vm_init(void);
extern void ar_probe_vm_shutdown(void);

@interface ARProbeDelegate : UIResponder <UIApplicationDelegate>
@property(nonatomic,strong) UIWindow *window;
@property(nonatomic,strong) ARMetalView *metalView;
@property(nonatomic,strong) UILabel *status;
@property(nonatomic,assign) BOOL ready;
@property(nonatomic,assign) NSUInteger successfulFrames;
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
            rsx_metal_backend_present();
            [self drawNextFrame:nil];
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
    NSString *message=nil;
    BOOL success=[self.metalView presentDiagnosticFrame:self.successfulFrames
                                                  error:&message];
    if (success) {
        self.successfulFrames++;
        self.status.text=[NSString stringWithFormat:
            @"RSX→Metal: inicializado\n"
             "GPU Metal: %lu quadro(s) apresentados\n"
             "Toque para trocar a cor (azul / verde / roxo)\n"
             "Diagnóstico sem jogo PS3",
             (unsigned long)self.successfulFrames];
    } else {
        self.status.text=[NSString stringWithFormat:
            @"RSX→Metal: inicializado, mas apresentação falhou.\n"
             "Erro: %@\nEnvie esta tela para análise.",
             message ?: @"desconhecido"];
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
