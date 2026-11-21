#!/usr/bin/env python3
"""Memory-bounded, per-module resumable NXNative rewrite for BioiOSMutant Colab.

Only monkeypatches NXNative's in-memory Python function, not engine source.
Never changes patch_nso.py, its emitted bytes or the upstream fingerprint.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import re
import shutil
from pathlib import Path

NEEDED = (
    "patched.bin", "fixups.tsv", "gates.tsv", "sites.tsv",
    "cuts.tsv", "changed.tsv", "obs.tsv",
)
STATE = ".bio-rewrite-fingerprint.json"


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _save(path: Path, obj: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(obj, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _valid_build_tools(tmp: Path, engine_tools: Path) -> bool:
    """Validate the legacy run's exact rewriter + imported helper digests."""
    record = tmp / "build_src.sha256"
    if not record.is_file():
        return False
    rows = [line.strip().split("  ", 1) for line in record.read_text(errors="replace").splitlines()]
    if not rows or any(len(row) != 2 for row in rows):
        return False
    try:
        return all(
            re.fullmatch(r"[0-9a-f]{64}", digest) is not None
            and (engine_tools / filename).resolve().is_file()
            and _hash((engine_tools / filename).resolve()) == digest
            for digest, filename in rows
        )
    except OSError:
        return False


def _output_files(tmp: Path, name: str) -> dict[str, Path] | None:
    paths = {suffix: tmp / f"{name}.{suffix}" for suffix in NEEDED}
    if not all(p.is_file() and p.stat().st_size > 0 for p in paths.values()
               if p.name.endswith(("patched.bin", "fixups.tsv"))):
        return None
    if not all(p.is_file() for p in paths.values()):
        return None
    if not paths["fixups.tsv"].read_text(errors="replace").startswith("# PATCH_OFF\t"):
        return None
    if "# BUILD_ID\t" not in paths["fixups.tsv"].read_text(errors="replace"):
        return None
    return paths


def _checkpoint_path(tmp: Path, name: str) -> Path:
    return tmp / f".bio-done-{name}.json"


def _write_checkpoint(tmp: Path, name: str, source: Path, key: str) -> None:
    paths = _output_files(tmp, name)
    if not paths:
        raise RuntimeError(f"Successful rewrite of {name} left incomplete output files")
    digest = _hash(source)
    output_hashes = {suffix: _hash(path) for suffix, path in paths.items()}
    _save(_checkpoint_path(tmp, name), {
        "format": 1, "module": name, "fingerprint": key,
        "source_sha256": digest, "files": output_hashes,
    })
    print(f"[BioiOSMutant] Durable module rewrite checkpoint: {name}, "
          f"{len(output_hashes)} files verified.", flush=True)


def _verified_checkpoint(tmp: Path, name: str, source: Path, key: str) -> bool:
    marker = _checkpoint_path(tmp, name)
    if not marker.is_file():
        return False
    try:
        saved = json.loads(marker.read_text())
        paths = _output_files(tmp, name)
        return (
            paths is not None and saved.get("format") == 1
            and saved.get("module") == name
            and saved.get("fingerprint") == key
            and saved.get("source_sha256") == _hash(source)
            and saved.get("files") == {suffix: _hash(path)
                                      for suffix, path in paths.items()})
    except (ValueError, OSError, TypeError):
        return False


def _legacy_finished(tmp: Path, logs: Path, name: str, source: Path) -> bool:
    """Recover only a whole module from the old failed four-process rewrite.

    The original parent has no success marker. Its worker emits a final
    completion line *after* closing all seven output files, which we require,
    alongside the tool checksums and the original source file's older mtime.
    """
    paths = _output_files(tmp, name)
    log = logs / f"rewrite_{name}.log"
    if not paths or not log.is_file() or not source.is_file():
        return False
    if min(p.stat().st_mtime for p in paths.values()) < source.stat().st_mtime:
        return False
    tail = log.read_text(errors="replace")[-8192:]
    if not re.search(rf"(?m)^{re.escape(name)}\s.+\bslot_refs\s+\d+\s+gates\s+\d+", tail):
        return False
    # This source file was previously rewritten in this exact engine checkout.
    return True


