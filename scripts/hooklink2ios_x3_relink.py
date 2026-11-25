#!/usr/bin/env python3
"""Rebuild the X3 host from the verified successful 4.0 IPA, never retranslate guest shaders."""
import argparse
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import hooklink2ios_native_relink as native
import hooklink2ios_perf_repack as repack
import hooklink2ios_v4_build as v4
import hooklink2ios_x3_recovery as recovery
import hooklink2ios_game_icon as game_icon

RUN="45214405727"
SOURCE_HEAD="c2aa86b2172ad337e811ff2c43ca695c59d55ff4"
CHAIN="b6112b954691"
PREFIX="Payload/DmIOS.app/"
RECOVERY_PRESETS={"x3-recovery":{"DM_FRAME_MODE":"1","DM_FPS_TARGET":"30","DM_FRAMEGEN":"0","DM_PSO_PREBUILD":"0","DM_DYNAMIC_RESOLUTION":"1","DM_RENDER_SCALE":"0.85","DM_PRESENT_UPSCALE":"metalfx"}}

def require(value,message):
    if not value:
        raise RuntimeError(message)

# Strict source anchors from the pinned X3 engine. Keep previous recovery and shader ABI.
HL_INPUT_EXIT_PATCHES = [
  [
    "dm/ios/Sources/DmGameMenu.h",
    "bool dm_setting_live(const char *env, const char *value);",
    "void dm_hl_pad_swap_set(const char *value);\nvoid dm_hl_confirm_exit(void);\nbool dm_setting_live(const char *env, const char *value);"
  ],
  [
    "dm/ios/Sources/DmGamepad.m",
    "static int g_merge, g_press_to_join;",
    "static int g_merge, g_press_to_join;\nstatic _Atomic unsigned hl_pad_swap;\n#define HL_SWAP_PAIR(m,a,b) (((m) & ~((a)|(b))) | (((m)&(a)) ? (b) : 0) | (((m)&(b)) ? (a) : 0))\n_Static_assert(HL_SWAP_PAIR(1ull,1ull,2ull)==2ull && HL_SWAP_PAIR(2ull,1ull,2ull)==1ull &&\n               HL_SWAP_PAIR(3ull,1ull,2ull)==3ull && HL_SWAP_PAIR(4ull,1ull,2ull)==4ull &&\n               HL_SWAP_PAIR(4ull,4ull,8ull)==8ull && HL_SWAP_PAIR(8ull,4ull,8ull)==4ull &&\n               HL_SWAP_PAIR(12ull,4ull,8ull)==12ull && HL_SWAP_PAIR(0ull,4ull,8ull)==0ull, \"face swap must preserve simultaneous inputs\");\nstatic uint64_t hl_remap_physical(uint64_t m) {\n    unsigned mode = atomic_load_explicit(&hl_pad_swap, memory_order_relaxed);\n    if (mode & 1) m = HL_SWAP_PAIR(m, 1ull << B_A, 1ull << B_B);\n    if (mode & 2) m = HL_SWAP_PAIR(m, 1ull << B_X, 1ull << B_Y);\n    return m;\n}"
  ],
  [
    "dm/ios/Sources/DmGamepad.m",
    "    dm_pad_set_player(p, m, axis(lx), axis(ly), axis(rx), axis(ry));",
    "    dm_pad_set_player(p, hl_remap_physical(m), axis(lx), axis(ly), axis(rx), axis(ry));"
  ],
  [
    "dm/ios/Sources/DmGamepad.m",
    "// Returns YES on first registration, so a controller waiting to join is logged once.",
    "void dm_hl_pad_swap_set(const char *value) {\n    unsigned mode = 0;\n    if (value && value[0] >= '0' && value[0] <= '3' && !value[1]) mode = (unsigned)(value[0] - '0');\n    unsigned previous = atomic_exchange_explicit(&hl_pad_swap, mode, memory_order_relaxed);\n    LOG(\"HookLink2iOS physical face buttons: AB=%s XY=%s\", mode & 1 ? \"swapped\" : \"original\", mode & 2 ? \"swapped\" : \"original\");\n    if (previous != mode) dispatch_async(dispatch_get_main_queue(), ^{\n        if (g_merge) return;   // merged mode retains last-moved semantics\n        for (int p = 0; p < DM_PLAYERS; p++) if (g_held[p]) read_pad(g_held[p]);\n    });\n}\n// Returns YES on first registration, so a controller waiting to join is logged once."
  ],
  [
    "dm/ios/Sources/DmGamepad.m",
    "static void pads_start(void) {\n    const char *e = getenv(\"DM_PAD_MERGE\");",
    "static void pads_start(void) {\n    dm_hl_pad_swap_set(getenv(\"DM_HL_PAD_SWAP\"));\n    const char *e = getenv(\"DM_PAD_MERGE\");"
  ],
  [
    "dm/ios/Sources/front_ios.m",
    "    if (!env || !g_root.game) return false;\n    if (!strcmp(env, \"DM_PICTURE_FIT\")) {",
    "    if (!env || !g_root.game) return false;\n    if (!strcmp(env, \"DM_HL_PAD_SWAP\")) {\n        if (value) dm_hl_pad_swap_set(value);\n        return true;\n    }\n    if (!strcmp(env, \"DM_PICTURE_FIT\")) {"
  ],
  [
    "dm/ios/Sources/front_ios.m",
    "static void launcher_done(void) { [g_root startGame]; }",
    "// Reuse the existing controlled process exit; never restart the guest in-place.\nvoid dm_hl_confirm_exit(void) {\n    dispatch_async(dispatch_get_main_queue(), ^{\n        static BOOL exiting = NO;\n        if (exiting || !g_root.game || !g_root.view.window) return;\n        UIViewController *parent = g_root;\n        while (parent.presentedViewController) parent = parent.presentedViewController;\n        if ([parent isKindOfClass:UIAlertController.class]) return;\n        UIAlertController *alert = [UIAlertController alertControllerWithTitle:@\"Sair do jogo?\"\n            message:@\"Salve o progresso no jogo antes de sair. O aplicativo será fechado; ao abrir novamente, o launcher será exibido.\"\n            preferredStyle:UIAlertControllerStyleAlert];\n        [alert addAction:[UIAlertAction actionWithTitle:@\"Cancelar\" style:UIAlertActionStyleCancel handler:nil]];\n        [alert addAction:[UIAlertAction actionWithTitle:@\"Sair\" style:UIAlertActionStyleDestructive handler:^(UIAlertAction *action) {\n            (void)action;\n            if (exiting) return;\n            exiting = YES;\n            LOG(\"HookLink2iOS: user requested graceful exit\");\n            dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{\n                if (!save_sync_flush(3000)) LOG(\"HookLink2iOS: cloud save sync pending; committed local save retained\");\n                dm_host_shutdown(\"HookLink2iOS Exit menu\");\n            });\n        }]];\n        [parent presentViewController:alert animated:YES completion:nil];\n    });\n}\nstatic void launcher_done(void) { [g_root startGame]; }"
  ],
  [
    "dm/ios/Sources/Launcher.swift",
    "    let model = LauncherModel(deviceAdjusted(file.settings))",
    "    let hlMappingData = Data(#\"{\"settings\":[{\"env\":\"DM_HL_PAD_SWAP\",\"kind\":\"choice\",\"label\":\"Gamepad: mapear A/B e X/Y\",\"note\":\"Altera somente os botões físicos. Normal mantém o layout original; inverta A/B, X/Y ou ambos para adequar as letras do controle. Os controles de toque não mudam.\",\"default\":\"0\",\"section\":\"Controls\",\"options\":[[\"0\",\"Original\"],[\"1\",\"Inverter A/B\"],[\"2\",\"Inverter X/Y\"],[\"3\",\"Inverter A/B e X/Y\"]]}]}\"#.utf8)\n    var hlSettings = file.settings\n    if !hlSettings.contains(where: { $0.env == \"DM_HL_PAD_SWAP\" }),\n       let extra = try? JSONDecoder().decode(SettingsFile.self, from: hlMappingData) {\n        hlSettings.append(contentsOf: extra.settings)\n    }\n    let model = LauncherModel(deviceAdjusted(hlSettings))"
  ],
  [
    "dm/ios/Sources/Launcher.swift",
    "fputs(\"launcher: \\(file.settings.count) settings shown\\n\", stderr)",
    "fputs(\"launcher: \\(hlSettings.count) settings shown\\n\", stderr)"
  ],
  [
    "dm/ios/Sources/GameMenu.swift",
    "    return items\n}",
    "    items.append(UIMenu(options: .displayInline, children: [UIAction(title: \"Sair do jogo\", image: UIImage(systemName: \"rectangle.portrait.and.arrow.right\"), attributes: .destructive) { _ in dm_hl_confirm_exit() }]))\n    return items\n}"
  ]
]

