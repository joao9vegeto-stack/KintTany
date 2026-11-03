from pathlib import Path

engine = Path("Runtime/XOWUEEngine.cpp").read_text()
bridge = Path("Runtime/Graphics/Xenos/XOWUEGpuBridge.cpp").read_text()
header = Path("Runtime/Graphics/Xenos/XOWUEGpuBridge.h").read_text()
patch = Path("patches/XenonRecomp-XOWUE.patch").read_text()

# 1. PPC write watchpoint covers the Build 89/90 stream objects.
for token in ("0x4147A980u", "0x4147B678u", "B95_GUEST_STORE",
              "oldValue", "pc=0x%08X lr=0x%08X", "lastGuestPc"):
    assert token in engine, token
for token in ("PPC_STORE_U8", "PPC_STORE_U16", "PPC_STORE_U32", "PPC_STORE_U64",
              "xowue_note_guest_store"):
    assert token in patch, token

# 2. Correlate real wait and signal transitions by thread/object/generation.
for token in ("B95_SYNC_WAIT_BEGIN", "B95_SYNC_WAIT_RESULT", "B95_SYNC_SIGNAL",
              "signalGeneration", "unconsumedSignals"):
    assert token in engine, token

# 3. Keep guest resolve, decoded color, commit and backend handoff distinct.
assert "guestFrame.resolve_valid=status!=0;" in bridge
assert "guestFrame.has_color_source=count>0;" in bridge
assert "void NotifyGuestFrameSubmitted()" in bridge
assert "guestFrame.copied_to_swapchain=true;" in bridge
assert "guestFrame.copied_to_swapchain&&" not in bridge
assert "NotifyGuestFrameSubmitted" in header
assert engine.count("NotifyGuestFrameSubmitted();") == 1
pm4_swap = engine[engine.index("} else if (opcode == kXenosPm4SwapOpcode"):
                  engine.index("\n            }\n        }", engine.index("} else if (opcode == kXenosPm4SwapOpcode"))]
assert "NotifyGuestFrameSubmitted" not in pm4_swap
vd_swap = engine[engine.index("void xowue_VdSwap("):
                 engine.index("\nvoid xowue_VdInitializeScalerCommandBuffer", engine.index("void xowue_VdSwap("))]
assert "NotifyGuestFrameSubmitted" not in vd_swap

# 4. Scatter I/O distinguishes invalid pages, host errors and short EOF transfers.
scatter = engine.split("void xowue_NtReadFileScatter", 1)[1].split("void xowue_NtDeviceIoControlFile", 1)[0]
for token in ("readBad", "readEof", "readFailed", "kNtStatusEndOfFile",
              "kNtStatusInvalidParameter", "writeGuestIoStatus(base, ioStatus, status, total)",
              "queueGuestApc", "B95_SCATTER_READ"):
    assert token in scatter, token
assert "if (!validGuestRange(segment, chunk)) {\n            status = kNtStatusInvalidParameter;" in scatter
print("PASS: XOWUE Build 95 four interventions")
