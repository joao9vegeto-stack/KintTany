#!/usr/bin/env python3
"""Patch the pinned PS3Recomp HLE sources with iOS host services."""
import argparse
from pathlib import Path


def once(text, old, new, what):
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"iOS service patch: {what} anchor count {n}, expected 1")
    return text.replace(old, new, 1)


def patch_pad(path):
    s = path.read_text()
    if "ASCENSION_IOS_VIRTUAL_PAD" in s:
        return
    old = """#if defined(PS3RECOMP_PAD_USE_SDL2)
  #define PAD_BACKEND_SDL2  1
  #define PAD_BACKEND_XINPUT 0
#elif defined(_WIN32)
  #define PAD_BACKEND_SDL2  0
  #define PAD_BACKEND_XINPUT 1
#else
  #define PAD_BACKEND_SDL2  1
  #define PAD_BACKEND_XINPUT 0
#endif"""
    new = """#if defined(PS3RECOMP_PAD_USE_SDL2)
  #define PAD_BACKEND_SDL2  1
  #define PAD_BACKEND_XINPUT 0
#elif defined(PS3RECOMP_PAD_IOS)
  #define PAD_BACKEND_IOS   1
  #define PAD_BACKEND_SDL2  0
  #define PAD_BACKEND_XINPUT 0
#elif defined(_WIN32)
  #define PAD_BACKEND_SDL2  0
  #define PAD_BACKEND_XINPUT 1
#else
  #define PAD_BACKEND_SDL2  1
  #define PAD_BACKEND_XINPUT 0
#endif"""
    s = once(s, old, new, "cellPad backend selection")
    anchor = "#include <string.h>\n"
    s = once(s, anchor, anchor + """#if defined(PS3RECOMP_PAD_IOS)
#include <pthread.h>
#endif
""", "cellPad pthread include")
    anchor = "static int s_data_fresh[PAD_MAX_HOST_PORTS];\n"
    backend = """
#if PAD_BACKEND_IOS
/* The UI publishes touch state; guest reads take a coherent snapshot. */
#define ASCENSION_IOS_VIRTUAL_PAD 1
static pthread_mutex_t s_ios_pad_lock = PTHREAD_MUTEX_INITIALIZER;
static PadHostState s_ios_pad_input;

void cellPad_set_host_state(u16 buttons, u8 lx, u8 ly, u8 rx, u8 ry,
                            u8 l2, u8 r2)
{
    pthread_mutex_lock(&s_ios_pad_lock);
    memset(&s_ios_pad_input, 0, sizeof(s_ios_pad_input));
    s_ios_pad_input.connected = 1;
    s_ios_pad_input.buttons = buttons;
    s_ios_pad_input.analog_lx = lx;
    s_ios_pad_input.analog_ly = ly;
    s_ios_pad_input.analog_rx = rx;
    s_ios_pad_input.analog_ry = ry;
    s_ios_pad_input.trigger_l2 = l2;
    s_ios_pad_input.trigger_r2 = r2;
    s_ios_pad_input.press_up = (buttons & CELL_PAD_CTRL_UP) ? 255 : 0;
    s_ios_pad_input.press_down = (buttons & CELL_PAD_CTRL_DOWN) ? 255 : 0;
    s_ios_pad_input.press_left = (buttons & CELL_PAD_CTRL_LEFT) ? 255 : 0;
    s_ios_pad_input.press_right = (buttons & CELL_PAD_CTRL_RIGHT) ? 255 : 0;
    s_ios_pad_input.press_triangle = (buttons & CELL_PAD_CTRL_TRIANGLE) ? 255 : 0;
    s_ios_pad_input.press_circle = (buttons & CELL_PAD_CTRL_CIRCLE) ? 255 : 0;
    s_ios_pad_input.press_cross = (buttons & CELL_PAD_CTRL_CROSS) ? 255 : 0;
    s_ios_pad_input.press_square = (buttons & CELL_PAD_CTRL_SQUARE) ? 255 : 0;
    s_ios_pad_input.press_l1 = (buttons & CELL_PAD_CTRL_L1) ? 255 : 0;
    s_ios_pad_input.press_r1 = (buttons & CELL_PAD_CTRL_R1) ? 255 : 0;
    pthread_mutex_unlock(&s_ios_pad_lock);
}

static void pad_init_backend(void)
{
    cellPad_set_host_state(0, 128, 128, 128, 128, 0, 0);
}
static void pad_shutdown_backend(void) { pad_init_backend(); }
#endif
"""
    s = once(s, anchor, anchor + backend, "cellPad input bridge")
    old = """#if PAD_BACKEND_XINPUT
    pad_poll_xinput();
#elif PAD_BACKEND_SDL2
    pad_poll_sdl2();
#endif"""
    new = """#if PAD_BACKEND_XINPUT
    pad_poll_xinput();
#elif PAD_BACKEND_SDL2
    pad_poll_sdl2();
#elif PAD_BACKEND_IOS
    pthread_mutex_lock(&s_ios_pad_lock);
    s_host_state[0] = s_ios_pad_input;
    for (int i = 1; i < PAD_MAX_HOST_PORTS; ++i) {
        memset(&s_host_state[i], 0, sizeof(s_host_state[i]));
        s_host_state[i].analog_lx = s_host_state[i].analog_ly = 128;
        s_host_state[i].analog_rx = s_host_state[i].analog_ry = 128;
    }
    pthread_mutex_unlock(&s_ios_pad_lock);
#endif"""
    s = once(s, old, new, "cellPad input polling")
    path.write_text(s)


