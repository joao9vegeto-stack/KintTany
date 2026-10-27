#!/usr/bin/env python3
"""Regression tests for Ascension RSX/SPURS handoff and SPU stack recovery."""

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
#define pthread_attr_setstacksize test_attr_setstacksize
#define pthread_create test_pthread_create
#define pthread_detach test_pthread_detach
static size_t requested_stack;
unsigned test_create_calls;
unsigned test_chosen_stack_mib;
static int test_attr_setstacksize(pthread_attr_t* attr, size_t size)
{ (void)attr; requested_stack = size; return 0; }
static int test_pthread_create(pthread_t* thread, const pthread_attr_t* attr,
                               void* (*start)(void*), void* arg)
{
    (void)thread; (void)attr; (void)start; (void)arg;
    ++test_create_calls;
    if (requested_stack > (32u << 20)) return EAGAIN;
    test_chosen_stack_mib = (unsigned)(requested_stack >> 20);
    return 0;
}
static int test_pthread_detach(pthread_t thread) { (void)thread; return 0; }
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


SPURS_REPORT_FIXTURE = r'''#include <stdint.h>
typedef uint32_t u32;
typedef uint8_t u8;
typedef uint64_t u64;
#define MAX_SPURS_INST 3
#define SPURS_MAX_WID 32
#define SPURS_WKL_CURCONT 0x30
struct SpursInst { volatile u32 ea; u8 idle[SPURS_MAX_WID]; int wake; };
static struct SpursInst s_inst[MAX_SPURS_INST];
static u8* vm_base;
static volatile u64 s_asc_pm_found, s_asc_pm_missing, s_asc_last_dispatch_wid;
static unsigned s_wake_calls;
static void WakeAllConditionVariable(int* wake);
void cellSpursResetAscensionMetrics(void)
{
    __atomic_store_n(&s_asc_last_dispatch_wid, UINT64_MAX, __ATOMIC_RELAXED);
}
void cellSpursCopyAscensionMetrics(u64 out[8]) {
    if (!out) return;
    out[0]=__atomic_load_n(&s_asc_pm_found,__ATOMIC_RELAXED);
    out[1]=__atomic_load_n(&s_asc_pm_missing,__ATOMIC_RELAXED);
    out[2]=__atomic_load_n(&s_asc_pm_missing,__ATOMIC_RELAXED);
    out[3]=__atomic_load_n(&s_asc_pm_found,__ATOMIC_RELAXED);
    out[4]=__atomic_load_n(&s_asc_pm_found,__ATOMIC_RELAXED);
    out[5]=__atomic_load_n(&s_asc_pm_found,__ATOMIC_RELAXED);
    out[6]=__atomic_load_n(&s_asc_pm_missing,__ATOMIC_RELAXED);
    out[7]=__atomic_load_n(&s_asc_last_dispatch_wid,__ATOMIC_RELAXED);
}
static void wkl_curcont_set(u32 ea, u32 wid, u8 v) __attribute__((unused));
static void wkl_curcont_set(u32 ea, u32 wid, u8 v)
{ if (wid < 16) vm_base[ea + SPURS_WKL_CURCONT + wid] = v; }
static void WakeAllConditionVariable(int* wake)
{ (void)wake; ++s_wake_calls; }
void test_spurs_init(void)
{
    for (u32 i = 0; i < SPURS_MAX_WID; ++i) {
        s_inst[0].idle[i] = 3;
        s_inst[1].idle[i] = 3;
        s_inst[2].idle[i] = 3;
    }
    s_inst[0].ea = 1;
    s_inst[1].ea = 0;
    s_inst[2].ea = 2;
}
int test_spurs_idle_state(void)
{
    for (u32 i = 0; i < SPURS_MAX_WID; ++i)
        if (s_inst[0].idle[i] || s_inst[2].idle[i] || s_inst[1].idle[i] != 3)
            return 0;
    return 1;
}
unsigned test_spurs_wake_calls(void) { return s_wake_calls; }
'''


