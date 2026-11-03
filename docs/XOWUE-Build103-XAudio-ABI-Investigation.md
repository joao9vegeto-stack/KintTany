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

## Verified ABI discrepancy

Xenia's `AudioSystem::RegisterClient` allocates a four-byte guest dword,
stores the original callback argument in it, and saves that address as
`wrapped_callback_arg`. `AudioSystem::WorkerThreadMain` passes the wrapper
address as the callback's first argument.

Xenon-Recomp's `AudioSystem::register_render_client` likewise allocates a
four-byte guest wrapper, writes the original argument in big-endian form, and
the callback pump invokes the guest callback with the wrapper address.
Its export reads the callback and callback argument from the two-dword
registration pair.

XOWUE Build 102 instead passed the original callback argument directly in
PPC `r3`. That is an ABI mismatch. Build 103 changes the callback to receive
a persistent guest pointer to a four-byte wrapper, preserving the original
argument inside it. Wrapper slots are reused per render-client slot and reset
with the audio runtime; no callback receives a host pointer.

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
