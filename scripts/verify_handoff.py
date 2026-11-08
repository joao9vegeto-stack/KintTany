#!/usr/bin/env python3
"""Verify a zstd-compressed handoff archive and safely extract it with system tar."""
from __future__ import annotations
import argparse, hashlib, json, subprocess
from pathlib import Path

def zstd_pipe(args):
    return subprocess.Popen(["zstd", "-dc", str(args.archive)], stdout=subprocess.PIPE)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", type=Path, required=True)
    ap.add_argument("--destination", type=Path, required=True)
    ap.add_argument("--sha256", required=True)
    args = ap.parse_args()
    h = hashlib.sha256()
    with args.archive.open("rb") as f:
        for block in iter(lambda: f.read(16 * 1024 * 1024), b""):
            h.update(block)
    if h.hexdigest().lower() != args.sha256.lower():
        raise SystemExit("Handoff archive SHA-256 does not match handoff.json")

    z = zstd_pipe(args)
    listing = subprocess.run(["tar", "-tvf", "-"], stdin=z.stdout, capture_output=True, text=True, check=True)
    z.stdout.close()
    if z.wait() != 0:
        raise SystemExit("zstd failed while listing the handoff archive")
    for line in listing.stdout.splitlines():
        if line.startswith(("l", "h")):
            raise SystemExit("Handoff archive contains a symbolic or hard link; refusing extraction")
    z = zstd_pipe(args)
    args.destination.mkdir(parents=True, exist_ok=True)
    extracted = subprocess.run(["tar", "-xf", "-", "-C", str(args.destination),
                                "--no-same-owner", "--no-same-permissions"], stdin=z.stdout, check=False)
    z.stdout.close()
    if extracted.returncode != 0 or z.wait() != 0:
        raise SystemExit("Could not extract the handoff archive")
    # Verify the member names too; the archive is produced by our notebook and must be relative.
    z = zstd_pipe(args)
    names = subprocess.run(["tar", "-tf", "-"], stdin=z.stdout, capture_output=True, text=True, check=True).stdout
    z.stdout.close()
    if z.wait() != 0:
        raise SystemExit("zstd failed while checking handoff paths")
    for name in names.splitlines():
        p = Path(name)
        if p.is_absolute() or ".." in p.parts:
            raise SystemExit(f"Unsafe path in handoff archive: {name}")
    manifest = json.loads((args.destination / "manifest.json").read_text())
    if manifest.get("format") != 1:
        raise SystemExit("Unsupported handoff archive format")
    if not (args.destination / "game.nup").is_file():
        raise SystemExit("Handoff archive has no game.nup")
    prep_path = args.destination / "work" / "kleo-linux-prep.json"
    if not prep_path.is_file():
        raise SystemExit("Handoff archive has no Linux preparation output")
    prep = json.loads(prep_path.read_text())
    if manifest.get("title_id") != prep.get("title_id") or manifest.get("engine_pin") != prep.get("engine_pin"):
        raise SystemExit("Archive manifest and Linux preparation metadata disagree")
    print(json.dumps(manifest, indent=2))

if __name__ == "__main__":
    main()
