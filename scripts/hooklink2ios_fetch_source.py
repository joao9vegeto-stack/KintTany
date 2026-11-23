#!/usr/bin/env python3
"""HookLink2iOS: ranged 16 MiB download of an existing Actions artifact or Drive IPA."""
from __future__ import annotations
import argparse, hashlib, json, os, re, time
from pathlib import Path
import requests

CHUNK = 16*1024*1024
REPO = "joao9vegeto-stack/KintTany"

def fail(msg):
    raise RuntimeError("[HookLink2iOS source] "+msg)

def ranged_download(out, total, signed_url, session=None, headers=None):
    if total < 20*1024*1024: fail("source too small for proven IPA")
    out.parent.mkdir(parents=True, exist_ok=True)
    client = session or requests.Session()
    offset = out.stat().st_size if out.exists() else 0
    if offset > total:
        out.unlink()
        offset = 0
    print(f"source {total:,} bytes; resuming from {offset:,}", flush=True)
    while offset < total:
        end = min(total, offset+CHUNK)-1
        for attempt in range(8):
            try:
                h = dict(headers or {})
                h["Range"] = f"bytes={offset}-{end}"
                with client.get(signed_url(), headers=h, stream=True, timeout=(30,180)) as response:
                    cr = response.headers.get("Content-Range", "")
                    match = re.fullmatch(r"bytes\s+(\d+)-(\d+)/(\d+)", cr)
                    if response.status_code != 206 or not match:
                        fail(f"expected 206 partial download, got {response.status_code} {cr}")
                    if tuple(map(int, match.groups())) != (offset, end, total):
                        fail("unexpected Content-Range "+cr)
                    n = 0
                    with out.open("r+b" if out.exists() else "w+b") as dest:
                        dest.truncate(offset)
                        dest.seek(offset)
                        for block in response.iter_content(chunk_size=1024*1024):
                            if block:
                                dest.write(block)
                                n += len(block)
                    if n != end-offset+1: fail("incomplete HTTP range")
                offset=end+1
                print(f"download {offset/total*100:.1f}% ({offset:,}/{total:,})",flush=True)
                break
            except Exception as e:
                if out.exists():
                    with out.open("r+b") as dest: dest.truncate(offset)
                if attempt==7: raise
                print("retry",offset,attempt+1,type(e).__name__,str(e)[:200],flush=True)
                time.sleep(min(30,2**attempt))
    if out.stat().st_size != total: fail("download size mismatch")

def drive_download(file_id, output):
    import google.auth
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    raw=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON","")
    if not raw: fail("missing GOOGLE_SERVICE_ACCOUNT_JSON")
    credentials=service_account.Credentials.from_service_account_info(
        json.loads(raw),scopes=["https://www.googleapis.com/auth/drive.readonly"])
    credentials.refresh(Request())
    drive=build("drive","v3",credentials=credentials,cache_discovery=False)
    meta=drive.files().get(fileId=file_id,fields="id,name,size,md5Checksum",supportsAllDrives=True).execute()
    size=int(meta["size"])
    url=f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&supportsAllDrives=true"
    class GoogleSession(requests.Session):
        def get(self,u,**kwargs):
            if credentials.expired or not credentials.valid: credentials.refresh(Request())
            kwargs.setdefault("headers",{})["Authorization"]="Bearer "+credentials.token
            return super().get(u,**kwargs)
    ranged_download(output,size,lambda:url,session=GoogleSession())
    if meta.get("md5Checksum"):
        h=hashlib.md5()
        with output.open("rb") as f:
            for b in iter(lambda:f.read(CHUNK),b""):h.update(b)
        if h.hexdigest()!=meta["md5Checksum"]: fail("Drive MD5 mismatch")
    print("Drive original:",meta["name"],flush=True)

def github_download(artifact_id,output):
    token=os.getenv("GITHUB_TOKEN","")
    if not token: fail("GITHUB_TOKEN not available")
    api=f"https://api.github.com/repos/{REPO}/actions/artifacts/{artifact_id}"
    h={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json"}
    response=requests.get(api,headers=h,timeout=30)
    response.raise_for_status()
    meta=response.json()
    if meta.get("expired"):fail("GitHub artifact expired. Supply a Drive copy instead.")
    total=int(meta["size_in_bytes"])
    def redirect():
        answer=requests.get(api+"/zip",headers=h,allow_redirects=False,timeout=30)
        if answer.status_code!=302 or "Location" not in answer.headers:
            fail(f"GitHub artifact redirect unavailable ({answer.status_code})")
        url=answer.headers["Location"]
        if not url.startswith("https://"): fail("unsafe GitHub redirect")
        return url
    ranged_download(output,total,redirect)
    expected=meta.get("digest","")
    if expected.startswith("sha256:"):
        checksum=hashlib.sha256()
        with output.open("rb") as f:
            for b in iter(lambda:f.read(CHUNK),b""):checksum.update(b)
        if checksum.hexdigest()!=expected.split(":",1)[1]:fail("GitHub checksum mismatch")

def main():
    ap=argparse.ArgumentParser()
    exclusive=ap.add_mutually_exclusive_group(required=True)
    exclusive.add_argument("--artifact-id",type=int)
    exclusive.add_argument("--drive-file-id")
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    if args.artifact_id: github_download(args.artifact_id,args.output)
    else: drive_download(args.drive_file_id,args.output)
    print("HOOKLINK2IOS_SOURCE_OK",args.output,args.output.stat().st_size,flush=True)

if __name__=="__main__":
    main()
