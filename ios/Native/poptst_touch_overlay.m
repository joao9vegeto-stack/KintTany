/* Transparent Xbox gamepad HUD drawn over the SDL/UIKit game window.
 * Uses exactly SDL_GamepadButton bit positions consumed by rePOP input_ios.c. */
#import <UIKit/UIKit.h>
#import <QuartzCore/QuartzCore.h>
#include <SDL3/SDL.h>
#include <SDL3/SDL_video.h>
#include <stdint.h>
#include <math.h>
#include <stdio.h>

extern void poptst_engine_exit_to_launcher(void);
static NSMutableArray<UIView *> *s_hud_controls;
static id s_exit_target;
static __weak UIWindow *s_hud_window;
static UILabel *s_fps_label;
static CFTimeInterval s_fps_last_refresh;
/* Adjustable camera sensitivity. 1.6x is the new default, persisted locally. */
static const CGFloat s_cam_levels[] = {0.5, 0.75, 1.0, 1.5, 2.0};
static NSInteger s_cam_mode=2;
static CGFloat s_cam_gain=1.0;
static UIButton *s_cam_button;
static UIButton *s_resolution_button;
static const int s_resolution_percents[] = {100,150,225};
static const int s_resolution_labels[] = {480,720,1080};
static NSInteger s_resolution_mode=0;
extern void poptst_ios_set_look_percent(int percent);
extern void xbox_SetRenderScalePercent(int percent);
extern void poptst_engine_trace(const char *);
static void poptst_apply_camera(void) {
    /* Game-authored lifted camera function sub_000DBDE0 calls
     * resot_scale_look: affect THAT option, not merely pad saturation. */
    poptst_ios_set_look_percent((int)(100.0*s_cam_gain+0.5));
}
static void poptst_apply_resolution(void) {
    xbox_SetRenderScalePercent(s_resolution_percents[s_resolution_mode]);
    char message[120];
    snprintf(message,sizeof message,"VIDEO B26: GPU internal target %dp (%d%%)",
             s_resolution_labels[s_resolution_mode],s_resolution_percents[s_resolution_mode]);
    poptst_engine_trace(message);
}
extern float poptst_ios_real_fps(void);
extern void poptst_engine_trace(const char *);

extern void poptst_touch_state(int32_t,int32_t,int32_t,int32_t,int32_t,int32_t,int32_t);
static int32_t lx,ly,rx,ry,lt,rt,buttons;
static void flush_input(void) { poptst_touch_state(lx,ly,rx,ry,lt,rt,buttons); }

