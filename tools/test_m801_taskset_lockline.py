#!/usr/bin/env python3
"""Compile and stress the exact patched taskset operations against a SPU writer."""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import tempfile


def c_function(source: str, name: str) -> str:
    match = re.search(r"\b" + re.escape(name) + r"\s*\([^;]*\)\s*\{", source)
    if not match:
        raise AssertionError(f"production function not found: {name}")
    start = source.index("{", match.start())
    depth = 1
    pos = start + 1
    while depth:
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
        pos += 1
    signature_start = source.rfind("\n", 0, match.start()) + 1
    return source[signature_start:pos]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=pathlib.Path, required=True)
    args = parser.parse_args()
    root = args.upstream.resolve()
    header = (root / "libs/spurs/spurs_taskset.h").read_text()
    workload = (root / "runtime/spu/spu_workload.c").read_text()
    assert "ASCENSION_M801_TASKSET_LOCKLINE_RMW_V1" in header
    assert "ASCENSION_M801_TASKSET_LOCKLINE_RMW_V1" in workload

    functions = "\n".join(
        c_function(header, name)
        for name in ("spurs_bitset_rmw", "spurs_bitset_set", "spurs_bitset_clear")
    )
    functions += "\n" + c_function(workload, "ts_bits_clear")
    fixture = r'''#define _GNU_SOURCE
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static uint8_t guest[256];
uint8_t* vm_base = guest;
static pthread_mutex_t lockline = PTHREAD_MUTEX_INITIALIZER;
static atomic_uint notifications;
void spu_lockline_lock(void) { pthread_mutex_lock(&lockline); }
void spu_lockline_unlock(void) { pthread_mutex_unlock(&lockline); }
int spu_coh_is_reserved(uint32_t ea) { (void)ea; return 1; }
void spu_coh_notify_write(uint32_t ea) { (void)ea; atomic_fetch_add(&notifications, 1); }
static uint8_t* vm_ptr8(uint32_t ea) { return vm_base + ea; }
/* PRODUCTION_FUNCTIONS */
typedef struct {
    pthread_mutex_t mutex;
    pthread_cond_t cond;
    unsigned total, waiting, generation;
} test_barrier;
static test_barrier gate;
static int barrier_init(test_barrier* b, unsigned total) {
    memset(b, 0, sizeof(*b)); b->total = total;
    return pthread_mutex_init(&b->mutex, NULL) || pthread_cond_init(&b->cond, NULL);
}
static void barrier_wait(test_barrier* b) {
    pthread_mutex_lock(&b->mutex);
    const unsigned generation = b->generation;
    if (++b->waiting == b->total) {
        b->waiting = 0; ++b->generation;
        pthread_cond_broadcast(&b->cond);
    } else {
        while (generation == b->generation) pthread_cond_wait(&b->cond, &b->mutex);
    }
    pthread_mutex_unlock(&b->mutex);
}
static void barrier_destroy(test_barrier* b) {
    pthread_cond_destroy(&b->cond); pthread_mutex_destroy(&b->mutex);
}
enum { BITSET_EA = 16, TASKSET_BYTE_EA = 64, ROUNDS = 50000 };
static void* set_bit0(void* p) {
    (void)p;
    for (int i = 0; i < ROUNDS; ++i) {
        barrier_wait(&gate);
        spurs_bitset_set(BITSET_EA, 0);
        barrier_wait(&gate);
    }
    return NULL;
}
static void* set_bit1(void* p) {
    (void)p;
    for (int i = 0; i < ROUNDS; ++i) {
        barrier_wait(&gate);
        spurs_bitset_set(BITSET_EA, 1);
        barrier_wait(&gate);
    }
    return NULL;
}
static void spu_create_task_bit(void) {
    spu_lockline_lock();
    guest[TASKSET_BYTE_EA] |= 0x40;
    if (spu_coh_is_reserved(TASKSET_BYTE_EA))
        spu_coh_notify_write(TASKSET_BYTE_EA);
    spu_lockline_unlock();
}
static void* clear_finished_task(void* p) {
    (void)p;
    for (int i = 0; i < ROUNDS; ++i) {
        barrier_wait(&gate);
        ts_bits_clear(TASKSET_BYTE_EA, 0x80);
        barrier_wait(&gate);
    }
    return NULL;
}
static void* create_sibling_task(void* p) {
    (void)p;
    for (int i = 0; i < ROUNDS; ++i) {
        barrier_wait(&gate);
        spu_create_task_bit();
        barrier_wait(&gate);
    }
    return NULL;
}
int main(void) {
    pthread_t a, b;
    if (barrier_init(&gate, 3)) return 2;
    if (pthread_create(&a, NULL, set_bit0, NULL) ||
        pthread_create(&b, NULL, set_bit1, NULL)) return 2;
    for (int i = 0; i < ROUNDS; ++i) {
        guest[BITSET_EA] = guest[BITSET_EA+1] =
        guest[BITSET_EA+2] = guest[BITSET_EA+3] = 0;
        barrier_wait(&gate);
        barrier_wait(&gate);
        if (guest[BITSET_EA] != 0xC0) {
            fprintf(stderr, "lost concurrent SPURS signal at round %d: %02X\n",
                    i, guest[BITSET_EA]);
            return 1;
        }
    }
    pthread_join(a, NULL); pthread_join(b, NULL);
    barrier_destroy(&gate);
    guest[BITSET_EA] = guest[BITSET_EA+1] =
    guest[BITSET_EA+2] = guest[BITSET_EA+3] = 0xFF;
    spurs_bitset_clear(BITSET_EA, 0);
    if (guest[BITSET_EA] != 0x7F) {
        fprintf(stderr, "SPURS clear changed the wrong bit: %02X\n", guest[BITSET_EA]);
        return 1;
    }

    if (barrier_init(&gate, 3)) return 2;
    if (pthread_create(&a, NULL, clear_finished_task, NULL) ||
        pthread_create(&b, NULL, create_sibling_task, NULL)) return 2;
    for (int i = 0; i < ROUNDS; ++i) {
        guest[TASKSET_BYTE_EA] = 0x80;
        barrier_wait(&gate);
        barrier_wait(&gate);
        if (guest[TASKSET_BYTE_EA] != 0x40) {
            fprintf(stderr, "lost concurrent SPU-created task at round %d: %02X\n",
                    i, guest[TASKSET_BYTE_EA]);
            return 1;
        }
    }
    pthread_join(a, NULL); pthread_join(b, NULL);
    barrier_destroy(&gate);
    if (!atomic_load(&notifications)) return 1;
    puts("M8.01 lock-line regressions: 50000 concurrent signal updates and 50000 task-exit/create updates PASS");
    return 0;
}
'''
    source = fixture.replace("/* PRODUCTION_FUNCTIONS */", functions)
    with tempfile.TemporaryDirectory(prefix="m801-taskset-lockline-") as tmp:
        c_file = pathlib.Path(tmp) / "test.c"
        binary = pathlib.Path(tmp) / "test"
        c_file.write_text(source)
        subprocess.run([os.environ.get("CC", "cc"), "-std=gnu17", "-O2", "-Wall",
                        "-Wextra", "-Werror", "-pthread", str(c_file), "-o", str(binary)],
                       check=True)
        subprocess.run([str(binary)], check=True, timeout=30)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
