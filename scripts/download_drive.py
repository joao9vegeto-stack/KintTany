#!/usr/bin/env python3
"""Download a private Google Drive handoff using a GitHub Actions service-account secret."""
from __future__ import annotations
import argparse, hashlib, json, os
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file-id", required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--expected-size", type=int, default=0)
    ap.add_argument("--expected-sha256", default="")
    args = ap.parse_args()
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        raise SystemExit("GOOGLE_SERVICE_ACCOUNT_JSON secret is empty")
    credentials = service_account.Credentials.from_service_account_info(
        json.loads(raw), scopes=["https://www.googleapis.com/auth/drive.readonly"])
    api = build("drive", "v3", credentials=credentials, cache_discovery=False)
    meta = api.files().get(fileId=args.file_id, fields="id,name,size,mimeType").execute()
    expected = args.expected_size or int(meta.get("size", 0))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    request = api.files().get_media(fileId=args.file_id)
    digest = hashlib.sha256()
    total = 0
    with args.output.open("wb") as output:
        downloader = MediaIoBaseDownload(output, request, chunksize=64 * 1024 * 1024)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                print(f"Drive download: {int(status.progress() * 100)}%", flush=True)
    with args.output.open("rb") as f:
        while True:
            block = f.read(16 * 1024 * 1024)
            if not block:
                break
            digest.update(block)
            total += len(block)
    actual = digest.hexdigest()
    if expected and total != expected:
        raise SystemExit(f"Drive size mismatch: expected {expected}, got {total}")
    if args.expected_sha256 and actual.lower() != args.expected_sha256.lower():
        raise SystemExit(f"Drive SHA-256 mismatch: expected {args.expected_sha256}, got {actual}")
    print(f"Downloaded {meta.get('name', args.file_id)}: {total} bytes; sha256={actual}")

if __name__ == "__main__":
    main()