@interface PoPTSTPadZone:UIView
@property(nonatomic) BOOL right;
@end
@implementation PoPTSTPadZone {
    UITouch *_tracked;
    UIView *_knob;
    CGPoint _origin;
}
- (instancetype)initWithFrame:(CGRect)frame {
    if ((self=[super initWithFrame:frame])) {
        self.multipleTouchEnabled=YES;
        self.backgroundColor=[UIColor colorWithWhite:0.1 alpha:0.18];
        self.layer.borderWidth=2;
        self.layer.cornerRadius=42;
        self.layer.borderColor=[UIColor colorWithRed:0.77 green:0.63 blue:0.3 alpha:0.72].CGColor;
        _knob=[[UIView alloc] initWithFrame:CGRectMake(40,40,42,42)];
        _knob.backgroundColor=[UIColor colorWithRed:0.27 green:0.45 blue:0.7 alpha:0.7];
        _knob.layer.cornerRadius=21;
        _knob.userInteractionEnabled=NO;
        [self addSubview:_knob];
    }
    return self;
}
- (void)layoutSubviews { [super layoutSubviews]; if(!_tracked) _knob.center=CGPointMake(CGRectGetMidX(self.bounds),CGRectGetMidY(self.bounds)); }
- (void)record:(UITouch *)touch {
    /* Floating origin: a press anywhere in the zone starts centered instead
     * of jumping to a max-axis value. Clamp radially for diagonal accuracy. */
    CGPoint p=[touch locationInView:self];
    CGFloat range=MAX(46,MIN(self.bounds.size.width,self.bounds.size.height)*0.40);
    CGFloat dx=(p.x-_origin.x)/range,dy=(p.y-_origin.y)/range;
    CGFloat length=hypot(dx,dy);
    if(length>1.0){dx/=length;dy/=length;length=1.0;}
    _knob.center=CGPointMake(_origin.x+dx*range*.55,
                             _origin.y+dy*range*.55);
    if(self.right){
        /* Xbox game camera: compensate for its native stick deadzone,
         * retain fine center control, and offer 4 user-selectable speeds. */
        CGFloat output=length<=0.045 ? 0.0 :
            MIN(1.0,pow((length-0.045)/0.955,0.96));
        CGFloat scale=length>0.0001?output/length:0.0;
        rx=(int32_t)lrint(MAX(-1.0,MIN(1.0,dx*scale))*32767.0);
        ry=(int32_t)lrint(MAX(-1.0,MIN(1.0,dy*scale))*32767.0);
    } else {
        lx=(int32_t)lrint(dx*32767.0);
        ly=(int32_t)lrint(dy*32767.0);
    }
    flush_input();
}
- (void)touchesBegan:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event {
    (void)event;
    if(!_tracked){
        _tracked=touches.anyObject;
        _origin=[_tracked locationInView:self];
        _knob.center=_origin;
        [self record:_tracked];
    }
}
- (void)touchesMoved:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event { (void)event; if([touches containsObject:_tracked]) [self record:_tracked]; }
- (void)touchesEnded:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event { (void)event; if([touches containsObject:_tracked]){_tracked=nil;if(self.right)rx=ry=0;else lx=ly=0;_knob.center=CGPointMake(CGRectGetMidX(self.bounds),CGRectGetMidY(self.bounds));flush_input();} }
- (void)touchesCancelled:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event { [self touchesEnded:touches withEvent:event]; }
@end

@interface PoPTSTButton:UIControl
@property(nonatomic) int bit;
@end
@implementation PoPTSTButton
- (void)down { buttons|=(1u<<self.bit);flush_input(); }
- (void)up { buttons&=~(1u<<self.bit);flush_input(); }
@end

static PoPTSTButton *new_button(UIView *root,NSString *title,int bit,CGRect bounds) {
    PoPTSTButton *b=[[PoPTSTButton alloc] initWithFrame:bounds];
    b.bit=bit;
    b.layer.cornerRadius=MIN(bounds.size.width,bounds.size.height)*0.48;
    b.layer.borderColor=[UIColor colorWithRed:.85 green:.69 blue:.35 alpha:1].CGColor;
    b.layer.borderWidth=1.5;
    b.backgroundColor=[UIColor colorWithRed:.17 green:.3 blue:.53 alpha:.66];
    UILabel *text=[[UILabel alloc] initWithFrame:b.bounds];
    text.autoresizingMask=UIViewAutoresizingFlexibleWidth|UIViewAutoresizingFlexibleHeight;
    text.text=title;text.textAlignment=NSTextAlignmentCenter;
    text.font=[UIFont boldSystemFontOfSize:15];text.textColor=UIColor.whiteColor;
    [b addSubview:text];
    [b addTarget:b action:@selector(down) forControlEvents:UIControlEventTouchDown];
    [b addTarget:b action:@selector(up) forControlEvents:UIControlEventTouchUpInside|UIControlEventTouchUpOutside|UIControlEventTouchCancel];
    [root addSubview:b];
    [s_hud_controls addObject:b];
    return b;
}
@interface PoPTSTCameraSensitivity:UIButton
@end
@implementation PoPTSTCameraSensitivity
- (void)cycle {
    s_cam_mode=(s_cam_mode+1)%5;
    s_cam_gain=s_cam_levels[s_cam_mode];
    poptst_apply_camera();
    [[NSUserDefaults standardUserDefaults] setInteger:s_cam_mode forKey:@"PoPTSTCameraModeV3"];
    [self setTitle:[NSString stringWithFormat:@"CAM %.2g×",(double)s_cam_gain] forState:UIControlStateNormal];
    char line[96]; snprintf(line,sizeof line,"INPUT B27: title-native camera sensitivity %.2gfx",(double)s_cam_gain);
    poptst_engine_trace(line);
}
@end
@interface PoPTSTResolutionButton:UIButton
@end
@implementation PoPTSTResolutionButton
- (void)cycle {
    s_resolution_mode=(s_resolution_mode+1)%3;
    [[NSUserDefaults standardUserDefaults] setInteger:s_resolution_mode forKey:@"PoPTSTResolutionMode"];
    poptst_apply_resolution();
    [self setTitle:[NSString stringWithFormat:@"RES %dp",s_resolution_labels[s_resolution_mode]] forState:UIControlStateNormal];
}
@end

