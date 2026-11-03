#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// Starts the native iOS playback engine. Safe to call more than once.
int XOWUEAudioStart(void);
void XOWUEAudioStop(void);

// Submit one 256-sample interleaved stereo float block at 48 kHz.
int XOWUEAudioSubmitStereoFrame(const float *interleaved, uint32_t frames);
uint32_t XOWUEAudioQueuedFrames(void);
uint64_t XOWUEAudioDroppedFrames(void);
uint64_t XOWUEAudioUnderrunFrames(void);

// 0 = starting/not started, 1 = running, -1 = failed to start.
int XOWUEAudioBackendState(void);

#ifdef __cplusplus
}
#endif
