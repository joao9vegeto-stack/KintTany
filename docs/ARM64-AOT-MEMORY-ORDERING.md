# XOWUE — ARM64 PPC memory ordering and startup-stream wait

## Scope

This change applies only to the XOWUE branch and only to the native ARM64 AOT code generated from the existing Wolverine executable. It does not change the guest executable, the Xenos renderer, the Bink decoder, or the stream callback's return value.

## Corrections

1. **PPC memory barriers:** generated sync, lwsync, eieio, isync, ptesync, and msync sites are followed by real C++ atomic fences. sync/ptesync/eieio use sequential consistency; lwsync and sync 1 use acquire-release; isync uses acquire semantics. The patcher is idempotent and fails if a barrier remains unfenced or changes unrelated source text.
2. **FPSCR on ARM64:** the host-to-guest rounding read-back table is now distinct for FPCR and MXCSR. The ARM64 FPCR ordering is [nearest, +infinity, -infinity, toward-zero], mapping to guest modes [0, 2, 3, 1]; four compile-time round-trip assertions validate the table on the target architecture.
3. **Xenon delay hints:** db8cyc, db10cyc, db12cyc, db14cyc, and db16cyc receive an AArch64 ISB pause. The guard leaves other architectures unchanged.

The workflow applies these changes after the normal AOT generation/instrumentation step and before the iOS engine is compiled. Its XOWUE-ARM64-AOT-Semantics artifact records exact site counts and any patched instructions found in the stream-related functions/PC windows (0x82575250, 0x82575510, 0x824ACBF8, 0x824ACC1C).

## Last-video/menu acceptance

The existing device evidence distinguishes a final Bink file read/EOF from successful video-thread completion and from the title entering its menu. These AOT fixes address memory ordering and aggressive polling, but they do not signal a Bink completion object, force a stream-manager callback to return success, skip the movie, or synthesize a menu frame.

A device run is accepted only when all of the following are observed after the final UE3_logo.bik frame:

- the media/Bink worker reports its real drain/completion state and its completion event/timer is signalled;
- the main PPC thread leaves the observed stream/SetState wait path (including the 0x82575250 callback/callsite path where applicable);
- guest VdSwap/PM4 submissions resume and guest pixels change across multiple frames;
- the Wolverine menu is actually visible and accepts input.

An IPA build or a host Metal presentation rate alone does not satisfy these gates.
