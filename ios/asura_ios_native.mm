#import <UIKit/UIKit.h>
#import <Foundation/Foundation.h>
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>
#import <CoreFoundation/CoreFoundation.h>
#include <unistd.h>
#include "asura_ios_native.h"
#include "Native/asura_crash_recorder.h"
#include <fstream>
#include <mutex>
#include <condition_variable>
#include <ctime>
#include <cstdlib>
#include <exception>
#include <csignal>
#include <fcntl.h>
#include <limits.h>
#include <cstdio>
#include <cstring>
#include <memory>
#include <atomic>
namespace {
std::mutex log_mutex2; std::string log_path2; char crash_path2[PATH_MAX]{}; UIWindow* overlay_window2=nil; UIWindow* prior_window2=nil;
NSURL* selected_game_url2=nil;
bool selected_game_scope2=false;
std::atomic<bool> first_present2{false};
int log_fd2=-1;
std::string docs_path2(){NSString*p=[NSHomeDirectory() stringByAppendingPathComponent:@"Documents"];[[NSFileManager defaultManager]createDirectoryAtPath:p withIntermediateDirectories:YES attributes:nil error:nil];return p.UTF8String?p.UTF8String:"";}
void write_crash_record2(const char* message){if(!crash_path2[0])return;int fd=open(crash_path2,O_WRONLY|O_CREAT|O_APPEND,0600);if(fd>=0){write(fd,message,std::strlen(message));close(fd);}}
void log_line2(const std::string&s){std::lock_guard<std::mutex>l(log_mutex2);const std::string docs=docs_path2();if(log_path2.empty())log_path2=docs+"/log.txt";if(!crash_path2[0])std::snprintf(crash_path2,sizeof(crash_path2),"%s/crash.txt",docs.c_str());std::time_t t=std::time(nullptr);std::tm tm{};localtime_r(&t,&tm);char b[32]{};std::strftime(b,sizeof(b),"%Y-%m-%d %H:%M:%S",&tm);const std::string line=std::string(b)+" [Asura-iOS] "+s+"\n";if(log_fd2<0)log_fd2=open(log_path2.c_str(),O_WRONLY|O_CREAT|O_APPEND,0600);if(log_fd2>=0){size_t off=0;while(off<line.size()){ssize_t n=write(log_fd2,line.data()+off,line.size()-off);if(n<=0)break;off+=(size_t)n;}(void)fsync(log_fd2);}}
void exception_handler2(NSException*exception){NSString*name=exception.name?:@"unknown";NSString*reason=exception.reason?:@"none";NSArray*frames=exception.callStackSymbols?:@[];NSString*stack=[frames componentsJoinedByString:@" | "];std::string detail=std::string("FATAL_NS_EXCEPTION name=")+(name.UTF8String?name.UTF8String:"unknown")+" reason="+(reason.UTF8String?reason.UTF8String:"none")+" stack="+(stack.UTF8String?stack.UTF8String:"");log_line2(detail);write_crash_record2((detail+"\n").c_str());}
void init_log2(){static dispatch_once_t once;dispatch_once(&once,^{const std::string docs=docs_path2();log_path2=docs+"/log.txt";std::snprintf(crash_path2,sizeof(crash_path2),"%s/crash.txt",docs.c_str());log_fd2=open(log_path2.c_str(),O_WRONLY|O_CREAT|O_APPEND,0600);if(log_fd2>=0){(void)dup2(log_fd2,STDOUT_FILENO);(void)dup2(log_fd2,STDERR_FILENO);(void)setvbuf(stdout,nullptr,_IONBF,0);(void)setvbuf(stderr,nullptr,_IONBF,0);}AsuraCrashRecorderInstall(crash_path2);NSSetUncaughtExceptionHandler(&exception_handler2);log_line2("ASURA_IOS_EXECUTION_LOG_V1");log_line2("PROCESS_START");NSString*build=[[NSBundle mainBundle]objectForInfoDictionaryKey:@"CFBundleVersion"]?:@"unknown";NSString*os=UIDevice.currentDevice.systemVersion?:@"unknown";NSString*model=UIDevice.currentDevice.model?:@"unknown";NSString*bundle=NSBundle.mainBundle.bundleIdentifier?:@"unknown";log_line2(std::string("APP_ENV build=")+(build.UTF8String?build.UTF8String:"unknown")+" os="+(os.UTF8String?os.UTF8String:"unknown")+" model="+(model.UTF8String?model.UTF8String:"unknown")+" bundle="+(bundle.UTF8String?bundle.UTF8String:"unknown"));std::atexit([]{log_line2("PROCESS_EXIT");});std::set_terminate([]{log_line2("FATAL std::terminate");write_crash_record2("FATAL std::terminate\n");std::abort();});NSNotificationCenter*n=NSNotificationCenter.defaultCenter;NSArray*names=@[UIApplicationDidBecomeActiveNotification,UIApplicationWillResignActiveNotification,UIApplicationDidEnterBackgroundNotification,UIApplicationWillEnterForegroundNotification,UIApplicationWillTerminateNotification];for(NSString*name in names)[n addObserverForName:name object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification*note){log_line2(std::string("LIFECYCLE ")+note.name.UTF8String);}];});}
}
@interface AsuraNativeLauncher2:UIViewController<UIDocumentPickerDelegate>{std::string path2;std::function<std::string()>scan2;std::function<void(std::string)>start2;UILabel*status2;UILabel*location2;UIButton*play2;UIDocumentPickerViewController*picker2;}
-(instancetype)initPath:(std::string)p scan:(std::function<std::string()>)s start:(std::function<void(std::string)>)f;
-(void)showLauncherMessage:(NSString*)message;
@end
static AsuraNativeLauncher2* launcher_controller2=nil;
@implementation AsuraNativeLauncher2
-(instancetype)initPath:(std::string)p scan:(std::function<std::string()>)s start:(std::function<void(std::string)>)f{if((self=[super init])){path2=std::move(p);scan2=std::move(s);start2=std::move(f);}return self;}
-(UIButton*)button:(NSString*)t action:(SEL)a{UIButton*b=[UIButton buttonWithType:UIButtonTypeSystem];[b setTitle:t forState:UIControlStateNormal];b.titleLabel.font=[UIFont boldSystemFontOfSize:15];b.backgroundColor=[UIColor colorWithRed:.66 green:.07 blue:.13 alpha:1];[b setTitleColor:UIColor.whiteColor forState:UIControlStateNormal];b.layer.cornerRadius=10;[b.heightAnchor constraintEqualToConstant:46].active=YES;[b addTarget:self action:a forControlEvents:UIControlEventTouchUpInside];return b;}
-(void)viewDidLoad{
 [super viewDidLoad]; launcher_controller2=self;
 self.view.backgroundColor=[UIColor colorWithRed:.025 green:.027 blue:.035 alpha:1];
 CAGradientLayer*back=[CAGradientLayer layer]; back.colors=@[(id)[UIColor colorWithRed:.12 green:.025 blue:.035 alpha:1].CGColor,(id)[UIColor colorWithRed:.025 green:.027 blue:.035 alpha:1].CGColor,(id)[UIColor colorWithRed:.045 green:.05 blue:.065 alpha:1].CGColor]; back.startPoint=CGPointMake(0,0); back.endPoint=CGPointMake(1,1); back.frame=self.view.bounds; [self.view.layer insertSublayer:back atIndex:0];
 UIScrollView*scroll=[UIScrollView new]; scroll.translatesAutoresizingMaskIntoConstraints=NO; scroll.alwaysBounceVertical=YES; scroll.showsVerticalScrollIndicator=NO; [self.view addSubview:scroll];
 [NSLayoutConstraint activateConstraints:@[[scroll.leadingAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.leadingAnchor constant:20],[scroll.trailingAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.trailingAnchor constant:-20],[scroll.topAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.topAnchor constant:12],[scroll.bottomAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.bottomAnchor constant:-12]]];
 UIStackView*s=[UIStackView new]; s.axis=UILayoutConstraintAxisVertical; s.spacing=16; s.alignment=UIStackViewAlignmentFill; s.translatesAutoresizingMaskIntoConstraints=NO; [scroll addSubview:s];
 [NSLayoutConstraint activateConstraints:@[[s.leadingAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.leadingAnchor],[s.trailingAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.trailingAnchor],[s.topAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.topAnchor constant:8],[s.bottomAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.bottomAnchor constant:-10],[s.widthAnchor constraintEqualToAnchor:scroll.frameLayoutGuide.widthAnchor]]];
 UIView*hero=[UIView new]; hero.translatesAutoresizingMaskIntoConstraints=NO; hero.backgroundColor=[UIColor colorWithRed:.12 green:.035 blue:.045 alpha:1]; hero.layer.cornerRadius=22; hero.layer.borderWidth=1; hero.layer.borderColor=[UIColor colorWithRed:.75 green:.18 blue:.18 alpha:.42].CGColor; hero.clipsToBounds=YES; [s addArrangedSubview:hero]; [hero.heightAnchor constraintGreaterThanOrEqualToConstant:190].active=YES;
 CAGradientLayer*heroGlow=[CAGradientLayer layer]; heroGlow.colors=@[(id)[UIColor colorWithRed:.62 green:.055 blue:.075 alpha:.65].CGColor,(id)[UIColor colorWithRed:.16 green:.025 blue:.04 alpha:.08].CGColor]; heroGlow.startPoint=CGPointMake(0,0); heroGlow.endPoint=CGPointMake(1,1); heroGlow.frame=CGRectMake(0,0,600,240); [hero.layer insertSublayer:heroGlow atIndex:0];
 UILabel*eyebrow=[UILabel new]; eyebrow.text=@"A FÚRIA NÃO CONHECE LIMITES"; eyebrow.textColor=[UIColor colorWithRed:1 green:.58 blue:.43 alpha:1]; eyebrow.font=[UIFont systemFontOfSize:10 weight:UIFontWeightHeavy]; eyebrow.textAlignment=NSTextAlignmentCenter; eyebrow.translatesAutoresizingMaskIntoConstraints=NO; [hero addSubview:eyebrow];
 UILabel*t=[UILabel new]; t.text=@"ASURA'S\nWRATH"; t.numberOfLines=2; t.textColor=UIColor.whiteColor; t.font=[UIFont systemFontOfSize:36 weight:UIFontWeightBlack]; t.textAlignment=NSTextAlignmentCenter; t.adjustsFontSizeToFitWidth=YES; t.minimumScaleFactor=.75; t.translatesAutoresizingMaskIntoConstraints=NO; [hero addSubview:t];
 UILabel*sub=[UILabel new]; sub.text=@"RECOMPILAÇÃO NATIVA PARA iOS"; sub.textColor=[UIColor colorWithWhite:.86 alpha:1]; sub.font=[UIFont systemFontOfSize:10 weight:UIFontWeightBold]; sub.textAlignment=NSTextAlignmentCenter; sub.translatesAutoresizingMaskIntoConstraints=NO; [hero addSubview:sub];
 UIView*rule=[UIView new]; rule.backgroundColor=[UIColor colorWithRed:.88 green:.17 blue:.17 alpha:1]; rule.translatesAutoresizingMaskIntoConstraints=NO; [hero addSubview:rule];
 [NSLayoutConstraint activateConstraints:@[[eyebrow.topAnchor constraintEqualToAnchor:hero.topAnchor constant:22],[eyebrow.leadingAnchor constraintEqualToAnchor:hero.leadingAnchor constant:14],[eyebrow.trailingAnchor constraintEqualToAnchor:hero.trailingAnchor constant:-14],[t.topAnchor constraintEqualToAnchor:eyebrow.bottomAnchor constant:10],[t.leadingAnchor constraintEqualToAnchor:hero.leadingAnchor constant:10],[t.trailingAnchor constraintEqualToAnchor:hero.trailingAnchor constant:-10],[rule.topAnchor constraintEqualToAnchor:t.bottomAnchor constant:10],[rule.centerXAnchor constraintEqualToAnchor:hero.centerXAnchor],[rule.widthAnchor constraintEqualToConstant:54],[rule.heightAnchor constraintEqualToConstant:3],[sub.topAnchor constraintEqualToAnchor:rule.bottomAnchor constant:10],[sub.leadingAnchor constraintEqualToAnchor:hero.leadingAnchor constant:12],[sub.trailingAnchor constraintEqualToAnchor:hero.trailingAnchor constant:-12],[sub.bottomAnchor constraintEqualToAnchor:hero.bottomAnchor constant:-20]]];
 UILabel*build=[UILabel new]; build.text=[NSString stringWithFormat:@"KOSMICKRISP  /  BUILD %s",ASURA_IOS_BUILD_NUMBER]; build.textColor=[UIColor colorWithWhite:.64 alpha:1]; build.font=[UIFont monospacedSystemFontOfSize:10 weight:UIFontWeightMedium]; build.textAlignment=NSTextAlignmentCenter; [s addArrangedSubview:build];
 UIView*statusCard=[UIView new]; statusCard.backgroundColor=[UIColor colorWithWhite:1 alpha:.055]; statusCard.layer.cornerRadius=15; statusCard.layer.borderWidth=1; statusCard.layer.borderColor=[UIColor colorWithWhite:1 alpha:.09].CGColor; [s addArrangedSubview:statusCard];
 UIStackView*statusStack=[UIStackView new]; statusStack.axis=UILayoutConstraintAxisVertical; statusStack.spacing=7; statusStack.translatesAutoresizingMaskIntoConstraints=NO; [statusCard addSubview:statusStack];
 [NSLayoutConstraint activateConstraints:@[[statusStack.leadingAnchor constraintEqualToAnchor:statusCard.leadingAnchor constant:16],[statusStack.trailingAnchor constraintEqualToAnchor:statusCard.trailingAnchor constant:-16],[statusStack.topAnchor constraintEqualToAnchor:statusCard.topAnchor constant:14],[statusStack.bottomAnchor constraintEqualToAnchor:statusCard.bottomAnchor constant:-14]]];
 UILabel*section=[UILabel new]; section.text=@"BIBLIOTECA"; section.textColor=[UIColor colorWithRed:1 green:.48 blue:.36 alpha:1]; section.font=[UIFont systemFontOfSize:10 weight:UIFontWeightHeavy]; [statusStack addArrangedSubview:section];
 status2=[UILabel new]; status2.textAlignment=NSTextAlignmentLeft; status2.font=[UIFont systemFontOfSize:15 weight:UIFontWeightBold]; status2.numberOfLines=2; [statusStack addArrangedSubview:status2];
 location2=[UILabel new]; location2.textAlignment=NSTextAlignmentLeft; location2.textColor=[UIColor colorWithWhite:.64 alpha:1]; location2.font=[UIFont monospacedSystemFontOfSize:10 weight:UIFontWeightRegular]; location2.numberOfLines=1; location2.lineBreakMode=NSLineBreakByTruncatingMiddle; [statusStack addArrangedSubview:location2];
 UILabel*info=[UILabel new]; info.text=@"Selecione a pasta extraída que contém default.xex e os dados do jogo. O conteúdo permanece no armazenamento do dispositivo."; info.textColor=[UIColor colorWithWhite:.76 alpha:1]; info.textAlignment=NSTextAlignmentLeft; info.numberOfLines=0; info.font=[UIFont systemFontOfSize:12]; [s addArrangedSubview:info];
 UIButton*choose=[self button:@"ESCOLHER PASTA DO JOGO" action:@selector(chooseTap)]; choose.contentHorizontalAlignment=UIControlContentHorizontalAlignmentCenter; [s addArrangedSubview:choose];
 UIButton*scan=[self button:@"DETECTAR JOGO AUTOMATICAMENTE" action:@selector(scanTap)]; scan.backgroundColor=[UIColor colorWithWhite:.15 alpha:1]; scan.layer.borderWidth=1; scan.layer.borderColor=[UIColor colorWithWhite:1 alpha:.12].CGColor; [s addArrangedSubview:scan];
 play2=[self button:@"INICIAR ASURA'S WRATH  ›" action:@selector(playTap)]; play2.titleLabel.font=[UIFont systemFontOfSize:15 weight:UIFontWeightBlack]; play2.layer.cornerRadius=13; [s addArrangedSubview:play2]; [self updateStatus];
 UILabel*foot=[UILabel new]; foot.text=@"XBOX 360  •  ARM64  •  METAL / VULKAN"; foot.textColor=[UIColor colorWithWhite:.38 alpha:1]; foot.font=[UIFont systemFontOfSize:9 weight:UIFontWeightSemibold]; foot.textAlignment=NSTextAlignmentCenter; [s addArrangedSubview:foot];
}
-(void)updateStatus{BOOL ok=!path2.empty();status2.text=ok?@"JOGO DETECTADO":@"AGUARDANDO ARQUIVOS DO JOGO";status2.textColor=ok?[UIColor colorWithRed:.25 green:.85 blue:.48 alpha:1]:[UIColor colorWithRed:1 green:.7 blue:.25 alpha:1];NSString*leaf=ok?[[NSString stringWithUTF8String:path2.c_str()] lastPathComponent]:@"default.xex não encontrado";location2.text=ok?[NSString stringWithFormat:@"PASTA: %@",leaf]:leaf;play2.enabled=ok;play2.alpha=ok?1:.4;}
-(void)showLauncherMessage:(NSString*)message{status2.text=message;status2.textColor=[UIColor colorWithRed:1 green:.48 blue:.32 alpha:1];play2.enabled=NO;play2.alpha=.5;}
-(void)dealloc{if(launcher_controller2==self)launcher_controller2=nil;}
-(void)chooseTap {
 log_line2("DOCUMENT_PICKER_OPEN");
 picker2=[[UIDocumentPickerViewController alloc]initForOpeningContentTypes:@[UTTypeFolder] asCopy:NO];
 picker2.delegate=self; picker2.allowsMultipleSelection=NO;
 [self presentViewController:picker2 animated:YES completion:nil];
}
-(void)documentPicker:(UIDocumentPickerViewController*)controller didPickDocumentsAtURLs:(NSArray<NSURL*>*)urls {
 NSURL* picked=urls.firstObject;
 if(!picked){log_line2("DOCUMENT_PICKER_EMPTY");return;}
 if(selected_game_scope2){[selected_game_url2 stopAccessingSecurityScopedResource];selected_game_scope2=false;}
 selected_game_scope2=[picked startAccessingSecurityScopedResource]; selected_game_url2=picked;
 std::string candidate=picked.path.UTF8String?picked.path.UTF8String:"";
 if(access((candidate+"/default.xex").c_str(),F_OK)!=0 && access((candidate+"/BCGame/default.xex").c_str(),F_OK)==0) candidate+="/BCGame";
 if(access((candidate+"/default.xex").c_str(),F_OK)!=0){log_line2("PICKER_FOLDER_MISSING_DEFAULT_XEX "+candidate);path2.clear();}
 else {path2=candidate;log_line2("PICKER_GAME_SELECTED "+candidate);}
 [self updateStatus];
}
-(void)documentPickerWasCancelled:(UIDocumentPickerViewController*)controller {log_line2("DOCUMENT_PICKER_CANCELLED");}
-(void)scanTap{log_line2("LAUNCHER_RESCAN");path2=scan2?scan2():std::string();log_line2(path2.empty()?"GAME_NOT_FOUND":"GAME_FOUND "+path2);[self updateStatus];}
-(void)playTap{if(path2.empty()||!play2.enabled)return;log_line2("LAUNCHER_START "+path2);play2.enabled=NO;play2.alpha=.55;status2.text=@"INICIANDO RECOMPILAÇÃO...";status2.textColor=UIColor.whiteColor;auto cb=start2;auto p=path2;if(cb)cb(std::move(p));}
@end
std::string AsuraIOSDocumentsPath(){init_log2();return docs_path2();}
void AsuraIOSLog(const std::string&s){init_log2();log_line2(s);}
void AsuraIOSShowLauncher(std::string p,std::function<std::string()>scan,std::function<void(std::string)>start) {
 init_log2();
 log_line2("NATIVE_LAUNCHER_REQUEST");
 // ReXApp can reach OnFinalizePaths while UIKit is still transitioning its
 // UIWindowScene from foreground-inactive to foreground-active. Creating a
 // frame-only UIWindow in that interval produces an unattached window on
 // scene-based iOS apps: the SDL surface stays black and the launcher never
 // appears. Wait for a real foreground UIWindowScene and always attach to it.
 auto path = std::make_shared<std::string>(std::move(p));
 auto scanner = std::make_shared<std::function<std::string()>>(std::move(scan));
 auto starter = std::make_shared<std::function<void(std::string)>>(std::move(start));
 auto attempts = std::make_shared<int>(0);
 auto present = std::make_shared<std::function<void()>>();
 *present = [path, scanner, starter, attempts, present]() {
  dispatch_async(dispatch_get_main_queue(), ^{
   UIWindowScene* scene=nil;
   for(UIScene* x in UIApplication.sharedApplication.connectedScenes) {
    if(![x isKindOfClass:UIWindowScene.class]) continue;
    UIWindowScene* candidate=(UIWindowScene*)x;
    if(candidate.activationState==UISceneActivationStateForegroundActive) { scene=candidate; break; }
    if(!scene && candidate.activationState==UISceneActivationStateForegroundInactive) scene=candidate;
   }
   if(!scene) {
    ++(*attempts);
    log_line2("LAUNCHER_SCENE_WAIT attempt="+std::to_string(*attempts));
    if(*attempts>=240) {
     log_line2("LAUNCHER_SCENE_WAIT_RETRY");
     *attempts=0;
    }
    // Keep retrying until UIKit has a foreground scene. Returning an empty
    // app from the factory would make the SDL entry point dereference nullptr.
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(250 * NSEC_PER_MSEC)), dispatch_get_main_queue(), ^{ if (*present) (*present)(); });
    return;
   }
   for(UIWindow* w in scene.windows) if(w.isKeyWindow){prior_window2=w;break;}
   overlay_window2=[[UIWindow alloc]initWithWindowScene:scene];
   overlay_window2.frame=scene.coordinateSpace.bounds;
   overlay_window2.windowLevel=UIWindowLevelNormal+1;
   overlay_window2.rootViewController=[[AsuraNativeLauncher2 alloc]initPath:*path scan:*scanner start:*starter];
   [overlay_window2 makeKeyAndVisible];
   log_line2("LAUNCHER_WINDOW_ATTACHED_TO_FOREGROUND_SCENE");
   log_line2("NATIVE_LAUNCHER_VISIBLE");
   *present = nullptr;
  });
 };
 (*present)();
}
std::string AsuraIOSWaitForGameSelection(std::string detected, std::function<std::string()> rescan) {
 struct GateState { std::mutex mutex; std::condition_variable changed; bool completed=false; std::string selected; };
 auto gate=std::make_shared<GateState>();
 AsuraIOSLog("APP_LAUNCH_GATE_WAITING_FOR_PLAY");
 AsuraIOSShowLauncher(std::move(detected), std::move(rescan), [gate](std::string selected) {
  { std::lock_guard<std::mutex> lock(gate->mutex); gate->selected=std::move(selected); gate->completed=true; }
  gate->changed.notify_all();
 });
 if ([NSThread isMainThread]) {
  // Keep UIKit/UIScene callbacks and launcher button actions running while the
  // factory waits. A blocking semaphore on the main thread would deadlock UI.
  for (;;) {
   { std::lock_guard<std::mutex> lock(gate->mutex); if (gate->completed) break; }
   CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.05, true);
  }
 } else {
  std::unique_lock<std::mutex> lock(gate->mutex);
  gate->changed.wait(lock, [&] { return gate->completed; });
 }
 std::lock_guard<std::mutex> lock(gate->mutex);
 AsuraIOSLog("APP_LAUNCH_GATE_PLAY_ACCEPTED " + gate->selected);
 return gate->selected;
}
__attribute__((constructor))static void AsuraIOSBootLog2(){init_log2();}

void AsuraIOSDismissLauncher(){dispatch_async(dispatch_get_main_queue(),^{if(overlay_window2){overlay_window2.hidden=YES;overlay_window2.rootViewController=nil;overlay_window2=nil;}if(prior_window2){[prior_window2 makeKeyAndVisible];prior_window2=nil;}log_line2("NATIVE_LAUNCHER_DISMISSED_AFTER_GUEST_FRAME");});}
extern "C" __attribute__((used, visibility("default"))) bool AsuraIOSHasPresentedFrame(){return first_present2.load(std::memory_order_acquire);}
extern "C" __attribute__((used, visibility("default"))) void AsuraIOSNotifyFirstPresent(){
 if(first_present2.exchange(true,std::memory_order_acq_rel))return;
 AsuraIOSLog("VULKAN_FIRST_GUEST_FRAME_PRESENTED");
 AsuraIOSDismissLauncher();
}
void AsuraIOSSetLauncherStatus(const std::string&message){dispatch_async(dispatch_get_main_queue(),^{if(launcher_controller2){NSString*text=[NSString stringWithUTF8String:message.c_str()];[launcher_controller2 showLauncherMessage:(text ?: @"Falha ao iniciar o runtime")];}log_line2("LAUNCHER_STATUS "+message);});}