@interface PoPTSTTrigger:UIControl
@property(nonatomic) BOOL isRight;
@end
@implementation PoPTSTTrigger
- (void)down {
    if (self.isRight) rt=32767; else lt=32767;
    flush_input();
}
- (void)up {
    if (self.isRight) rt=0; else lt=0;
    flush_input();
}
@end
static PoPTSTTrigger *new_trigger(UIView *root,NSString *title,BOOL right,CGRect rect) {
    PoPTSTTrigger *b=[[PoPTSTTrigger alloc] initWithFrame:rect];
    b.isRight=right;
    b.backgroundColor=[UIColor colorWithRed:.19 green:.31 blue:.48 alpha:.78];
    b.layer.cornerRadius=MIN(rect.size.height,rect.size.width)*.43;
    b.layer.borderWidth=1.5;
    b.layer.borderColor=[UIColor colorWithRed:.85 green:.69 blue:.35 alpha:1].CGColor;
    UILabel *label=[[UILabel alloc] initWithFrame:b.bounds];
    label.autoresizingMask=UIViewAutoresizingFlexibleWidth|UIViewAutoresizingFlexibleHeight;
    label.text=title; label.textAlignment=NSTextAlignmentCenter;
    label.font=[UIFont boldSystemFontOfSize:14]; label.textColor=UIColor.whiteColor;
    [b addSubview:label];
    [b addTarget:b action:@selector(down) forControlEvents:UIControlEventTouchDown];
    [b addTarget:b action:@selector(up) forControlEvents:UIControlEventTouchUpInside|UIControlEventTouchUpOutside|UIControlEventTouchCancel];
    [root addSubview:b]; [s_hud_controls addObject:b]; return b;
}


