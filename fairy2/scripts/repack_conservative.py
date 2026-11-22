#!/usr/bin/env python3
"""One consolidated conservative iOS host-memory candidate, no shader rebuild.

Restores the verified complete 4GiB address partition and physical map budget,
retains A/B + 30/60, reduces concurrent GPU work during KTGL startup, and
logs changes to the failing allocator bin. This is a candidate, not a proven
on-device fix. It never silently relabels the previous crashed IPA as good.
"""
import argparse
import json
import sys
import zipfile
from pathlib import Path

import repack_global_memory as original
import repack_ipa as menu

NAME = "Fairy2iOS-FairyTail2-ConservativeGPU-MemoryTrace.ipa"
KEYS = ("DM_NVN_ENC_THREAD", "DM_NVN_PREFETCH", "DM_PSO_PREBUILD")

def configure(data):
    current = menu._fairy2_real_config(data)
    rows = [r for r in current["settings"] if r.get("env") not in KEYS]
    for env, label in (
        ("DM_NVN_ENC_THREAD", "Serializar comandos Metal durante inicialização"),
        ("DM_NVN_PREFETCH", "Desativar pré-carregamento GPU simultâneo"),
        ("DM_PSO_PREBUILD", "Desativar pré-compilação paralela de pipelines"),
    ):
        rows.append({"env":env, "kind":"choice", "section":"Advanced",
                     "label":label, "default":"0",
                     "note":"Modo conservador para isolar corrida GPU/CPU no alocador de Fairy Tail 2.",
                     "options":[["0","Modo conservador"],["1","Modo original"]],
                     "level":"advanced"})
    current["settings"] = rows
    assert len({r["env"] for r in rows}) == len(rows)
    return current

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source-ipa", type=Path, required=True)
    ap.add_argument("--source-report", type=Path, required=True)
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    opt=ap.parse_args()
    path=opt.repo / "engine/dm/host/probe.c"
    source=path.read_text()
    if source.count("fairy2_bin47_poll") != 2:
        raise RuntimeError("Forensic iOS host instrumentation missing before Xcode build")
    menu._fairy2_real_config=menu.configure_launcher
    menu.configure_launcher=configure
    original.OUT_NAME=NAME
    report=original.make(opt.source_ipa,opt.source_report,
                         opt.repo.resolve(),opt.output)
    result=opt.output/NAME
    with zipfile.ZipFile(result) as z:
        p="Payload/DmShell.app/Frameworks/"+original.FRAMEWORK+"/dm/launcher.json"
        settings=json.loads(z.read(p))["settings"]
        keyed={r["env"]:r for r in settings}
        for k in KEYS:
            if keyed[k]["default"] != "0":
                raise RuntimeError("GPU synchronization default lost in packaged IPA: "+k)
    report.update({
        "repair_candidate":True,
        "runtime_verified_on_iphone":False,
        "from_confirmed_crash_run":44990224107,
        "conservative_defaults":{k:"0" for k in KEYS},
        "native_host_bin47_poll":True,
        "no_proven_guest_corruption_fix_yet":True,
        "fps_30_60_selector_preserved":True,
        "shader_and_guest_code_reused":True,
    })
    (opt.output/"global-memory-report.json").write_text(json.dumps(report,indent=2)+"\n")
    (opt.output/"conservative-report.json").write_text(json.dumps(report,indent=2)+"\n")
    print("[Fairy2iOS] HOST-ONLY candidate built and validated:",
          NAME,report["output_ipa_sha256"],flush=True)

if __name__=="__main__":
    main()
