#!/usr/bin/env python3
"""Build 150 experimental EOF-zero behavior is narrow, bounded and flag-gated."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
engine = (root / "Runtime" / "XOWUEEngine.cpp").read_text(encoding="utf-8")
header = (root / "Runtime" / "xowue_engine.h").read_text(encoding="utf-8")
swift = (root / "iOS" / "App" / "XOWUEApp.swift").read_text(encoding="utf-8")
patcher = (root / "tools" / "patch_xowue_stream_memset_probe.py").read_text(encoding="utf-8")

assert "XOWUE_EXP_EOF_ZERO" in swift
assert 'UserDefaults.standard.object(forKey: "XOWUE_EXP_EOF_ZERO") as? Bool' in swift
assert 'XOWUEBuild.number == "150" || XOWUEBuild.number.hasPrefix("150.")' in swift
assert "xowue_set_exp_eof_zero_enabled(eofZeroEnabled ? 1 : 0)" in swift
assert "void xowue_set_exp_eof_zero_enabled(int enabled);" in header
assert 'extern "C" void xowue_set_exp_eof_zero_enabled(int enabled)' in engine

assert "bool xowue_exp_eof_zero_apply(PPCContext &ctx, uint8_t *base)" in engine
start = engine.index("bool xowue_exp_eof_zero_apply(")
end = engine.index("\n}\n", start) + 2
helper = engine[start:end]
assert "g_xowueExpEofZeroEnabled.load" in helper
assert "index < count || count == 0u || count > 65536u" in helper
assert "cursor >= windowStart && cursor < windowEnd" in helper
assert "cursor >= entryStart && static_cast<uint64_t>(cursor) < entryEnd" in helper
assert "static_cast<uint64_t>(cursor) < lastWindowEnd" in helper
assert "static_cast<uint64_t>(cursor) < maxWindowEnd" in helper
assert "cursor >= streamSize" in helper
assert "entrySize > 0x400000u" in helper
assert "allocateSmallGuestPoolBlock(base, 0x1000u, 0x1000u)" in helper
assert "std::memset(base + zeroBuffer, 0, 0x1000u)" in helper
for offset in (140, 148, 156, 164, 168):
    assert f"object + {offset}u" in helper
assert "cursor + 0x1000u" in helper
assert "ctx.r3.u64 = 1ull;" in helper

assert "beyondEndRequests > 4096u" in helper
assert "B150_EOF_ZERO_RUNAWAY" in helper
assert "g_xowueExpEofZeroEnabled.store(false" in helper
assert "g_b150RunawayLogged" in helper
assert "g_b150AppliedLogCount < 16u" in helper
assert "B150_EOF_ZERO_APPLIED" in helper
assert "applied=%u" in helper
persist = engine[engine.index("bool shouldPersistRuntimeTrace"):engine.index("void persistRuntimeTrace")]
assert 'event.find("B148_")' in persist and 'event.find("B149_")' in persist and 'event.find("B150_")' in persist

assert 'EOF_ZERO_CALL = "if (xowue_exp_eof_zero_apply(ctx, base)) return;"' in patcher
assert 'prologue = "PPC_FUNC_PROLOGUE();"' in patcher
assert "B150 EOF-zero hook must run after PPC_FUNC_PROLOGUE" in patcher
assert "eof_zero_function" in patcher and "eof_zero_inserted" in patcher
assert "assert zero_pos > prologue_pos" in patcher

for tag in ("B147_VM_RECOMMIT", "B147_VM_RELEASE", "B147_CHUNK_ENTRY",
            "B148_STREAM_EOF_POLL", "B148_CHUNK_IDX_OOB", "B148_READ_ZERO",
            "B149_STREAM_EOF_POLL", "B149_STREAM_LAST_READS",
            "B149_CHUNK_ENTRY", "B149_CHUNK_IDX_OOB"):
    assert tag in engine or tag in patcher, f"missing retained diagnostic {tag}"
print("PASS: B150 EOF-zero runtime flag, table/window guards, 4KB guest zero buffer, 16-log cap, 4096-request runaway shutoff, post-prologue hook")
