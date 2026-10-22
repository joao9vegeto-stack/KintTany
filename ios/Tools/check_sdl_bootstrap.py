#!/usr/bin/env python3
"""Build 28 source-level regression: SwiftUI @main requires manual SDL3 readiness."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
c=(root/"Native/poptst_engine.c").read_text()
swift=(root/"App/PoPTSTApp.swift").read_text()
proj=(root/"project.yml").read_text()
assert "#define SDL_MAIN_HANDLED 1" in c
assert "#include <SDL3/SDL_main.h>" in c
assert c.index("SDL_SetMainReady();") < c.index("SDL_Init(SDL_INIT_VIDEO")
assert "pthread_main_np()" in c
assert "Build 28: SDL3 pronto" in c
assert "PoPTST-Diagnostico-Build-\\(BuildInfo.number).txt" in swift
assert "BIBLIOTECA DO JOGO  ·  BUILD" in swift
assert "BUILD \\(BuildInfo.number)" in swift
assert "CFBundleVersion: '28'" in proj
assert "CURRENT_PROJECT_VERSION: '28'" in proj
assert "MARKETING_VERSION: '2.8'" in proj
assert "CFBundleDisplayName: 'PoPTST B28'" in proj
assert "ARM64REG lr=0x" in c
hud=(root/"Native/poptst_touch_overlay.m").read_text()
assert 's_cam_levels[] = {0.5, 0.75, 1.0, 1.5, 2.0}' in hud
assert 'PoPTSTCameraModeV3' in hud and 'INPUT B27: title-native camera sensitivity' in hud
assert '_origin=[_tracked locationInView:self]' in hud
assert 'pow((length-0.045)/0.955,0.96)' in hud
assert 'CAM %.2g' in hud and 'poptst_ios_real_fps()' in hud
assert "poptst_ios_touch_overlay_tick();" in c
assert "void poptst_ios_fps_presented(void)" in c
assert "float poptst_ios_real_fps(void)" in c
assert "dispatch_sync_f(dispatch_get_main_queue(),&op,poptst_gpu_claim_main)" in c
assert "dispatch_sync_f(dispatch_get_main_queue(),&op,poptst_gpu_release_main)" in c
assert "SDL_ClaimWindowForGPUDevice(op->device,op->target)" in c
assert "SDL_ReleaseWindowFromGPUDevice(op->device,op->target)" in c
assert "GPU B23: SDL window claimed" in c
assert proj.count("ASSETCATALOG_COMPILER_APPICON_NAME: AppIcon")==1
print("PASS: SwiftUI entry, SDL3 main ready before SDL_Init, Build 28 UI/log/plist/icon")

assert 'poptst_ios_set_look_percent((int)(100.0*s_cam_gain+0.5))' in hud
assert 'new_trigger(root,@"LT"' in hud and 'new_trigger(root,@"RT"' in hud
assert 'xbox_SetRenderScalePercent(s_resolution_percents[s_resolution_mode])' in hud
assert 'PoPTSTSaveButton' in hud and 'backupProgress' in hud
assert 'native-save-slot' in hud
assert 'Encerrar completamente?' in hud
assert 'void poptst_engine_exit_to_launcher' in c and '_exit(0);' in c
assert 'SAVE B28: restored ONLY guest UDATA/TDATA titles' in swift
assert 'restoreNativeSaveAndPlay' in swift

assert 'NSArray<NSString *> *saveNames=@[@"UDATA",@"TDATA",@"UserData",@"TitleData"]' in hud
assert 'NSDirectoryEnumerator *enumerator=[fm enumeratorAtPath:path]' in hud
assert 'native-save-restore-pending' in swift and 'native-save-before-restore' in swift
assert 'native-save-slot' in swift and '.devices' in swift
