#!/usr/bin/env python3
"""Strict PowerPC64 -> freestanding C probe. Unsupported instructions are errors, never NOPs."""
import argparse
import struct
from pathlib import Path

class UnsupportedOpcode(Exception):
    pass

def sx(v, b):
    return v - (1 << b) if v & (1 << (b - 1)) else v

def lift_words(words, origin):
    lines = [
        "typedef unsigned long long u64;",
        "typedef unsigned int u32;",
        "typedef signed int s32;",
        "typedef struct { u64 gpr[32]; u64 lr; u64 cia; } ar_ppu;",
        "extern u32 ar_read32(u64);",
        "extern void ar_write64(u64, u64);",
        "extern int ar_guest_call(ar_ppu*, u64);",
        "int ar_lifted_entry(ar_ppu* ctx) {",
        "  /* Local AOT experiment. Do NOT publish game-derived output. */",
    ]
    supported = []
    terminated = False
    for i, w in enumerate(words):
        pc = origin + 4 * i
        op = (w >> 26) & 63
        rt, ra = (w >> 21) & 31, (w >> 16) & 31
        if w == 0x4e800020:
            lines.append("  ctx->cia = ctx->lr; return 0;")
            supported.append("blr")
            terminated = True
            break
        if op == 14:
            imm = sx(w & 0xffff, 16)
            lines.append(f'  ctx->gpr[{rt}] = (u64)({("ctx->gpr[%d]" % ra) if ra else "0ULL"} + (u64)((long long){imm}));')
            supported.append("li" if ra == 0 else "addi")
        elif op == 15:
            imm = sx(w & 0xffff, 16) << 16
            lines.append(f'  ctx->gpr[{rt}] = (u64)({("ctx->gpr[%d]" % ra) if ra else "0ULL"} + (u64)((long long){imm}));')
            supported.append("lis" if ra == 0 else "addis")
        elif op in (24, 25):
            val = (w & 0xffff) << (16 if op == 25 else 0)
            lines.append(f"  ctx->gpr[{ra}] = ctx->gpr[{rt}] | 0x{val:x}ULL;")
            supported.append("oris" if op == 25 else ("nop" if w == 0x60000000 else "ori"))
        elif op == 32:
            disp = sx(w & 0xffff, 16)
            lines.append(f'  ctx->gpr[{rt}] = (u64)ar_read32((u64)({("ctx->gpr[%d]" % ra) if ra else "0ULL"} + (u64)((long long){disp})));')
            supported.append("lwz")
        elif op == 62 and (w & 3) in (0, 1):
            disp = sx(w & 0xfffc, 16)
            base = ("ctx->gpr[%d]" % ra) if ra else "0ULL"
            lines.append(f"  u64 ea_{i} = (u64)({base} + (u64)((long long){disp}));")
            lines.append(f"  ar_write64(ea_{i}, ctx->gpr[{rt}]);")
            if w & 3:
                if not ra:
                    raise UnsupportedOpcode("stdu with zero base register is invalid")
                lines.append(f"  ctx->gpr[{ra}] = ea_{i};")
            supported.append("stdu" if w & 3 else "std")
        elif op == 18 and w & 1:
            delta = sx(w & 0x3fffffc, 26)
            target = delta if w & 2 else pc + delta
            lines.append(f"  ctx->lr = 0x{pc + 4:x}ULL;")
            lines.append(f"  if (ar_guest_call(ctx, 0x{target:x}ULL)) return -3;")
            supported.append("bl")
        elif op == 31 and ((w >> 1) & 1023) == 986:
            lines.append(f"  ctx->gpr[{ra}] = (u64)(long long)(s32)(u32)ctx->gpr[{rt}];")
            supported.append("extsw")
        else:
            raise UnsupportedOpcode(f"unsupported PPU opcode at 0x{pc:x}: primary={op} ext={(w >> 1) & 1023}")
    if not terminated:
        raise UnsupportedOpcode("no blr in requested window; function boundary not proven")
    return "\n".join(lines + ["}"]) + "\n", supported

def read_ppu_words(elf: Path, start: int, count: int):
    d = elf.read_bytes()
    if d[:7] != b"\x7fELF\x02\x02\x01" or struct.unpack_from(">H", d, 18)[0] != 21:
        raise ValueError("expected big-endian PowerPC64 ELF")
    phoff = struct.unpack_from(">Q", d, 32)[0]
    phsize = struct.unpack_from(">H", d, 54)[0]
    phcount = struct.unpack_from(">H", d, 56)[0]
    if not (0 < count <= 256):
        raise ValueError("instruction limit exceeded")
    if phoff + phsize * phcount > len(d) or phsize < 56:
        raise ValueError("ELF program headers invalid")
    for i in range(phcount):
        typ, flags, offset, vaddr, _paddr, file_size, _mem_size, _align = struct.unpack_from(">IIQQQQQQ", d, phoff + i * phsize)
        if typ == 1 and flags & 1 and vaddr <= start and start + 4 * count <= vaddr + file_size and offset + file_size <= len(d):
            return struct.unpack_from(">" + str(count) + "I", d, offset + start - vaddr)
    raise ValueError("requested range is not executable PT_LOAD")

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("elf", type=Path)
    p.add_argument("--start", type=lambda s: int(s, 0), required=True)
    p.add_argument("--count", type=int, default=16)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    source, ops = lift_words(read_ppu_words(args.elf, args.start, args.count), args.start)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(source)
    print("AOT probe:", len(ops), "instructions", ops)
