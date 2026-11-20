#!/usr/bin/env python3
"""Rebase the entire NX2Apple patch queue onto one immutable nxnative commit.
No DMC2 survey, game profile or IPA build. Keep downstream source in
overlapping hunks but fail if any unresolved conflict or fork-only patch loss.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
ENGINE=ROOT/"engine"
sys.path.insert(0,str(ROOT/"tools"))
import patches as P
REPORT=Path("/tmp/dante-full-nxnative-rebase.json")
UPSTREAM="https://github.com/seedds/nxnative.git"

def call(*args, cwd=ROOT, check=True):
    p=subprocess.run(args,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                     errors="replace",env=P.clean_env())
    if check and p.returncode:
        raise RuntimeError(f"{' '.join(args)}: {p.stderr[-3500:]}")
    return p

def rev(text):
    return call("git","rev-parse",text,cwd=ENGINE).stdout.strip()

def write_report(d):
    REPORT.write_text(json.dumps(d,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as s:
            s.write("## Dante2iOS — full nxnative engine rebase\n\n")
            for k,v in d.items():
                if k not in ("rebase_output","rebase_stderr","unmerged_files"):
                    s.write(f"- **{k}**: {v}\n")
            if d.get("unmerged_files"):
                s.write("\n### Unresolved files\n\n")
                for file in d["unmerged_files"]:
                    s.write(f"- {file}\n")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--target",required=True)
    a=ap.parse_args()
    target=a.target.strip()
    if len(target)!=40 or any(x not in "0123456789abcdef" for x in target):
        ap.error("target must be an immutable full commit SHA")
    report={"target":target,"status":"started"}
    write_report(report)
    oldpin=(ROOT/".upstream-ref").read_text().strip()
    original=P.load(ROOT)
    if len(original)<56:
        raise RuntimeError(f"Expected the preserved NX2Apple queue, found only {len(original)} patches")
    report.update({"old_pin":oldpin,"original_patches":len(original)})
    print(f"Rebase {len(original)} original patches: {oldpin[:12]} -> {target[:12]}",flush=True)
    call(sys.executable,"tools/engine.py","sync")
    if call("git","status","--porcelain",cwd=ENGINE).stdout.strip():
        raise RuntimeError("Engine worktree not clean after the validated sync")
    patchtip=rev("HEAD^")
    oldcommits=call("git","rev-list","--reverse",f"{oldpin}..{patchtip}",cwd=ENGINE).stdout.split()
    if len(oldcommits)!=len(original):
        raise RuntimeError(f"Expected exactly {len(original)} patch commits; found {len(oldcommits)}")
    print("Fetching full ancestry up to the target",flush=True)
    call("git","fetch","--quiet","--no-tags","--depth=160",UPSTREAM,target,cwd=ENGINE)
    if call("git","cat-file","-e",target+"^{commit}",cwd=ENGINE,check=False).returncode:
        raise RuntimeError("Fetched nxnative target absent from engine object store")
    call("git","config","user.name","Dante2iOS verified nxnative rebase",cwd=ENGINE)
    call("git","config","user.email","dante2ios-rebase@users.noreply.github.com",cwd=ENGINE)
    call("git","checkout","--detach","--quiet",patchtip,cwd=ENGINE)
    started=time.monotonic()
    # During a rebase, theirs = the downstream fork patch; ours = new upstream.
    # Keep NX2Apple behaviour ONLY in overlapping conflict hunks while importing
    # every clean upstream change. Unresolved add/delete conflicts stop the run.
    rebased=call("git","-c","commit.gpgsign=false","rebase","--merge",
                 "--strategy=ort","-X","theirs","--reapply-cherry-picks","--empty=drop",
                 "--onto",target,oldpin,cwd=ENGINE,check=False)
    report["rebase_elapsed_s"]=round(time.monotonic()-started,2)
    if rebased.returncode:
        conflicts=call("git","diff","--name-only","--diff-filter=U",cwd=ENGINE,check=False).stdout.splitlines()
        report.update({"status":"conflict","unmerged_files":conflicts,
                       "rebase_output":rebased.stdout[-20000:],"rebase_stderr":rebased.stderr[-20000:]})
        write_report(report)
        print("REBASE FAILED. Unresolved files:",flush=True)
        for f in conflicts:print("  "+f,flush=True)
        print(rebased.stdout[-5000:],flush=True)
        print(rebased.stderr[-5000:],flush=True)
        raise RuntimeError("Could not preserve all NX2Apple patches without unresolved conflicts")
    commits=call("git","rev-list","--reverse",f"{target}..HEAD",cwd=ENGINE).stdout.split()
    bysubject={p.subject:p for p in original}
    applied=[];used=set()
    for c in commits:
        subject=call("git","log","-1","--format=%s",c,cwd=ENGINE).stdout.strip()
        p=bysubject.get(subject)
        if p is None:
            raise RuntimeError(f"Rebased commit not mapped to an original fork patch: {subject}")
        if p.file in used:
            raise RuntimeError(f"Rebased original patch twice: {p.file}")
        applied.append((p,c));used.add(p.file)
    dropped=[p for p in original if p.file not in used]
    missing_fork=[p.file for p in dropped if p.kind=="fork-only"]
    report.update({"rebase_commits":len(commits),"landed_upstream":len(dropped),
                   "dropped_patch_names":[p.file for p in dropped],
                   "missing_fork_only":missing_fork})
    if missing_fork:
        report["status"]="unsafe_dropped_fork"
        write_report(report)
        raise RuntimeError("Refusing to discard fork-only patches: "+", ".join(missing_fork))
    P.write_series(ROOT,ENGINE,applied,dropped,original)
    (ROOT/".upstream-ref").write_text(target+"\n",encoding="utf-8")
    import engine as E
    moved=E.relink(ROOT)
    report.update({"status":"rebased_unverified","new_pin":target,
                   "remaining_patches":len(applied),"updated_links":[p.as_posix() for p in moved]})
    write_report(report)
    print(f"Rebased {len(applied)} patches onto nxnative {target[:12]}; {len(dropped)} upstream duplicates retired.",flush=True)
    print("NEXT: check, scratch rebuild and complete test suite before any push.",flush=True)

if __name__=="__main__":
    try:
        main()
    except Exception as e:
        print("DANTE FULL REBASE ERROR: "+str(e),file=sys.stderr,flush=True)
        sys.exit(2)
