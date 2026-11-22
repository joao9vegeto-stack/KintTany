"""Reject GitHub artifact ZIPs and damaged files masquerading as Fairy2iOS IPAs.

A .ipa is a ZIP containing Payload/<app>.app. Checking only the filename,
outer artifact checksum or byte length is not sufficient for iOS importers.
"""
from __future__ import annotations
import json
import plistlib
import zipfile
from pathlib import Path

TITLE_ID = "0100B9801F872000"

def check(condition, message):
    if not condition:
        raise RuntimeError("[Fairy2iOS IPA] " + message)

def validate_ipa(path, report, verify_crc=True):
    path = Path(path)
    check(path.is_file() and path.suffix.lower() == ".ipa", "expected an extracted .ipa file")
    check(zipfile.is_zipfile(path), "download is not a ZIP-based IPA")
    app = "Payload/DmShell.app/"
    framework = report.get("framework", "")
    check(framework == "DmGame0100B9801F872000.framework", "wrong game framework in build report")
    fw = app + "Frameworks/" + framework + "/"
    with zipfile.ZipFile(path, "r", allowZip64=True) as z:
        infos = z.infolist()
        names = set(z.namelist())
        check(len(infos) == len(names), "IPA contains duplicate ZIP member names")
        check(all(not i.filename.startswith("/") and
                  ".." not in Path(i.filename).parts and
                  "\\" not in i.filename and
                  not (i.flag_bits & 0x1) for i in infos),
              "IPA has unsafe or encrypted ZIP members")
        needed = [app + "Info.plist", app + "DmShell", fw + "game.manifest.json",
                  fw + "dm/launcher.json"]
        check(all(name in names for name in needed),
              "missing Payload/DmShell.app or required game framework files")
        check(z.getinfo(app + "DmShell").file_size > 4096,
              "app executable missing or empty")
        plist = plistlib.loads(z.read(app + "Info.plist"))
        check(plist.get("CFBundleExecutable") == "DmShell" and
              str(plist.get("CFBundleIdentifier", "")).startswith("org.nxnative."),
              "app Info.plist is not a Fairy2iOS shell")
        manifest = json.loads(z.read(fw + "game.manifest.json"))
        check(str(manifest.get("title_id", "")).upper() == TITLE_ID,
              "game manifest Title ID mismatch")
        launcher = json.loads(z.read(fw + "dm/launcher.json"))
        check(launcher.get("game") == TITLE_ID, "launcher game Title ID mismatch")
        settings = {x.get("env"): x for x in launcher.get("settings", [])}
        fps, buttons = settings.get("DM_FPS_TARGET", {}), settings.get("DM_PAD_MAP", {})
        check(fps.get("default") == "30" and
              [x[0] for x in fps.get("options", [])] == ["30", "60"] and
              buttons.get("on") == "A=B,B=A",
              "30/60 FPS or A/B swap settings missing from IPA")
        shader = report.get("shader_payload", {})
        shader_path = app + str(shader.get("ipa_path", ""))
        check(shader_path in names and
              z.getinfo(shader_path).file_size == int(shader.get("size_bytes") or -1),
              "Metal shader image missing or wrong length")
        if verify_crc:
            bad = z.testzip()
            check(bad is None, f"IPA internal ZIP CRC failed: {bad}")
    return {"app": "DmShell.app", "framework": framework,
            "shader_size": int(shader["size_bytes"]), "crc_verified": bool(verify_crc),
            "fps": [30, 60], "swap_ab": True}
