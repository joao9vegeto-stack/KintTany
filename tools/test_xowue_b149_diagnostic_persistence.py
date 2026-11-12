#!/usr/bin/env python3
"""Build 149 diagnostics must survive persistence and identify every hook path."""
from pathlib import Path
import re

engine = Path("Runtime/XOWUEEngine.cpp").read_text(encoding="utf-8")

# The persistent writer must explicitly preserve both generations before the
# generic sequence sampler (first 96 / every 256) can discard ordinary events.
persist_start = engine.index("bool shouldPersistRuntimeTrace(")
persist_end = engine.index("\n}\n\nvoid persistRuntimeTrace", persist_start)
persist = engine[persist_start:persist_end]
assert 'event.find("B148_")' in persist and 'event.find("B149_")' in persist
assert "return true;" in persist[:persist.index('event.find("XOWUE_XAUDIO_")')]

# The old B148_READ_ZERO producer is inside performRead. The B99 event is emitted
# only after that same result is handed to completionSignal.signalNow().
read_start = engine.index("void xowue_NtReadFile(")
read_end = engine.index("\nvoid xowue_NtWriteFile(", read_start)
read_body = engine[read_start:read_end]
zero_at = read_body.index('"B148_READ_ZERO sample=')
zero_guard = read_body.rfind("if (bytesRead == 0u)", 0, zero_at)
assert zero_guard >= 0
assert read_body.index("result.sequence = file->lastReadSequence", zero_at) > zero_at
assert "result = performRead(true);" in read_body
assert "result = performRead(false);" in read_body
assert "completionSignal.signalNow(result.sequence, result.offset, result.bytesRead," in read_body
assert read_body.index("result = performRead(true);") < read_body.index("completionSignal.signalNow(")
assert read_body.index("result = performRead(false);") < read_body.rindex("completionSignal.signalNow(")

# B99's EOF completion is gated by the exact result's EOF bit/status; B148 sees
# bytesRead==0 earlier in the same performRead lambda.
completion_start = engine.index("struct GuestFileCompletionSignalOnReturn")
completion_end = engine.index("\n};", completion_start)
completion = engine[completion_start:completion_end]
assert "if (readCompleted && readEof)" in completion
assert '"B99_MEDIA_EOF_COMPLETION kind=%s' in completion
assert "readStatus" in completion

# This branch did not previously define B148_FILE_OPEN_SIZE. It is now an
# explicit per-startup-media-open record, not merely an alias of B86's capped line.
assert '"B148_FILE_OPEN_SIZE api=%s' in engine
assert "recordRuntimeTrace(sizeEvent);" in engine

# The boot marker and stream poll entry are independent of EOF/OOB conditions.
assert '"B149_BOOT_MARK build=149 registered=' in engine
assert '"B149_STREAM_POLL_ENTRY sample=%u' in engine
for token in ("obj=0x%08X", "cursor=0x%08X", "stream_size=0x%08X",
              "window_start=0x%08X", "window_end=0x%08X",
              "r4=0x%08X r5=0x%08X", "table=0x%08X count=%u"):
    assert token in engine, f"poll entry missing {token}"

helper_start = engine.index("void xowue_trace_stream_eof_poll_b149(")
helper_end = engine.index("\n\n\nvoid xowue_trace_chunk_entry", helper_start)
helper = engine[helper_start:helper_end]
for reason in ("table_invalid", "count_excessive", "interval_unreadable",
               "window_covers_request", "cursor_before_window_end",
               "event_sample_cap"):
    assert f'logSkip("{reason}"' in helper, f"silent B149 return: {reason}"
for match in re.finditer(r"\breturn;", helper):
    prefix = helper[max(0, match.start() - 180):match.start()]
    assert "logSkip(" in prefix, f"unreported early return near: {prefix[-100:]}"
assert '"B149_STREAM_POLL_SKIP sample=%u reason=%s' in helper
assert '"B149_STREAM_LAST_READS sample=%u' in helper
assert '"B149_STREAM_EOF_POLL sample=%u' in helper
# Diagnostics must be read-only with respect to the PPC context.
assert not re.search(r"ctx\.(?:r\d+|lr|cr\d+)\.[A-Za-z0-9_]+\s*=", helper)

# Chunk helper is invoked at sub_82575108 entry by the AOT patcher. Its B149
# sample includes valid and invalid indices and safely prints unavailable bytes
# rather than reading outside the guest table.
chunk_start = engine.index("void xowue_trace_chunk_entry(")
chunk_end = engine.index("\nvoid xowue_dispatch_indirect(", chunk_start)
chunk = engine[chunk_start:chunk_end]
assert "if (sample <= 16u)" in chunk
assert '"B149_CHUNK_ENTRY sample=%u obj=0x%08X idx=%u count=%u ' in chunk
assert "entry16=%s entry_valid=%u" in chunk
assert "entryRangeValid" in chunk and 'std::snprintf(entry16, sizeof(entry16), "unavailable")' in chunk
assert "B148_READ_ZERO" in engine and "B148_STREAM_EOF_POLL" in engine
assert "B148_CHUNK_IDX_OOB" in engine
assert "B149_STREAM_EOF_POLL" in engine and "B149_CHUNK_IDX_OOB" in engine
print("PASS: B149 boot/poll/chunk markers, all helper returns explained, B148/B149 persist allowlist, NtReadFile EOF correlation")
