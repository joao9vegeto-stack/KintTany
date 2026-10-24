#!/usr/bin/env python3
"""Host-test production native LFQueue with guest-BE memory and real H8 protocol."""
import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

def body(s,tag):
    assert s.count(tag)==1,(tag,s.count(tag))
    a=s.index(tag);b=s.index("{",a+len(tag));d=0
    for i in range(b,len(s)):
        if s[i]=="{":d+=1
        elif s[i]=="}":d-=1
        if i>=b and d==0:return s[a:i+1]
    raise ValueError(tag)

PFX=r"""
#include <stdint.h>
#include <stdio.h>
#include <assert.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t u32; typedef uint64_t u64; typedef uint16_t u16;
typedef int32_t s32; typedef int16_t s16; typedef uint8_t u8;
#define CELL_OK 0
#define CELL_SPURS_TASK_ERROR_NULL_POINTER (-1)
#define CELL_SPURS_TASK_ERROR_INVAL (-2)
#define CELL_SPURS_TASK_ERROR_FAULT (-3)
#define CELL_SPURS_TASK_ERROR_ALIGN (-4)
#define CELL_SPURS_TASK_ERROR_AGAIN (-5)
#define CELL_SPURS_TASK_ERROR_BUSY (-7)
#define CELL_SPURS_TASK_ERROR_PERM (-6)
#define CELL_SPURS_TASK_ERROR_NOMEM (-8)
typedef struct { u32 dummy; } CellSpursEventFlag;
int edge_inflate(uint8_t*dst,uint32_t cap,const uint8_t*src,uint32_t len) {
 (void)dst;(void)cap;(void)src;(void)len;
 return -1; /* Unused by LFQueue-only host test. */
}
s32 cellSpursEventFlagSet(CellSpursEventFlag*flag,u16 bits) {
 (void)flag;(void)bits;return CELL_OK;
}
static uint8_t guest[0x10000];
uint8_t *vm_base=guest;
static int locked, line_wakes, waiter_wakes;
static int spurs_guest_range_valid(u32 a,u32 n){
 return a<sizeof guest && n<=sizeof guest-a;
}
static u16 vm_read16(u32 a){return (u16)((u16)guest[a]<<8 | guest[a+1]);}
static u32 vm_read32(u32 a){
 return ((u32)guest[a]<<24)|((u32)guest[a+1]<<16)|((u32)guest[a+2]<<8)|guest[a+3];
}
static u64 vm_read64(u32 a){return ((u64)vm_read32(a)<<32)|vm_read32(a+4);}
static void vm_write8(u32 a,uint8_t v){guest[a]=v;}
static void vm_write16(u32 a,u16 v){guest[a]=(uint8_t)(v>>8);guest[a+1]=(uint8_t)v;}
static void vm_write32(u32 a,u32 v){guest[a]=v>>24;guest[a+1]=v>>16;guest[a+2]=v>>8;guest[a+3]=v;}
static void vm_write64(u32 a,u64 v){vm_write32(a,v>>32);vm_write32(a+4,v);}
static void spu_lockline_lock(void){assert(!locked);locked=1;}
static void spu_lockline_unlock(void){assert(locked);locked=0;}
static void ef_w16(u32 a,u16 v){assert(locked);vm_write16(a,v);}
static void ef_line_end(u32 a){(void)a;spu_lockline_unlock();}
static void Sleep(int ms){(void)ms;}
static u32 spurs_signal_waiter(u32 ea,u32 waiter){
 (void)ea;(void)waiter;waiter_wakes++;return 1;
}
static int spu_signal_parked_on_line(u32 line){
 (void)line;line_wakes++;return 1;
}
"""
SUFFIX=r"""
int main(void){
 const u32 q=0x200,buf=0x400,src=0x800;
 for(u32 i=0;i<16;i++)guest[src+i]=(uint8_t)(0x40+i);
 assert(_cellSpursLFQueueInitialize(0x100,q,buf,16,4,LFQ_DIR_PPU2SPU)==CELL_OK);
 assert(vm_read32(q+LFQ_DEPTH)==4 && vm_read32(q+LFQ_SIZE)==16);
 assert(vm_read32(q+0x04)==0);
 assert(_cellSpursLFQueuePushBody(q,src,0)==CELL_OK);
 assert(vm_read32(q+0x04)==1);
 assert(memcmp(guest+buf,guest+src,16)==0 && line_wakes==1 && !locked);
 assert(_cellSpursLFQueuePushBody(q,src,0)==CELL_OK);
 assert(vm_read32(q+0x04)==2);
 assert(_cellSpursLFQueuePushBody(q,src,0)==CELL_OK);
 assert(_cellSpursLFQueuePushBody(q,src,0)==CELL_OK);
 assert(_cellSpursLFQueuePushBody(q,src,0)==CELL_SPURS_TASK_ERROR_BUSY);
 assert(_cellSpursLFQueuePushBody(q,src+1,0)==CELL_SPURS_TASK_ERROR_ALIGN);
 assert(_cellSpursLFQueueInitialize(0x100,0x1000,0x1200,16,4,LFQ_DIR_ANY2ANY)==CELL_OK);
 assert(vm_read32(0x1000+LFQ_DIRECTION)==LFQ_DIR_ANY2ANY);
 assert((vm_read64(0x1000+LFQ_BUFFER)&1u)==1u);
 assert(vm_read16(0x1000+LFQ_PUSH2)==0xffffu);
 assert(vm_read16(0x1000+LFQ_PUSH1_H8)==0u);
 assert(_cellSpursLFQueuePushBody(0x1000,src,0)==CELL_OK);
 assert(vm_read16(0x1000+LFQ_PUSH1_H8)==1u);
 assert(!locked && s_asc_lfq_metrics[2]==5 && s_asc_lfq_metrics[3]==80);
 printf("[PASS] M8.10 native LFQueue: PPU2SPU W1, ANY2ANY H8, payload, saturation, no double-lock\n");
 return 0;
}
"""
def main():
 p=argparse.ArgumentParser();p.add_argument("--upstream",type=Path,required=True)
 a=p.parse_args()
 s=(a.upstream/"libs/spurs/cellSpurs.c").read_text()
 assert s.count("ASCENSION_M810_NATIVE_LFQUEUE_V1")==1
 assert "ASCENSION_M772_EDGE_ZLIB_HLE_V2" in s
 assert "ASCENSION_M772_LFQUEUE_SDK_LAYOUT_V1" in s
 assert "edge_inflate(" in s and "cellSpursEventFlagSet" in s
 start=s.index("#define LFQ_DIR_PPU2SPU")
 end=s.index("static u32 s_taskset_registry",start)
 source=s[start:end]
 funcs="\n".join(body(s,x) for x in (
   "s32 _cellSpursLFQueueInitialize(",
   "static s32 lfq_get_push_pointer(",
   "static s32 lfq_complete_push_pointer(",
   "static s32 asc_lfq_ppu2spu_push(",
   "s32 _cellSpursLFQueuePushBody("))
 cc=shutil.which("clang") or shutil.which("cc")
 assert cc
 with tempfile.TemporaryDirectory(prefix="asc-lfq-") as t:
  path=Path(t)/"host.c"; exe=Path(t)/"host"
  path.write_text(PFX+source+funcs+SUFFIX)
  subprocess.run([cc,"-std=c11","-O2","-Wall","-Wextra","-Werror",
                  str(path),"-o",str(exe)],check=True)
  subprocess.run([str(exe)],check=True)
if __name__=="__main__":main()