extern const char *poptst_engine_data_path(void);
static void poptst_save_message(NSString *title, NSString *info) {
    UIViewController *controller=s_hud_window.rootViewController;
    if(!controller)return;
    UIAlertController *a=[UIAlertController alertControllerWithTitle:title message:info preferredStyle:UIAlertControllerStyleAlert];
    [a addAction:[UIAlertAction actionWithTitle:@"OK" style:UIAlertActionStyleDefault handler:nil]];
    [controller presentViewController:a animated:YES completion:nil];
}
@interface PoPTSTSaveButton:UIButton
@end
@implementation PoPTSTSaveButton
- (void)backupProgress {
    const char *data=poptst_engine_data_path();
    if (!data || !*data) { poptst_save_message(@"Sem jogo",@"Inicie o jogo antes do backup."); return; }
    NSFileManager *fm=[NSFileManager defaultManager];
    NSString *base=[NSString stringWithUTF8String:data];
    NSString *source=[base stringByAppendingPathComponent:@"saves/xbox-retail"];
    /* The B27 backup accidentally counted and copied .devices/Partition*.img
     * (synthetic Xbox HDD), even when there was NO actual gameplay save.
     * Only title saves belong in a portable progress backup. */
    NSArray<NSString *> *saveNames=@[@"UDATA",@"TDATA",@"UserData",@"TitleData"];
    BOOL hasSaves=NO;
    for (NSString *folder in saveNames) {
        NSString *path=[source stringByAppendingPathComponent:folder];
        NSDirectoryEnumerator *enumerator=[fm enumeratorAtPath:path];
        for (NSString *item in enumerator) {
            NSString *filename=[path stringByAppendingPathComponent:item];
            NSDictionary *attrs=[fm attributesOfItemAtPath:filename error:NULL];
            if ([attrs[NSFileType] isEqualToString:NSFileTypeRegular] &&
                [attrs[NSFileSize] unsignedLongLongValue]>0) {
                hasSaves=YES; break;
            }
        }
        if (hasSaves) break;
    }
    if(!hasSaves){
        poptst_save_message(@"Nenhum save do jogo",@"Salve primeiro numa fonte de areia. Backup copia os arquivos do jogo, não é savestate do quadro atual.");
        return;
    }
    NSString *dir=[base stringByAppendingPathComponent:@"backups"];
    NSString *tmp=[dir stringByAppendingPathComponent:@"native-save-pending"];
    NSString *dst=[dir stringByAppendingPathComponent:@"native-save-slot"];
    NSString *prev=[dir stringByAppendingPathComponent:@"native-save-previous"];
    NSError *error=nil;
    [fm createDirectoryAtPath:dir withIntermediateDirectories:YES attributes:nil error:&error];
    [fm removeItemAtPath:tmp error:NULL];
    BOOL ok=!error && [fm createDirectoryAtPath:tmp withIntermediateDirectories:YES attributes:nil error:&error];
    if(ok) {
        for (NSString *folder in saveNames) {
            NSString *from=[source stringByAppendingPathComponent:folder];
            NSString *to=[tmp stringByAppendingPathComponent:folder];
            if (![fm fileExistsAtPath:from]) continue;
            if (![fm copyItemAtPath:from toPath:to error:&error]) { ok=NO; break; }
        }
    }
    if(ok) {
        [fm removeItemAtPath:prev error:NULL];
        if([fm fileExistsAtPath:dst]) ok=[fm moveItemAtPath:dst toPath:prev error:&error];
        if(ok)ok=[fm moveItemAtPath:tmp toPath:dst error:&error];
        if(!ok && [fm fileExistsAtPath:prev] && ![fm fileExistsAtPath:dst])
            [fm moveItemAtPath:prev toPath:dst error:NULL];
    }
    if(!ok){
        poptst_engine_trace("SAVE B27: native-save backup failed");
        poptst_save_message(@"Backup falhou",error.localizedDescription ?: @"Arquivo ocupado ou sem permissão.");
    } else {
        poptst_engine_trace("SAVE B27: native-save-slot backed up");
        poptst_save_message(@"Backup de progresso criado",@"Restaurável pelo launcher após reabrir o aplicativo; dentro do jogo use Carregar. Não é savestate instantâneo.");
    }
}
@end
@interface PoPTSTExitTarget : NSObject
- (void)exitPressed;
@end
@implementation PoPTSTExitTarget
- (void)exitPressed {
    UIViewController *controller=s_hud_window.rootViewController;
    if(!controller){poptst_engine_exit_to_launcher();return;}
    UIAlertController *a=[UIAlertController alertControllerWithTitle:@"Encerrar completamente?"
      message:@"O processo do jogo e todos os recursos Xbox/Vulkan serão encerrados. Reabra PoPTST/LiveContainer. Progresso não salvo no jogo será perdido."
      preferredStyle:UIAlertControllerStyleAlert];
    [a addAction:[UIAlertAction actionWithTitle:@"Cancelar" style:UIAlertActionStyleCancel handler:nil]];
    [a addAction:[UIAlertAction actionWithTitle:@"Encerrar" style:UIAlertActionStyleDestructive handler:^(UIAlertAction *item){(void)item;poptst_engine_exit_to_launcher();}]];
    [controller presentViewController:a animated:YES completion:nil];
}
@end

