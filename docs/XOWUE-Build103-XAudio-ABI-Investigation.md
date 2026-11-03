# XOWUE Build 103 investigation — XAudio render callback ABI

## Build 102.1 evidence

The on-device diagnostic for build 102.1 records:

- Render-driver registration: callback `0x82B63CA8`, original argument
  `0x400573FC`, handle `0x41550000`.
- Dedicated callback worker starts as guest thread 7 with its own KPCR
  `0x7C005000` and guest stack `0x79DD0000+0x00100000`.
- PPC FPSCR initialization is reached.
- No `XOWUE_XAUDIO_CALLBACK` completion or `XOWUE_XAUDIO_SUBMIT` record is
  present. The callback entered AOT but did not return far enough to submit a
  render frame.
- The final thread snapshot shows thread 7 inside guest code
  `0x82C2A1F0`, called from `0x82B57E58`, with callback entry
  `0x82B63CA8`. This is a blocked/incomplete callback, not proof of a missing
  audio device.
- The main guest continues to execute its copyright/movie path. Graphics
  submits and swap readback are present; that does not establish gameplay.

## Verified callback-context behavior

The XAudio registration pair contains the guest callback address in its first
dword and the callback context value in its second dword. The MW2 Recompiled
kernel export reads both values from that pair; its audio worker invokes the
registered callback with the original context value directly in PPC r3. The
UnleashedRecomp audio implementation independently follows the same contract:
its registration helper calls XAudioRegisterClient with callback[1] as the
context, without allocating a pointer-to-context wrapper.

XOWUE had followed the Xenia/XenonRecomp wrapper approach instead. Build 103.1
provides title-specific evidence that this path is not progressing: the
callback enters once on thread 7, remains in guest code, never logs a callback
return, and never reaches XAudioSubmitRenderDriverFrame. The diagnostic does
not by itself prove the wrapper caused the loop, but the direct-context behavior
in MW2 and UnleashedRecomp is the better match for this title's registration
pair. XOWUE now passes the original context value directly in r3 and removes
the extra guest wrapper allocation. The next device run must show repeated
callback returns and frame submissions; if it still does not, the PPC call
chain at 0x82B63CA8 -> 0x82B57E58 -> 0x82C2A1F0 remains the next target.

## Source references

- Xenia audio worker and wrapper allocation:
  https://github.com/xenia-project/xenia/blob/master/src/xenia/apu/audio_system.cc
- Xenon audio export and wrapper allocation:
  https://github.com/nimauria/Xenon-Recomp/blob/development-restructure/src/audio/exports.cpp
- Xenon callback pump and wrapper invocation:
  https://github.com/nimauria/Xenon-Recomp/blob/development-restructure/src/audio/system.cpp
- Xenon real guest callback thread/KPCR/TLS:
  https://github.com/nimauria/Xenon-Recomp/blob/development-restructure/src/core/session/pumps/audio_callbacks.cpp
- Xenon Audio V1 design and guest callback ABI:
  https://github.com/nimauria/Xenon-Recomp/blob/development-restructure/docs/audio/AUDIO_V1.md

## What this patch does not claim

This is a specific correction to the callback argument ABI, not a claim that
XAudio, XMA, Bink, or the whole title is now complete. The next device run
must prove that callback entry is followed by callback return and
`XAudioSubmitRenderDriverFrame`. The separate bounded callback-credit /
host-consumption model still requires validation against the iOS audio output
path. Bink worker events are not synthetically signaled or bypassed.


## Build 103.1 — correlate the actual timer waiter

Build 102.1 repeatedly records timer handle 0x00000116 firing with a null
APC routine and target guest thread 12. The old B98 wait markers were
hard-coded to handle 0x00000115, so they could not establish whether thread
12 was blocked on 0x00000116, whether that wait returned, or what PPC address
thread 12 was executing when the timer fired.

The follow-up source change adds bounded B102_TIMER_WAIT_BEGIN and
B102_TIMER_WAIT_RESULT records for every timer waitable. Each record captures
the timer handle/object, guest thread, last PPC PC/LR, signaled/pending state,
signal and timer generations, timer armed state, APC metadata, wait result,
reason, and elapsed wait time. B98_TIMER_FIRE is extended with the target
thread's last PPC PC, wait target, kernel-wait flag, and exited flag at the
instant the timer fires.

This is instrumentation, not a fabricated wakeup: it does not signal another
object, return STATUS_WAIT_0 early, change timer periods, or force thread 12
to run. The next device diagnostic can now distinguish a timer that fires
while its target is waiting on that same handle from an unrelated timer, and
can show whether the waiter actually resumes. The existing Swift compact
summary already retains B98_ records, so no additional summary plumbing is
needed.


