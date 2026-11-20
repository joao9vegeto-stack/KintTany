#!/usr/bin/env python3
"""Reconcile new nxnative iOS HUD bridge and Switch language names.

Runs only AFTER the complete fork rebase and a verified from-scratch engine
sync. Every source change is exported as an ordinary NX2Apple patch, not a
mutation hidden in the ignored engine/ checkout.
"""
from pathlib import Path
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
ENGINE=ROOT/"engine"
LOCALES={
  "en":("Polish","Thai"),
  "pt-br":("Polonês","Tailandês"),
  "zh":("波兰语","泰语"),
  "es":("Polaco","Tailandés"),
  "fr":("Polonais","Thaï"),
  "it":("Polacco","Thailandese"),
  "de":("Polnisch","Thailändisch"),
  "ja":("ポーランド語","タイ語"),
  "ko":("폴란드어","태국어"),
  "sv":("Polska","Thailändska"),
}

def cmd(*args,cwd=ROOT):
    p=subprocess.run(args,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    if p.returncode:
        raise RuntimeError(" ".join(args)+": "+p.stderr[-3000:])
    if p.stdout.strip():print(p.stdout[-3000:],flush=True)

def main():
    for locale,(polish,thai) in LOCALES.items():
        path=ROOT/"frontend"/"l10n"/(locale+".json")
        raw=path.read_text(encoding="utf-8")
        for lang,entry,anchor in [
            ("pl",polish,'"launch.opt.DM_LANG.pt"'),
            ("th",thai,'"launch.opt.DM_LANG.zh-Hans"')]:
            key='"launch.opt.DM_LANG.'+lang+'"'
            if key in raw:
                continue
            target="  "+anchor+":"
            if raw.count(target)!=1:
                raise RuntimeError("Language list changed; cannot insert "+lang+" into "+str(path))
            raw=raw.replace(target,
                            "  "+key+": "+json.dumps(entry,ensure_ascii=False)+",\n"+target)
        data=json.loads(raw)
        if data.get("launch.opt.DM_LANG.pl")!=polish or data.get("launch.opt.DM_LANG.th")!=thai:
            raise RuntimeError("Localization could not be verified: "+locale)
        path.write_text(raw,encoding="utf-8")
    print("Added the two Switch language labels across all ten frontend locales.",flush=True)
    cmd(sys.executable,"tools/l10n_shell_catalogs.py")
    cmd(sys.executable,"tools/tests/test_launcher_texts.py","--write")
    # Under the shared iOS shell, Metal HUD is enabled process-wide before
    # UIApplicationMain, then the game's HUD selection controls its layer.
    # The old single-game app derives this flag from NSUserDefaults; the shell
    # already expresses the equivalent contract as DM_HUD_PER_LAYER.
    glue=ENGINE/"dm/ios/framework/ShellGlue.m"
    source=glue.read_text(encoding="utf-8")
    token="bool front_ios_hud_enabled_from_saved_choice(void)"
    if token not in source:
        anchor="int dm_locate_game_data(void) {"
        if source.count(anchor)!=1:
            raise RuntimeError("Cannot find the verified ShellGlue insertion anchor")
        impl=(
          "// The shared shell enables Metal's HUD before UIKit starts and gates it per-game.\n"
          "// When Play has not opted into DM_METAL_HUD, disable just the game layer.\n"
          "bool front_ios_hud_enabled_from_saved_choice(void) {\n"
          "    const char *per_layer = getenv(\"DM_HUD_PER_LAYER\");\n"
          "    return per_layer && strcmp(per_layer, \"0\") != 0;\n"
          "}\n\n"
        )
        source=source.replace(anchor,impl+anchor)
        glue.write_text(source,encoding="utf-8")
        cmd("git","add","--","dm/ios/framework/ShellGlue.m",cwd=ENGINE)
        cmd("git","-c","user.name=Dante2iOS integration","-c","user.email=dante2ios-integration@users.noreply.github.com",
            "commit","-m","ios: implement saved HUD bridge for multi-game shell",cwd=ENGINE)
        cmd(sys.executable,"tools/engine.py","export","HEAD",
            "--status","pending",
            "--reason","Implement the shell equivalent of nxnative's new front_ios saved-choice HUD bridge; preserve per-game HUD isolation",
            "--issue","seedds/nxnative@ee998ae6d73d5960671ec837ea2ae4a8a0489fec")
    if token not in glue.read_text(encoding="utf-8"):
        raise RuntimeError("HUD bridge implementation missing after integration")
    cmd(sys.executable,"tools/engine.py","check")
    cmd(sys.executable,"tools/engine.py","sync")
    cmd(sys.executable,"tools/l10n_shell_catalogs.py","--check")
    print("New HUD integration patch and localization catalogs verified.",flush=True)

if __name__=="__main__":
    try:main()
    except Exception as e:
        print("Dante2iOS HEAD compatibility error: "+str(e),file=sys.stderr,flush=True)
        sys.exit(2)
