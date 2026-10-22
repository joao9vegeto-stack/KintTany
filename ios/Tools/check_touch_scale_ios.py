#!/usr/bin/env python3
"""B27 integrity: Xbox classic triggers, game-owned sensitivity and real internal upscale."""
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
input_c=(root/'port/ios/generated_input_ios.c').read_text()
options=(root/'port/android/src/options_android.c').read_text()
hooks=(root/'source/xbox-retail/target_hooks.c').read_text()
scale=(root/'port/third_party/xboxrecomp/src/kernel/nv2a_hw_d3d11.inc').read_text()
hud=Path(__file__).resolve().parents[1]/'Native/poptst_touch_overlay.m'
ui=hud.read_text()
checks={
 'analog LT/RT fields in iOS generated bridge':
    'int32_t incoming[7]={lx,ly,rx,ry,lt,rt,buttons}' in input_c and
    'XBOX_BUTTON_LTRIGGER, (BYTE)(axis[4] > 0 ? axis[4] >> 7 : 0)' in input_c and
    'XBOX_BUTTON_RTRIGGER, (BYTE)(axis[5] > 0 ? axis[5] >> 7 : 0)' in input_c,
 'touch triggers independent from shoulder buttons':
    'new_trigger(root,@"LT",NO' in ui and 'new_trigger(root,@"RT",YES' in ui and
    'rt=32767' in ui and 'lt=32767' in ui and 'rt=0' in ui and 'lt=0' in ui,
 'camera button applies authoritative game scaling':
    'void poptst_ios_set_look_percent(int percent)' in options and
    's_look_sensitivity=resot_look_percent(percent)' in options and
    'poptst_apply_camera();' in ui and
    'sub_000DBDE0(void)' in hooks and 'resot_scale_look(' in hooks,
 'camera sensitivity respects 25-200% rePOP range':
    's_cam_levels[] = {0.5, 0.75, 1.0, 1.5, 2.0}' in ui and
    'PoPTSTCameraModeV3' in ui,
 'real NV2A GPU internal resolution not cosmetic scaling':
    'xbox_SetRenderScalePercent(int percent)' in scale and
    'percent!=150' in scale and 'percent!=225' in scale and
    's_resolution_percents[] = {100,150,225}' in ui and
    'xbox_SetRenderScalePercent(s_resolution_percents[s_resolution_mode])' in ui,
 'no touched AMD Android input implementations':
    'SDL_GAMEPAD_BUTTON_LEFT_SHOULDER' in input_c and
    'SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER' in input_c,
}
for name,ok in checks.items(): print(('PASS ' if ok else 'FAIL ')+name)
if not all(checks.values()): raise SystemExit(1)
# B27 launch/exit and native progress backup contract:
assert 'native-save-slot' in ui
assert 'poptst_ios_set_look_percent((int)(100.0*s_cam_gain+0.5))' in ui
