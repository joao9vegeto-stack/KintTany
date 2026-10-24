#!/usr/bin/env python3
"""Install native guest-BE CellSpursLFQueue: no emulation or synthetic jobs."""
from pathlib import Path
import argparse
MARK="ASCENSION_M810_NATIVE_LFQUEUE_V1"
SOURCE=r'''/* ASCENSION_M810_NATIVE_LFQUEUE_V1
 * Native guest LFQueue protocol from RichardFontoura/ps3recomp gowa-fixes
 * f6ab60baf37662bd712592b7ef9f66891972a5fc (MIT license).
 */
#define LFQ_DIR_PPU2SPU     2u
#define LFQ_DIR_ANY2ANY     3u
#define LFQ_POP1_H1         0x00u
#define LFQ_POP1_H3         0x04u
#define LFQ_POP1_H4         0x06u
#define LFQ_PUSH3_H5        0x08u
#define LFQ_PUSH3_H6        0x0Au
#define LFQ_PUSH1_H8        0x0Eu
#define LFQ_SIZE            0x10u
#define LFQ_DEPTH           0x14u
#define LFQ_BUFFER          0x18u
#define LFQ_BS              0x20u
#define LFQ_DIRECTION       0x24u
#define LFQ_V1              0x28u
#define LFQ_PUSH2           0x30u
#define LFQ_HS1             0x32u
#define LFQ_POP2            0x50u
#define LFQ_EA_SIGNAL       0x70u
static volatile u64 s_asc_lfq_metrics[6];
static u32 s_asc_lfq_mode_q[128], s_asc_lfq_mode_dir[128];
void cellSpursResetAscensionLFQueueMetrics(void) {
 for(unsigned i=0;i<6;i++) __atomic_store_n(&s_asc_lfq_metrics[i],0,__ATOMIC_RELAXED);
 for(unsigned i=0;i<128;i++){__atomic_store_n(&s_asc_lfq_mode_q[i],0,__ATOMIC_RELAXED);__atomic_store_n(&s_asc_lfq_mode_dir[i],0,__ATOMIC_RELAXED);}
}
void cellSpursCopyAscensionLFQueueMetrics(u64 out[6]) {
 if(!out)return;
 for(unsigned i=0;i<6;i++)out[i]=__atomic_load_n(&s_asc_lfq_metrics[i],__ATOMIC_RELAXED);
}
static u16 asc_lfq_be16(u32 ea) {
 return (u16)(((u16)vm_base[ea]<<8)|vm_base[ea+1]);
}
static u32 asc_lfq_be32(u32 ea) {
 return ((u32)vm_base[ea]<<24)|((u32)vm_base[ea+1]<<16)|((u32)vm_base[ea+2]<<8)|vm_base[ea+3];
}
/* PPU2SPU owns +0x24 as SPU state, NOT a direction field.
 * Keep the mode supplied to _LFQueueInitialize in native host metadata. */

static void asc_lfq_register_mode(u32 q,u32 dir) {
    for(unsigned i=0;i<128;i++) {
        u32 old=__atomic_load_n(&s_asc_lfq_mode_q[i],__ATOMIC_ACQUIRE);
        if(old==q) {
            __atomic_store_n(&s_asc_lfq_mode_dir[i],dir,__ATOMIC_RELEASE);
            return;
        }
        if(!old) {
            u32 expected=0;
            if(__atomic_compare_exchange_n(&s_asc_lfq_mode_q[i],&expected,q,0,
                                           __ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE)) {
                __atomic_store_n(&s_asc_lfq_mode_dir[i],dir,__ATOMIC_RELEASE);
                return;
            }
        }
    }
}
static u32 asc_lfq_get_mode(u32 q) {
    for(unsigned i=0;i<128;i++)
        if(__atomic_load_n(&s_asc_lfq_mode_q[i],__ATOMIC_ACQUIRE)==q)
            return __atomic_load_n(&s_asc_lfq_mode_dir[i],__ATOMIC_ACQUIRE);
    return 0;
}
static u32 s_taskset_registry[CELL_SPURS_MAX_TASKSET*4];
extern void spu_taskset_signal_task(u32,u32);
extern int spu_signal_parked_on_line(u32);
static void spurs_taskset_registry_add(u32 taskset_ea)
{
    u32 n = sizeof(s_taskset_registry) / sizeof(s_taskset_registry[0]);
    for (u32 i = 0; i < n; i++)
        if (s_taskset_registry[i] == taskset_ea) return;
    for (u32 i = 0; i < n; i++)
        if (!s_taskset_registry[i]) { s_taskset_registry[i] = taskset_ea; return; }
}
static u32 spurs_signal_waiter(u32 ea_signal, u32 waiter)
{
    u32 task = waiter & 0xFFu;
    u32 wid = waiter >> 8;
    u32 delivered = 0;
    if (!(ea_signal & 1u)) {
        spu_taskset_signal_task(ea_signal, task);
        return 1;
    }
    u32 n = sizeof(s_taskset_registry) / sizeof(s_taskset_registry[0]);
    for (u32 i = 0; i < n; i++) {
        u32 ts = s_taskset_registry[i];
        if (!ts || task >= CELL_SPURS_MAX_TASK) continue;
        if (vm_read32(ts + CSTS_WID) != wid) continue;
        if ((u32)vm_read64(ts + CSTS_SPURS) != (ea_signal & ~1u)) continue;
        if (!(vm_read8(ts + CSTS_ENABLED + task / 8) & (0x80u >> (task & 7)))) continue;
        spu_taskset_signal_task(ts, task);
        delivered++;
    }
    return delivered;
}
s32 _cellSpursLFQueueInitialize(u64 owner_ea, u64 queue_ea, u64 buffer_ea,
                                u32 size, u32 depth, u32 direction)
{
    if (!queue_ea || !buffer_ea) return CELL_SPURS_TASK_ERROR_NULL_POINTER;
    if (!size || !depth)         return CELL_SPURS_TASK_ERROR_INVAL;

    if (queue_ea > UINT32_MAX || buffer_ea > UINT32_MAX ||
        (queue_ea & 127u) || (u64)size * depth > UINT32_MAX ||
        !spurs_guest_range_valid((u32)queue_ea, 128u) ||
        !spurs_guest_range_valid((u32)buffer_ea, (u32)((u64)size*depth)))
        return CELL_SPURS_TASK_ERROR_FAULT;
    __atomic_fetch_add(&s_asc_lfq_metrics[0],1,__ATOMIC_RELAXED);
    uint32_t q = (uint32_t)queue_ea;
    asc_lfq_register_mode(q,direction);
    for (uint32_t o = 0; o < 128; o += 4) vm_write32(q + o, 0);

    /* ASCENSION_M772_LFQUEUE_SDK_LAYOUT_V1: SDK-correct ANY2ANY guest format. */
    if (direction == LFQ_DIR_ANY2ANY) {
        vm_write32(q + LFQ_SIZE, size);
        vm_write32(q + LFQ_DEPTH, depth);
        vm_write64(q + LFQ_BUFFER, (u64)(uint32_t)buffer_ea | 1u);
        vm_write8(q + LFQ_BS + 0, 0xFF);
        vm_write8(q + LFQ_BS + 1, 0xFF);
        vm_write32(q + LFQ_DIRECTION, direction);
        vm_write32(q + LFQ_V1, 0xFFFFFFFFu);
        vm_write16(q + LFQ_PUSH2, 0xFFFF);
        vm_write16(q + LFQ_POP2, 0xFFFF);
        vm_write64(q + LFQ_EA_SIGNAL, (u64)(uint32_t)owner_ea);
        memset(vm_base + (uint32_t)buffer_ea, 0, (size_t)size * depth);
        printf("[cellSpurs] _LFQueueInitialize ANY2ANY(owner=0x%08X q=0x%08X buf=0x%08X size=%u depth=%u)\n",
               (u32)owner_ea, q, (u32)buffer_ea, size, depth);
        return CELL_OK;
    }

    /* W3 at +0x0C is the ring modulus the consumer reduces indices by: the
     * empty test is (W1-W0) mod 2*W3 and the buffer slot is index mod W3
     * (derived at 0x12914..0x129B8). Leaving it zero degenerated both and made
     * the queue look permanently empty no matter what a producer wrote. */
    vm_write32(q + 0x0C, depth);
    vm_write32(q + 0x10, size);
    vm_write32(q + 0x14, depth);
    vm_write64(q + 0x18, (u64)(uint32_t)buffer_ea);   /* bcptr<void,u64> */
    /* NOT direction at +0x24 and NOT init at +0x2C. Both sit inside the
     * 16-byte group at +0x20..+0x2F that the consumer owns and shifts wholesale
     * (shlqbyi <group>,1 at 0x12A0C). The trace shows the two values we used to
     * write there marching through it one byte per dequeue --
     *   +0x24: 00000002 -> 00000200 -> 00020000 -> 02000000
     *   +0x2C: 00000001 -> 00000100 -> 00010000 -> 01000000
     * -- i.e. we were feeding garbage into the SPU's own state every cycle.
     * Whatever holds direction/init, it is not these offsets. */                          /* init: constructed */
    vm_write64(q + 0x70, (u64)(uint32_t)owner_ea);    /* eaSignal <- taskset/spurs */

    memset(vm_base + (uint32_t)buffer_ea, 0, (size_t)size * depth);

    static int _n = 0;
    if (_n++ < 8)
        printf("[cellSpurs] _LFQueueInitialize(owner=0x%08X q=0x%08X buf=0x%08X size=%u depth=%u dir=%u) -> BE line written\n",
               (u32)owner_ea, (u32)queue_ea, (u32)buffer_ea, size, depth, direction);
    return CELL_OK;
}
static s32 lfq_get_push_pointer(u32 q, u32 is_blocking, s32* pointer)
{
    for (;;) {
        spu_lockline_lock();
        s32 depth = (s32)asc_lfq_be32(q + LFQ_DEPTH);
        s32 h8 = (s16)asc_lfq_be16(q + LFQ_PUSH1_H8);
        s32 used = h8 - (s32)asc_lfq_be16(q + LFQ_POP1_H1);
        if (used < 0) used += depth * 2;
        if (used < depth) {
            *pointer = h8;
            ef_w16(q + LFQ_PUSH1_H8, (u16)(h8 + 1 >= depth * 2 ? 0 : h8 + 1));
            ef_line_end(q);
            return CELL_OK;
        }
        spu_lockline_unlock();
        if (!is_blocking)
            return CELL_SPURS_TASK_ERROR_AGAIN;
        Sleep(0);
    }
}
static s32 lfq_complete_push_pointer(u32 q, s32 pointer)
{
    u32 pack_off = asc_lfq_be32(q + LFQ_DIRECTION) == LFQ_DIR_ANY2ANY ? LFQ_POP1_H3 : LFQ_PUSH2;
    for (;;) {
        spu_lockline_lock();
        s32 depth = (s32)asc_lfq_be32(q + LFQ_DEPTH);
        u16 h5 = asc_lfq_be16(q + LFQ_PUSH3_H5);
        u16 h6 = asc_lfq_be16(q + LFQ_PUSH3_H6);
        u16 pack = asc_lfq_be16(q + pack_off);

        s32 var1 = pointer - h5;
        if (var1 < 0) var1 += depth * 2;
        s32 var2 = (s32)(s16)asc_lfq_be16(q + LFQ_POP1_H4) - (s32)asc_lfq_be16(q + LFQ_POP1_H1);
        if (var2 < 0) var2 += depth * 2;

        s32 bit = 15 - var1;
        bit = (bit & 0x30) ? 0 : (1 << bit);
        s32 shift = __builtin_clz((u32)(u16)~(bit | h6)) - 16;
        s32 mask = (shift & 0x30) ? 0 : ((h6 | bit) << shift);
        s32 next = h5 + shift;
        if (next >= depth * 2) next -= depth * 2;

        s32 f0 = pack & 0x1F, f1 = (pack >> 5) & 0x1F, f2 = (pack >> 10) & 0x1F;
        s32 waiting = f2 - f1;
        if (waiting < 0) waiting += 0x1E;

        s32 waiter = -1;
        u16 new_pack = pack;
        if (var2 + waiting <= 15 && f2 != f0) {
            s32 slot = f2 >= 15 ? f2 - 15 : f2;
            u16 f2_next = f2 == 0x1D ? 0 : (u16)((f2 + 1) << 10);
            new_pack = (u16)((pack & 0x83FF) | f2_next);
            waiter = asc_lfq_be16(q + LFQ_HS1 + 2 * slot);
        } else if (f2 != f0) {
            spu_lockline_unlock();
            Sleep(0);
            continue;
        }

        ef_w16(q + LFQ_PUSH3_H5, (u16)next);
        ef_w16(q + LFQ_PUSH3_H6, (u16)mask);
        ef_w16(q + pack_off, new_pack);
        ef_line_end(q);

        if (waiter >= 0) {
            u32 ea_signal = (u32)vm_read64(q + LFQ_EA_SIGNAL);
            u32 n = spurs_signal_waiter(ea_signal, (u32)waiter);
            __atomic_fetch_add(&s_asc_lfq_metrics[4],n,__ATOMIC_RELAXED);
            if (!n)
                fprintf(stderr, "[cellSpurs] LFQueuePush q=0x%08X waiter 0x%04X has no taskset to signal\n",
                        q, (u32)waiter);
        }
        return CELL_OK;
    }
}
/* The PPU2SPU queue has a DIFFERENT BE layout from ANY2ANY: its ring
 * indices are full 32-bit W0/W1 and +0x0C is the 32-bit modulus.
 * Treating the low half of W3 as H8 corrupts the stream. */
static s32 asc_lfq_ppu2spu_push(u32 q,u32 src,u32 is_blocking)
{
    for (;;) {
        spu_lockline_lock();
        u32 depth=asc_lfq_be32(q+0x0C), size=asc_lfq_be32(q+LFQ_SIZE);
        u32 base=asc_lfq_be32(q+0x1C);
        u32 raw_pop=asc_lfq_be32(q), raw_push=asc_lfq_be32(q+4);
        if(!depth || depth>0x7FFFu || !size) {
            spu_lockline_unlock();
            return CELL_SPURS_TASK_ERROR_INVAL;
        }
        u32 pop=(int32_t)raw_pop<0?~raw_pop:raw_pop;
        u32 push=(int32_t)raw_push<0?~raw_push:raw_push;
        u32 ring=2u*depth;
        u32 used=(push+ring-(pop%ring))%ring;
        if(used<depth) {
            u32 slot=(push%depth);
            memcpy(vm_base+base+(size_t)slot*size,vm_base+src,size);
            u32 next=(push+1u)%ring;
            vm_base[q+4]=(u8)(next>>24);vm_base[q+5]=(u8)(next>>16);
            vm_base[q+6]=(u8)(next>>8);vm_base[q+7]=(u8)next;
            ef_line_end(q);
            __atomic_fetch_add(&s_asc_lfq_metrics[2],1,__ATOMIC_RELAXED);
            __atomic_fetch_add(&s_asc_lfq_metrics[3],size,__ATOMIC_RELAXED);
            int woke=spu_signal_parked_on_line(q);
            if(woke>0)__atomic_fetch_add(&s_asc_lfq_metrics[5],(u64)woke,__ATOMIC_RELAXED);
            return CELL_OK;
        }
        spu_lockline_unlock();
        if(!is_blocking)return CELL_SPURS_TASK_ERROR_BUSY;
        Sleep(1);
    }
}

s32 _cellSpursLFQueuePushBody(u64 queue_ea, u64 data_ea, u32 isBlocking)
{
    u32 q = (u32)queue_ea;
    u32 src = (u32)data_ea;
    __atomic_fetch_add(&s_asc_lfq_metrics[1],1,__ATOMIC_RELAXED);
    static int s_off=-1;
    if (s_off<0) s_off=getenv("SPURS_LFQUEUE_NO_PUSH")?1:0;
    if (!q || !src)
        return CELL_SPURS_TASK_ERROR_NULL_POINTER;
    if (s_off) return CELL_OK;
    /* ASCENSION_M810_RETAIN_EDGE_DEFLATE */
    /* The already game-proven EDGE path from patch_ps3recomp_spurs2.py is
     * inserted byte-for-byte by apply() before old queue producer deletion. */
    if ((q & 127u) || (src & 15u))
        return CELL_SPURS_TASK_ERROR_ALIGN;
    u32 direction = asc_lfq_get_mode(q);
    if (direction != LFQ_DIR_PPU2SPU && direction != LFQ_DIR_ANY2ANY)
        return CELL_SPURS_TASK_ERROR_PERM;

    if (!spurs_guest_range_valid(q,128u)) return CELL_SPURS_TASK_ERROR_FAULT;
    u32 sz_check = vm_read32(q+LFQ_SIZE), depth_check=vm_read32(q+LFQ_DEPTH);
    u32 base_check=(u32)(vm_read64(q+LFQ_BUFFER)&~1ull);
    if (!sz_check || !depth_check ||
        (u64)sz_check*depth_check > UINT32_MAX ||
        !spurs_guest_range_valid(base_check,(u32)((u64)sz_check*depth_check)) ||
        !spurs_guest_range_valid(src,sz_check)) return CELL_SPURS_TASK_ERROR_FAULT;
    if (direction==LFQ_DIR_PPU2SPU) return asc_lfq_ppu2spu_push(q,src,isBlocking);
    s32 pos;
    s32 rc = lfq_get_push_pointer(q, isBlocking, &pos);
    if (rc != CELL_OK)
        return rc;

    s32 depth = (s32)vm_read32(q + LFQ_DEPTH);
    u32 size = vm_read32(q + LFQ_SIZE);
    u32 base = (u32)(vm_read64(q + LFQ_BUFFER) & ~1ull);
    u32 dst = base + size * (u32)(pos >= depth ? pos - depth : pos);
    memcpy(vm_base + dst, vm_base + src, size);

    static int _n = 0;
    if (_n++ < 16)
        printf("[cellSpurs] LFQueuePush(q=0x%08X slot=%d dst=0x%08X size=%u)\n", q, pos, dst, size);
    rc=lfq_complete_push_pointer(q,pos);
    if (rc==CELL_OK) {
        __atomic_fetch_add(&s_asc_lfq_metrics[2],1,__ATOMIC_RELAXED);
        __atomic_fetch_add(&s_asc_lfq_metrics[3],size,__ATOMIC_RELAXED);
        int woke=spu_signal_parked_on_line(q);
        if(woke>0) __atomic_fetch_add(&s_asc_lfq_metrics[5],(u64)woke,__ATOMIC_RELAXED);
    }
    return rc;
}
'''
def span(s,tag):
    assert s.count(tag)==1,(tag,s.count(tag))
    a=s.index(tag);op=s.index("{",a+len(tag));d=0
    for i in range(op,len(s)):
        if s[i]=="{":d+=1
        if s[i]=="}":d-=1
        if i>=op and d==0:return a,i+1
    raise ValueError(tag)
