/* PoPTST iOS APU sound sink. Implements the reSOT xa2_* host contract via
 * SDL3 audio streams, matching the Android queue policy (48 kHz, stereo S16).
 * No AudioUnit, Java/JNI or Android-specific library is required. MIT. */
#include <SDL3/SDL.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define PP_SAMPLE_RATE 48000
#define PP_CHANNELS 2
#define PP_FRAME_SAMPLES 256
#define PP_FRAME_BYTES (PP_FRAME_SAMPLES * PP_CHANNELS * sizeof(int16_t))
#define PP_QUEUE_PRIME 4
#define PP_QUEUE_MAX 16

static SDL_AudioStream *s_audio;
static int s_frames_written, s_queued, s_dropped, s_starved;
int xa2_init(void) {
    if (s_audio) return 1;
    if (!(SDL_WasInit(SDL_INIT_AUDIO) & SDL_INIT_AUDIO) && !SDL_InitSubSystem(SDL_INIT_AUDIO))
        return 0;
    SDL_AudioSpec spec = {0};
    spec.format = SDL_AUDIO_S16;
    spec.channels = PP_CHANNELS;
    spec.freq = PP_SAMPLE_RATE;
    s_audio = SDL_OpenAudioDeviceStream(SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK, &spec, NULL, NULL);
    if (!s_audio) return 0;
    if (!SDL_ResumeAudioStreamDevice(s_audio)) {
        SDL_DestroyAudioStream(s_audio); s_audio = NULL; return 0;
    }
    s_frames_written = s_queued = s_dropped = s_starved = 0;
    return 1;
}
void xa2_shutdown(void) {
    if (s_audio) SDL_DestroyAudioStream(s_audio);
    s_audio = NULL;
}
int xa2_is_active(void) { return s_audio != NULL; }
int xa2_get_buffer_size(void) { return PP_FRAME_SAMPLES; }
int xa2_submit_samples(const int16_t *samples, int num_samples) {
    static const int16_t silence[PP_FRAME_SAMPLES * PP_CHANNELS] = {0};
    if (!s_audio || !samples || num_samples <= 0) return 0;
    if (num_samples > PP_FRAME_SAMPLES) num_samples = PP_FRAME_SAMPLES;
    int queued = SDL_GetAudioStreamQueued(s_audio);
    if (queued < 0) return 0;
    int frames = queued / PP_FRAME_BYTES;
    s_queued = frames;
    if (frames >= PP_QUEUE_MAX) { ++s_dropped; return 0; }
    if (queued == 0) {
        if (s_frames_written) ++s_starved;
        for (int i = 0; i < PP_QUEUE_PRIME; ++i)
            if (!SDL_PutAudioStreamData(s_audio, silence, sizeof silence)) return 0;
    }
    if (!SDL_PutAudioStreamData(s_audio, samples, num_samples * PP_CHANNELS * sizeof(int16_t)))
        return 0;
    ++s_frames_written;
    return 1;
}
void xa2_get_stats(int *queued, int *dropped, int *starved) {
    if (queued) *queued = s_queued;
    if (dropped) *dropped = s_dropped;
    if (starved) *starved = s_starved;
}
/* iOS UIApplication callbacks can suspend playback without destroying the
 * stream; SDL's device will resume after an interruption when requested. */
void pp_ios_audio_suspend(void) {
    if (s_audio) SDL_PauseAudioStreamDevice(s_audio);
}
void pp_ios_audio_resume(void) {
    if (s_audio) SDL_ResumeAudioStreamDevice(s_audio);
}
