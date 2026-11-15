#!/usr/bin/env python3
"""Persist and resume the pinned NXNative shader CAS in the Mugiwara Drive game folder."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time


class ShaderCacheCheckpoint:
    NAME = "mugiwara4ios-shader-cas.db"
    CACHE_TAG = "mugiwara4ios-shader-cas-v1"
    INTERVAL_SECONDS = 600
    UPLOAD_CHUNK = 256 * 1024 * 1024

    def __init__(
        self,
        drive,
        credentials,
        folder_id: str,
        cache_path: Path,
        *,
        engine_pin: str,
        title_id: str,
        package_version: str,
        shader_chain: str,
        shader_package_key: str,
    ):
        self.drive = drive
        self.credentials = credentials
        self.folder_id = str(folder_id)
        self.cache_path = Path(cache_path)
        self.identity = {
            "mugiwara4ios_cache": self.CACHE_TAG,
            "engine_pin": str(engine_pin),
            "title_id": str(title_id),
            "package_version": str(package_version),
            "shader_chain": str(shader_chain),
            "shader_package_key": str(shader_package_key),
        }
        self.stop_event = threading.Event()
        self.thread = None
        self.file_id = None
        self.lock = threading.Lock()

    @classmethod
    def from_environment(
        cls,
        prepared: dict,
        work_dir: Path,
        *,
        engine_pin: str,
        title_id: str,
        shader_chain: str,
        shader_package_key: str,
    ) -> "ShaderCacheCheckpoint":
        raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        if not raw:
            raise RuntimeError(
                "GOOGLE_SERVICE_ACCOUNT_JSON is required for resumable Metal shader checkpoints."
            )
        try:
            from google.auth.transport.requests import AuthorizedSession  # noqa: F401
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
            info = json.loads(raw)
            credentials = service_account.Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/drive"],
            )
            drive = build("drive", "v3", credentials=credentials, cache_discovery=False)
        except Exception as exc:
            raise RuntimeError(f"Could not initialize Google Drive checkpoint client: {exc}") from exc

        game_data = prepared.get("game_data") or {}
        folder_id = game_data.get("folder_id")
        if not folder_id:
            raise RuntimeError("Colab handoff has no game_data.folder_id for the Metal CAS checkpoint.")
        package_version = str(prepared.get("package_version") or "")
        if not package_version:
            raise RuntimeError("Colab handoff has no package_version for the Metal CAS checkpoint.")
        cache_path = Path(work_dir) / "shader" / "cache" / "cas.db"
        return cls(
            drive,
            credentials,
            folder_id,
            cache_path,
            engine_pin=engine_pin,
            title_id=title_id,
            package_version=package_version,
            shader_chain=shader_chain,
            shader_package_key=shader_package_key,
        )

    def _find(self):
        query = (
            f"'{self.folder_id}' in parents and name = '{self.NAME}' "
            "and trashed = false"
        )
        result = self.drive.files().list(
            q=query,
            spaces="drive",
            pageSize=100,
            fields="files(id,name,size,md5Checksum,appProperties,modifiedTime)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute(num_retries=5)
        candidates = []
        for item in result.get("files", []):
            props = item.get("appProperties") or {}
            if all(props.get(key) == value for key, value in self.identity.items()):
                candidates.append(item)
        if not candidates:
            return None
        item = sorted(candidates, key=lambda value: value.get("modifiedTime", ""))[-1]
        self.file_id = item["id"]
        return item

    def restore(self) -> int:
        item = self._find()
        if not item:
            print(
                "[Mugiwara4iOS] No matching Metal CAS checkpoint in Drive; starting a clean shader cache.",
                flush=True,
            )
            return 0
        props = item.get("appProperties") or {}
        record = {
            "id": item["id"],
            "name": self.NAME,
            "size": int(item.get("size", 0)),
            "sha256": props.get("sha256", ""),
            "md5": item.get("md5Checksum", ""),
        }
        if (
            record["size"] <= 0
            or not re.fullmatch(r"[0-9a-f]{64}", str(record["sha256"]).lower())
            or not re.fullmatch(r"[0-9a-f]{32}", str(record["md5"]).lower())
        ):
            print("[Mugiwara4iOS] Drive Metal CAS checkpoint metadata is incomplete; ignoring it.", flush=True)
            return 0

        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # Use the same parallel, range-checked Drive downloader as the RomFS restore.
            from prepare_mugiwara_actions import download_drive_file
            download_drive_file(
                self.drive,
                self.credentials,
                record,
                self.cache_path,
                parallel_workers=4,
            )
            check = sqlite3.connect(
                self.cache_path.as_uri() + "?mode=ro",
                uri=True,
                timeout=120,
            )
            try:
                verdict = check.execute("PRAGMA quick_check(1)").fetchone()
            finally:
                check.close()
            if not verdict or verdict[0] != "ok":
                raise RuntimeError(f"SQLite quick_check failed: {verdict!r}")
            size = self.cache_path.stat().st_size
            print(
                f"[Mugiwara4iOS] Metal CAS checkpoint restored and SQLite-verified: {size:,} bytes.",
                flush=True,
            )
            return size
        except Exception as exc:
            self.cache_path.unlink(missing_ok=True)
            for suffix in ("-wal", "-shm", "-journal"):
                Path(str(self.cache_path) + suffix).unlink(missing_ok=True)
            print(
                f"::warning::Metal CAS checkpoint could not be restored; rebuilding this cache: {exc}",
                flush=True,
            )
            return 0

    def _snapshot(self):
        if not self.cache_path.is_file() or self.cache_path.stat().st_size < 4096:
            return None
        snapshot = self.cache_path.with_name("cas.checkpoint.db")
        snapshot.unlink(missing_ok=True)
        source = sqlite3.connect(
            self.cache_path.as_uri() + "?mode=ro",
            uri=True,
            timeout=120,
        )
        target = sqlite3.connect(str(snapshot), timeout=120)
        try:
            source.backup(target, pages=4096, sleep=0.05)
            verdict = target.execute("PRAGMA quick_check(1)").fetchone()
            if not verdict or verdict[0] != "ok":
                raise RuntimeError(f"SQLite checkpoint snapshot is inconsistent: {verdict!r}")
        finally:
            target.close()
            source.close()
        return snapshot

    def _upload(self, snapshot: Path):
        from googleapiclient.http import MediaFileUpload

        size = snapshot.stat().st_size
        sha = self._digest(snapshot, "sha256")
        md5 = self._digest(snapshot, "md5")
        properties = dict(self.identity, sha256=sha)
        media = MediaFileUpload(
            str(snapshot),
            mimetype="application/octet-stream",
            chunksize=self.UPLOAD_CHUNK,
            resumable=True,
        )
        fields = "id,name,size,md5Checksum,appProperties,modifiedTime"
        if self.file_id:
            request = self.drive.files().update(
                fileId=self.file_id,
                body={"appProperties": properties},
                media_body=media,
                fields=fields,
                supportsAllDrives=True,
            )
        else:
            request = self.drive.files().create(
                body={
                    "name": self.NAME,
                    "parents": [self.folder_id],
                    "appProperties": properties,
                },
                media_body=media,
                fields=fields,
                supportsAllDrives=True,
            )

        item = None
        failures = 0
        while item is None:
            try:
                status, item = request.next_chunk(num_retries=8)
                failures = 0
                if status:
                    print(
                        f"[Mugiwara4iOS] Metal CAS checkpoint → Drive: {status.progress() * 100:.1f}%.",
                        flush=True,
                    )
            except Exception as exc:
                failures += 1
                if failures > 12:
                    raise RuntimeError(
                        f"Metal CAS checkpoint upload failed after {failures} attempts: {exc}"
                    ) from exc
                delay = min(60, 2 ** min(failures, 6))
                print(
                    f"[Mugiwara4iOS] Metal CAS checkpoint upload interrupted; "
                    f"retry {failures}/12 in {delay}s.",
                    flush=True,
                )
                time.sleep(delay)

        if int(item.get("size", -1)) != size or str(item.get("md5Checksum", "")).lower() != md5:
            raise RuntimeError("Drive returned a different size/MD5 for the Metal CAS checkpoint.")
        self.file_id = item["id"]
        print(
            f"[Mugiwara4iOS] Metal CAS checkpoint persisted: {size:,} bytes | SHA-256 {sha}.",
            flush=True,
        )

    @staticmethod
    def _digest(path: Path, algorithm: str) -> str:
        digest = hashlib.new(algorithm)
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def checkpoint(self):
        with self.lock:
            snapshot = None
            try:
                snapshot = self._snapshot()
                if snapshot is None:
                    return
                self._upload(snapshot)
            except Exception as exc:
                print(
                    f"::warning::Metal CAS checkpoint failed; the build continues and will retry: {exc}",
                    flush=True,
                )
            finally:
                if snapshot is not None:
                    snapshot.unlink(missing_ok=True)

    def _run(self):
        while not self.stop_event.wait(self.INTERVAL_SECONDS):
            self.checkpoint()

    def start(self):
        self.thread = threading.Thread(
            target=self._run,
            name="mugiwara4ios-metal-cas-checkpoint",
            daemon=True,
        )
        self.thread.start()
        print(
            "[Mugiwara4iOS] Automatic Metal cas.db checkpoint to Drive is active every "
            f"{self.INTERVAL_SECONDS // 60} minutes.",
            flush=True,
        )

    def stop(self, force=False):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join()
        if force:
            print("[Mugiwara4iOS] Saving the Metal CAS checkpoint after build failure...", flush=True)
            self.checkpoint()
