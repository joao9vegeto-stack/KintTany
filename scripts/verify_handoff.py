#!/usr/bin/env python3
"""Verify a zstd-compressed handoff archive and safely extract it with system tar."""
from __future__ import annotations
import argparse, hashlib, json, subprocess
from pathlib import Path

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
    listing = subprocess.run(["tar", "--zstd", "-tf", str(args.archive)], capture_output=True, text=True, check=True).stdout
    for name in listing.splitlines():
        p = Path(name)
        if p.is_absolute() or ".." in p.parts:
            raise SystemExit(f"Unsafe path in handoff archive: {name}")
    args.destination.mkdir(parents=True, exist_ok=True)
    subprocess.run(["tar", "--zstd", "-xf", str(args.archive), "-C", str(args.destination),
                    "--no-same-owner", "--no-same-permissions"], check=True)
    manifest = json.loads((args.destination / "manifest.json").read_text())
    if manifest.get("format") != 1:
        raise SystemExit("Unsupported handoff archive format")
    if not (args.destination / "game.nup").is_file():
        raise SystemExit("Handoff archive has no game.nup")
    if not (args.destination / "work" / "kleo-linux-prep.json").is_file():
        raise SystemExit("Handoff archive has no Linux preparation output")
    prep = json.loads((args.destination / "work" / "kleo-linux-prep.json").read_text())
    if manifest.get("title_id") != prep.get("title_id") or manifest.get("engine_pin") != prep.get("engine_pin"):
        raise SystemExit("Archive manifest and Linux preparation metadata disagree")
    print(json.dumps(manifest, indent=2))

if __name__ == "__main__":
    main()
