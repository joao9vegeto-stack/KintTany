#import <AVFAudio/AVFAudio.h>
#import <Foundation/Foundation.h>
#import <dispatch/dispatch.h>

#include <array>
#include <atomic>
#include <cstdint>
#include <cstring>

namespace {

constexpr uint32_t kSamplesPerFrame = 256u;
constexpr uint32_t kChannels = 2u;
constexpr uint32_t kAudioRingCapacity = 32u;

using AudioBlock = std::array<float, kSamplesPerFrame * kChannels>;

std::array<AudioBlock, kAudioRingCapacity> g_audioRing{};
std::atomic<uint32_t> g_writeFrame{0u};
std::atomic<uint32_t> g_readFrame{0u};
std::atomic<uint64_t> g_droppedFrames{0u};
std::atomic<uint64_t> g_underrunFrames{0u};
std::atomic<int> g_backendState{0};
std::atomic<bool> g_startScheduled{false};

// Only the AVAudioSourceNode render thread accesses this partial-block offset.
uint32_t g_readOffset = 0u;
AVAudioEngine *g_audioEngine = nil;
AVAudioSourceNode *g_audioSource = nil;

// AVAudioEngine/AVAudioSession lifecycle is serialized independently of the
// SwiftUI main queue. Starting playback must never wait behind a full-screen
// game view or its touch/render work.
dispatch_queue_t audioControlQueue() {
    static dispatch_queue_t queue =
        dispatch_queue_create("com.joaopedro.xowue.audio-control", DISPATCH_QUEUE_SERIAL);
    return queue;
}

bool readStereoSample(float &left, float &right) {
    const uint32_t read = g_readFrame.load(std::memory_order_relaxed);
    const uint32_t write = g_writeFrame.load(std::memory_order_acquire);
    if (read == write) return false;

    const AudioBlock &block = g_audioRing[read % kAudioRingCapacity];
    left = block[g_readOffset * 2u];
    right = block[g_readOffset * 2u + 1u];
    if (++g_readOffset == kSamplesPerFrame) {
        g_readOffset = 0u;
        g_readFrame.store(read + 1u, std::memory_order_release);
    }
    return true;
}

OSStatus renderAudio(BOOL *isSilence,
                     AVAudioFrameCount frameCount,
                     AudioBufferList *outputData) {
    if (!outputData) return noErr;

    for (UInt32 i = 0u; i < outputData->mNumberBuffers; ++i) {
        AudioBuffer &buffer = outputData->mBuffers[i];
        if (buffer.mData && buffer.mDataByteSize != 0u)
            std::memset(buffer.mData, 0, buffer.mDataByteSize);
    }

    float *leftOutput = nullptr;
    float *rightOutput = nullptr;
    float *interleavedOutput = nullptr;
    if (outputData->mNumberBuffers >= 2u) {
        leftOutput = static_cast<float *>(outputData->mBuffers[0].mData);
        rightOutput = static_cast<float *>(outputData->mBuffers[1].mData);
    } else if (outputData->mNumberBuffers == 1u) {
        interleavedOutput = static_cast<float *>(outputData->mBuffers[0].mData);
    }

    bool producedAudio = false;
    for (uint32_t frame = 0u; frame < frameCount; ++frame) {
        float left = 0.0f;
        float right = 0.0f;
        if (!readStereoSample(left, right)) {
            g_underrunFrames.fetch_add(frameCount - frame, std::memory_order_relaxed);
            break;
        }

        if (leftOutput && rightOutput) {
            leftOutput[frame] = left;
            rightOutput[frame] = right;
        } else if (interleavedOutput) {
            interleavedOutput[frame * 2u] = left;
            interleavedOutput[frame * 2u + 1u] = right;
        }
        producedAudio = true;
    }

    if (isSilence) *isSilence = producedAudio ? NO : YES;
    return noErr;
}

void startAudioOnControlQueue() {
    if (g_backendState.load(std::memory_order_acquire) == 1 && g_audioEngine)
        return;

    NSError *error = nil;
    AVAudioSession *session = [AVAudioSession sharedInstance];
    if (![session setCategory:AVAudioSessionCategoryPlayback
                         mode:AVAudioSessionModeDefault
                      options:AVAudioSessionCategoryOptionMixWithOthers
                        error:&error]) {
        NSLog(@"XOWUE_AUDIO_BACKEND category failed: %@", error.localizedDescription);
    }

    error = nil;
    if (![session setPreferredSampleRate:48000.0 error:&error])
        NSLog(@"XOWUE_AUDIO_BACKEND sample-rate preference failed: %@", error.localizedDescription);

    error = nil;
    if (![session setPreferredIOBufferDuration:(double)kSamplesPerFrame / 48000.0
                                          error:&error]) {
        NSLog(@"XOWUE_AUDIO_BACKEND buffer-duration preference failed: %@", error.localizedDescription);
    }

    error = nil;
    if (![session setActive:YES error:&error]) {
        NSLog(@"XOWUE_AUDIO_BACKEND session activation failed: %@", error.localizedDescription);
    }

    AVAudioFormat *format = [[AVAudioFormat alloc]
        initWithCommonFormat:AVAudioPCMFormatFloat32
                  sampleRate:48000.0
                    channels:kChannels
                 interleaved:NO];
    if (!format) {
        g_backendState.store(-1, std::memory_order_release);
        g_startScheduled.store(false, std::memory_order_release);
        NSLog(@"XOWUE_AUDIO_BACKEND failed: unable to create 48 kHz stereo float format");
        return;
    }

    AVAudioEngine *engine = [[AVAudioEngine alloc] init];
    AVAudioSourceNode *source = [[AVAudioSourceNode alloc]
        initWithFormat:format
           renderBlock:^OSStatus(BOOL *isSilence,
                                const AudioTimeStamp *timestamp,
                                AVAudioFrameCount frames,
                                AudioBufferList *outputData) {
               (void)timestamp;
               return renderAudio(isSilence, frames, outputData);
           }];
    if (!source) {
        g_backendState.store(-1, std::memory_order_release);
        g_startScheduled.store(false, std::memory_order_release);
        NSLog(@"XOWUE_AUDIO_BACKEND failed: unable to create AVAudioSourceNode");
        return;
    }

    [engine attachNode:source];
    [engine connect:source to:engine.mainMixerNode format:format];
    engine.mainMixerNode.outputVolume = 1.0f;

    error = nil;
    if (![engine startAndReturnError:&error]) {
        g_backendState.store(-1, std::memory_order_release);
        g_startScheduled.store(false, std::memory_order_release);
        NSLog(@"XOWUE_AUDIO_BACKEND engine start failed: %@", error.localizedDescription);
        return;
    }

    g_audioEngine = engine;
    g_audioSource = source;
    g_backendState.store(1, std::memory_order_release);
    NSLog(@"XOWUE_AUDIO_BACKEND_STARTED sample_rate=48000 channels=2 format=float32");
}

} // namespace

