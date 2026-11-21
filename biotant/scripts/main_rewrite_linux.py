#!/usr/bin/env python3
"""A single private Biomutant NSO rewrite on an Ubuntu GitHub Actions runner.

Input and patched output are transported exclusively by verified Google Drive
files. No proprietary game executable is committed or exposed as an artifact.
This job is separate from the signed iOS IPA build.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "biotant"))
sys.path.insert(0, str(ROOT / "biotant/colab"))
from drive_chunks import download_drive_file
from offload_main import pack_zstd, unpack_zstd, sha

TITLE = "01004BA017CD6000"
PIN = "b526a50b85e4cfa3142c111e1ad491d9fd11f0eb"
SUFFIXES = (
    "patched.bin", "fixups.tsv", "gates.tsv", "sites.tsv",
    "cuts.tsv", "changed.tsv", "obs.tsv",
)


def check(flag, message):
    if not flag:
        raise RuntimeError("[BioiOSMutant Linux main rewrite] " + message)


def dependency_entries(path):
    """Relocation-safe NXNative build_src.sha256 equality.

    The names may contain absolute colab/runner paths to provisional profile
    files. Require identical individual bytes (sha256) and the same filenames,
    ignoring only directory location.
    """
    entries = []
    for line in Path(path).read_text(errors="replace").splitlines():
        parts = line.split("  ", 1)
        check(len(parts) == 2 and re.fullmatch(r"[0-9a-f]{64}", parts[0]),
              "Corrupt SHA-256 dependency inventory")
        entries.append((parts[0], Path(parts[1].strip()).name))
    check(bool(entries), "Empty rewriter SHA-256 inventory")
    return sorted(entries)


def drive():
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    check(bool(raw), "GOOGLE_SERVICE_ACCOUNT_JSON must be set with Drive write access")
    info = json.loads(raw)
    credentials = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/drive"])
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def upload(api, parent, result_id, path, name):
    # The Google account owns the pre-created empty file in My Drive.
    # A service account cannot CREATE files in personal My Drive (no quota);
    # it CAN update a user-owned file where it has writer access.
    metadata = api.files().get(
        fileId=result_id, fields="id,name,size,parents",
        supportsAllDrives=True).execute()
    check(metadata.get("id") == result_id
          and metadata.get("name") == name
          and parent in metadata.get("parents", []),
          "Destination is not the exact pre-created user-owned Drive file")
    check(int(metadata.get("size") or 0) == 0,
          "The result file already has content; refusing to overwrite a previous build")
    uploaded = api.files().update(
        fileId=result_id,
        media_body=MediaFileUpload(str(path),
                                   mimetype="application/octet-stream",
                                   chunksize=64 * 1024 * 1024, resumable=True),
        supportsAllDrives=True, fields="id,name,size,md5Checksum")
    md5 = hashlib.md5()
    with path.open("rb") as source:
        for data in iter(lambda: source.read(8 * 1024 * 1024), b""):
            md5.update(data)
    result = None
    while result is None:
        status, result = uploaded.next_chunk(num_retries=5)
        if status:
            print("[BioiOSMutant] Verified result transfer:",
                  f"{status.progress():.1%}", flush=True)
    check(int(result.get("size") or 0) == path.stat().st_size
          and result.get("md5Checksum") == md5.hexdigest(),
          "Drive output size/MD5 mismatch")
    print("[BioiOSMutant] Main patched output stored privately on Drive:",
          result["id"], "SHA-256:", sha(path), flush=True)


def run_main(py, script, source, output, env):
    # Launch only one module, and sample its Python call stack every 3 min.
    # The rewriter itself is byte-identical to the Colab pin.
    bootstrap = (
        "import faulthandler,runpy,sys;"
        "faulthandler.enable();"
        "faulthandler.dump_traceback_later(180,repeat=True);"
        "script=sys.argv[1];"
        "from pathlib import Path;"
        "sys.path.insert(0,str(Path(script).parent));"
        "sys.argv=sys.argv[1:];"
        "runpy.run_path(script,run_name='__main__')"
    )
    cmd = [py, "-u", "-c", bootstrap, str(script), str(source), str(output), "main"]
    print("[BioiOSMutant] Starting one Linux main rewrite; "
          "traceback samples every 180 sec, no Xcode, no NSP, no keys.",
          flush=True)
    proc = subprocess.Popen(cmd, env=env)
    stop = threading.Event()
    def heartbeat():
        while not stop.wait(60):
            if proc.poll() is not None:
                break
            try:
                status = Path(f"/proc/{proc.pid}/status").read_text()
                memory = [line for line in status.splitlines()
                          if line.startswith(("VmRSS:", "VmHWM:", "Threads:", "State:"))]
                cpu = subprocess.run(["ps", "-p", str(proc.pid), "-o", "time=,pcpu=,etime="],
                                     capture_output=True, text=True, timeout=8, check=False)
                print("[BioiOSMutant] Main rewrite live:",
                      ", ".join(memory), "| CPU:", cpu.stdout.strip(), flush=True)
            except OSError:
                pass
    watcher = threading.Thread(target=heartbeat, daemon=True)
    watcher.start()
    try:
        status = proc.wait()
    finally:
        stop.set()
    if status != 0:
        print("[BioiOSMutant] Main rewrite terminated with code", status,
              ". Existing Colab 3/4 checkpoints remain untouched.", flush=True)
        for path in ("/sys/fs/cgroup/memory.events",
                     "/sys/fs/cgroup/memory.peak", "/sys/fs/cgroup/memory.max"):
            try:
                print(path, Path(path).read_text()[:500], flush=True)
            except OSError:
                pass
        raise RuntimeError(f"main-only Linux rewrite failed: exit {status}")
    print("[BioiOSMutant] main patch_nso.py successfully completed.", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    req = json.loads(args.request.read_text())
    check(req.get("project") == req.get("branch") == "BioiOSMutant"
          and req.get("title_id") == TITLE
          and req.get("engine_pin") == PIN
          and re.fullmatch(r"v[0-9]+", req.get("version", ""))
          and re.fullmatch(r"[0-9a-f]{32}", req.get("request_id", ""))
          and re.fullmatch(r"[0-9a-f]{64}", req.get("fingerprint", ""))
          and req.get("output_file_name") ==
              "main-result-" + req.get("request_id", "") + ".tar.zst"
          and isinstance(req.get("output_file_id"), str)
          and bool(req["output_file_id"]),
          "Request identity invalid")
    check((ROOT / ".upstream-ref").read_text().strip() == PIN,
          "The fork's pinned engine changed")
    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    api = drive()
    input_archive = workspace / "main-input.tar.zst"
    download_drive_file(api, req["archive"], input_archive)
    stage = workspace / "input"
    unpack_zstd(input_archive, stage)
    info = json.loads((stage / "input.json").read_text())
    for key in ("project", "branch", "title_id", "version", "request_id",
                "engine_pin", "source_commit", "main_sha256", "fingerprint"):
        check(req.get(key) == info.get(key), "Source package mismatch: " + key)
    source = stage / "main.nso"
    check(source.is_file() and sha(source) == req["main_sha256"],
          "Game main input SHA-256 mismatch")
    profile = stage / "profile" / TITLE
    check((profile / "game.tsv").is_file(), "Private Biomutant profile missing")
    profile_files = {
        x.relative_to(stage).as_posix(): sha(x)
        for x in sorted((stage / "profile").rglob("*")) if x.is_file()
    }
    check(profile_files == info["profile_hashes"],
          "Provisional game profile changed during transfer")
    engine = ROOT / "engine"
    tool = engine / "dm/tools/patch_nso.py"
    check(tool.is_file() and sha(tool) == info["patch_nso_sha256"],
          "The exact pinned rewrite tool differs from the Colab tool. "
          "Cannot safely continue; leave Colab cache intact.")
    output = workspace / "patched_main"
    output.mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update({
        "DM_GAME": TITLE,
        "DM_GAMES_DIR": str(stage / "profile"),
        "DM_GAMES_FIRST": "1",
        "DM_REWRITE_J": "2",
        "PYTHONUNBUFFERED": "1",
        "PYTHONFAULTHANDLER": "1",
    })
    # Preserve the exact patch front switch used by the submitted Colab run.
    if info.get("dm_patch_front"):
        env["DM_PATCH_FRONT"] = info["dm_patch_front"]
    run_main(sys.executable, tool, source, output, env)
    result_record = output / "build_src.sha256"
    original_record = stage / "build_src.sha256"
    check(result_record.is_file() and original_record.is_file()
          and sha(original_record) == info["build_src_sha256"]
          and dependency_entries(result_record) == dependency_entries(original_record),
          "Rewriter dependency source hashes differ from the original Colab "
          "run; refuse a different engine/profile")
    files = {}
    for suffix in SUFFIXES:
        name = "main." + suffix
        path = output / name
        check(path.is_file(), "Incomplete main output: " + name)
        files[name] = sha(path)
    check((output / "main.patched.bin").stat().st_size > 0
          and "# BUILD_ID\t" in (output / "main.fixups.tsv").read_text(),
          "Produced main is not a validated AArch64 rewrite")
    report = {
        "format": 1, "project": "BioiOSMutant", "title_id": TITLE,
        "request_id": req["request_id"], "version": req["version"],
        "engine_pin": PIN, "main_sha256": req["main_sha256"],
        "fingerprint": req["fingerprint"], "build_src_sha256":
            sha(original_record), "runner_build_src_sha256":
            sha(result_record), "file_hashes": files,
        "runner": "GitHub Ubuntu Linux", "reused_colab_modules": 3,
    }
    out = workspace / "returned"
    out.mkdir()
    for name in files:
        shutil.copy2(output / name, out / name)
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    archive = workspace / ("main-result-" + req["request_id"] + ".tar.zst")
    pack_zstd(out, archive)
    check(archive.name == req["output_file_name"],
          "Output name differs from user-owned reserved file")
    upload(api, req["folder_id"], req["output_file_id"], archive, archive.name)
    print("[BioiOSMutant] Main-only rewrite completed and Drive upload "
          "verified. Return to Colab to import this result, then "
          "continue Linux shader preparation.", flush=True)


if __name__ == "__main__":
    main()
