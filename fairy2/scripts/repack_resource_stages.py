#!/usr/bin/env python3
"""Fairy2iOS: trace exact G1T factory failure through guest BRK branch emulation.

Reuses 44995690307 + verified 6GiB root repacker and unchanged 19,210 shaders.
Offline-patches *only* eleven verified ARM64 conditional branches and replaces
these branches with BRK #0xF202. On iOS a per-game host hook records and emulates
the exact original branch predicate/PC without touching the original resources.
This is a diagnostic candidate, NOT a claimed gameplay fix.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import repack_full_resource_va as base

TRACE_SITES = (
    (0x612120, 'a0050054', 0x6121d4, 'eq',     'header-validation-failed'),
    (0x612160, 'c00300b4', 0x6121d8, 'cbz0',   'g1t-object-allocation-failed'),
    (0x612278, 'e1f9ff54', 0x6121b4, 'ne',     'texture-header-short-read'),
    (0x612428, '60ecff54', 0x6121b4, 'eq',     'texture-descriptor-creation-failed'),
    (0x61244c, 'a11b0054', 0x6127c0, 'ne',     'pixel-data-upload-success'),
    (0x6125f0, '20deffb4', 0x6121b4, 'cbz0',   'texture-instance-allocation-failed'),
    (0x612798, 'e8d0ff34', 0x6121b4, 'cbzw8',  'pixel-upload-failed'),
    (0x6127b8, 'e0cfff54', 0x6121b4, 'eq',     'texture-finalization-failed'),
    (0x1dc3b58, '200200b4', 0x1dc3b9c, 'cbz0','g1t-parser-returned-null'),
    (0x1dc3b88, 'e00000b4', 0x1dc3ba4, 'cbz0','resource-wrapper-allocation-failed'),
    (0xc1098c,  'd90100b4', 0xc109c4, 'cbz25','resource-factory-returned-null'),
)
BRK_WORD = 0xD43E4040
BRK = BRK_WORD.to_bytes(4, 'little')


def verify_encoded_branch(site: int, opcode: bytes, target: int, kind: str):
    """Check the actual AArch64 B.cond / CBZ encoding and sign-extended destination."""
    word = int.from_bytes(opcode, 'little')
    imm = (word >> 5) & 0x7ffff
    if imm & 0x40000: imm -= 0x80000
    base.require(site + imm * 4 == target, f'branch target mismatched at {site:#x}')
    if kind in ('eq', 'ne'):
        base.require((word & 0xff000010) == 0x54000000 and (word & 15) == ('eq', 'ne').index(kind),
                     f'expected B.{kind} at {site:#x}')
    else:
        base.require((word & 0x7f000000) == 0x34000000 and
                     ((word >> 31) & 1) == (kind != 'cbzw8') and
                     (word & 31) == {'cbz0':0, 'cbz25':25, 'cbzw8':8}[kind],
                     f'expected {kind} at {site:#x}')

REAL_PATCH_MAIN = base.patch_main
REAL_VERIFY_MAIN = base.verify_main


def trace_guest(raw: bytes):
    """Return only exact conditional-site swaps; abort on unknown guest binary."""
    patched = bytearray(raw)
    for site, expected, target, kind, label in TRACE_SITES:
        base.require(site + 4 <= len(raw), f'{label}: guest site out of bounds')
        base.require(raw[site:site+4] == bytes.fromhex(expected),
                     f'{label}: guest opcode differs at main+0x{site:x}: {raw[site:site+4].hex()}')
        base.require(target < len(raw), f'{label}: guest branch destination out of bounds')
        verify_encoded_branch(site, bytes.fromhex(expected), target, kind)
        patched[site:site+4] = BRK
    base.require(sum(a != b for a, b in zip(raw, patched)) <= len(TRACE_SITES) * 4,
                 'unexpected guest changes')
    return bytes(patched)


def trace_patch_main(exe: Path, oldreport: dict):
    stamp = REAL_PATCH_MAIN(exe, oldreport)
    parts, raw = base.main_sections(exe)
    changed = trace_guest(raw)
    section = parts['x0']
    base.require(all(site + 4 <= section['size'] for site, *_ in TRACE_SITES),
                 'trace site not in original executable x0')
    with exe.open('r+b') as f:
        f.seek(section['offset'])
        base.require(f.read(section['size']) == section['data'], 'guest x0 modified unexpectedly')
        f.seek(section['offset'])
        f.write(changed[:section['size']])
    out_parts, out = base.main_sections(exe)
    base.require(out == changed, 'non-x0 segment changed unexpectedly')
    stamp['after_sha256'] = hashlib.sha256(out).hexdigest()
    stamp['x0_after_sha256'] = hashlib.sha256(out_parts['x0']['data']).hexdigest()
    stamp['resource_stage_traps'] = [{'site': f'main+0x{x:x}', 'target': f'main+0x{y:x}',
                                     'name': label, 'kind': kind}
                                    for x, _, y, kind, label in TRACE_SITES]
    stamp['resource_stage_trap_opcode'] = BRK.hex()
    return stamp


def trace_verify_main(exe: Path, stamp: dict):
    REAL_VERIFY_MAIN(exe, stamp)
    _, raw = base.main_sections(exe)
    for site, *_ in TRACE_SITES:
        base.require(raw[site:site+4] == BRK, f'guest BRK lost main+0x{site:x}')
    base.require(len(stamp.get('resource_stage_traps', [])) == len(TRACE_SITES),
                 'trace stage stamp missing')


def host_trace_source():
    """iOS-safe signal hook: all guest patching happened OFFLINE before signing.

    No mprotect, no JIT entitlement, no in-process code modification. Events
    are stored in a lock-free ring and printed if the actual guest abort fires.
    """
    kinds = {'eq': 0, 'ne': 1, 'cbz0': 2, 'cbz25': 3, 'cbzw8': 4}
    rows = '\n'.join('  {%#xULL, %#xULL, %d, "%s"},' % (at, target, kinds[kind], label)
                     for at, _, target, kind, label in TRACE_SITES)
    return r'''
/* FAIRY2 G1T STAGE TRACE: Branch-for-branch equivalent; only this per-game host.
 * The 11 original branch opcodes were replaced OFFLINE with BRK #0xF202,
 * verified by SHA and re-signed in the framework IPA. No runtime patching. */
struct fairy2_stage_spec { uint64_t off, target; unsigned kind; const char *label; };
static const struct fairy2_stage_spec fairy2_stage_specs[] = {
''' + rows + r'''
};
#define FAIRY2_STAGE_COUNT (sizeof fairy2_stage_specs / sizeof fairy2_stage_specs[0])
struct fairy2_stage_event {
  unsigned seq, slot, taken;
  uint64_t x0, x8, x25, x27, lr, cpsr;
};
static struct fairy2_stage_event fairy2_stage_events[256];
static _Atomic unsigned fairy2_stage_sequence;
static int fairy2_stage_trap(ucontext_t *uc) {
  uint64_t pc = uc->uc_mcontext->__ss.__pc;
  module_t *m = module_of((void *)(uintptr_t)pc);
  if (!m || strcmp(m->name, "main")) return 0;
  uint64_t off = pc - (uint64_t)(uintptr_t)m->base;
  for (unsigned i = 0; i < FAIRY2_STAGE_COUNT; ++i) {
    const struct fairy2_stage_spec *s = &fairy2_stage_specs[i];
    if (off != s->off) continue;
    if (*(volatile uint32_t *)(uintptr_t)pc != 0xD43E4040U) return 0;
    uint64_t x0 = uc->uc_mcontext->__ss.__x[0], x8 = uc->uc_mcontext->__ss.__x[8];
    uint64_t x25 = uc->uc_mcontext->__ss.__x[25], x27 = uc->uc_mcontext->__ss.__x[27];
    uint64_t cpsr = uc->uc_mcontext->__ss.__cpsr;
    unsigned z = (unsigned)((cpsr >> 30) & 1), taken = 0;
    switch (s->kind) {
      case 0: taken = z; break;
      case 1: taken = !z; break;
      case 2: taken = (x0 == 0); break;
      case 3: taken = (x25 == 0); break;
      case 4: taken = ((uint32_t)x8 == 0); break;
      default: return 0;
    }
    unsigned seq = __atomic_fetch_add(&fairy2_stage_sequence, 1, __ATOMIC_RELAXED);
    struct fairy2_stage_event *e = &fairy2_stage_events[seq & 255];
    e->seq = seq;
    e->slot = i; e->taken = taken;
    e->x0 = x0; e->x8 = x8; e->x25 = x25; e->x27 = x27;
    e->lr = uc->uc_mcontext->__ss.__lr; e->cpsr = cpsr;
    uc->uc_mcontext->__ss.__pc = (uint64_t)(uintptr_t)m->base +
       (taken ? s->target : s->off + 4);
    return 1;
  }
  return 0;
}
static void fairy2_stage_dump(void) {
  unsigned last = __atomic_load_n(&fairy2_stage_sequence, __ATOMIC_RELAXED);
  if (!last) return;
  unsigned first = last > 128 ? last - 128 : 0;
  char buf[448];
  int k = snprintf(buf, sizeof buf,
      "[dm] FAIRY2_G1T_TRACE last %u of %u branch decisions preceding fatal trap\n",
      last - first, last);
  if (k > 0) write(2, buf, (size_t)k);
  for (unsigned n = first; n < last; ++n) {
    const struct fairy2_stage_event *e = &fairy2_stage_events[n & 255];
    if (e->seq != n || e->slot >= FAIRY2_STAGE_COUNT) continue;
    k = snprintf(buf, sizeof buf,
       "[dm] FAIRY2_G1T_TRACE #%u main+0x%llx %s branch=%s x0=%#llx x8=%#llx x25=%#llx x27=%#llx lr=%#llx nzcv=%#llx\n",
       n, (unsigned long long)fairy2_stage_specs[e->slot].off,
       fairy2_stage_specs[e->slot].label, e->taken ? "taken" : "not-taken",
       (unsigned long long)e->x0, (unsigned long long)e->x8,
       (unsigned long long)e->x25, (unsigned long long)e->x27,
       (unsigned long long)e->lr, (unsigned long long)((e->cpsr >> 28) & 15));
    if (k > 0 && (size_t)k < sizeof buf) write(2, buf, (size_t)k);
  }
}
'''


def patch_host_crash(path: Path):
    src = path.read_text()
    probe_anchor = 'static void on_crash(int sig, siginfo_t *si, void *uc_) {'
    hook_anchor = '    if (sig == SIGTRAP && g_trap_hook && g_trap_hook(uc)) return;'
    base.require(src.count(probe_anchor) == 1 and src.count(hook_anchor) == 1,
                 'pinned NXNative crash trap anchors changed')
    base.require('FAIRY2 G1T STAGE TRACE' not in src, 'host already instrumented')
    src = src.replace(probe_anchor, host_trace_source() + '\n' + probe_anchor, 1)
    src = src.replace(hook_anchor,
                      '    if (sig == SIGTRAP && fairy2_stage_trap(uc)) return;\n'
                      '    if (sig == SIGTRAP) fairy2_stage_dump();\n' + hook_anchor, 1)
    path.write_text(src)
    base.require(src.count('FAIRY2 G1T STAGE TRACE') == 1 and
                 src.count('fairy2_stage_dump();') == 1,
                 'missing iOS host instrumentation')


def make(source: Path, report: Path, repo: Path, out: Path):
    base.require((repo/'.upstream-ref').read_text().strip() == base.hook.ENGINE_PIN,
                 'wrong pinned engine')
    patch_host_crash(repo/'engine/dm/host/crash.c')
    base.patch_main = trace_patch_main
    base.verify_main = trace_verify_main
    base.OUT_NAME = 'Fairy2iOS-FairyTail2-G1T-BranchTrace.ipa'
    result = base.make(source, report, repo, out)
    result.update({'resource_stage_trace': True,
                   'branch_emulation': 'iOS SIGTRAP exact original conditional semantics',
                   'branch_trace_sites': len(TRACE_SITES),
                   'g1t_header_sha256': '558ada8c563fe44fa18d894d01f39e8b1a230b26ad1bcd0782743797f815e494',
                   'not_a_gameplay_fix': True,
                   'reason': 'determine the precise branch returning NULL for G1T 0xfb9ebd24'})
    (out/'g1t-branchtrace-report.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--source-ipa', required=True, type=Path)
    p.add_argument('--source-report', required=True, type=Path)
    p.add_argument('--repo', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a=p.parse_args()
    make(a.source_ipa, a.source_report, a.repo.resolve(), a.output)
