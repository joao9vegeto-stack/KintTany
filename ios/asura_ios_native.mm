#import <UIKit/UIKit.h>
#import <Foundation/Foundation.h>
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>
#import <CoreFoundation/CoreFoundation.h>
#include <unistd.h>
#include "asura_ios_native.h"
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
namespace {
std::mutex log_mutex2; std::string log_path2; char crash_path2[PATH_MAX]{}; UIWindow* overlay_window2=nil; UIWindow* prior_window2=nil;
NSURL* selected_game_url2=nil;
bool selected_game_scope2=false;
std::string docs_path2(){NSString*p=[NSHomeDirectory() stringByAppendingPathComponent:@"Documents"];[[NSFileManager defaultManager]createDirectoryAtPath:p withIntermediateDirectories:YES attributes:nil error:nil];return p.UTF8String?p.UTF8String:"";}
void write_crash_record2(const char* message){if(!crash_path2[0])return;int fd=open(crash_path2,O_WRONLY|O_CREAT|O_APPEND,0600);if(fd>=0){write(fd,message,std::strlen(message));close(fd);}}
void fatal_signal2(int sig){const char* message="FATAL SIGNAL\\n";switch(sig){case SIGABRT:message="FATAL SIGNAL SIGABRT\\n";break;case SIGSEGV:message="FATAL SIGNAL SIGSEGV\\n";break;case SIGBUS:message="FATAL SIGNAL SIGBUS\\n";break;case SIGILL:message="FATAL SIGNAL SIGILL\\n";break;case SIGFPE:message="FATAL SIGNAL SIGFPE\\n";break;}int fd=open(crash_path2,O_WRONLY|O_CREAT|O_APPEND,0600);if(fd>=0){write(fd,message,std::strlen(message));close(fd);}_exit(128+sig);}
void log_line2(const std::string&s){std::lock_guard<std::mutex>l(log_mutex2);const std::string docs=docs_path2();if(log_path2.empty())log_path2=docs+"/log.txt";if(!crash_path2[0])std::snprintf(crash_path2,sizeof(crash_path2),"%s/crash.txt",docs.c_str());std::time_t t=std::time(nullptr);std::tm tm{};localtime_r(&t,&tm);char b[32]{};std::strftime(b,sizeof(b),"%Y-%m-%d %H:%M:%S",&tm);const std::string line=std::string(b)+" [Asura-iOS] "+s+"\\n";for(const auto&path:{log_path2,docs+"/asura-ios.log"}){std::ofstream f(path,std::ios::app);if(f){f<<line;f.flush();}}}
void init_log2(){static dispatch_once_t once;dispatch_once(&once,^{const std::string docs=docs_path2();std::snprintf(crash_path2,sizeof(crash_path2),"%s/crash.txt",docs.c_str());log_line2("PROCESS_START");std::signal(SIGABRT,fatal_signal2);std::signal(SIGSEGV,fatal_signal2);std::signal(SIGBUS,fatal_signal2);std::signal(SIGILL,fatal_signal2);std::signal(SIGFPE,fatal_signal2);std::atexit([]{log_line2("PROCESS_EXIT");});std::set_terminate([]{log_line2("FATAL std::terminate");write_crash_record2("FATAL std::terminate\\n");std::abort();});NSNotificationCenter*n=NSNotificationCenter.defaultCenter;NSArray*names=@[UIApplicationDidBecomeActiveNotification,UIApplicationWillResignActiveNotification,UIApplicationDidEnterBackgroundNotification,UIApplicationWillEnterForegroundNotification,UIApplicationWillTerminateNotification];for(NSString*name in names)[n addObserverForName:name object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification*note){log_line2(std::string("LIFECYCLE ")+note.name.UTF8String);}];});}
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
 self.view.backgroundColor=[UIColor colorWithRed:.035 green:.04 blue:.06 alpha:1];
 UIScrollView*scroll=[UIScrollView new]; scroll.translatesAutoresizingMaskIntoConstraints=NO; scroll.alwaysBounceVertical=YES; scroll.showsVerticalScrollIndicator=YES; [self.view addSubview:scroll];
 [NSLayoutConstraint activateConstraints:@[[scroll.leadingAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.leadingAnchor constant:18],[scroll.trailingAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.trailingAnchor constant:-18],[scroll.topAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.topAnchor constant:8],[scroll.bottomAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.bottomAnchor constant:-8]]];
 UIStackView*s=[UIStackView new]; s.axis=UILayoutConstraintAxisVertical; s.spacing=9; s.alignment=UIStackViewAlignmentFill; s.translatesAutoresizingMaskIntoConstraints=NO; [scroll addSubview:s];
 NSLayoutConstraint*width=[s.widthAnchor constraintEqualToAnchor:scroll.frameLayoutGuide.widthAnchor multiplier:0.96]; width.priority=UILayoutPriorityDefaultHigh;
 [NSLayoutConstraint activateConstraints:@[[s.leadingAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.leadingAnchor],[s.trailingAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.trailingAnchor],[s.topAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.topAnchor constant:8],[s.bottomAnchor constraintEqualToAnchor:scroll.contentLayoutGuide.bottomAnchor constant:-8],[s.centerXAnchor constraintEqualToAnchor:scroll.frameLayoutGuide.centerXAnchor],[s.widthAnchor constraintLessThanOrEqualToConstant:520],width]];
 UILabel*top=[UILabel new]; top.text=@"RECOMPILAÇÃO NATIVA • iOS"; top.textColor=[UIColor colorWithRed:.95 green:.3 blue:.24 alpha:1]; top.font=[UIFont boldSystemFontOfSize:10]; top.textAlignment=NSTextAlignmentCenter; [s addArrangedSubview:top];
 UILabel*t=[UILabel new]; t.text=@"ASURA'S WRATH"; t.textColor=UIColor.whiteColor; t.font=[UIFont systemFontOfSize:27 weight:UIFontWeightBlack]; t.textAlignment=NSTextAlignmentCenter; t.adjustsFontSizeToFitWidth=YES; t.minimumScaleFactor=.7; [s addArrangedSubview:t];
 UILabel*sub=[UILabel new]; sub.text=[NSString stringWithFormat:@"KOSMICKRISP • BUILD %s",ASURA_IOS_BUILD_NUMBER]; sub.textColor=UIColor.lightGrayColor; sub.font=[UIFont systemFontOfSize:11 weight:UIFontWeightMedium]; sub.textAlignment=NSTextAlignmentCenter; [s addArrangedSubview:sub];
 status2=[UILabel new]; status2.textAlignment=NSTextAlignmentCenter; status2.font=[UIFont boldSystemFontOfSize:14]; status2.numberOfLines=2; [s addArrangedSubview:status2];
 location2=[UILabel new]; location2.textAlignment=NSTextAlignmentCenter; location2.textColor=UIColor.lightGrayColor; location2.font=[UIFont monospacedSystemFontOfSize:10 weight:UIFontWeightRegular]; location2.numberOfLines=1; location2.lineBreakMode=NSLineBreakByTruncatingMiddle; [s addArrangedSubview:location2];
 UILabel*info=[UILabel new]; info.text=@"Selecione a pasta extraída do jogo. Ela deve conter default.xex e os arquivos de dados."; info.textColor=[UIColor colorWithWhite:.8 alpha:1]; info.textAlignment=NSTextAlignmentCenter; info.numberOfLines=2; info.font=[UIFont systemFontOfSize:11]; [s addArrangedSubview:info];
 UIButton*choose=[self button:@"ESCOLHER PASTA DO JOGO" action:@selector(chooseTap)]; choose.backgroundColor=[UIColor colorWithRed:.22 green:.24 blue:.30 alpha:1]; [s addArrangedSubview:choose];
 UIButton*scan=[self button:@"DETECTAR AUTOMATICAMENTE" action:@selector(scanTap)]; scan.backgroundColor=UIColor.darkGrayColor; [s addArrangedSubview:scan];
 play2=[self button:@"INICIAR JOGO" action:@selector(playTap)]; [s addArrangedSubview:play2]; [self updateStatus];
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

void AsuraIOSDismissLauncher(){dispatch_async(dispatch_get_main_queue(),^{if(overlay_window2){overlay_window2.hidden=YES;overlay_window2.rootViewController=nil;overlay_window2=nil;}if(prior_window2){[prior_window2 makeKeyAndVisible];prior_window2=nil;}log_line2("NATIVE_LAUNCHER_DISMISSED_RUNTIME_READY");});}
void AsuraIOSSetLauncherStatus(const std::string&message){dispatch_async(dispatch_get_main_queue(),^{if(launcher_controller2){NSString*text=[NSString stringWithUTF8String:message.c_str()];[launcher_controller2 showLauncherMessage:text?:@"Falha ao iniciar o runtime";}log_line2("LAUNCHER_STATUS "+message);});}
