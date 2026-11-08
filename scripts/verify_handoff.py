#!/usr/bin/env python3
"""Validate a Colab handoff archive and extract it without trusting its paths."""
from __future__ import annotations
import argparse, hashlib, json, tarfile
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", type=Path, required=True)
    ap.add_argument("--destination", type=Path, required=True)
    ap.add_argument("--sha256", required=True)
    args = ap.parse_args()
    h = hashlib.sha256()
    with args.archive.open("rb") as f:
        while True:
            block = f.read(16 * 1024 * 1024)
            if not block:
                break
            h.update(block)
    if h.hexdigest().lower() != args.sha256.lower():
        raise SystemExit("Handoff archive SHA-256 does not match handoff.json")
    args.destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(args.archive, "r|*") as tf:
        for member in tf:
            p = Path(member.name)
            if p.is_absolute() or ".." in p.parts:
                raise SystemExit(f"Unsafe path in handoff archive: {member.name}")
            tf.extract(member, args.destination, filter="data")
    manifest = json.loads((args.destination / "manifest.json").read_text())
    if manifest.get("format") != 1:
        raise SystemExit("Unsupported handoff archive format")
    if not (args.destination / "game.nup").is_file():
        raise SystemExit("Handoff archive has no game.nup")
    if not (args.destination / "work" / "kleo-linux-prep.json").is_file():
        raise SystemExit("Handoff archive has no Linux preparation output")
    print(json.dumps(manifest, indent=2))

if __name__ == "__main__":
    main()
