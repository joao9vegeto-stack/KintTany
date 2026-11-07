# XOWUE Build 117.4 — input API and Bink EOF trace audit

Base: `f52e8c947dc576407a6eab6c6a021b6de75a6144` (Build 117.3).
This change is diagnostic and correctness-oriented; it does not claim that the iPhone has reached the menu.

## Why the trace needed correction

- The old B105 `eof` field read `GuestFile.lastReadEof` before the current transfer updated that field. It therefore described the previous read, not the Bink chunk being logged.
- The old B99 EOF completion event assembled sequence/offset/bytes/status from mutable per-file atomics. Two APC-backed reads of the same file could replace those fields between one read completing and its completion signal being emitted.
- Build 117.4 carries sequence, offset, byte count, NT status and EOF on the individual `GuestFileReadResult`, then emits the B99 event from that exact result after signalling the file completion object.

## Input API evidence

Each generated XAM/XInput import now records a bounded `XOWUE_INPUT_API` sample with API name, call number, guest thread, caller LR, PPC argument registers and return status. This deliberately distinguishes:
- `XamInputGetCapabilities`: device capability query; not a live button-state read.
- `XamInputSetState`: vibration output; not a live button-state read.
- `XamInputGetState` / `XInputGetState`: live gamepad state reads.

The implementation follows the Xenia XAM input ABI. It does not smuggle touch state into the capabilities structure or reinterpret vibration output as input. The sidecar keeps its existing 256 KiB cap; the runtime log remains independently bounded.

## Required next iPhone evidence

After installing Build 117.4, export the runtime log and `XOWUE-Input.log`. The key discriminator is whether the title actually calls either GetState import after the loading stage. If it only calls GetCapabilities/SetState, that is not evidence that the title has consumed the touch state; the next investigation must follow the guest input callsite/alternate input path rather than changing the public API semantics.

For media, compare `B105_MEDIA_READ_ORDER` and `B99_MEDIA_EOF_COMPLETION` by path, per-file sequence, offset, bytes and status. Verify the expected Copyright → ravenlogo → ATVI → MARVEL → FOX → UE3 → loading sequence against the observed runtime callbacks, not preload/open order.