def apply(path):
    p=Path(path)/"libs/spurs/cellSpurs.c";s=p.read_text()
    if MARK in s:
        assert s.count(MARK)==1 and "lfq_complete_push_pointer(q,pos)" in s
        return
    assert "spu_signal_parked_on_line" in s and "spu_taskset_track(taskset_ea);" in s
    anchor="static s32 spurs_create_taskset(CellSpurs* spurs, CellSpursTaskset* taskset,"
    assert s.count(anchor)==1
    s=s.replace(anchor,"static void spurs_taskset_registry_add(u32 taskset_ea);\n"+anchor,1)
    assert s.count("spu_taskset_track(taskset_ea);")==1
    s=s.replace("spu_taskset_track(taskset_ea);","spu_taskset_track(taskset_ea); spurs_taskset_registry_add(taskset_ea);",1)
    original_push=s[slice(*span(s,"s32 _cellSpursLFQueuePushBody("))]
    assert "ASCENSION_M772_EDGE_ZLIB_HLE_V2" in original_push, "EDGE HLE was lost before M8.10"
    begin=original_push.index("    /* ASCENSION_M772_EDGE_ZLIB_HLE_V2")
    end=original_push.index("    const uint32_t q =",begin)
    edge=original_push[begin:end]
    assert "PS3_EDGE_ZLIB_HLE" in edge and "cellSpursEventFlagSet" in edge
    # Preserve the real host decompression and event flag completion first.
    source=SOURCE.replace("    /* ASCENSION_M810_RETAIN_EDGE_DEFLATE */",
                          edge + "\n    /* ASCENSION_M810_RETAIN_EDGE_DEFLATE */",1)
    assert "ASCENSION_M772_LFQUEUE_SDK_LAYOUT_V1" in source
    spans=[span(s,x) for x in ("s32 _cellSpursLFQueueInitialize(","s32 _cellSpursLFQueuePushBody(")]
    for a,b in sorted(spans,reverse=True):s=s[:a]+s[b:]
    anchor="s32 cellSpursLFQueueAttachLv2EventQueue("
    assert s.count(anchor)==1
    s=s.replace(anchor,source+"\n"+anchor,1)
    p.write_text(s)
    print("[PASS] M8.10 native LFQueue reserve/complete/wake guest ABI installed")
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--upstream",required=True)
    apply(p.parse_args().upstream)