def patch_audio(path):
    s = path.read_text()
    if "ASCENSION_IOS_SILENT_AUDIO_SERVICE" in s:
        return
    old = """#if defined(PS3RECOMP_AUDIO_USE_SDL2)
  #define AUDIO_BACKEND_SDL2    1
  #define AUDIO_BACKEND_WASAPI  0
#elif defined(_WIN32)
  #define AUDIO_BACKEND_SDL2    0
  #define AUDIO_BACKEND_WASAPI  1
#else
  #define AUDIO_BACKEND_SDL2    1
  #define AUDIO_BACKEND_WASAPI  0
#endif"""
    new = """#if defined(PS3RECOMP_AUDIO_USE_SDL2)
  #define AUDIO_BACKEND_SDL2    1
  #define AUDIO_BACKEND_WASAPI  0
#elif defined(PS3RECOMP_AUDIO_IOS)
  #define AUDIO_BACKEND_IOS     1
  #define AUDIO_BACKEND_SDL2    0
  #define AUDIO_BACKEND_WASAPI  0
#elif defined(_WIN32)
  #define AUDIO_BACKEND_SDL2    0
  #define AUDIO_BACKEND_WASAPI  1
#else
  #define AUDIO_BACKEND_SDL2    1
  #define AUDIO_BACKEND_WASAPI  0
#endif"""
    s = once(s, old, new, "cellAudio backend selection")
    anchor = "#if AUDIO_BACKEND_SDL2\n\nstatic SDL_AudioDeviceID s_sdl_audio_dev = 0;\n"
    backend = """#if AUDIO_BACKEND_IOS
/* Preserve cellAudio ports, BE guest PCM reads and period notifications.
 * Output is silent until the app gains an iOS PCM device adapter. */
#define ASCENSION_IOS_SILENT_AUDIO_SERVICE 1
static int audio_backend_init(void) { return 0; }
static void audio_backend_shutdown(void) {}
static void audio_backend_submit(const float* samples, u32 count)
{ (void)samples; (void)count; }
static int audio_backend_room(void) { return CELL_AUDIO_BLOCK_SAMPLES; }
static void audio_backend_wait(void) { usleep(CELL_AUDIO_PERIOD_US); }
static u32 audio_backend_queued_samples(void) { return 0; }
#endif

#if AUDIO_BACKEND_SDL2

static SDL_AudioDeviceID s_sdl_audio_dev = 0;
"""
    s = once(s, anchor, backend, "cellAudio silent backend")
    old = """        u32 queued = audio_backend_queued_samples();
        if (queued > CELL_AUDIO_BLOCK_SAMPLES * 4) {
            usleep(5000);
        } else {
            usleep(2000);
        }"""
    new = """#if AUDIO_BACKEND_IOS
        usleep(CELL_AUDIO_PERIOD_US);
#else
        u32 queued = audio_backend_queued_samples();
        if (queued > CELL_AUDIO_BLOCK_SAMPLES * 4) {
            usleep(5000);
        } else {
            usleep(2000);
        }
#endif"""
    s = once(s, old, new, "cellAudio service pacing")
    path.write_text(s)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path)
    root = parser.parse_args().upstream
    patch_pad(root / "libs/input/cellPad.c")
    patch_audio(root / "libs/audio/cellAudio.c")
    print("iOS cellPad touch input and silent cellAudio event/mixer services enabled")


if __name__ == "__main__":
    main()