void poptst_ios_touch_overlay_uninstall(void) {
    if (![NSThread isMainThread]) return;
    for (UIView *control in s_hud_controls) [control removeFromSuperview];
    [s_hud_controls removeAllObjects];
    s_hud_controls = nil;
    s_exit_target = nil;
    s_hud_window = nil; s_fps_label = nil; s_fps_last_refresh = 0; s_cam_button=nil; s_resolution_button=nil;
    lx=ly=rx=ry=lt=rt=buttons=0;
    flush_input();
}

void poptst_ios_touch_overlay_install(SDL_Window *sdl_window) {
    if (![NSThread isMainThread] || s_hud_controls) return;
    if(!sdl_window) return;
    SDL_PropertiesID props=SDL_GetWindowProperties(sdl_window);
    UIWindow *window=(__bridge UIWindow *)SDL_GetPointerProperty(props,SDL_PROP_WINDOW_UIKIT_WINDOW_POINTER,NULL);
    /* SDL_uikitview setSDLWindow replaces rootViewController.view when the
     * Vulkan CAMetalLayer is created (Build23). UI controls attached to that
     * view disappear behind the new Metal view. Attach directly to UIWindow
     * and raise above subsequent SDL root-view swaps instead. */
    UIView *root=window;
    if (!root) return;
    s_hud_window=window;
    s_hud_controls = [NSMutableArray array];
    poptst_engine_trace("HUD B24: attaching controls to UIWindow ABOVE replaceable Vulkan view");
    CGFloat w=root.bounds.size.width, h=root.bounds.size.height;
    /* Slightly larger floating sticks; preserve the landscape separation
     * between camera, A/B/X/Y and the D-pad at 16:9. */
    CGFloat z=MIN(158,MAX(116,h*0.31));
    PoPTSTPadZone *left=[[PoPTSTPadZone alloc] initWithFrame:CGRectMake(22,h-z-22,z,z)];
    left.autoresizingMask=UIViewAutoresizingFlexibleTopMargin|UIViewAutoresizingFlexibleRightMargin;
    [root addSubview:left];
    [s_hud_controls addObject:left];
    PoPTSTPadZone *right=[[PoPTSTPadZone alloc] initWithFrame:CGRectMake(w-z-245,h-z-22,z,z)];
    right.right=YES;
    right.autoresizingMask=UIViewAutoresizingFlexibleTopMargin|UIViewAutoresizingFlexibleLeftMargin;
    [root addSubview:right];
    [s_hud_controls addObject:right];
    CGFloat bx=w-173,by=h-164;
    PoPTSTButton *a=new_button(root,@"A",SDL_GAMEPAD_BUTTON_SOUTH,CGRectMake(bx+55,by+55,48,48));
    PoPTSTButton *b=new_button(root,@"B",SDL_GAMEPAD_BUTTON_EAST,CGRectMake(bx+108,by+12,48,48));
    PoPTSTButton *x=new_button(root,@"X",SDL_GAMEPAD_BUTTON_WEST,CGRectMake(bx,by+12,48,48));
    PoPTSTButton *y=new_button(root,@"Y",SDL_GAMEPAD_BUTTON_NORTH,CGRectMake(bx+55,by-32,48,48));
    for(PoPTSTButton *control in @[a,b,x,y]) control.autoresizingMask=UIViewAutoresizingFlexibleLeftMargin|UIViewAutoresizingFlexibleTopMargin;
    /* Compact real game FPS at the upper-left, above LB. This is only
     * the number of successfully submitted NV2A swapchain frames / time. */
    s_fps_label=[[UILabel alloc] initWithFrame:CGRectMake(10,8,88,24)];
    s_fps_label.text=@"FPS 0.0";
    s_fps_label.font=[UIFont monospacedDigitSystemFontOfSize:12 weight:UIFontWeightBold];
    s_fps_label.textColor=UIColor.whiteColor;
    s_fps_label.backgroundColor=[UIColor colorWithWhite:0 alpha:.62];
    s_fps_label.layer.cornerRadius=5; s_fps_label.clipsToBounds=YES;
    s_fps_label.textAlignment=NSTextAlignmentCenter;
    s_fps_label.userInteractionEnabled=NO;
    s_fps_label.autoresizingMask=UIViewAutoresizingFlexibleRightMargin|UIViewAutoresizingFlexibleBottomMargin;
    [root addSubview:s_fps_label]; [s_hud_controls addObject:s_fps_label];
    /* B26 mistakenly read V1 and saved V2; use a single V3 key. */
    id stored=[[NSUserDefaults standardUserDefaults] objectForKey:@"PoPTSTCameraModeV3"];
    s_cam_mode=stored?MAX(0,MIN(4,[[NSUserDefaults standardUserDefaults] integerForKey:@"PoPTSTCameraModeV3"])):2;
    s_cam_gain=s_cam_levels[s_cam_mode];
    poptst_apply_camera();
    NSInteger requestedResolution=[[NSUserDefaults standardUserDefaults] integerForKey:@"PoPTSTResolutionMode"];
    s_resolution_mode=MAX(0,MIN(2,requestedResolution));
    poptst_apply_resolution();
    PoPTSTResolutionButton *resolution=[[PoPTSTResolutionButton alloc] initWithFrame:CGRectMake(108,8,105,28)];
    resolution.backgroundColor=[UIColor colorWithWhite:0 alpha:.62];
    resolution.layer.cornerRadius=6;
    resolution.titleLabel.font=[UIFont monospacedDigitSystemFontOfSize:12 weight:UIFontWeightBold];
    [resolution setTitle:[NSString stringWithFormat:@"RES %dp",s_resolution_labels[s_resolution_mode]]
              forState:UIControlStateNormal];
    [resolution setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
    [resolution addTarget:resolution action:@selector(cycle) forControlEvents:UIControlEventTouchUpInside];
    [root addSubview:resolution]; [s_hud_controls addObject:resolution]; s_resolution_button=resolution;
    PoPTSTCameraSensitivity *cam=[[PoPTSTCameraSensitivity alloc] initWithFrame:CGRectMake(w-192,8,109,28)];
    cam.frame=CGRectMake(w-192,8,109,28);
    cam.backgroundColor=[UIColor colorWithWhite:0 alpha:.62];
    cam.layer.cornerRadius=6;
    cam.titleLabel.font=[UIFont monospacedDigitSystemFontOfSize:12 weight:UIFontWeightBold];
    [cam setTitle:[NSString stringWithFormat:@"CAM %.2g×",(double)s_cam_gain] forState:UIControlStateNormal];
    [cam setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
    [cam addTarget:cam action:@selector(cycle) forControlEvents:UIControlEventTouchUpInside];
    cam.autoresizingMask=UIViewAutoresizingFlexibleLeftMargin|UIViewAutoresizingFlexibleBottomMargin;
    [root addSubview:cam]; [s_hud_controls addObject:cam]; s_cam_button=cam;
    new_button(root,@"LB",SDL_GAMEPAD_BUTTON_LEFT_SHOULDER,CGRectMake(18,45,58,38));
    new_trigger(root,@"LT",NO,CGRectMake(18,94,58,38));
    PoPTSTButton *rb=new_button(root,@"RB",SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER,CGRectMake(w-77,45,58,38));
    rb.autoresizingMask=UIViewAutoresizingFlexibleLeftMargin|UIViewAutoresizingFlexibleBottomMargin;
    PoPTSTTrigger *rtButton=new_trigger(root,@"RT",YES,CGRectMake(w-77,94,58,38));
    rtButton.autoresizingMask=UIViewAutoresizingFlexibleLeftMargin|UIViewAutoresizingFlexibleBottomMargin;
    PoPTSTButton *back=new_button(root,@"BACK",SDL_GAMEPAD_BUTTON_BACK,CGRectMake(w*0.5-126,22,76,36));
    back.autoresizingMask=UIViewAutoresizingFlexibleLeftMargin|UIViewAutoresizingFlexibleRightMargin;
    UIButton *exitButton=[UIButton buttonWithType:UIButtonTypeSystem];
    exitButton.frame=CGRectMake(w*0.5-36,22,72,36);
    exitButton.autoresizingMask=UIViewAutoresizingFlexibleLeftMargin|UIViewAutoresizingFlexibleRightMargin;
    exitButton.layer.cornerRadius=12;
    exitButton.layer.borderColor=[UIColor colorWithRed:0.99 green:0.65 blue:0.32 alpha:1].CGColor;
    exitButton.layer.borderWidth=2;
    exitButton.backgroundColor=[UIColor colorWithRed:0.34 green:0.14 blue:0.15 alpha:0.92];
    [exitButton setTitle:@"EXIT" forState:UIControlStateNormal];
    [exitButton setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
    exitButton.titleLabel.font=[UIFont boldSystemFontOfSize:15];
    s_exit_target=[PoPTSTExitTarget new];
    [exitButton addTarget:s_exit_target action:@selector(exitPressed) forControlEvents:UIControlEventTouchUpInside];
    [root addSubview:exitButton]; [s_hud_controls addObject:exitButton];
    PoPTSTButton *start=new_button(root,@"START",SDL_GAMEPAD_BUTTON_START,CGRectMake(w*0.5+50,22,76,36));
    start.autoresizingMask=UIViewAutoresizingFlexibleLeftMargin|UIViewAutoresizingFlexibleRightMargin;
    PoPTSTSaveButton *save=[[PoPTSTSaveButton alloc] initWithFrame:CGRectMake(w*0.5-43,65,86,32)];
    save.backgroundColor=[UIColor colorWithRed:.17 green:.32 blue:.36 alpha:.80];
    save.layer.cornerRadius=9; save.layer.borderWidth=1.3;
    save.layer.borderColor=[UIColor colorWithRed:.85 green:.69 blue:.35 alpha:1].CGColor;
    save.titleLabel.font=[UIFont boldSystemFontOfSize:12];
    [save setTitle:@"BACKUP" forState:UIControlStateNormal];
    [save setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];
    [save addTarget:save action:@selector(backupProgress) forControlEvents:UIControlEventTouchUpInside];
    save.autoresizingMask=UIViewAutoresizingFlexibleLeftMargin|UIViewAutoresizingFlexibleRightMargin;
    [root addSubview:save]; [s_hud_controls addObject:save];
    /* Separate actual Xbox D-pad signals, not virtual keyboard shortcuts. */
    CGFloat dpx=z+102, dpy=h-125;
    new_button(root,@"↑",SDL_GAMEPAD_BUTTON_DPAD_UP,CGRectMake(dpx+36,dpy,34,34));
    new_button(root,@"↓",SDL_GAMEPAD_BUTTON_DPAD_DOWN,CGRectMake(dpx+36,dpy+68,34,34));
    new_button(root,@"←",SDL_GAMEPAD_BUTTON_DPAD_LEFT,CGRectMake(dpx,dpy+34,34,34));
    new_button(root,@"→",SDL_GAMEPAD_BUTTON_DPAD_RIGHT,CGRectMake(dpx+72,dpy+34,34,34));
    [window bringSubviewToFront:s_fps_label];
    char message[120];
    snprintf(message,sizeof message,"HUD B24: %lu touch elements attached to UIWindow", (unsigned long)s_hud_controls.count);
    poptst_engine_trace(message);
}

/* UIKit only: keep touch controls above the SDL-owned root view after
 * SDL_Vulkan_CreateSurface/UIKit_Metal_CreateView changes the view hierarchy. */
void poptst_ios_touch_overlay_tick(void) {
    if (![NSThread isMainThread] || !s_hud_controls.count || !s_hud_window) return;
    for (UIView *item in s_hud_controls)
        if (item.superview != s_hud_window) [s_hud_window addSubview:item];
        else [s_hud_window bringSubviewToFront:item];
    CFTimeInterval now=CACurrentMediaTime();
    if (s_fps_label && (!s_fps_last_refresh || now-s_fps_last_refresh >= .25)) {
        s_fps_last_refresh=now;
        s_fps_label.text=[NSString stringWithFormat:@"FPS %.1f",poptst_ios_real_fps()];
    }
}