extern "C" int XOWUEAudioStart(void) {
    if (g_backendState.load(std::memory_order_acquire) == 1) return 1;

    bool expected = false;
    if (g_startScheduled.compare_exchange_strong(expected, true,
                                                  std::memory_order_acq_rel)) {
        dispatch_async(audioControlQueue(), ^{
            @autoreleasepool {
                startAudioOnControlQueue();
            }
        });
    }
    return 1;
}

extern "C" void XOWUEAudioStop(void) {
    dispatch_async(audioControlQueue(), ^{
        [g_audioEngine stop];
        g_audioEngine = nil;
        g_audioSource = nil;
        g_readOffset = 0u;
        const uint32_t write = g_writeFrame.load(std::memory_order_acquire);
        g_readFrame.store(write, std::memory_order_release);
        g_backendState.store(0, std::memory_order_release);
        g_startScheduled.store(false, std::memory_order_release);
    });
}

extern "C" int XOWUEAudioSubmitStereoFrame(const float *interleaved,
                                            uint32_t frames) {
    if (!interleaved || frames != kSamplesPerFrame) return 0;

    const uint32_t write = g_writeFrame.load(std::memory_order_relaxed);
    const uint32_t read = g_readFrame.load(std::memory_order_acquire);
    if (write - read >= kAudioRingCapacity) {
        g_droppedFrames.fetch_add(1u, std::memory_order_relaxed);
        return 0;
    }

    std::memcpy(g_audioRing[write % kAudioRingCapacity].data(),
                interleaved, sizeof(float) * kSamplesPerFrame * kChannels);
    g_writeFrame.store(write + 1u, std::memory_order_release);
    return 1;
}

extern "C" uint32_t XOWUEAudioQueuedFrames(void) {
    const uint32_t write = g_writeFrame.load(std::memory_order_acquire);
    const uint32_t read = g_readFrame.load(std::memory_order_acquire);
    return write - read;
}

extern "C" uint64_t XOWUEAudioDroppedFrames(void) {
    return g_droppedFrames.load(std::memory_order_relaxed);
}

extern "C" uint64_t XOWUEAudioUnderrunFrames(void) {
    return g_underrunFrames.load(std::memory_order_relaxed);
}

extern "C" int XOWUEAudioBackendState(void) {
    return g_backendState.load(std::memory_order_acquire);
}
