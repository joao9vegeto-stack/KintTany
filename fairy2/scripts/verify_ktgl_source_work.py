#!/usr/bin/env python3
"""Linux-only real Colab KTGL source audit. No giant RomFS, shaders, NSP or IPA.

Download only the immutable 113 MB Drive work archive using the existing
handoff, verify its SHA, stream only the original NSO, rewritten main and
profile, check 10 real source-vs-AOT regions, publish JSON with no game bytes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
import tarfile
from pathlib import Path, PurePosixPath
from ktgl_reference_baseline import audit

TARGETS = {
    "extract/v458752/ExeFS/main": "source_main.nso",
    "patched_v458752/main.patched.bin": "rewritten_main.bin",
    "profile/0100B9801F872000/game.tsv": "game.tsv",
}

def fail(msg):
    raise ValueError("[KTGL Drive source parity] " + msg)

def verify_digest(path, expected):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    if path.stat().st_size != int(expected["size"]) or h.hexdigest() != expected["sha256"]:
        fail("immutable Colab archive size or SHA-256 mismatch")
    return h.hexdigest()

def download_handoff_archive(d, output):
    import os
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        fail("Drive read-only service-account secret absent; cannot verify real inputs")
    item = d["work_archive"]
    ident = str(item["id"])
    if not ident or len(ident) > 200 or not all(x.isalnum() or x in "_-" for x in ident):
        fail("invalid Drive file ID")
    credentials = service_account.Credentials.from_service_account_info(
        json.loads(raw), scopes=["https://www.googleapis.com/auth/drive.readonly"])
    session = AuthorizedSession(credentials)
    url = "https://www.googleapis.com/drive/v3/files/" + ident
    with session.get(url, params={"alt": "media"}, stream=True,
                     timeout=(30, 240)) as response:
        response.raise_for_status()
        with output.open("wb") as f:
            for chunk in response.iter_content(chunk_size=4 * 1024 * 1024):
                if chunk:
                    f.write(chunk)
    verify_digest(output, item)

def extract_reference_parts(archive: Path, directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    found = {}
    with subprocess.Popen(["zstd", "-dc", str(archive)], stdout=subprocess.PIPE) as proc:
        if proc.stdout is None:
            fail("cannot start streaming zstd decompressor")
        with tarfile.open(fileobj=proc.stdout, mode="r|") as bundle:
            for member in bundle:
                raw = PurePosixPath(member.name)
                if raw.is_absolute() or ".." in raw.parts or member.issym() or member.islnk():
                    fail("unsafe archive path/link")
                name = "/".join(x for x in raw.parts if x not in ("", "."))
                if name not in TARGETS:
                    continue
                if not member.isfile() or name in found or member.size > 128 * 1024 * 1024:
                    fail("invalid or duplicate original game module")
                source = bundle.extractfile(member)
                if source is None:
                    fail("tar truncated requested original module")
                dest = directory / TARGETS[name]
                with source, dest.open("wb") as f:
                    remaining = member.size
                    while remaining:
                        chunk = source.read(min(4 * 1024 * 1024, remaining))
                        if not chunk:
                            fail("tar truncated game module bytes")
                        f.write(chunk)
                        remaining -= len(chunk)
                found[name] = dest
        proc.stdout.close()
        if proc.wait() != 0:
            fail("zstd exited with error")
    if set(found) != set(TARGETS):
        fail("missing original NSO, rewritten main or game profile from Colab archive")
    return found

def verify(handoff_path: Path, output: Path, local_archive: Path | None = None):
    d = json.loads(handoff_path.read_text())
    if (d.get("branch") != "Fairy2iOS" or
        d.get("title_id") != "0100B9801F872000" or
        d.get("package_version") != "v458752" or
        d.get("engine_pin") != "b526a50b85e4cfa3142c111e1ad491d9fd11f0eb"):
        fail("wrong user-owned handoff title, update or upstream engine")
    output.mkdir(parents=True, exist_ok=True)
    archive = local_archive or output / "work.tar.zst"
    if local_archive is None:
        download_handoff_archive(d, archive)
    digest = verify_digest(archive, d["work_archive"])
    files = extract_reference_parts(archive, output / "private_parts")
    report = audit(files["extract/v458752/ExeFS/main"],
                   files["patched_v458752/main.patched.bin"],
                   files["profile/0100B9801F872000/game.tsv"])
    report.update({
        "real_Colab_source_verified": True,
        "work_archive_sha256": digest,
        "work_archive_bytes": archive.stat().st_size,
        "fdata_romfs_not_downloaded": True,
        "gameplay_fix_claimed": False,
    })
    (output / "ktgl-reference-real-source-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print("PASS REAL COLAB SOURCE:", report["original_code_verified_bytes"],
          "bytes, 10 untouched KTGL regions, no IPA or shaders")
    return report

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--handoff", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--local-archive", type=Path)
    a = p.parse_args()
    verify(a.handoff, a.output, a.local_archive)

if __name__ == "__main__":
    main()