def prepare_partial(tmp: Path, names: list[str], src: dict, key: str,
                    logs: Path, engine_tools: Path) -> set[str]:
    """Retain valid per-module results and discard only invalid/foreign cache."""
    saved = tmp / STATE
    state_matches = False
    legacy = False
    if tmp.is_dir():
        if saved.is_file():
            try:
                state_matches = json.loads(saved.read_text()).get("fingerprint") == key
            except (OSError, ValueError):
                pass
        else:
            # Preserve prior-run partial output only with a complete
            # signed-by-file SHA-256 inventory of its original rewriter tools.
            legacy = _valid_build_tools(tmp, engine_tools)

    if tmp.is_dir() and not (state_matches or legacy):
        print("[BioiOSMutant] Stale/unknown rewrite partial discarded; "
              "game NSPs and extracted RomFS are untouched.", flush=True)
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)

    reused = set()
    for name in names:
        valid = (state_matches and _verified_checkpoint(tmp, name, src[name], key))
        if not valid and legacy and _legacy_finished(tmp, logs, name, src[name]):
            _write_checkpoint(tmp, name, src[name], key)
            valid = True
            print(f"[BioiOSMutant] Salvaged previous completed module {name} "
                  "from the failed parallel rewrite.", flush=True)
        if valid:
            reused.add(name)
        else:
            _checkpoint_path(tmp, name).unlink(missing_ok=True)
            # An incomplete or killed worker may have left partial outputs.
            for path in tmp.glob(f"{name}.*"):
                if path.is_file():
                    path.unlink()
    _save(saved, {"format": 1, "fingerprint": key})
    print(f"[BioiOSMutant] Rewrite: {len(reused)}/{len(names)} modules "
          f"checkpoint-verified; only missing modules will run, one at a time.",
          flush=True)
    return reused


def pending(names: list[str], cached: set[str]) -> list[str]:
    return [name for name in names if name not in cached]


def save_module(tmp: Path, name: str, source: Path, key: str) -> None:
    _write_checkpoint(tmp, name, source, key)


def install(builder) -> None:
    """Install exact-anchor transforms; fail before expensive work if incompatible."""
    source = inspect.getsource(builder.rewrite)
    anchors = [
        (
            "tmp = out.with_name(out.name + '.partial'); rmtree(tmp); tmp.mkdir(parents=True); logs.mkdir(parents=True, exist_ok=True)",
            "tmp = out.with_name(out.name + '.partial'); logs.mkdir(parents=True, exist_ok=True)\n"
            "    _bio_cached = _bio_rewrite_prepare(tmp, names, src, key, logs, repo / 'dm/tools')",
        ),
        (
            "PROG.set(step=', '.join(mods) + (f' and {len(nros)} NROs' if nros else ''), done=0, total=len(names), unit='modules')",
            "PROG.set(step=', '.join(mods) + (f' and {len(nros)} NROs' if nros else ''), done=len(_bio_cached), total=len(names), unit='modules')",
        ),
        (
            "procs, logf, todo, cores = {}, {}, list(names), max(2, os.cpu_count() or 4)",
            "procs, logf, todo, cores = {}, {}, _bio_rewrite_pending(names, _bio_cached), 1",
        ),
        (
            "jobs = max(1, min(cores, 2 * cores // max(1, len(names))))",
            "jobs = 1",
        ),
        (
            "rewrite_env = dict(env, DM_REWRITE_J=str(workers if workers is not None else jobs))",
            "rewrite_env = dict(env, DM_REWRITE_J='1')",
        ),
        (
            "            time.sleep(0.2)\n    finally:   # an error or an interrupt stops the other rewrites",
            "                _bio_rewrite_saved(tmp, m, src[m], key)\n"
            "            time.sleep(0.2)\n    finally:   # an error or an interrupt stops the other rewrites",
        ),
    ]
    for old, new in anchors:
        if source.count(old) != 1:
            raise RuntimeError(f"NXNative rewrite code changed; refusing unsafe patch: {old[:90]}")
        source = source.replace(old, new, 1)
    builder.__dict__.update({
        "_bio_rewrite_prepare": prepare_partial,
        "_bio_rewrite_pending": pending,
        "_bio_rewrite_saved": save_module,
    })
    exec(compile(source, builder.rewrite.__code__.co_filename, "exec"), builder.__dict__)
    print("[BioiOSMutant] Protected rewrite: ONE module process, "
          "DM_REWRITE_J=1, SHA-256 checkpoints after each module, "
          "resuming valid previous .partial outputs.", flush=True)
