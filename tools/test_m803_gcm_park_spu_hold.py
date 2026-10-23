#!/usr/bin/env python3
"""Regression test for the bounded Ascension GCM park/SPU handoff."""

from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import tempfile

import patch_ps3recomp_spurs2


STACK_FIXTURE = r'''#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdlib.h>
static void spu_async_run(void *p) { (void)p; }
typedef unsigned long DWORD;
#define WINAPI
#ifdef _WIN32
static DWORD WINAPI spu_async_thread(void* p) { spu_async_run(p); return 0; }
#else
static void* spu_async_thread(void* p) { spu_async_run(p); return NULL; }
#endif

int dispatch(void)
{
    void *j = NULL;
    pthread_t th;
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    int prc = EINVAL;
    if (pthread_attr_setstacksize(&attr, 256u << 20) == 0)
        prc = pthread_create(&th, &attr, spu_async_thread, j);
    pthread_attr_destroy(&attr);
    if (prc != 0)
        prc = pthread_create(&th, NULL, spu_async_thread, j);
    if (prc != 0) return 0;
    pthread_detach(th);
    return 1;
}
'''


FIXTURE = r'''#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef unsigned int u32;
static u32 s_fifo_getoff;   /* tentative: defined below */
extern long active_tasks;
extern unsigned long long now_ms;

int walk_jump(u32 target, u32 put)
{
    u32 w = 1;
    const char *why = "run";
    (void)put;
    for (int pass = 0; pass < 1; ++pass) {
        if ((w & 3) == 1) {
            { u32 tgt = target;
              if (tgt == s_fifo_getoff) {
                  why = "parked";
                  break;
              }
              s_fifo_getoff = tgt; }
            continue;
        }
        if ((w & 3) == 2) {                    /* CALL: offset | 2 */ return -2; }
    }
    if (why && (strcmp(why, "parked") == 0 || strcmp(why, "sema-acquire") == 0 ||
                  strcmp(why, "report-hold") == 0)) { return 2; }
    return s_fifo_getoff == target ? 0 : -1;
}

int main(void)
{
    unsigned long long metrics[3] = {0};
    setenv("GCM_PARK_SPU_HOLD_MS", "50", 1);
    cellGcmResetAscensionParkHoldMetrics();

    s_fifo_getoff = 16;
    if (walk_jump(16, 32) != 2) return 10; /* the title's self-JUMP park */
    active_tasks = 4; now_ms = 1000;
    if (walk_jump(32, 32) != 2 || s_fifo_getoff != 16) return 11;
    active_tasks = 0; now_ms = 1010;
    if (walk_jump(32, 32) != 0 || s_fifo_getoff != 32) return 12;

    if (walk_jump(32, 40) != 2) return 13;
    active_tasks = 1; now_ms = 2000;
    if (walk_jump(40, 40) != 2 || s_fifo_getoff != 32) return 14;
    now_ms = 2051;
    if (walk_jump(40, 40) != 0 || s_fifo_getoff != 40) return 15;

    cellGcmCopyAscensionParkHoldMetrics(metrics);
    if (metrics[0] != 2 || metrics[1] != 1 || metrics[2] != 1) {
        fprintf(stderr, "unexpected M8.03 metrics: %llu/%llu/%llu\n",
                metrics[0], metrics[1], metrics[2]);
        return 16;
    }
    s_fifo_getoff = 48;
    if (walk_jump(48, 64) != 2) return 17;
    cellGcmResetAscensionParkHoldMetrics();
    active_tasks = 4; now_ms = 3000;
    if (walk_jump(64, 64) != 0 || s_fifo_getoff != 64) return 18;
    cellGcmCopyAscensionParkHoldMetrics(metrics);
    if (metrics[0] || metrics[1] || metrics[2]) return 19;
    puts("M8.03 GCM park/SPU hold: pause, completion release, timeout and reset PASS");
    return 0;
}
'''


