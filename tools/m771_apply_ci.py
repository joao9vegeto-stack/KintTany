#!/usr/bin/env python3
"""M7.71 post-stage refinement: physical frontier forensic telemetry and concise reports.
Runs after M7.70 unpacks and registers ALL 3835 handlers; no game-code modifications.
"""
import sys
from pathlib import Path

def one(s, old, new, label):
    n=s.count(old)
    if n!=1: raise RuntimeError(f'{label}: anchor count {n}, expected 1: {old[:70]!r}')
    return s.replace(old,new,1)

def main(root):
    changes={}
    name='runtime/ppu_bridge.h'
    s=(root/name).read_text()
    s=one(s, '} ar_aot_trace;\nvoid ar_trace_snapshot(ar_aot_trace *out);',
'''    /* M7.71: exact native frontier entry and handler returns, NOT first visits. */
    uint32_t m771_enters,m771_returns,m771_child_calls;
    int32_t m771_status,m771_fault,m771_child_status;
    uint64_t m771_r2_entry,m771_r2_exit,m771_lr_entry,m771_sp_entry;
    uint64_t m771_r3_entry,m771_cia_exit,m771_child_r2;
} ar_aot_trace;
void ar_trace_snapshot(ar_aot_trace *out);''',name)
    changes[name]=s
    name='runtime/ppu_bridge.c';s=(root/name).read_text()
    s=one(s,'static uint32_t aot_hash(uint32_t pc){',
'''/* Physical-entry observation only. Never patch game registers or memory. */
static uint32_t m771_enters,m771_returns,m771_child_calls,m771_inside;
static int32_t m771_status,m771_fault,m771_child_status;
static uint64_t m771_r2_entry,m771_r2_exit,m771_lr_entry,m771_sp_entry;
static uint64_t m771_r3_entry,m771_cia_exit,m771_child_r2;
static uint32_t aot_hash(uint32_t pc){''',name)
    s=one(s,' out->m768_last_hle_depth=m768_last_hle_depth;',
''' out->m768_last_hle_depth=m768_last_hle_depth;
 out->m771_enters=m771_enters;out->m771_returns=m771_returns;
 out->m771_child_calls=m771_child_calls;
 out->m771_status=m771_status;out->m771_fault=m771_fault;
 out->m771_child_status=m771_child_status;
 out->m771_r2_entry=m771_r2_entry;out->m771_r2_exit=m771_r2_exit;
 out->m771_lr_entry=m771_lr_entry;out->m771_sp_entry=m771_sp_entry;
 out->m771_r3_entry=m771_r3_entry;out->m771_cia_exit=m771_cia_exit;
 out->m771_child_r2=m771_child_r2;''',name)
    s=one(s,'    int status=fn(c);',
'''    const int is_frontier=(pc==UINT32_C(0x0052a740));
    const int is_nested=(m771_inside && pc==UINT32_C(0x0052e3f4));
    if(is_frontier){
      m771_inside++;m771_enters++;
      m771_r2_entry=c->gpr[2];m771_lr_entry=c->lr;
      m771_sp_entry=c->gpr[1];m771_r3_entry=c->gpr[3];
    }
    if(is_nested){m771_child_calls++;m771_child_r2=c->gpr[2];}
    int status=fn(c);
    if(is_nested)m771_child_status=status;
    if(is_frontier){
      m771_returns++;m771_status=status;m771_fault=fault;
      m771_r2_exit=c->gpr[2];m771_cia_exit=c->cia;
      m771_inside--;
    }''',name)
    s=one(s,'  m767_fail_pc=m767_fail_reason=m767_failed_handler_pc=0;',
'''  m767_fail_pc=m767_fail_reason=m767_failed_handler_pc=0;
  m771_enters=m771_returns=m771_child_calls=m771_inside=0;
  m771_status=m771_fault=m771_child_status=0;
  m771_r2_entry=m771_r2_exit=m771_lr_entry=m771_sp_entry=0;
  m771_r3_entry=m771_cia_exit=m771_child_r2=0;''',name)
    changes[name]=s
    # M7.73 now owns its game-first launcher and truthful runtime report in
    # ios/ARProbeApp.m. Do not mutate that UI during CI staging.
    for path,contents in changes.items(): (root/path).write_text(contents)
    print('M7.71 staged: exact native frontier entry/exit telemetry. Launcher UI is source-owned. Files:',list(changes))

if __name__=='__main__':main(Path(sys.argv[1]).resolve())