GCM_REPORT_FIXTURE = r'''#include <stdint.h>
static struct { uint32_t timestamp, value; } s_report_data[2];
static uint32_t idx, ts = 7, val = 9;
void test_gcm_report(void)
{
                            s_report_data[idx].timestamp = ts;
                            s_report_data[idx].value = val;
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
        "stack_sizes[4] = {32u << 20, 16u << 20, 64u << 20, 256u << 20}",
        "spu_workload_reset_ascension_stack_metrics",
        "spu_workload_copy_ascension_stack_metrics",
        "s_asc_worker_stack_metrics[16]",
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
            raise SystemExit("M8.04 SPU stack recovery patch is not idempotent")

    spurs_source = upstream / "libs/spurs/cellSpurs.c"
    spurs_text = spurs_source.read_text(errors="replace")
    gcm_text = source.read_text(errors="replace")
    wake_required = (
        patch_ps3recomp_spurs2.SPURS_REPORT_WAKE_MARKER,
        "void spurs_external_event(void)",
        "s_asc_gpu_report_events",
        "s_asc_gpu_report_wakes",
        "out[8]=__atomic_load_n(&s_asc_gpu_report_events",
        "out[9]=__atomic_load_n(&s_asc_gpu_report_wakes",
    )
    wake_missing = [token for token in wake_required if token not in spurs_text]
    if wake_missing or "spurs_external_event();" not in gcm_text:
        raise SystemExit(f"M8.04 patched upstream is missing SPURS report wake: {wake_missing}")
    with tempfile.TemporaryDirectory(prefix="m804-report-idempotence-") as temp:
        fixture_upstream = pathlib.Path(temp)
        spurs_target = fixture_upstream / "libs/spurs/cellSpurs.c"
        gcm_target = fixture_upstream / "libs/video/cellGcmSys.c"
        spurs_target.parent.mkdir(parents=True)
        gcm_target.parent.mkdir(parents=True)
        shutil.copy2(spurs_source, spurs_target)
        shutil.copy2(source, gcm_target)
        before = (spurs_target.read_bytes(), gcm_target.read_bytes())
        patch_ps3recomp_spurs2.apply_ascension_spurs_report_wake(fixture_upstream)
        if before != (spurs_target.read_bytes(), gcm_target.read_bytes()):
            raise SystemExit("M8.04 SPURS report-wake patch is not idempotent")


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
        harness = root / "stack-main.c"
        harness.write_text(r'''#include <errno.h>
#include <stdint.h>
extern int dispatch(void);
extern unsigned test_create_calls, test_chosen_stack_mib;
extern void spu_workload_reset_ascension_stack_metrics(void);
extern void spu_workload_copy_ascension_stack_metrics(unsigned long long out[17]);
int main(void)
{
    unsigned long long m[17] = {0};
    spu_workload_reset_ascension_stack_metrics();
    if (!dispatch() || test_create_calls != 1 || test_chosen_stack_mib != 32)
        return 1;
    spu_workload_copy_ascension_stack_metrics(m);
    if (m[0] != 1 || m[1] != 1 || m[2] != 1 ||
        m[3] || m[4] || m[5] || m[6] || m[7] || m[8] || m[9] ||
        m[10] || m[11] || m[12] || m[13] || m[14] || m[15] || m[16]) return 2;
    return 0;
}
''')
        output = root / "m804-stack-recovery-test"
        subprocess.run(
            [compiler, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
             str(source), str(harness), "-o", str(output)],
            check=True,
        )
        subprocess.run([str(output)], check=True)


def check_spurs_report_wake() -> None:
    compiler = shutil.which("cc") or shutil.which("clang")
    if not compiler:
        raise SystemExit("M8.04 report-wake behavior test requires cc or clang")
    with tempfile.TemporaryDirectory(prefix="m804-report-wake-") as temp:
        root = pathlib.Path(temp)
        upstream = root / "upstream"
        spurs = upstream / "libs/spurs/cellSpurs.c"
        gcm = upstream / "libs/video/cellGcmSys.c"
        spurs.parent.mkdir(parents=True)
        gcm.parent.mkdir(parents=True)
        spurs.write_text(SPURS_REPORT_FIXTURE)
        gcm.write_text(GCM_REPORT_FIXTURE)
        patch_ps3recomp_spurs2.apply_ascension_spurs_report_wake(upstream)
        before = (spurs.read_bytes(), gcm.read_bytes())
        patch_ps3recomp_spurs2.apply_ascension_spurs_report_wake(upstream)
        if before != (spurs.read_bytes(), gcm.read_bytes()):
            raise SystemExit("M8.04 SPURS GPU-report wake patch is not idempotent")

        harness = root / "report-wake-main.c"
        harness.write_text(r'''#include <stdint.h>
extern void cellSpursResetAscensionMetrics(void);
extern void cellSpursCopyAscensionMetrics(uint64_t out[10]);
extern void test_spurs_init(void);
extern void test_gcm_report(void);
extern int test_spurs_idle_state(void);
extern unsigned test_spurs_wake_calls(void);
int main(void)
{
    uint64_t metrics[10] = {0};
    cellSpursResetAscensionMetrics();
    test_spurs_init();
    test_gcm_report();
    cellSpursCopyAscensionMetrics(metrics);
    if (!test_spurs_idle_state() || test_spurs_wake_calls() != 2 ||
        metrics[8] != 1 || metrics[9] != 2) return 1;
    return 0;
}
''')
        output = root / "m804-report-wake-test"
        subprocess.run(
            [compiler, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
             str(spurs), str(gcm), str(harness), "-o", str(output)],
            check=True,
        )
        subprocess.run([str(output)], check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=pathlib.Path)
    args = parser.parse_args()
    if args.upstream:
        check_upstream_idempotence(args.upstream.resolve())
    check_behavior()
    check_stack_patch_syntax()
    check_spurs_report_wake()


if __name__ == "__main__":
    main()