## Build 103.2 — restore Xbox guest processor affinity

A source comparison against the working MW2 Recompiled runtime found a concrete
kernel ABI gap in XOWUE. MW2 derives the guest processor number from the top
byte of ExCreateThread's creation flags and writes it to
KPCR.CurrentProcessorNumber at r13 + 268. Its KeSetAffinityThread handler
resolves the KTHREAD object, derives the processor with ctz(affinity), and
updates that same KPCR byte. The MW2 runtime documentation explains that the
game reads this byte for worker dispatch and that XAudio workers synchronize by
processor number.

Before this change, XOWUE zeroed KPCR + 268 for every created thread and its
KeSetAffinityThread handler only returned success; it did not update the guest
thread's processor field. It also treated r5 as a previous-affinity pointer,
although the MW2 implementation does not write through that register. The
result could make guest worker barriers/dispatch disagree with the CPU mask
chosen by the title, even while host threads were alive and timers fired.

The correction records the processor selected by ExCreateThread's top-byte
mask, initializes the KPCR byte, and makes KeSetAffinityThread update the
resolved guest thread's KPCR byte. It emits B103_THREAD_AFFINITY records and
returns the affinity mask in r3, matching the MW2 implementation. No timer is
forced, no guest wait is bypassed, and no host CPU pinning is claimed.

Reference implementation:
- https://github.com/PaulCombal/mw2-recompiled/blob/master/runtime/kernel/threads.cpp
- https://github.com/PaulCombal/mw2-recompiled/blob/master/docs/runtime.md#r13-the-kpcr-and-thread-ids
- iPadOS host port notes: https://github.com/vrcnx/mw2-recompiled-ios/blob/ios-port/ios/README.md

This is a verified kernel contract correction, not yet proof that it alone
unblocks Wolverine. The next run must show nonzero processor values where the
guest requests them, then correlate thread 12's PPC progress and first actual
Xenos draw/swap after the copyright sequence.


## iOS host-thread stack — MW2 port parity

The iPadOS reference fork also documents a host-side requirement that is
separate from the guest PPC stack: Apple's default secondary-thread stack is
512 KB, while the recompiled PPC C++ call chains can overflow it during the
first frames. MW2's Apple platform layer therefore creates every guest-code
host thread with a 16 MB pthread stack and raises it to interactive QoS.
Reference: https://github.com/vrcnx/mw2-recompiled-ios/blob/ios-port/runtime/platform.cpp
and https://github.com/vrcnx/mw2-recompiled-ios/blob/ios-port/runtime/platform.h

XOWUE used std::thread directly for both ExCreateThread workers and its
XAudio guest callback worker, inheriting the small Apple secondary-thread
stack. This change routes those guest-code workers through GuestHostThread:
on Apple it uses pthread attributes for a 16 MB stack and interactive QoS;
on other platforms it remains std::thread. Timer and watchdog helper threads
remain ordinary std::thread because they do not execute recompiled PPC code.

This addresses a second concrete difference in the proven MW2 iOS port. It is
not evidence by itself that the copyright screen will advance; the next device
run must show the worker survives deep AOT execution, correct KPCR processor
numbers, and subsequent guest graphics progress.


## Build 103.3 — pass the XAudio context directly

The complete 103.1 diagnostic shows XAudio callback registration and entry,
but no callback return and no XAudioSubmitRenderDriverFrame. Thread 7 enters
callback 0x82B63CA8, then remains in guest code around 0x82B57E58 and
0x82C2A1F0. This is a more actionable lead than the periodic timer: timer
waits return STATUS_SUCCESS and are not the blocking edge.

A direct source comparison found that MW2 Recompiled's kernel export reads the
callback and context from the registration pair, and its audio worker passes
the context value directly as PPC r3. UnleashedRecomp independently calls its
XAudio client registration helper with callback[1] directly as context. XOWUE
had used a pointer-to-context wrapper based on Xenia/XenonRecomp. That wrapper
is not universal across titles and is now removed for Wolverine. The callback
pump passes client->context directly in r3 and logs the context value on entry
and return.

References:
- https://github.com/PaulCombal/mw2-recompiled/blob/master/runtime/kernel/audio.cpp
- https://github.com/PaulCombal/mw2-recompiled/blob/master/runtime/apu/audio.cpp
- https://github.com/hedge-dev/UnleashedRecomp/blob/main/UnleashedRecomp/apu/audio.cpp

The next device log must show XOWUE_XAUDIO_CALLBACK_RETURN and
XOWUE_XAUDIO_SUBMIT. This patch does not fabricate a return or submit; it
executes the guest callback with the reference ABI and records the result.
