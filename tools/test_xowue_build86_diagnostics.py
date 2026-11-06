#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
engine = (root / "Runtime/XOWUEEngine.cpp").read_text()
diagnostics = (root / "iOS/App/XOWUEDiagnostics.swift").read_text()
app = (root / "iOS/App/XOWUEApp.swift").read_text()

for forbidden in ("isSplashBikMovie", "isKnownOptionalStartupMovie",
                  "XOWUE_OPTIONAL_STARTUP_MOVIE_EOF", ".XOWUEVirtualMedia",
                  "splash-bik bypass"):
    assert forbidden not in engine, f"synthetic startup-media bypass remains: {forbidden}"

for required in ("B86_MEDIA_OPEN", "isStartupMoviePath", "B86_STREAM_ANOMALY",
                 "B86_STREAM_OBJECT_WORD", "B86_STREAM_CHUNK_TABLE",
                 "vtable_slot64_io_target", "previous_guest_fn_candidate",
                 "g_runtimeTracePersistB83", "g_runtimeTracePersistB85",
                 "kMaxRuntimeTraceFileBytes"):
    assert required in engine, f"missing Build 86 runtime diagnostic: {required}"

assert "fetch_add(1, std::memory_order_relaxed) < 200u" in engine
assert "16 * 1024 * 1024" in engine
assert "max_bytes=16777216" in engine
assert "object + 0x70u + i * 4u" in engine
assert "validGuestRange(address, 0xC0u)" in engine
assert "calls & 0xFFFFFu" in engine
assert "guestAddress == 0x82C4BE30u" in engine
assert "B87_STREAM_WAIT_STATE" in engine and "B87_STREAM_CACHE_ANOMALY" in engine
assert "B87_NTREADFILE" in engine
assert "B90_STREAM_WATCH_ARMED" in engine
assert "B90_STREAM_FIELD_TRANSITION" in engine
assert "g_b90StreamWatch" in engine
assert "Build 89: a hot poll may service the Xenos command processor" in engine
assert "Build 73 (MCLA-4iOS / rexglue-sdk pattern): Wake both guest" not in engine
qpc_fastpaths = [line for line in engine.splitlines() if "const bool qpcFastPath =" in line]
assert len(qpc_fastpaths) == 2 and all("0x822A0278u" not in line for line in qpc_fastpaths)
assert "kNtStatusEndOfFile = 0xC0000011u" in engine
assert "bytesRead == 0u && readEof" in engine
assert "validGuestPointer(plus90, 0x20u)" in engine
assert "objectSource" in engine
assert "B94_STREAM_CONTEXT" in engine
assert "streamAnomaly" in diagnostics and "streamObject" in diagnostics
assert "streamTable" in diagnostics and "streamRecent" in diagnostics

for required in ("summaryFilename", "summaryFileURL()", "refreshCompactSummaryLocked",
                 "B86_STREAM_", "B86_MEDIA_OPEN", "B87_STREAM_WAIT_STATE", "B87_STREAM_CACHE_ANOMALY", "B87_NTREADFILE"):
    assert required in diagnostics, f"summary generation missing {required}"
assert diagnostics.count("refreshCompactSummaryLocked(diagnosticURL:") >= 4
assert "XOWUEDiagnostics.summaryFileURL()" in app
assert "XOWUEDiagnostics.summaryFilename" in app
print("PASS: Build 87 stream-wait tracing, bounded NT file I/O evidence, EOF status and app summary")
