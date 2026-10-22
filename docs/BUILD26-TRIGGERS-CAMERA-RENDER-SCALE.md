# PoPTST B26 – correct Xbox classic triggers, genuine title camera sensitivity, internal 720p / 1080p

## Grounded findings (2026-10-22)
- User screenshots show the real game rendering at 59.9 FPS in the title/settings screen on an iPhone 17 Pro. B25 11-second video cycles CAM 1.0 -> 1.6 -> 2.2 -> 2.8 while the actual rotation speed is not perceptibly improved, confirming the GUI value changes but not proving title sensitivity changed.
- Original Xbox LT/RT are ANALOG buttons in XBOX_GAMEPAD bAnalogButtons[XBOX_BUTTON_LTRIGGER / RTRIGGER]. Pin rePOP source port/android/src/input_android.c maps SDL axes[4]/axes[5] shifted right 7 to these values. The iOS bridge has these slots; the UIKit HUD did not expose LT/RT buttons. Default native rePOP bindings SPECIAL uses code 8=R trigger and REWIND uses code 7=L trigger. Modern LB/RB are distinct digital buttons and are not a substitute.
- The prior CAM multiplier altered only the *touch pad output* (which saturates at int16 max 32767). But original rePOP port/android/src/options_android.c has s_look_sensitivity default 200% and the retail lifted title hook source/xbox-retail/target_hooks.c::sub_000DBDE0 explicitly calls resot_scale_look. Thus visible CAM text did not control the authoritative post-deadzone title look scaling.
- rePOP already supports true internal GPU resolution via xbox_SetRenderScalePercent with exact values 100=480p, 150=720p, 225=1080p; main render targets are recreated when scale changes. This is supersampling / internal high-resolution rendering through the existing NV2A->Vulkan->Metal path, **not DLSS or machine-learning enhancement**.

## Integrated B26 correction
- Add independently press-and-hold, multitouch iOS LT and RT above the game, updating the exact int32_t touch fields [4] and [5] and resetting on touch up/cancel.
- Leave existing move pad and other Xbox controls intact; gain on camera pad is no longer an unproven proxy for camera sensitivity. New CAM 0.5x/1.0x/1.5x/2.0x selector calls poptst_ios_set_look_percent against the actual Xbox game hook s_look_sensitivity (25-200%). Persist under NEW key PoPTSTCameraModeV2 to avoid carrying over incomparable older B25 modes.
- Add RES 480p/720p/1080p toggle, calling the rePOP native renderer's real GPU render-scale setter. Persist under PoPTSTResolutionMode. Default 480p for known B25 performance/stability; player can request 720/1080 to compare quality vs real FPS. Avoid unbounded >1080p pressure on iPhone.
- New post-patch CI regression checks original title hook, iOS generated touch axis to Xbox pad translation, actual setter, and native NV2A scale. Existing AOT structural audit remains in Actions, branch PoPTST only, orphan root commit, one workflow per root commit.

## Acceptance tests
1. Hold LT and verify Rewind; hold RT and verify Special Action in the playable scene. With no Sands of Time charges, Rewind may be unavailable even though LT is correctly mapped.
2. With the camera held at identical right stick displacement, CAM speeds MUST differ in original lifted camera hook output. Note that menu/cutscene may lock the camera.
3. Switch RES 480->720->1080; app trace must log GPU internal target resolution; screenshot edge quality and FPS should change. B26 explicitly does NOT guarantee 60 FPS at 1080p.
4. A successful IPA does not prove all graphical defects or long gameplay stability are resolved. Existing corruption and crash state require direct iPhone validation.