def check_upstream_idempotence(upstream: pathlib.Path) -> None:
    source = upstream / "libs/video/cellGcmSys.c"
    text = source.read_text(errors="replace")
    required = (
        patch_ps3recomp_spurs2.PARK_SPU_HOLD_MARKER,
        'getenv("GCM_PARK_SPU_HOLD_MS")',
        "spu_taskset_tasks_running()",
        "s_asc_park_spu_hold_since",
        'why = "spu-hold"',
        'strcmp(why, "spu-hold") == 0',
        "cellGcmResetAscensionParkHoldMetrics",
        "cellGcmCopyAscensionParkHoldMetrics",
    )
    missing = [token for token in required if token not in text]
    if missing:
        raise SystemExit(f"M8.03 patched upstream is missing: {missing}")
    with tempfile.TemporaryDirectory(prefix="m803-idempotence-") as temp:
        fixture_upstream = pathlib.Path(temp)
        target = fixture_upstream / "libs/video/cellGcmSys.c"
        target.parent.mkdir(parents=True)
        shutil.copy2(source, target)
        before = target.read_bytes()
        patch_ps3recomp_spurs2.apply_ascension_gcm_park_spu_hold(fixture_upstream)
        if target.read_bytes() != before:
            raise SystemExit("M8.03 GCM park/SPU patch is not idempotent")

    stack_source = upstream / "runtime/spu/spu_workload.c"
    stack_text = stack_source.read_text(errors="replace")
    stack_required = (
        patch_ps3recomp_spurs2.STACK_METRICS_MARKER,
        "pthread_attr_setstacksize(&attr, 256u << 20)",
        "spu_workload_reset_ascension_stack_metrics",
        "spu_workload_copy_ascension_stack_metrics",
        "s_asc_worker_stack_metrics[4]",
    )
    stack_missing = [token for token in stack_required if token not in stack_text]
    if stack_missing:
        raise SystemExit(f"M8.03 patched upstream is missing stack telemetry: {stack_missing}")
    with tempfile.TemporaryDirectory(prefix="m803-stack-idempotence-") as temp:
        fixture_upstream = pathlib.Path(temp)
        target = fixture_upstream / "runtime/spu/spu_workload.c"
        target.parent.mkdir(parents=True)
        shutil.copy2(stack_source, target)
        before = target.read_bytes()
        patch_ps3recomp_spurs2.apply_ascension_spu_stack_metrics(fixture_upstream)
        if target.read_bytes() != before:
            raise SystemExit("M8.03 SPU stack metrics patch is not idempotent")


def check_behavior() -> None:
    compiler = shutil.which("cc") or shutil.which("clang")
    if not compiler:
        raise SystemExit("M8.03 behavior test requires cc or clang")
    with tempfile.TemporaryDirectory(prefix="m803-park-hold-") as temp:
        root = pathlib.Path(temp)
        upstream = root / "upstream"
        source = upstream / "libs/video/cellGcmSys.c"
        source.parent.mkdir(parents=True)
        source.write_text(FIXTURE)
        patch_ps3recomp_spurs2.apply_ascension_gcm_park_spu_hold(upstream)
        stubs = root / "m803-park-hold-stubs.c"
        stubs.write_text(
            "long active_tasks;\n"
            "unsigned long long now_ms;\n"
            "long spu_taskset_tasks_running(void) { return active_tasks; }\n"
            "unsigned long long ps3_ms_now(void) { return now_ms; }\n"
        )
        output = root / "m803-park-hold-test"
        subprocess.run(
            [compiler, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
             str(source), str(stubs), "-o", str(output)],
            check=True,
        )
        subprocess.run([str(output)], check=True)


def check_stack_patch_syntax() -> None:
    compiler = shutil.which("cc") or shutil.which("clang")
    if not compiler:
        raise SystemExit("M8.03 stack patch syntax test requires cc or clang")
    with tempfile.TemporaryDirectory(prefix="m803-stack-patch-") as temp:
        root = pathlib.Path(temp)
        upstream = root / "upstream"
        source = upstream / "runtime/spu/spu_workload.c"
        source.parent.mkdir(parents=True)
        source.write_text(STACK_FIXTURE)
        patch_ps3recomp_spurs2.apply_ascension_spu_stack_metrics(upstream)
        subprocess.run(
            [compiler, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
             "-fsyntax-only", str(source)],
            check=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=pathlib.Path)
    args = parser.parse_args()
    if args.upstream:
        check_upstream_idempotence(args.upstream.resolve())
    check_behavior()
    check_stack_patch_syntax()


if __name__ == "__main__":
    main()