def apply_input_exit(engine):
    edited = {}
    counts = {}
    for name, anchor, replacement in HL_INPUT_EXIT_PATCHES:
        path = engine / name
        body = edited.get(path)
        if body is None:
            body = path.read_text(encoding="utf-8")
        if body.count(anchor) != 1:
            raise RuntimeError("HookLink2iOS input/exit anchor absent or duplicated: " + name + ": " + anchor[:90])
        edited[path] = body.replace(anchor, replacement, 1)
        counts[name] = counts.get(name, 0) + 1
    for path, body in edited.items():
        path.write_text(body, encoding="utf-8")
    return counts


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--artifact",type=Path,required=True)
    p.add_argument("--engine",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    require(sys.platform=="darwin","native iOS host relink requires macOS")
    require(os.environ.get("GITHUB_REF")=="refs/heads/HookLink2iOS","wrong branch")
    v4.verify_v4_engine(a.engine)
    report_files=list(a.artifact.rglob("build-report.json"))
    ipas=list(a.artifact.rglob("*.ipa"))
    require(len(report_files)==1 and len(ipas)==1,"source artifact does not have exactly one IPA and report")
    report=json.loads(report_files[0].read_text())
    source=ipas[0]
    require(str(report.get("run_id"))==RUN and report.get("commit")==SOURCE_HEAD,"wrong source build")
    require(report.get("engine_commit")==v4.UPSTREAM_PIN and report.get("hooklink_release")=="4.0","wrong X3 engine/release")
    require(report.get("shader_chain")==CHAIN and report.get("original_1_8_shader_image_reused") is False,"wrong shader chain")
    require(report.get("gpu_arch")=="none" and report.get("romfs_mode")=="separate","source is not thin")
    require(native.sha256(source)==report["ipa"]["sha256"] and source.stat().st_size==report["ipa"]["size"],"source IPA hash/size mismatch")
    a.output.mkdir(parents=True,exist_ok=True)
    work=a.output.parent/"host-work"
    work.mkdir(parents=True,exist_ok=True)
    original=work/"original-DmIOS"
    origdm=work/"original_dm"; origdm.mkdir(exist_ok=True)
    patches=work/"original_rewritten"; patches.mkdir(exist_ok=True)
    repack.PRESETS=RECOVERY_PRESETS
    with zipfile.ZipFile(source) as z:
        # Validate the actual source IPA launcher before rebuilding the host.
        # Do not change the source IPA or lock settings through env.txt.
        with tempfile.TemporaryDirectory(prefix="x3-launcher-preflight-") as tmp:
            app=Path(tmp)
            dm=app/"dm"; dm.mkdir()
            for name in ("launcher.json", "env.txt"):
                member=PREFIX+"dm/"+name
                if name=="launcher.json" or member in z.namelist():
                    (dm/name).write_bytes(z.read(member))
            settings_check=repack.patch_launcher_and_env(app,RECOVERY_PRESETS["x3-recovery"])
            print("HOOKLINK2IOS_LAUNCHER_PREFLIGHT_OK",json.dumps(settings_check["launcher_defaults"],sort_keys=True),flush=True)
        marker,images=repack.audit(z)
        require(marker==report["ipa"]["contents"]["romfs_marker"],"source RomFS marker differs from report")
        require(all("/msl/b-"+CHAIN+".img" in name for name in images),"source contains another shader image")
        plist=plistlib.loads(z.read(PREFIX+"Info.plist"))
        native.extract_member(z,PREFIX+"DmIOS",original,1_500_000_000)
        for info in z.infolist():
            if info.filename.startswith(PREFIX+"dm/") and not info.is_dir():
                rel=info.filename[len(PREFIX+"dm/"):]
                require(rel and ".." not in Path(rel).parts and "\\" not in rel,"bad source resource path")
                native.extract_member(z,info.filename,origdm/rel,256*1024*1024)
        guest=native.extract_guest_sections(original,source,z,patches)
    icon=work/"official-game-icon.jpg"
    icon_provenance=game_icon.prepare(icon)
    print("HOOKLINK2IOS_OFFICIAL_ICON_OK",json.dumps(icon_provenance),flush=True)
    changes=recovery.apply(a.engine)
    changes["input_exit"] = apply_input_exit(a.engine)
    print("X3 source changes:",changes,flush=True)
    executable,buildlog,checked=native.generate_and_build(a.engine,work,patches,plist,original)
    output=a.output/"OcarinaOfTime-HookLink2iOS-X3-Recovery.ipa"
    internal=a.output/"repack-report.json"
    # Do not lock the launcher: all modes remain selectable. Stop full pair scanning
    # by default, retain the original prewarm manifest and all existing graphics controls.
    # PRESETS was assigned and validated against the actual IPA above.
    sys.argv=["hooklink2ios_perf_repack.py","--source",str(source),"--replacement-executable",str(executable),"--game-icon",str(icon),"--preset","x3-recovery","--output",str(output),"--report",str(internal)]
    repack.main()
    audit=json.loads(internal.read_text())
    audit["native_host_relinked"]["source"]="pinned original X3 host with source-level recovery patch"
    internal.write_text(json.dumps(audit,indent=2)+"\n")
    with zipfile.ZipFile(output) as z:
        newmarker,newimages=repack.audit(z)
        require(newmarker==marker and newimages==images,"RomFS or Metal image changed")
        contents=report["ipa"]["contents"].copy()
        contents["romfs_marker"]=newmarker
    report.update(commit=os.environ["GITHUB_SHA"],run_id=os.environ["GITHUB_RUN_ID"],
                  native_recovery={"source_run":RUN,"source_commit":SOURCE_HEAD,"source_ipa_sha256":native.sha256(source),
                  "changes":changes,"guest_section_hashes_verified":checked,"shader_images_preserved":True,
                  "original_game_shaders_recompiled":False,"game_code_rewritten":False,
                  "native_executable_sha256":audit["native_host_relinked"]["signed_executable_sha256"]},
                  game_icon={**icon_provenance,"packed_files":audit["game_icon"]},
                  ipa={"name":output.name,"size":output.stat().st_size,"sha256":native.sha256(output),"contents":contents})
    (a.output/"build-report.json").write_text(json.dumps(report,indent=2)+"\n")
    overlays=list(a.artifact.rglob("Bootup.Nin_Ounce_NVN2.pack.zs"))
    require(len(overlays)==1 and native.sha256(overlays[0])==report["resolution_overlay"]["sha256"],"verified overlay missing")
    dst=a.output/"res_overlay/Pack";dst.mkdir(parents=True,exist_ok=True)
    shutil.copy2(overlays[0],dst/overlays[0].name)
    print("HOOKLINK2IOS_X3_RECOVERY_HOST_ONLY_OK",output.stat().st_size,report["ipa"]["sha256"],flush=True)

if __name__=="__main__":
    main()
