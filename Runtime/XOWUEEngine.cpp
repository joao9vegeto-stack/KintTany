#include "xowue_engine.h"

#include "image.h"
#include "ppc_recomp_shared.h"
#include "XOWUEDispatchGuard.h"
#include "Graphics/Xenos/XOWUEGpuBridge.h"
#include "Graphics/Xenos/XOWUEGuestDraw.h"
#include "Graphics/Xenos/XOWUEDxt.h"
#include "xex.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <bit>
#include <cerrno>
#include <chrono>
#include <cstdarg>
#include <cctype>
#include <cstdlib>
#include <condition_variable>
#include <cstdio>
#include <cstring>
#include <deque>
#include <fstream>
#include <filesystem>
#include <iterator>
#include <limits>
#include <memory>
#include <mutex>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

#include <arpa/inet.h>
#include <fcntl.h>
#include <netdb.h>
#include <netinet/in.h>
#include <poll.h>
#include <sys/socket.h>
#include <sys/mman.h>
#include <sys/ioctl.h>
#include <sys/types.h>
#include <unistd.h>

extern "C" void xowue_vulkan_backend_guest_swap(uint32_t frontbuffer,
                                                 uint32_t width,
                                                 uint32_t height)
    __attribute__((weak));
extern "C" void xowue_vulkan_backend_guest_frame_rgba(
    uint32_t frontbuffer, uint32_t width, uint32_t height, uint32_t format,
    const uint8_t *rgba, size_t byte_count) __attribute__((weak));
extern "C" void xowue_vulkan_backend_guest_frame_reset(void) __attribute__((weak));

void pumpGuestXenosRingBuffer();
bool validGuestRange(uint32_t address, uint64_t size);
void xowue_NtClose(PPCContext &context);
void xowue_ExCreateThread(PPCContext &context, uint8_t *base);
uint32_t guestStackArgument(PPCContext &context, uint8_t *base,
                            uint32_t argumentIndex);

namespace {
uint32_t allocateGuestPhysicalRange(uint8_t *base, uint32_t requestedSize,
                                    uint32_t alignment, uint32_t protection);
bool releaseGuestPhysicalRange(uint32_t address);
void signalGuestEventHandle(uint32_t handle);
constexpr size_t kGuestAddressSpaceSize = static_cast<size_t>(PPC_MEMORY_SIZE);
constexpr uint32_t kInitialStackPointer = 0x7FFF0000u;
// Xbox 360 virtual and Xenos physical address spaces are separate.
constexpr uint32_t kFirstVirtualAllocation = 0x40000000u;
constexpr uint32_t kLastVirtualAllocation = 0x70000000u;
constexpr uint32_t kFirstPhysicalAllocation = 0x10000000u;
constexpr uint32_t kLastPhysicalAllocation = 0x20000000u;
static_assert(kLastPhysicalAllocation<=kFirstVirtualAllocation);
constexpr uint32_t kNtStatusSuccess = 0x00000000u;
constexpr uint32_t kNtStatusNotImplemented = 0xC0000002u;
constexpr uint32_t kNtStatusInvalidParameter = 0xC000000Du;
constexpr uint32_t kNtStatusBufferTooSmall = 0xC0000023u;
constexpr uint32_t kNtStatusInvalidParameter1 = 0xC00000EFu;
constexpr uint32_t kNtStatusInvalidParameter2 = 0xC00000F0u;
constexpr uint32_t kNtStatusInvalidParameter3 = 0xC00000F1u;
constexpr uint32_t kNtStatusNoMemory = 0xC0000017u;
constexpr uint32_t kNtStatusUnsuccessful = 0xC0000001u;
constexpr uint32_t kNtStatusMemoryNotAllocated = 0xC00000A0u;
constexpr uint32_t kXbox360PerformanceFrequency = 50000000u;
constexpr uint32_t kXamErrorNotFound = 0x80070490u;
constexpr uint32_t kXamErrorInvalidParameter = 0x80070057u;
constexpr uint32_t kNtStatusInvalidHandle = 0xC0000008u;
constexpr uint32_t kNtStatusObjectTypeMismatch = 0xC0000024u;
constexpr uint32_t kXboxEventObjectType = 0xD00EBEEFu;
constexpr uint32_t kXboxSemaphoreObjectType = 0xD017BEEFu;
constexpr uint32_t kXboxThreadObjectType = 0xD01BBEEFu;
constexpr uint32_t kFirstGuestEventObjectAddress = 0x7E000000u;
constexpr uint32_t kLastGuestEventObjectAddress = 0x7F000000u;
constexpr uint32_t kGuestEventObjectStride = 0x1000u;
constexpr uint32_t kNtStatusTimeout = 0x00000102u;
constexpr uint32_t kNtStatusCancelled = 0xC0000120u;
constexpr uint32_t kNtStatusAbandonedWait0 = 0x00000080u;
constexpr uint32_t kNtStatusWait0 = 0x00000000u;
constexpr uint32_t kNtStatusUserApc = 0x000000C0u;
constexpr size_t kTlsSlotCount = 4096;
constexpr uint32_t kDefaultTlsSlotCount = 1024u;
constexpr uint32_t kTlsOutOfIndexes = 0xFFFFFFFFu;
constexpr uint32_t kFirstGuestThreadStackTop = 0x7FE00000u;
constexpr uint32_t kMinimumGuestThreadStackAddress = 0x78000000u;
constexpr uint32_t kFirstGuestThreadObjectAddress = 0x7D000000u;
constexpr uint32_t kFirstGuestPcrAddress = 0x7C000000u;
constexpr uint32_t kFirstGuestTlsAddress = 0x7B000000u;
constexpr uint32_t kGuestThreadTlsStride = 0x10000u;
constexpr uint32_t kMainGuestTlsAddress = 0x7A000000u;
constexpr uint32_t kGuestThreadObjectSize = 0x0AB0u;
constexpr uint32_t kGuestKThreadApcDisableOffset = 0x0B0u;
constexpr uint32_t kGuestThreadMetadataStride = 0x1000u;
constexpr uint32_t kXenosShaderConstantFetchRegister = 0x4800u;
constexpr uint32_t kXenosGpuRegisterBase = 0x7FC80000u;
constexpr uint32_t kXenosCommandProcessorWritePointerOffset = 0x0714u;
constexpr uint32_t kXenosPm4SwapOpcode = 0x64u;
constexpr uint32_t kXenosPm4IndirectBufferOpcode = 0x3Fu;
constexpr uint32_t kXenosPm4DrawIndexOpcode = 0x22u;
constexpr uint32_t kXenosPm4DrawIndex2Opcode = 0x36u;
constexpr uint32_t kXenosPm4DrawIndexBinOpcode = 0x34u;
constexpr uint32_t kXenosPm4DrawIndex2BinOpcode = 0x35u;
constexpr uint32_t kXenosPm4EventWriteOpcode = 0x46u;
constexpr uint32_t kXInputButtonDPadUp = 0x0001u;
constexpr uint32_t kXInputButtonDPadDown = 0x0002u;
constexpr uint32_t kXInputButtonDPadLeft = 0x0004u;
constexpr uint32_t kXInputButtonDPadRight = 0x0008u;
constexpr uint32_t kXInputButtonStart = 0x0010u;
constexpr uint32_t kXInputButtonBack = 0x0020u;
constexpr uint32_t kXInputButtonLeftThumb = 0x0040u;
constexpr uint32_t kXInputButtonRightThumb = 0x0080u;
constexpr uint32_t kXInputButtonLeftShoulder = 0x0100u;
constexpr uint32_t kXInputButtonRightShoulder = 0x0200u;
constexpr uint32_t kXInputButtonA = 0x1000u;
constexpr uint32_t kXInputButtonB = 0x2000u;
constexpr uint32_t kXInputButtonX = 0x4000u;
constexpr uint32_t kXInputButtonY = 0x8000u;
constexpr uint32_t kXInputErrorDeviceNotConnected = 1167u;
constexpr uint32_t kXInputErrorBadArguments = 160u;

thread_local uint32_t g_currentGuestThreadId = 1;
thread_local std::array<uint32_t, kTlsSlotCount> g_tlsValues{};
thread_local std::array<uint32_t, kTlsSlotCount> g_tlsValueGenerations{};

struct XexTlsInfo {
    be<uint32_t> slotCount;
    be<uint32_t> rawDataAddress;
    be<uint32_t> dataSize;
    be<uint32_t> rawDataSize;
};

struct GuestReservation {
    uint32_t address;
    uint32_t size;
    uint32_t protection;
};
struct GuestCommit {
    uint32_t address;
    uint32_t size;
    uint32_t protection;
};
struct GuestWaitable {
    enum class Kind { Event, Thread, Semaphore, Mutant, Timer };
    Kind kind = Kind::Event;
    uint32_t handle = 0;
    uint32_t objectAddress = 0;
    bool manualReset;
    bool signaled;
    int32_t semaphoreCount = 0;
    int32_t semaphoreLimit = 0;
    uint32_t ownerThread = 0u;
    uint32_t recursion = 0u;
    uint64_t timerGeneration = 0u;
    uint64_t pulseGeneration = 0u;
    std::mutex mutex;
    std::condition_variable changed;
};
struct GuestFile {
    std::filesystem::path path;
    std::fstream stream;
    bool readable = false;
    bool writable = false;
    bool directory = false;
    std::vector<std::filesystem::path> entries;
    size_t directoryCursor = 0;
    std::shared_ptr<GuestWaitable> completion;
    std::mutex mutex;
};
struct GuestApc {
    uint32_t routine = 0u;
    uint32_t context = 0u;
    uint32_t argument1 = 0u;
    uint32_t argument2 = 0u;
};
struct GuestThread {
    uint32_t id = 0;
    uint32_t handle = 0;
    uint32_t objectAddress = 0;
    uint32_t pcrAddress = 0;
    uint32_t tlsAddress = 0;
    uint32_t stackBase = 0;
    uint32_t stackSize = 0;
    uint32_t startupAddress = 0;
    uint32_t startAddress = 0;
    uint32_t startContext = 0;
    uint32_t creationFlags = 0;
    std::atomic<uint32_t> suspendCount{0};
    std::atomic<uint32_t> exitStatus{kNtStatusSuccess};
    std::atomic<bool> exited{false};
    std::mutex stateMutex;
    std::mutex apcMutex;
    std::deque<GuestApc> pendingApcs;
    std::condition_variable stateChanged;
    std::condition_variable exitChanged;
    std::shared_ptr<GuestWaitable> completion;
    std::thread hostThread;
};

struct XenosFrontendState {
    uint32_t ringBufferAddress = 0;
    uint32_t ringBufferSize = 0;
    uint32_t ringReadPointer = 0;
    uint32_t readPointerWritebackAddress = 0;
    uint32_t readPointerBlockSizeLog2 = 0;
    uint32_t systemCommandBufferGpuAddress = 0;
    uint32_t graphicsInterruptCallback = 0;
    uint32_t graphicsInterruptContext = 0;
    std::array<uint32_t, 6> swapFetch{};
    uint8_t swapFetchMask = 0;
    bool swapFetchValid = false;
    uint32_t latestFrontbufferAddress = 0;
    uint32_t latestWidth = 0;
    uint32_t latestHeight = 0;
    uint64_t packets = 0;
    uint64_t draws = 0;
    uint64_t indirectBuffers = 0;
    uint64_t swaps = 0;
    uint64_t malformedPackets = 0;
    uint64_t decodedFrames = 0;
    uint64_t lastSwapTimestampNs = 0;
    bool enginesInitialized = false;
};

struct TouchControllerState {
    uint32_t buttons = 0;
    uint8_t leftTrigger = 0;
    uint8_t rightTrigger = 0;
    int16_t leftX = 0;
    int16_t leftY = 0;
    int16_t rightX = 0;
    int16_t rightY = 0;
    uint32_t packetNumber = 0;
};

uint32_t g_nextVirtualAllocation = kFirstVirtualAllocation;
uint32_t g_nextPhysicalAllocation = kFirstPhysicalAllocation;
uint32_t g_nextGuestHandle = 0x100u;
uint32_t g_nextGuestEventObjectAddress = kFirstGuestEventObjectAddress;
uint32_t g_nextGuestThreadId = 2u;
uint32_t g_nextGuestThreadStackTop = kFirstGuestThreadStackTop;
uint32_t g_nextGuestThreadObjectAddress = kFirstGuestThreadObjectAddress;
uint32_t g_nextGuestPcrAddress = kFirstGuestPcrAddress;
uint32_t g_nextGuestTlsAddress = kFirstGuestTlsAddress;
uint32_t g_mainThreadObjectAddress = kFirstGuestThreadObjectAddress - kGuestThreadMetadataStride;
uint32_t g_mainPcrAddress = kFirstGuestPcrAddress - kGuestThreadMetadataStride;
uint32_t g_mainTlsAddress = kMainGuestTlsAddress;
std::vector<GuestReservation> g_virtualAllocations;
std::vector<GuestCommit> g_virtualCommits;
std::vector<GuestReservation> g_physicalAllocations;
std::vector<std::string> g_runtimeTrace;
uint32_t g_xexSystemFlags = 0;
std::array<bool, kTlsSlotCount> g_tlsAllocated{};
std::array<uint32_t, kTlsSlotCount> g_tlsGenerations{};
size_t g_tlsSlotLimit = kDefaultTlsSlotCount;
uint32_t g_tlsStaticDataSize = 0;
uint32_t g_tlsRawDataAddress = 0;
uint32_t g_tlsRawDataSize = 0;
uint32_t g_tlsBlockSize = 0x1000u;
std::atomic<size_t> g_criticalSectionInitCount{0};
std::mutex g_runtimeTraceMutex;
std::mutex g_runtimeTraceFileMutex;
int g_runtimeTraceFileDescriptor = -1;
std::atomic<size_t> g_runtimeTracePersistSequence{0};
std::atomic<size_t> g_runtimeTracePersistFailures{0};
std::atomic<size_t> g_runtimeTracePersistMilestones{0};
std::atomic<size_t> g_runtimeTracePersistSwaps{0};
std::mutex g_tlsMutex;
std::mutex g_virtualMemoryMutex;
std::mutex g_guestObjectMutex;
std::mutex g_guestFileMutex;
std::mutex g_spinLockMapMutex;
std::mutex g_slistMutex;
std::mutex g_ioShareMutex;
std::mutex g_socketMutex;
std::mutex g_l2Mutex;
std::unordered_map<uint32_t, std::shared_ptr<GuestFile>> g_guestFiles;
std::unordered_map<uint32_t, PPCFunc *> g_aotFunctionMap;
std::unordered_map<uint32_t, std::shared_ptr<std::mutex>> g_guestSpinLocks;
std::unordered_map<uint32_t, std::pair<uint32_t, uint32_t>> g_ioShareByFileObject;
std::unordered_map<uint32_t, int> g_guestSockets;
std::unordered_set<uint32_t> g_guestXmaContexts;
thread_local int32_t g_wsaLastError = 0;
std::unordered_map<std::string, std::string> g_guestSymbolicLinks;
std::filesystem::path g_guestGameRoot;
std::filesystem::path g_guestSaveRoot;
thread_local uint32_t g_guestIrql = 0u;
std::mutex g_guestThreadMutex;
std::mutex g_guestStackMutex;
std::mutex g_criticalSectionMapMutex;
std::mutex g_waitSetMutex;
std::mutex g_xenosMutex;
std::mutex g_xenosPumpMutex;
std::mutex g_touchControllerMutex;
TouchControllerState g_touchController;
std::condition_variable g_waitSetChanged;
std::unordered_map<uint32_t, std::shared_ptr<GuestWaitable>> g_guestWaitables;
std::unordered_map<uint32_t, uint32_t> g_guestObjectReferences;
std::unordered_map<uint32_t, std::shared_ptr<GuestWaitable>> g_guestReferencedWaitables;
std::unordered_map<uint32_t, std::shared_ptr<GuestThread>> g_guestThreadsByHandle;
std::unordered_map<uint32_t, std::shared_ptr<GuestThread>> g_guestThreadsByObject;
std::shared_ptr<GuestThread> g_mainGuestThread;
std::unordered_map<uint32_t, std::shared_ptr<GuestWaitable>> g_guestPointerWaitables;
std::vector<std::shared_ptr<GuestThread>> g_guestThreads;
std::unordered_map<uint32_t, std::shared_ptr<std::recursive_mutex>> g_criticalSectionLocks;
XenosFrontendState g_xenosFrontend;
std::atomic<bool> g_schedulerStopRequested{false};
std::atomic<bool> g_runtimeSessionPoisoned{false};
thread_local GuestThread *g_currentGuestThread = nullptr;
std::unique_ptr<std::atomic<uint64_t>[]> g_aotExecutionBitmap;
size_t g_aotExecutionBitmapWords = 0u;
std::atomic<uint64_t> g_aotExecutionCalls{0u};
std::atomic<uint64_t> g_aotExecutionDistinct{0u};
std::atomic<bool> g_aotExecutionTelemetryActive{false};
std::atomic<uint32_t> g_lastAotGuestFunction{0u};
std::atomic<uint32_t> g_lastAotGuestThread{0u};

bool shouldPersistRuntimeTrace(const std::string &event, size_t sequence) {
    if (sequence < 96u) return true;
    if (sequence < 32768u && sequence % 64u == 0u) return true;

    const bool failure = event.find("exception") != std::string::npos ||
                         event.find("failed") != std::string::npos ||
                         event.find("rejected") != std::string::npos ||
                         event.find("untranslated") != std::string::npos;
    if (event.find("AOT execution") != std::string::npos &&
        g_runtimeTracePersistMilestones.fetch_add(1, std::memory_order_relaxed) < 128u) {
        return true;
    }

    if (failure && g_runtimeTracePersistFailures.fetch_add(1, std::memory_order_relaxed) < 128u) {
        return true;
    }

    const bool milestone = event.find("Chamando PPC entry point") != std::string::npos ||
                           event.find("Main PPC thread initialized") != std::string::npos ||
                           event.find("PPC thread started") != std::string::npos ||
                           event.find("PPC thread exit") != std::string::npos ||
                           event.find("VdInitializeEngines accepted") != std::string::npos ||
                           event.find("VdInitializeRingBuffer") != std::string::npos;
    if (milestone && g_runtimeTracePersistMilestones.fetch_add(1, std::memory_order_relaxed) < 96u) {
        return true;
    }

    if (event.find("VdSwap") != std::string::npos &&
        g_runtimeTracePersistSwaps.fetch_add(1, std::memory_order_relaxed) < 4u) {
        return true;
    }
    return false;
}

void persistRuntimeTrace(const std::string &tagged, size_t sequence) {
    if (!shouldPersistRuntimeTrace(tagged, sequence)) return;
    const std::string line = "RUNTIME seq=" + std::to_string(sequence) + " " + tagged + "\n";
    std::lock_guard<std::mutex> lock(g_runtimeTraceFileMutex);
    if (g_runtimeTraceFileDescriptor < 0) return;

    const char *cursor = line.data();
    size_t remaining = line.size();
    while (remaining > 0u) {
        const ssize_t written = ::write(g_runtimeTraceFileDescriptor, cursor, remaining);
        if (written < 0 && errno == EINTR) continue;
        if (written <= 0) break;
        cursor += written;
        remaining -= static_cast<size_t>(written);
    }
}

void recordRuntimeTrace(const std::string &event) {
    constexpr size_t kMaxTraceEvents = 128;
    const std::string tagged = "thread=" + std::to_string(g_currentGuestThreadId) + " " + event;
    {
        std::lock_guard<std::mutex> lock(g_runtimeTraceMutex);
        if (g_runtimeTrace.size() == kMaxTraceEvents) g_runtimeTrace.erase(g_runtimeTrace.begin());
        g_runtimeTrace.push_back(tagged);
    }
    const size_t sequence = g_runtimeTracePersistSequence.fetch_add(1, std::memory_order_relaxed);
    persistRuntimeTrace(tagged, sequence);
}

std::string runtimeTraceText() {
    std::vector<std::string> events;
    {
        std::lock_guard<std::mutex> lock(g_runtimeTraceMutex);
        events = g_runtimeTrace;
    }
    std::string result = "\n\nEVENTOS PPC RECENTES:";
    result += "\n- RtlInitializeCriticalSection calls=" + std::to_string(g_criticalSectionInitCount.load());
    for (const auto &event : events) {
        result += "\n- ";
        result += event;
    }
    XenosFrontendState graphics;
    {
        std::lock_guard<std::mutex> lock(g_xenosMutex);
        graphics = g_xenosFrontend;
    }
    result += "\n\nESTADO XENOS/VD:";
    result += "\n- engines=" + std::string(graphics.enginesInitialized ? "initialized" : "not-initialized");
    result += " ring=0x";
    char value[384];
    std::snprintf(value, sizeof(value), "%08X size=0x%08X rptr=%u readback=0x%08X swaps=%llu packets=%llu draws=%llu indirect=%llu malformed=%llu decoded_frames=%llu last=%ux%u frontbuffer=0x%08X",
                  graphics.ringBufferAddress, graphics.ringBufferSize,
                  graphics.ringReadPointer,
                  graphics.readPointerWritebackAddress,
                  static_cast<unsigned long long>(graphics.swaps),
                  static_cast<unsigned long long>(graphics.packets),
                  static_cast<unsigned long long>(graphics.draws),
                  static_cast<unsigned long long>(graphics.indirectBuffers),
                  static_cast<unsigned long long>(graphics.malformedPackets),
                  static_cast<unsigned long long>(graphics.decodedFrames),
                  graphics.latestWidth, graphics.latestHeight,
                  graphics.latestFrontbufferAddress);
    result += value;
    result += "\n- " + xowue::xenos::Diagnostics();
    return result;
}

struct GuestMemory final {
    uint8_t *base = nullptr;
    size_t size = 0;

    GuestMemory() : size(kGuestAddressSpaceSize) {
        int flags = MAP_PRIVATE | MAP_ANON;
#ifdef MAP_NORESERVE
        flags |= MAP_NORESERVE;
#endif
        void *mapping = mmap(nullptr, size, PROT_READ | PROT_WRITE, flags, -1, 0);
        if (mapping == MAP_FAILED) {
            base = nullptr;
            throw std::runtime_error("could not reserve 4 GiB guest address space");
        }
        base = static_cast<uint8_t *>(mapping);
    }

    ~GuestMemory() {
        if (base) munmap(base, size);
    }

    GuestMemory(const GuestMemory &) = delete;
    GuestMemory &operator=(const GuestMemory &) = delete;
};

std::weak_ptr<GuestMemory> g_activeGuestMemory;
// Xenos draws outlive PPC execution: the host render thread drains them after
// AOT has returned (including controlled fail-closed dispatch failures).
// Keep ONE guest mapping until the next boot; never dereference a dead weak_ptr.
std::mutex g_graphicsGuestMemoryMutex;
std::shared_ptr<GuestMemory> g_graphicsGuestMemory;
static std::shared_ptr<GuestMemory> acquireGraphicsGuestMemory() {
    std::lock_guard<std::mutex> lock(g_graphicsGuestMemoryMutex);
    return g_graphicsGuestMemory;
}
uint32_t g_activeImageBase = 0;
uint32_t g_activeEntryPoint = 0u;
std::vector<std::pair<uint32_t, uint32_t>> g_activeImageSections;
uint32_t g_activeExecutionInfoAddress = 0u;
constexpr uint32_t kXowueTitleId = 0x41560816u;

struct GuestThreadStopRequested final {};
struct GuestThreadExit final {
    explicit GuestThreadExit(uint32_t code) : exitCode(code) {}
    uint32_t exitCode;
};

using GuestTimeout = std::optional<std::chrono::nanoseconds>;

PPCFunc *findGuestFunction(uint32_t address) {
    const auto function = g_aotFunctionMap.find(address);
    return function == g_aotFunctionMap.end() ? nullptr : function->second;
}

void resetAotExecutionTelemetry() {
    g_aotExecutionTelemetryActive.store(false, std::memory_order_relaxed);
    g_aotExecutionBitmap.reset();
    g_aotExecutionBitmapWords = 0u;
    const uint64_t functionCount = (static_cast<uint64_t>(PPC_CODE_SIZE) + 3u) / 4u;
    const uint64_t wordCount = (functionCount + 63u) / 64u;
    if (wordCount == 0u || wordCount > std::numeric_limits<size_t>::max())
        throw std::runtime_error("AOT execution bitmap size is invalid");
    auto bitmap = std::make_unique<std::atomic<uint64_t>[]>(static_cast<size_t>(wordCount));
    for (size_t i = 0; i < static_cast<size_t>(wordCount); ++i)
        bitmap[i].store(0u, std::memory_order_relaxed);
    g_aotExecutionBitmap = std::move(bitmap);
    g_aotExecutionBitmapWords = static_cast<size_t>(wordCount);
    g_aotExecutionCalls.store(0u, std::memory_order_relaxed);
    g_aotExecutionDistinct.store(0u, std::memory_order_relaxed);
    g_lastAotGuestFunction.store(0u, std::memory_order_relaxed);
    g_lastAotGuestThread.store(0u, std::memory_order_relaxed);
    g_aotExecutionTelemetryActive.store(true, std::memory_order_release);
}

void recordAotFunctionExecution(uint32_t guestAddress) {
    if (!g_aotExecutionTelemetryActive.load(std::memory_order_acquire)) return;
    const uint64_t calls = g_aotExecutionCalls.fetch_add(1u, std::memory_order_relaxed) + 1u;
    const uint32_t threadId = g_currentGuestThread ? g_currentGuestThread->id : 0u;
    g_lastAotGuestFunction.store(guestAddress, std::memory_order_relaxed);
    g_lastAotGuestThread.store(threadId, std::memory_order_relaxed);

    if (guestAddress >= PPC_CODE_BASE && (guestAddress & 3u) == 0u) {
        const uint64_t offset = static_cast<uint64_t>(guestAddress) - PPC_CODE_BASE;
        if (offset < PPC_CODE_SIZE) {
            const uint64_t functionIndex = offset / 4u;
            const uint64_t wordIndex = functionIndex / 64u;
            if (wordIndex < g_aotExecutionBitmapWords) {
                const uint64_t mask = uint64_t{1} << (functionIndex & 63u);
                const uint64_t previous = g_aotExecutionBitmap[wordIndex].fetch_or(
                    mask, std::memory_order_relaxed);
                if ((previous & mask) == 0u)
                    g_aotExecutionDistinct.fetch_add(1u, std::memory_order_relaxed);
            }
        }
    }

    if (calls == 1u || calls % 65536u == 0u) {
        char event[192];
        std::snprintf(event, sizeof(event),
            "AOT execution milestone calls=%llu distinctGuestFunctions=%llu lastGuest=0x%08X thread=%u",
            static_cast<unsigned long long>(calls),
            static_cast<unsigned long long>(g_aotExecutionDistinct.load(std::memory_order_relaxed)),
            guestAddress, threadId);
        recordRuntimeTrace(event);
    }
}

void recordAotExecutionSummary(const char *reason) {
    if (!g_aotExecutionTelemetryActive.load(std::memory_order_acquire)) return;
    char event[224];
    std::snprintf(event, sizeof(event),
        "AOT execution summary reason=%s calls=%llu distinctGuestFunctions=%llu lastGuest=0x%08X thread=%u",
        reason ? reason : "unknown",
        static_cast<unsigned long long>(g_aotExecutionCalls.load(std::memory_order_relaxed)),
        static_cast<unsigned long long>(g_aotExecutionDistinct.load(std::memory_order_relaxed)),
        g_lastAotGuestFunction.load(std::memory_order_relaxed),
        g_lastAotGuestThread.load(std::memory_order_relaxed));
    recordRuntimeTrace(event);
}

void notifyGuestWaiters();

void queueGuestApc(GuestThread *thread, uint32_t routine, uint32_t apcContext,
                   uint32_t argument1, uint32_t argument2) {
    if (!thread || routine == 0u) return;
    routine &= ~1u;
    {
        std::lock_guard<std::mutex> lock(thread->apcMutex);
        thread->pendingApcs.push_back({routine, apcContext, argument1, argument2});
    }
    notifyGuestWaiters();
}

bool guestApcCanInterruptWait() {
    GuestThread *thread = g_currentGuestThread;
    const auto memory = g_activeGuestMemory.lock();
    uint8_t *base = memory ? memory->base : nullptr;
    if (!thread || g_guestIrql > 1u || !base ||
        !validGuestRange(thread->objectAddress + kGuestKThreadApcDisableOffset, 4u) ||
        static_cast<int32_t>(PPC_LOAD_U32(
            thread->objectAddress + kGuestKThreadApcDisableOffset)) < 0) {
        return false;
    }
    std::lock_guard<std::mutex> lock(thread->apcMutex);
    return !thread->pendingApcs.empty();
}

bool deliverPendingGuestApcs() {
    GuestThread *thread = g_currentGuestThread;
    const auto memory = g_activeGuestMemory.lock();
    uint8_t *base = memory ? memory->base : nullptr;
    if (!thread || g_guestIrql > 1u || !base ||
        !validGuestRange(thread->objectAddress + kGuestKThreadApcDisableOffset, 4u) ||
        static_cast<int32_t>(PPC_LOAD_U32(thread->objectAddress + kGuestKThreadApcDisableOffset)) < 0)
        return false;
    bool delivered = false;
    for (uint32_t count = 0; count < 64u; ++count) {
        GuestApc apc;
        {
            std::lock_guard<std::mutex> lock(thread->apcMutex);
            if (thread->pendingApcs.empty()) break;
            apc = thread->pendingApcs.front();
            thread->pendingApcs.pop_front();
        }
        PPCFunc *routine = findGuestFunction(apc.routine);
        if (!routine) {
            recordRuntimeTrace("queued APC routine is absent from AOT map address=0x" + [&] {
                char value[16]; std::snprintf(value, sizeof(value), "%08X", apc.routine);
                return std::string(value);
            }());
            continue;
        }
        PPCContext callback{};
        callback.r1.u32 = (thread->stackBase + thread->stackSize - 0x200u) & ~0xFu;
        callback.r2.u32 = g_activeImageBase;
        callback.r13.u32 = thread->pcrAddress;
        callback.lr = 0;
        callback.r3.u32 = apc.context;
        callback.r4.u32 = apc.argument1;
        callback.r5.u32 = apc.argument2;
        PPC_STORE_U32(callback.r1.u32, 0u);
        try {
            routine(callback, base);
            delivered = true;
        } catch (const std::exception &error) {
            recordRuntimeTrace(std::string("APC callback failed: ") + error.what());
        } catch (...) {
            recordRuntimeTrace("APC callback terminated with a guest control transfer");
        }
    }
    return delivered;
}

void notifyGuestWaiters() {
    g_waitSetChanged.notify_all();
    std::vector<std::shared_ptr<GuestWaitable>> waitables;
    {
        std::lock_guard<std::mutex> lock(g_guestObjectMutex);
        waitables.reserve(g_guestWaitables.size() + g_guestPointerWaitables.size());
        for (const auto &entry : g_guestWaitables) waitables.push_back(entry.second);
        for (const auto &entry : g_guestPointerWaitables) waitables.push_back(entry.second);
    }
    for (const auto &waitable : waitables) waitable->changed.notify_all();
    std::vector<std::shared_ptr<GuestThread>> threads;
    {
        std::lock_guard<std::mutex> lock(g_guestThreadMutex);
        threads = g_guestThreads;
    }
    for (const auto &thread : threads) thread->stateChanged.notify_all();
}

uint32_t allocateGuestHandle() {
    std::lock_guard<std::mutex> lock(g_guestObjectMutex);
    if (g_nextGuestHandle == 0 || g_nextGuestHandle == 0xFFFFFFFFu) return 0;
    return g_nextGuestHandle++;
}

uint32_t allocateGuestEventObjectAddress() {
    std::lock_guard<std::mutex> lock(g_guestObjectMutex);
    if (g_nextGuestEventObjectAddress > kLastGuestEventObjectAddress - kGuestEventObjectStride) return 0;
    const uint32_t address = g_nextGuestEventObjectAddress;
    g_nextGuestEventObjectAddress += kGuestEventObjectStride;
    return address;
}

std::shared_ptr<GuestWaitable> lookupGuestWaitable(uint32_t handleOrObject) {
    std::lock_guard<std::mutex> lock(g_guestObjectMutex);
    const auto handle = g_guestWaitables.find(handleOrObject);
    if (handle != g_guestWaitables.end()) return handle->second;
    const auto pointer = g_guestPointerWaitables.find(handleOrObject);
    if (pointer != g_guestPointerWaitables.end()) return pointer->second;
    const auto referenced = g_guestReferencedWaitables.find(handleOrObject);
    if (referenced != g_guestReferencedWaitables.end()) return referenced->second;
    return nullptr;
}

void writeGuestDispatcherSignalState(const std::shared_ptr<GuestWaitable> &waitable,
                                     int32_t signalState) {
    if (!waitable || waitable->objectAddress == 0u) return;
    const auto memory = g_activeGuestMemory.lock();
    uint8_t *base = memory ? memory->base : nullptr;
    const uint32_t signalAddress = waitable->objectAddress + 4u;
    if (base && validGuestRange(signalAddress, 4u))
        PPC_STORE_U32(signalAddress, static_cast<uint32_t>(signalState));
}

int32_t guestDispatcherSignalState(const GuestWaitable &waitable) {
    switch (waitable.kind) {
        case GuestWaitable::Kind::Semaphore:
            return waitable.semaphoreCount;
        case GuestWaitable::Kind::Mutant:
            return waitable.ownerThread == 0u
                ? 1
                : 1 - static_cast<int32_t>(std::min<uint32_t>(
                      waitable.recursion, static_cast<uint32_t>(INT32_MAX)));
        case GuestWaitable::Kind::Event:
        case GuestWaitable::Kind::Thread:
        case GuestWaitable::Kind::Timer:
            return waitable.signaled ? 1 : 0;
    }
    return 0;
}

void syncGuestDispatcherSignalState(const std::shared_ptr<GuestWaitable> &waitable) {
    if (!waitable) return;
    writeGuestDispatcherSignalState(waitable, guestDispatcherSignalState(*waitable));
}

std::shared_ptr<GuestThread> lookupGuestThread(uint32_t handleOrObject) {
    if (handleOrObject == 0xFFFFFFFEu ||
        (g_mainGuestThread && handleOrObject == g_mainGuestThread->objectAddress)) {
        return g_mainGuestThread;
    }
    std::lock_guard<std::mutex> lock(g_guestThreadMutex);
    const auto handle = g_guestThreadsByHandle.find(handleOrObject);
    if (handle != g_guestThreadsByHandle.end()) return handle->second;
    const auto object = g_guestThreadsByObject.find(handleOrObject);
    if (object != g_guestThreadsByObject.end()) return object->second;
    return nullptr;
}

std::shared_ptr<GuestWaitable> ensurePointerWaitable(uint32_t address, uint8_t *base) {
    if (!base || address > kGuestAddressSpaceSize - 8u) return nullptr;
    {
        std::lock_guard<std::mutex> lock(g_guestObjectMutex);
        const auto object = g_guestWaitables.find(address);
        if (object != g_guestWaitables.end()) return object->second;
        const auto found = g_guestPointerWaitables.find(address);
        if (found != g_guestPointerWaitables.end()) return found->second;
    }
    auto waitable = std::make_shared<GuestWaitable>();
    waitable->kind = GuestWaitable::Kind::Event;
    waitable->objectAddress = address;
    waitable->manualReset = (base[address] == 0u);
    waitable->signaled = PPC_LOAD_U32(address + 4u) != 0u;
    {
        std::lock_guard<std::mutex> lock(g_guestObjectMutex);
        const auto inserted = g_guestPointerWaitables.emplace(address, waitable);
        if (!inserted.second) return inserted.first->second;
    }
    return waitable;
}

bool readGuestTimeout(uint8_t *base, uint32_t pointer, GuestTimeout &timeout) {
    if (pointer == 0u) {
        timeout.reset();
        return true;
    }
    if (!base || pointer > kGuestAddressSpaceSize - sizeof(uint64_t)) return false;
    const int64_t guestTime = static_cast<int64_t>(PPC_LOAD_U64(pointer));
    constexpr int64_t kTicksPerSecond = 10000000;
    constexpr int64_t kFileTimeEpochOffset = 116444736000000000LL;
    constexpr int64_t kMaximumWaitTicks = 86400LL * kTicksPerSecond;
    int64_t waitTicks = guestTime;
    if (guestTime > 0) {
        const auto now = std::chrono::system_clock::now().time_since_epoch();
        const int64_t nowTicks = kFileTimeEpochOffset +
            std::chrono::duration_cast<std::chrono::nanoseconds>(now).count() / 100;
        waitTicks = guestTime - nowTicks;
    } else if (guestTime < 0) {
        waitTicks = guestTime == std::numeric_limits<int64_t>::min()
            ? kMaximumWaitTicks : -guestTime;
    }
    waitTicks = std::clamp<int64_t>(waitTicks, 0, kMaximumWaitTicks);
    timeout = std::chrono::nanoseconds(waitTicks * 100);
    return true;
}

uint32_t waitGuestObject(const std::shared_ptr<GuestWaitable> &waitable,
                         const GuestTimeout &timeout, bool alertable = false) {
    if (!waitable) return kNtStatusInvalidHandle;
    std::unique_lock<std::mutex> lock(waitable->mutex);
    const uint64_t initialPulseGeneration = waitable->pulseGeneration;
    const auto ready = [&] {
        const bool available = waitable->kind == GuestWaitable::Kind::Semaphore
            ? waitable->semaphoreCount > 0
            : waitable->kind == GuestWaitable::Kind::Mutant
                ? waitable->ownerThread == 0u || waitable->ownerThread == g_currentGuestThreadId
                : waitable->signaled;
        return available || waitable->pulseGeneration != initialPulseGeneration ||
               g_schedulerStopRequested.load() ||
               (alertable && guestApcCanInterruptWait());
    };
    const auto deadline = timeout ? std::optional<std::chrono::steady_clock::time_point>(
        std::chrono::steady_clock::now() + *timeout) : std::nullopt;
    for (;;) {
        if (alertable && guestApcCanInterruptWait()) {
            lock.unlock();
            const bool delivered = deliverPendingGuestApcs();
            lock.lock();
            if (delivered) return kNtStatusUserApc;
        }
        if (g_schedulerStopRequested.load() && g_currentGuestThreadId != 1u)
            throw GuestThreadStopRequested{};
        if (waitable->pulseGeneration != initialPulseGeneration)
            return kNtStatusWait0;
        const bool available = waitable->kind == GuestWaitable::Kind::Semaphore
            ? waitable->semaphoreCount > 0
            : waitable->kind == GuestWaitable::Kind::Mutant
                ? waitable->ownerThread == 0u || waitable->ownerThread == g_currentGuestThreadId
                : waitable->signaled;
        if (available) {
            if (waitable->kind == GuestWaitable::Kind::Semaphore) {
                --waitable->semaphoreCount;
                waitable->signaled = waitable->semaphoreCount > 0;
            } else if (waitable->kind == GuestWaitable::Kind::Mutant) {
                waitable->ownerThread = g_currentGuestThreadId;
                ++waitable->recursion;
                waitable->signaled = false;
            } else if (!waitable->manualReset) waitable->signaled = false;
            syncGuestDispatcherSignalState(waitable);
            return kNtStatusSuccess;
        }
        if (deadline) {
            if (std::chrono::steady_clock::now() >= *deadline) return kNtStatusTimeout;
            waitable->changed.wait_until(lock, *deadline, ready);
        } else {
            waitable->changed.wait(lock, ready);
        }
    }
}

uint32_t waitGuestObjects(const std::vector<std::shared_ptr<GuestWaitable>> &waitables,
                          uint32_t waitType, const GuestTimeout &timeout,
                          bool alertable = false) {
    if (waitables.empty() || waitables.size() > 64u || waitType > 1u) {
        return kNtStatusInvalidParameter;
    }
    std::vector<uint64_t> initialPulseGenerations;
    initialPulseGenerations.reserve(waitables.size());
    for (const auto &waitable : waitables) {
        if (!waitable) return kNtStatusInvalidHandle;
        std::lock_guard<std::mutex> objectLock(waitable->mutex);
        initialPulseGenerations.push_back(waitable->pulseGeneration);
    }
    const auto readyIndex = [&]() -> int32_t {
        int32_t firstReady = -1;
        bool allReady = true;
        for (size_t index = 0; index < waitables.size(); ++index) {
            if (!waitables[index]) return -2;
            std::lock_guard<std::mutex> objectLock(waitables[index]->mutex);
            const auto &candidate = *waitables[index];
            const bool signaled = candidate.kind == GuestWaitable::Kind::Semaphore
                ? candidate.semaphoreCount > 0
                : candidate.kind == GuestWaitable::Kind::Mutant
                    ? candidate.ownerThread == 0u || candidate.ownerThread == g_currentGuestThreadId
                    : candidate.signaled;
            const bool pulsed = candidate.pulseGeneration != initialPulseGenerations[index];
            if (!signaled && !pulsed) allReady = false;
            else if (firstReady < 0) firstReady = static_cast<int32_t>(index);
        }
        if (waitType == 0u) return allReady ? 0 : -1; // WaitAll.
        return firstReady; // WaitAny.
    };

    const auto deadline = timeout ? std::optional<std::chrono::steady_clock::time_point>(
        std::chrono::steady_clock::now() + *timeout) : std::nullopt;
    for (;;) {
        if (alertable && guestApcCanInterruptWait() && deliverPendingGuestApcs())
            return kNtStatusUserApc;
        int32_t selected = -1;
        {
            std::unique_lock<std::mutex> waitLock(g_waitSetMutex);
            selected = readyIndex();
            if (selected == -2) return kNtStatusInvalidHandle;
            if (selected < 0 && g_schedulerStopRequested.load()) {
                if (g_currentGuestThreadId != 1u) throw GuestThreadStopRequested{};
                return kNtStatusCancelled;
            }
            if (selected >= 0) {
                if (waitType == 0u) {
                    for (const auto &waitable : waitables) {
                        std::lock_guard<std::mutex> objectLock(waitable->mutex);
                        if (waitable->kind == GuestWaitable::Kind::Semaphore) {
                            --waitable->semaphoreCount;
                            waitable->signaled = waitable->semaphoreCount > 0;
                        } else if (waitable->kind == GuestWaitable::Kind::Mutant) {
                            waitable->ownerThread = g_currentGuestThreadId;
                            ++waitable->recursion;
                            waitable->signaled = false;
                        } else if (!waitable->manualReset) waitable->signaled = false;
                        syncGuestDispatcherSignalState(waitable);
                    }
                    return kNtStatusWait0;
                }
                auto &waitable = waitables[static_cast<size_t>(selected)];
                std::lock_guard<std::mutex> objectLock(waitable->mutex);
                if (waitable->kind == GuestWaitable::Kind::Semaphore) {
                    --waitable->semaphoreCount;
                    waitable->signaled = waitable->semaphoreCount > 0;
                } else if (waitable->kind == GuestWaitable::Kind::Mutant) {
                    waitable->ownerThread = g_currentGuestThreadId;
                    ++waitable->recursion;
                    waitable->signaled = false;
                } else if (!waitable->manualReset) waitable->signaled = false;
                syncGuestDispatcherSignalState(waitable);
                return kNtStatusWait0 + static_cast<uint32_t>(selected);
            }
            if (deadline) {
                if (std::chrono::steady_clock::now() >= *deadline) return kNtStatusTimeout;
                g_waitSetChanged.wait_until(waitLock, *deadline, [&] {
                    return g_schedulerStopRequested.load() || readyIndex() >= 0 ||
                           (alertable && guestApcCanInterruptWait());
                });
            } else {
                g_waitSetChanged.wait(waitLock, [&] {
                    return g_schedulerStopRequested.load() || readyIndex() >= 0 ||
                           (alertable && guestApcCanInterruptWait());
                });
            }
        }
    }
}

void signalGuestWaitable(const std::shared_ptr<GuestWaitable> &waitable) {
    if (!waitable) return;
    {
        std::lock_guard<std::mutex> lock(waitable->mutex);
        waitable->signaled = true;
        syncGuestDispatcherSignalState(waitable);
    }
    waitable->changed.notify_all();
    g_waitSetChanged.notify_all();
}

void signalGuestEventHandle(uint32_t handle) {
    if (handle == 0u) return;
    const auto waitable = lookupGuestWaitable(handle);
    if (!waitable || waitable->kind != GuestWaitable::Kind::Event) return;
    signalGuestWaitable(waitable);
}

struct GuestEventSignalOnReturn final {
    explicit GuestEventSignalOnReturn(uint32_t eventHandle) : handle(eventHandle) {}
    ~GuestEventSignalOnReturn() { signalGuestEventHandle(handle); }
    uint32_t handle;
};

std::shared_ptr<std::recursive_mutex> criticalSectionLock(uint32_t address) {
    std::lock_guard<std::mutex> lock(g_criticalSectionMapMutex);
    auto &entry = g_criticalSectionLocks[address];
    if (!entry) entry = std::make_shared<std::recursive_mutex>();
    return entry;
}

bool allocateGuestThreadStack(uint32_t requestedSize, uint32_t &stackBase,
                              uint32_t &stackSize) {
    constexpr uint32_t kPageSize = 0x1000u;
    if (requestedSize == 0u) requestedSize = 0x00100000u;
    requestedSize = std::max<uint32_t>(requestedSize, 0x4000u);
    const uint64_t aligned = (static_cast<uint64_t>(requestedSize) + kPageSize - 1u) &
                            ~static_cast<uint64_t>(kPageSize - 1u);
    if (aligned > 0x01000000u) return false;
    std::lock_guard<std::mutex> lock(g_guestStackMutex);
    if (g_nextGuestThreadStackTop < kMinimumGuestThreadStackAddress + aligned) return false;
    stackSize = static_cast<uint32_t>(aligned);
    stackBase = g_nextGuestThreadStackTop - stackSize;
    g_nextGuestThreadStackTop = stackBase;
    return true;
}

void initializeGuestThreadEnvironment(uint8_t *base, uint32_t objectAddress,
                                      uint32_t pcrAddress, uint32_t tlsAddress,
                                      uint32_t stackBase, uint32_t stackSize,
                                      uint32_t threadId, uint32_t startAddress,
                                      uint32_t creationFlags, uint32_t suspendCount) {
    if (!base || objectAddress > kGuestAddressSpaceSize - kGuestThreadObjectSize ||
        pcrAddress > kGuestAddressSpaceSize - 0x200u ||
        tlsAddress > kGuestAddressSpaceSize - g_tlsBlockSize ||
        stackBase > kGuestAddressSpaceSize - stackSize) {
        throw std::runtime_error("invalid guest thread metadata range");
    }

    std::memset(base + objectAddress, 0, kGuestThreadObjectSize);
    std::memset(base + pcrAddress, 0, 0x200u);
    std::memset(base + tlsAddress, 0, g_tlsBlockSize);
    if (g_tlsRawDataSize != 0u) {
        std::memcpy(base + tlsAddress, base + g_tlsRawDataAddress, g_tlsRawDataSize);
    }
    std::memset(base + stackBase, 0, stackSize);

    // X_KTHREAD / KPCR layouts follow the retail Xbox 360 ABI used by Xenia.
    // r13 points at KPCR; the image base remains in r2.
    base[objectAddress + 0x00u] = 6u; // Dispatcher object: thread.
    PPC_STORE_U32(objectAddress + 0x10u, objectAddress + 0x10u);
    PPC_STORE_U32(objectAddress + 0x14u, objectAddress + 0x10u);
    PPC_STORE_U32(objectAddress + 0x40u, objectAddress + 0x20u);
    PPC_STORE_U32(objectAddress + 0x44u, objectAddress + 0x20u);
    PPC_STORE_U32(objectAddress + 0x48u, objectAddress);
    PPC_STORE_U32(objectAddress + 0x4Cu, objectAddress + 0x18u);
    PPC_STORE_U16(objectAddress + 0x54u, 0x0102u);
    PPC_STORE_U16(objectAddress + 0x56u, 1u);
    PPC_STORE_U32(objectAddress + 0x5Cu, stackBase + stackSize);
    PPC_STORE_U32(objectAddress + 0x60u, stackBase);
    PPC_STORE_U32(objectAddress + 0x68u, tlsAddress);
    PPC_STORE_U32(objectAddress + 0x74u, objectAddress + 0x74u);
    PPC_STORE_U32(objectAddress + 0x78u, objectAddress + 0x74u);
    PPC_STORE_U32(objectAddress + 0x7Cu, objectAddress + 0x7Cu);
    PPC_STORE_U32(objectAddress + 0x80u, objectAddress + 0x7Cu);
    PPC_STORE_U32(objectAddress + 0x9Cu, 0xFDFFD7FFu);
    base[objectAddress + 0xBCu] = static_cast<uint8_t>(std::min(suspendCount, 0xFFu));
    base[objectAddress + 0xBFu] = 0u;
    PPC_STORE_U32(objectAddress + 0xD0u, stackBase + stackSize);
    PPC_STORE_U32(objectAddress + 0x140u, kNtStatusSuccess);
    PPC_STORE_U32(objectAddress + 0x14Cu, threadId);
    PPC_STORE_U32(objectAddress + 0x150u, startAddress);
    PPC_STORE_U32(objectAddress + 0x16Cu, creationFlags);
    PPC_STORE_U32(objectAddress + 0x17Cu, 1u);

    PPC_STORE_U32(pcrAddress + 0x00u, tlsAddress);
    PPC_STORE_U32(pcrAddress + 0x30u, pcrAddress);
    PPC_STORE_U32(pcrAddress + 0x70u, stackBase + stackSize);
    PPC_STORE_U32(pcrAddress + 0x74u, stackBase);
    PPC_STORE_U32(pcrAddress + 0x100u, objectAddress);
    base[pcrAddress + 0x10Cu] = 0u;
    PPC_STORE_U32(pcrAddress + 0x150u, 0u);
}

uint32_t allocateGuestPhysicalRange(uint8_t *base, uint32_t requestedSize,
                                    uint32_t alignment, uint32_t protection) {
    if (!base || requestedSize == 0u) return 0u;
    constexpr uint32_t kPageSize = 0x1000u;
    alignment = std::max(alignment, kPageSize);
    if ((alignment & (alignment - 1u)) != 0u) return 0u;
    const uint64_t roundedSize = (static_cast<uint64_t>(requestedSize) + kPageSize - 1u) &
                                 ~static_cast<uint64_t>(kPageSize - 1u);
    if (roundedSize == 0 || roundedSize > std::numeric_limits<uint32_t>::max()) return 0u;
    const uint32_t size = static_cast<uint32_t>(roundedSize);

    std::lock_guard<std::mutex> lock(g_virtualMemoryMutex);
    uint64_t candidate = (static_cast<uint64_t>(g_nextPhysicalAllocation) + alignment - 1u) &
                         ~static_cast<uint64_t>(alignment - 1u);
    while (candidate + size <= kLastPhysicalAllocation) {
        bool moved = false;
        for (const auto &allocation : g_physicalAllocations) {
            const uint64_t allocationEnd = static_cast<uint64_t>(allocation.address) + allocation.size;
            if (candidate < allocationEnd && candidate + size > allocation.address) {
                candidate = (allocationEnd + alignment - 1u) &
                            ~static_cast<uint64_t>(alignment - 1u);
                moved = true;
                break;
            }
        }
        if (moved) continue;
        if (candidate < kFirstPhysicalAllocation || candidate + size > kLastPhysicalAllocation) return 0u;
        const uint32_t address = static_cast<uint32_t>(candidate);
        g_physicalAllocations.push_back({address, size, protection});
                 g_nextPhysicalAllocation = static_cast<uint32_t>(candidate + size);
        std::memset(base + address, 0, size);
        return address;
    }
    return 0u;
}

bool releaseGuestPhysicalRange(uint32_t address) {
    std::lock_guard<std::mutex> lock(g_virtualMemoryMutex);
    const auto allocation=std::find_if(
        g_physicalAllocations.begin(),g_physicalAllocations.end(),
        [address](const auto& it){return it.address==address;});
    if(allocation==g_physicalAllocations.end())return false;
    const uint64_t end=uint64_t(allocation->address)+allocation->size;
    if(end==g_nextPhysicalAllocation)
        g_nextPhysicalAllocation=allocation->address;
    g_physicalAllocations.erase(allocation);
    return true;
}

void checkpointGuestThread() {
    GuestThread *thread = g_currentGuestThread;
    if (!thread) return;
    if (g_schedulerStopRequested.load()) throw GuestThreadStopRequested{};
    if (thread->suspendCount.load() == 0u) return;
    std::unique_lock<std::mutex> lock(thread->stateMutex);
    thread->stateChanged.wait(lock, [&] {
        return thread->suspendCount.load() == 0u || g_schedulerStopRequested.load();
    });
    if (g_schedulerStopRequested.load()) throw GuestThreadStopRequested{};
}

void finishGuestThread(const std::shared_ptr<GuestThread> &thread, uint32_t exitCode) {
    thread->exitStatus.store(exitCode);
    char event[120];
    std::snprintf(event, sizeof(event), "PPC thread exit id=%u code=0x%08X", thread->id, exitCode);
    recordRuntimeTrace(event);
    signalGuestWaitable(thread->completion);
    thread->exited.store(true);
    thread->exitChanged.notify_all();
}

void requestGuestSchedulerStop() {
    g_schedulerStopRequested.store(true);
    g_waitSetChanged.notify_all();
    notifyGuestWaiters();
}

void stopGuestThreads() {
    requestGuestSchedulerStop();
    std::vector<std::shared_ptr<GuestThread>> threads;
    {
        std::lock_guard<std::mutex> lock(g_guestThreadMutex);
        threads = g_guestThreads;
    }
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(3);
    bool orphaned = false;
    for (const auto &thread : threads) {
        if (!thread->hostThread.joinable()) continue;
        {
            std::unique_lock<std::mutex> lock(thread->stateMutex);
            if (!thread->exitChanged.wait_until(lock, deadline, [&] { return thread->exited.load(); })) {
                orphaned = true;
                thread->hostThread.detach();
                char event[120];
                std::snprintf(event, sizeof(event), "PPC thread id=%u did not stop before session deadline; guest memory retained", thread->id);
                recordRuntimeTrace(event);
                continue;
            }
        }
        thread->hostThread.join();
    }
    if (orphaned) {
        g_runtimeSessionPoisoned.store(true);
        return;
    }
    {
        std::lock_guard<std::mutex> lock(g_guestObjectMutex);
        g_guestWaitables.clear();
        g_guestPointerWaitables.clear();
    }
    {
        std::lock_guard<std::mutex> lock(g_guestThreadMutex);
        g_guestThreadsByHandle.clear();
        g_guestThreadsByObject.clear();
        g_guestThreads.clear();
    }
    g_mainGuestThread.reset();
    {
        std::lock_guard<std::mutex> lock(g_criticalSectionMapMutex);
        g_criticalSectionLocks.clear();
    }
    g_activeGuestMemory.reset();
}

struct GuestSchedulerSessionGuard final {
    bool stopped = false;
    void stop() {
        if (!stopped) {
            stopGuestThreads();
            stopped = true;
        }
    }
    ~GuestSchedulerSessionGuard() { stop(); }
};

struct GuestXenosPumpSessionGuard final {
    std::atomic<bool> stopRequested{false};
    std::thread worker;

    GuestXenosPumpSessionGuard()
        : worker([this] {
              while (!stopRequested.load(std::memory_order_relaxed)) {
                  try {
                      pumpGuestXenosRingBuffer();
                  } catch (const std::exception &error) {
                      recordRuntimeTrace(std::string("Xenos ring worker: ") + error.what());
                  } catch (...) {
                      recordRuntimeTrace("Xenos ring worker: unknown host exception");
                  }
                  std::this_thread::sleep_for(std::chrono::milliseconds(1));
              }
          }) {}

    ~GuestXenosPumpSessionGuard() {
        stopRequested.store(true, std::memory_order_relaxed);
        if (worker.joinable()) worker.join();
    }
};

struct GuestThreadBinding final {
    GuestThread *previousThread = nullptr;
    uint32_t previousId = 1u;
    uint32_t previousIrql = 0u;
    explicit GuestThreadBinding(GuestThread *thread)
        : previousThread(g_currentGuestThread), previousId(g_currentGuestThreadId),
          previousIrql(g_guestIrql) {
        g_currentGuestThread = thread;
        g_currentGuestThreadId = thread ? thread->id : 1u;
        g_guestIrql = 0u;
    }
    ~GuestThreadBinding() {
        g_currentGuestThread = previousThread;
        g_currentGuestThreadId = previousId;
        g_guestIrql = previousIrql;
    }
};

struct GuestFirmwareReturn final : std::runtime_error {
    explicit GuestFirmwareReturn(const PPCContext &context)
        : std::runtime_error("guest requested a firmware return"),
          routine(context.r3.u32), returnAddress(static_cast<uint32_t>(context.lr)) {}
    uint32_t routine;
    uint32_t returnAddress;
};

std::vector<uint8_t> readFile(const char *path) {
    if (!path || !*path) throw std::runtime_error("missing XEX path");
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("cannot open the selected XEX");
    input.seekg(0, std::ios::end);
    const auto end = input.tellg();
    if (end <= 0) throw std::runtime_error("selected XEX is empty");
    input.seekg(0, std::ios::beg);
    std::vector<uint8_t> bytes(static_cast<size_t>(end));
    input.read(reinterpret_cast<char *>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
    if (!input) throw std::runtime_error("could not read the complete XEX file");
    return bytes;
}

Image parseImage(const char *path) {
    const auto file = readFile(path);
    if (file.size() < 4 || std::memcmp(file.data(), "XEX2", 4) != 0) {
        throw std::runtime_error("the selected file is not an XEX2 executable");
    }
    Image image = Image::ParseImage(file.data(), file.size());
    if (!image.data || image.size == 0 || image.sections.empty()) {
        throw std::runtime_error("XEX parsing failed (unsupported or damaged image)");
    }
    if (image.base != PPC_IMAGE_BASE) {
        throw std::runtime_error("XEX image base does not match this AOT build");
    }
    if (image.entry_point == 0) throw std::runtime_error("XEX has no entry point");
    g_xexSystemFlags = 0;
    g_tlsSlotLimit = kDefaultTlsSlotCount;
    g_tlsStaticDataSize = 0u;
    g_tlsRawDataAddress = 0u;
    g_tlsRawDataSize = 0u;
    if (const void *flags = getOptHeaderPtr(file.data(), XEX_HEADER_SYSTEM_FLAGS)) {
        g_xexSystemFlags = static_cast<const be<uint32_t> *>(flags)->get();
    }
    if (const void *tls = getOptHeaderPtr(file.data(), XEX_HEADER_TLS_INFO)) {
        const auto *info = static_cast<const XexTlsInfo *>(tls);
        const uint32_t requestedSlots = info->slotCount.get();
        g_tlsSlotLimit = requestedSlots == 0u ? kDefaultTlsSlotCount : requestedSlots;
        g_tlsRawDataAddress = info->rawDataAddress.get();
        g_tlsStaticDataSize = info->dataSize.get();
        g_tlsRawDataSize = info->rawDataSize.get();
    }
    if (g_tlsSlotLimit > kTlsSlotCount || g_tlsRawDataSize > g_tlsStaticDataSize) {
        throw std::runtime_error("XEX TLS layout exceeds the supported slot/data limits");
    }
    const uint64_t tlsBytes = static_cast<uint64_t>(g_tlsStaticDataSize) +
                              static_cast<uint64_t>(g_tlsSlotLimit) * sizeof(uint32_t);
    const uint64_t tlsRounded = (tlsBytes + 0xFFFu) & ~uint64_t{0xFFFu};
    if (tlsRounded == 0u || tlsRounded > kGuestThreadTlsStride) {
        throw std::runtime_error("XEX TLS block is larger than the reserved 64 KiB per-thread range");
    }
    g_tlsBlockSize = static_cast<uint32_t>(tlsRounded);
    if (g_tlsRawDataSize != 0u) {
        const uint64_t rawEnd = static_cast<uint64_t>(g_tlsRawDataAddress) + g_tlsRawDataSize;
        const bool insideImageSection = std::any_of(image.sections.begin(), image.sections.end(),
            [rawEnd](const auto &section) {
                const uint64_t sectionEnd = static_cast<uint64_t>(section.base) + section.size;
                return section.base <= g_tlsRawDataAddress && rawEnd <= sectionEnd;
            });
        if (!insideImageSection) {
            throw std::runtime_error("XEX TLS raw data address is outside its loaded sections");
        }
    }
    return image;
}

void copyImage(const Image &image, GuestMemory &memory) {
    for (const auto &section : image.sections) {
        const uint64_t end = static_cast<uint64_t>(section.base) + section.size;
        if (section.base >= memory.size || end > memory.size || !section.data) {
            throw std::runtime_error("XEX section lies outside the 32-bit guest address space");
        }
        if (section.base < image.base) {
            throw std::runtime_error("XEX section begins below the image base");
        }
        const uint64_t imageOffset = section.base - image.base;
        const uint32_t sourceSize = imageOffset >= image.size
            ? 0
            : static_cast<uint32_t>(std::min<uint64_t>(section.size, image.size - imageOffset));
        if (sourceSize != 0) {
            std::memcpy(memory.base + section.base, image.data.get() + imageOffset, sourceSize);
        }
        if (sourceSize < section.size) {
            std::memset(memory.base + section.base + sourceSize, 0, section.size - sourceSize);
        }
    }
}

size_t installDispatchTable(GuestMemory &memory) {
    const uint64_t tableStart = PPC_IMAGE_BASE + PPC_IMAGE_SIZE;
    const uint64_t tableEnd = tableStart + static_cast<uint64_t>(PPC_CODE_SIZE) * 2;
    if (tableEnd > memory.size) throw std::runtime_error("AOT dispatch table exceeds guest address space");

    size_t installed = 0;
    g_aotFunctionMap.clear();
    g_aotFunctionMap.reserve(90000u);
    for (const PPCFuncMapping *mapping = PPCFuncMappings; mapping->host; ++mapping) {
        if (mapping->guest < PPC_CODE_BASE) continue;
        const uint64_t codeOffset = mapping->guest - PPC_CODE_BASE;
        if (codeOffset >= PPC_CODE_SIZE) continue;
        g_aotFunctionMap[mapping->guest] = mapping->host;
        const uint64_t slotOffset = tableStart + codeOffset * 2;
        auto **slot = reinterpret_cast<PPCFunc **>(memory.base + slotOffset);
        *slot = mapping->host;
        ++installed;
    }
    if (installed == 0) throw std::runtime_error("AOT function dispatch table is empty");
    return installed;
}

void writeMessage(char *output, size_t capacity, const char *format, ...) {
    if (!output || capacity == 0) return;
    va_list args;
    va_start(args, format);
    std::vsnprintf(output, capacity, format, args);
    va_end(args);
    output[capacity - 1] = '\0';
}

int fail(char *output, size_t capacity, const std::exception &error) {
    recordAotExecutionSummary("exception");
    g_aotExecutionTelemetryActive.store(false, std::memory_order_release);
    const std::string trace = runtimeTraceText();
    writeMessage(output, capacity, "Falha: %s%s", error.what(), trace.c_str());
    return 1;
}

} // namespace

void xowue_thread_checkpoint() {
    checkpointGuestThread();
    pumpGuestXenosRingBuffer();
}

void xowue_thread_checkpoint(uint32_t guestAddress) {
    recordAotFunctionExecution(guestAddress);
    xowue_thread_checkpoint();
}

static const char *dispatchGuardErrorName(xowue_dispatch_guard::Result result) {
    using Result = xowue_dispatch_guard::Result;
    switch (result) {
        case Result::ok: return "ok";
        case Result::null_base: return "null guest memory";
        case Result::target_below_code: return "target below AOT code range";
        case Result::target_out_of_code: return "target outside AOT code range";
        case Result::target_unaligned: return "unaligned PPC target";
        case Result::table_out_of_memory: return "dispatch slot outside guest memory";
        case Result::empty_slot: return "AOT dispatch slot is empty";
    }
    return "unknown dispatch guard result";
}

extern "C" void XOWUECrashRecorderWriteFatal(const char *message) __attribute__((weak));

[[noreturn]] static void failPpcIndirectDispatch(
    PPCContext &context, uint32_t target, PPCFunc *slotFunction,
    const char *reason) {
    const uint32_t lr = static_cast<uint32_t>(context.lr);
    const uint32_t threadId = g_currentGuestThread ? g_currentGuestThread->id : 0u;
    // Real source PPC branch is bctrl (4E800421): report CTR rather than
    // inventing any destination or switching to a PPC interpreter.
#if defined(PPC_CONFIG_CTR_AS_LOCAL)
    const uint32_t ctr = target;
#else
    const uint32_t ctr = context.ctr.u32;
#endif
    uint32_t nearbyOpcodes[8]{};
    const uint32_t firstOpcode=lr>=32u ? lr-32u : 0u;
    const auto opcodeMemory=acquireGraphicsGuestMemory();
    const bool nearbyValid=firstOpcode && validGuestRange(firstOpcode,32u) &&
       opcodeMemory && opcodeMemory->base;
    if(nearbyValid) for(uint32_t i=0;i<8u;++i) {
       const uint32_t p=firstOpcode+4u*i;
       nearbyOpcodes[i]=(uint32_t(opcodeMemory->base[p])<<24u) |
           (uint32_t(opcodeMemory->base[p+1u])<<16u) |
           (uint32_t(opcodeMemory->base[p+2u])<<8u) |
           uint32_t(opcodeMemory->base[p+3u]);
    }
    // Capture actual AOT site and PPC branch operands. Never guess or
    // substitute a new destination for an invalid indirect call.
    uint8_t site[4]{};
    const auto graphicsMemory = acquireGraphicsGuestMemory();
    const bool siteValid = lr>=4u && validGuestRange(lr-4u,4u) &&
       graphicsMemory && graphicsMemory->base;
    if (siteValid) std::memcpy(site,graphicsMemory->base+lr-4u,4u);
    char event[1152];
    std::snprintf(event, sizeof(event),
        "PPC indirect dispatch failed reason=%s guestTarget=0x%08X CTR=0x%08X LR=0x%08X lrMinus4Unverified=0x%08X callsite_bytes=%s%02X%02X%02X%02X "
        "nearby_start=%08X opcodes=%s%08X,%08X,%08X,%08X,%08X,%08X,%08X,%08X "
        "r0=%08X r1=%08X r2=%08X r3=%08X r4=%08X r5=%08X r6=%08X r7=%08X r8=%08X r9=%08X r10=%08X r11=%08X r12=%08X r31=%08X "
        "lastAotEntry=0x%08X thread=%u slot=0x%llX",
        reason ? reason : "unknown",target,ctr,lr,lr>=4u?lr-4u:0u,
        siteValid?"":"unavailable:",site[0],site[1],site[2],site[3],
        firstOpcode,nearbyValid?"":"unavailable:",
        nearbyOpcodes[0],nearbyOpcodes[1],nearbyOpcodes[2],nearbyOpcodes[3],
        nearbyOpcodes[4],nearbyOpcodes[5],nearbyOpcodes[6],nearbyOpcodes[7],
        context.r0.u32,context.r1.u32,context.r2.u32,
        context.r3.u32,context.r4.u32,context.r5.u32,context.r6.u32,
        context.r7.u32,context.r8.u32,context.r9.u32,context.r10.u32,
        context.r11.u32,context.r12.u32,context.r31.u32,
        g_lastAotGuestFunction.load(std::memory_order_relaxed),threadId,
        static_cast<unsigned long long>(reinterpret_cast<uintptr_t>(slotFunction)));
    recordRuntimeTrace(event);
    if (XOWUECrashRecorderWriteFatal) XOWUECrashRecorderWriteFatal(event);
    requestGuestSchedulerStop();
    throw std::runtime_error(event);
}

PPCFunc *xowue_lookup_indirect(PPCContext &context, uint8_t *base, uint32_t target) {
    // Generated PPC code can remain in a guest-side indirect-dispatch loop
    // without entering a syscall/wait primitive. Poll cancellation here so the
    // native Exit button can unwind such loops instead of leaving an orphaned
    // PPC worker alive behind the launcher.
    if (g_schedulerStopRequested.load(std::memory_order_relaxed))
        throw GuestThreadStopRequested{};

    PPCFunc *slotFunction = nullptr;
    const uint64_t tableStart = static_cast<uint64_t>(PPC_IMAGE_BASE) + PPC_IMAGE_SIZE;
    const auto guard = xowue_dispatch_guard::resolve<PPCFunc>(
        base, kGuestAddressSpaceSize, target, PPC_CODE_BASE, PPC_CODE_SIZE,
        tableStart, slotFunction);
    if (guard != xowue_dispatch_guard::Result::ok)
        failPpcIndirectDispatch(context, target, slotFunction, dispatchGuardErrorName(guard));

    const auto mapped = g_aotFunctionMap.find(target);
    if (mapped == g_aotFunctionMap.end() || !mapped->second)
        failPpcIndirectDispatch(context, target, slotFunction, "target absent from linked AOT map");
    if (mapped->second != slotFunction)
        failPpcIndirectDispatch(context, target, slotFunction, "dispatch slot does not match linked AOT map");

    return mapped->second;
}

void xowue_dispatch_indirect(PPCContext &context, uint8_t *base, uint32_t target) {
    xowue_lookup_indirect(context, base, target)(context, base);
}

// Physical Xenos readback uses the active guest memory mapping; no synthetic data.
extern "C" bool xowue_xenos_copy_guest_physical(uint32_t address, void *out, size_t size) {
    if (!out || !size || address >= 0x20000000u ||
        size > static_cast<size_t>(0x20000000u - address))
        return false;
    const auto memory = acquireGraphicsGuestMemory();
    if (!memory || !memory->base || !validGuestRange(address, size)) return false;
    std::memcpy(out, memory->base + address, size);
    return true;
}


// Commit a GPU-generated Xenos resolve into the original guest texture.
// Only validates and writes bytes produced by actual shaders. No fake pixels.
// The active VdSwap texture descriptor supplies layout/endian/swizzle.
// Original format adapters are defined below the PM4 decoder. Forward
// declarations preserve one exact implementation (not an emulator fallback).
static uint64_t xenosTiledOffset2D(uint32_t x,uint32_t y,
                                   uint32_t pitchAligned,uint32_t bytesPerPixelLog2);
static void swapXenosPixelEndian(uint8_t* pixel,uint32_t bytesPerPixel,
                                 uint32_t endian);

extern "C" bool xowue_xenos_commit_resolved_rgba(
    uint32_t dest,uint32_t pitch,uint32_t height,uint32_t info,
    const uint8_t* rgba,size_t sourceBytes) {
    if(!rgba || pitch==0u || height==0u || pitch>2048u || height>2048u ||
       ((info>>7u)&63u)!=6u || (uint64_t(pitch)*height*4u)!=sourceBytes)
        return false;
    std::array<uint32_t,6> fetch{};
    {
        std::lock_guard<std::mutex> lk(g_xenosMutex);
        if(!g_xenosFrontend.swapFetchValid ||
           g_xenosFrontend.latestFrontbufferAddress!=dest ||
           g_xenosFrontend.latestWidth!=pitch ||
           g_xenosFrontend.latestHeight!=height)
            return false;
        fetch=g_xenosFrontend.swapFetch;
    }
    if((fetch[1]&63u)!=6u || (((fetch[1]>>12u)&0xFFFFFu)<<12u)!=dest)
        return false;
    const uint32_t actualPitch=((fetch[0]>>22u)&0x1FFu)<<5u;
    const bool tiled=(fetch[0]>>31u)!=0u;
    const uint32_t pitchPixels=(actualPitch>=pitch)?actualPitch:
        (tiled?((pitch+31u)&~31u):pitch);
    const uint32_t alignedPitch=(pitchPixels+31u)&~31u;
    const uint32_t endian=(fetch[1]>>6u)&3u;
    const auto memory=acquireGraphicsGuestMemory();
    if(!memory || !memory->base)return false;
    // The fetch-constant swizzle controls texture sampling, not the memory
    // layout of a color render-target resolve. The Vulkan readback is already
    // RGBA8; applying the sampling swizzle here (or rejecting repeated
    // selectors such as the valid default descriptor) can prevent every
    // rendered frame from reaching the guest framebuffer.
    // Verify the entire native texture destination before the first write.
    // A partially committed framebuffer could corrupt the AOT state.
    for(uint32_t y=0;y<height;++y)for(uint32_t x=0;x<pitch;++x){
        const uint64_t off=tiled?xenosTiledOffset2D(x,y,alignedPitch,2u):
            (uint64_t(y)*pitchPixels+x)*4u;
        const uint64_t addr=uint64_t(dest)+off;
        if(addr>UINT32_MAX || !validGuestRange(uint32_t(addr),4u))return false;
    }
    uint64_t committed=0u;
    for(uint32_t y=0;y<height;++y)for(uint32_t x=0;x<pitch;++x) {
        const uint64_t offset=tiled?
            xenosTiledOffset2D(x,y,alignedPitch,2u):
            (uint64_t(y)*pitchPixels+x)*4u;
        const uint64_t address=uint64_t(dest)+offset;
        if(address>UINT32_MAX || !validGuestRange(uint32_t(address),4u))
            return false;
        const uint8_t* source=rgba+(size_t(y)*pitch+x)*4u;
        uint8_t pixel[4];
        std::memcpy(pixel,source,sizeof(pixel));
        swapXenosPixelEndian(pixel,4u,endian);
        std::memcpy(memory->base+address,pixel,4u);
        ++committed;
    }
    char event[240];
    std::snprintf(event,sizeof(event),
        "XENOS_GPU_GUEST_RESOLVE_COMMITTED dest=%08X %ux%u format=6 tiled=%u endian=%u pixels=%llu",
        dest,pitch,height,tiled?1u:0u,endian,
        static_cast<unsigned long long>(committed));
    recordRuntimeTrace(event);
    if(xowue_vulkan_backend_guest_frame_rgba)
        xowue_vulkan_backend_guest_frame_rgba(dest,pitch,height,6u,rgba,sourceBytes);
    return true;
}

extern "C" void xowue_set_touch_controller_state(
    uint32_t buttons, uint8_t left_trigger, uint8_t right_trigger,
    int16_t left_x, int16_t left_y, int16_t right_x, int16_t right_y) {
    std::lock_guard<std::mutex> lock(g_touchControllerMutex);
    const bool changed = g_touchController.buttons != buttons ||
        g_touchController.leftTrigger != left_trigger ||
        g_touchController.rightTrigger != right_trigger ||
        g_touchController.leftX != left_x || g_touchController.leftY != left_y ||
        g_touchController.rightX != right_x || g_touchController.rightY != right_y;
    g_touchController.buttons = buttons;
    g_touchController.leftTrigger = left_trigger;
    g_touchController.rightTrigger = right_trigger;
    g_touchController.leftX = left_x;
    g_touchController.leftY = left_y;
    g_touchController.rightX = right_x;
    g_touchController.rightY = right_y;
    if (changed) ++g_touchController.packetNumber;
}

extern "C" int xowue_set_runtime_trace_path(const char *path) {
    std::lock_guard<std::mutex> lock(g_runtimeTraceFileMutex);
    if (g_runtimeTraceFileDescriptor >= 0) {
        ::close(g_runtimeTraceFileDescriptor);
        g_runtimeTraceFileDescriptor = -1;
    }
    if (!path || path[0] == '\0') return 0;

    g_runtimeTraceFileDescriptor = ::open(path, O_WRONLY | O_CREAT | O_APPEND, 0600);
    return g_runtimeTraceFileDescriptor >= 0 ? 0 : errno;
}

extern "C" int xowue_inspect_xex(const char *path, char *output, size_t output_capacity) {
    try {
        const Image image = parseImage(path);
        writeMessage(output, output_capacity,
                     "XEX2 validado\nBase: 0x%08zX\nEntry point: 0x%08zX\nImagem: %u bytes\nSeções: %zu\nImports resolvidos: %zu",
                     image.base, image.entry_point, image.size, image.sections.size(), image.symbols.size());
        return 0;
    } catch (const std::exception &error) {
        return fail(output, output_capacity, error);
    } catch (...) {
        writeMessage(output, output_capacity, "Falha: erro desconhecido ao ler XEX");
        return 2;
    }
}

extern "C" int xowue_runtime_snapshot(char *output, size_t output_capacity) {
    if (!output || output_capacity == 0u) return 1;
    const std::string snapshot = runtimeTraceText();
    writeMessage(output, output_capacity, "%s", snapshot.c_str());
    return 0;
}

// Resolve the authentic case-insensitive Xbox path for asset preflight.
// The implementation is defined later in this translation unit.
static bool translateGuestFilePath(const std::string &guestPath, bool forWrite,
                                   std::filesystem::path &hostPath);

// Exit must terminate guest PPC execution; dismissing the view alone leaves
// native guest workers running indefinitely behind the single-game launcher.
extern "C" void xowue_request_stop(void) {
    // Cancellation is a lifecycle operation, not an optional telemetry feature.
    // Always wake guest waiters and stop the PPC scheduler even before AOT
    // execution counters have been enabled or after diagnostics are disabled.
    recordRuntimeTrace("XOWUE_USER_EXIT scheduler cancellation requested");
    requestGuestSchedulerStop();
}

extern "C" int xowue_boot_xex(const char *path, char *output, size_t output_capacity) {
    try {
        g_aotExecutionTelemetryActive.store(false, std::memory_order_relaxed);
        xowue::xenos::Reset();
        {
            std::lock_guard<std::mutex> lock(g_graphicsGuestMemoryMutex);
            g_graphicsGuestMemory.reset();
        }
        if (g_runtimeSessionPoisoned.load()) {
            throw std::runtime_error("uma thread PPC não encerrou após o limite de parada; feche e reabra o app para iniciar outra sessão");
        }
        {
            std::lock_guard<std::mutex> traceLock(g_runtimeTraceMutex);
            g_runtimeTrace.clear();
        }
        g_runtimeTracePersistSequence.store(0, std::memory_order_relaxed);
        g_runtimeTracePersistFailures.store(0, std::memory_order_relaxed);
        g_runtimeTracePersistMilestones.store(0, std::memory_order_relaxed);
        g_runtimeTracePersistSwaps.store(0, std::memory_order_relaxed);
        resetAotExecutionTelemetry();
        {
            std::lock_guard<std::mutex> tlsLock(g_tlsMutex);
            g_tlsAllocated.fill(false);
            g_tlsGenerations.fill(1u);
        }
        g_tlsValues.fill(0);
        g_tlsValueGenerations.fill(0);
        g_criticalSectionInitCount.store(0);
        g_schedulerStopRequested.store(false);
        g_nextGuestThreadId = 2u;
        g_nextGuestThreadStackTop = kFirstGuestThreadStackTop;
        g_nextGuestThreadObjectAddress = kFirstGuestThreadObjectAddress;
        g_nextGuestPcrAddress = kFirstGuestPcrAddress;
        g_nextGuestTlsAddress = kFirstGuestTlsAddress;
        g_guestIrql = 0u;
        g_mainThreadObjectAddress = kFirstGuestThreadObjectAddress - kGuestThreadMetadataStride;
        g_mainPcrAddress = kFirstGuestPcrAddress - kGuestThreadMetadataStride;
        g_mainTlsAddress = kMainGuestTlsAddress;
        {
            std::lock_guard<std::mutex> graphicsLock(g_xenosMutex);
            g_xenosFrontend = {};
        }
        {
            std::lock_guard<std::mutex> controllerLock(g_touchControllerMutex);
            g_touchController = {};
        }
        if (xowue_vulkan_backend_guest_frame_reset)
            xowue_vulkan_backend_guest_frame_reset();
        if (!path || path[0] == '\0') throw std::runtime_error("XEX path is empty");
        g_guestGameRoot = std::filesystem::path(path).parent_path();
        if (g_guestGameRoot.empty()) g_guestGameRoot = std::filesystem::current_path();
        g_guestSaveRoot = g_guestGameRoot.parent_path().parent_path() / "XOWUE-Saves";
        std::error_code saveError;
        std::filesystem::create_directories(g_guestSaveRoot, saveError);
        if (saveError) recordRuntimeTrace("save directory unavailable: " + saveError.message());
        recordRuntimeTrace("Xbox filesystem roots game=" + g_guestGameRoot.string() +
                           " saves=" + g_guestSaveRoot.string());
        // Log *actual host filesystem* inventory instead of fabricating
        // successful UE3/Bink movie opens (or skipping guest video calls).
        // A missing file is often a wrong game extraction rather than PPC AOT.
        for (const char *guestMovie : {
                 "D:\\WGame\\Movies\\ravenlogo.xxx",
                 "D:\\WGame\\Movies\\blank.bik",
                 "D:\\WGame\\Movies\\UE3_logo.xxx",
                 "D:\\WGame\\Movies\\FOX_LOGO.xxx",
                 "D:\\WGame\\Movies\\MARVEL_INTRO.xxx",
                 "D:\\WGame\\Movies\\ATVI_logo.xxx"}) {
            std::filesystem::path hostMovie;
            const bool mapped = translateGuestFilePath(guestMovie, false, hostMovie);
            std::error_code ioError;
            const bool exists = mapped && std::filesystem::is_regular_file(hostMovie, ioError);
            recordRuntimeTrace(std::string("XOWUE_ASSET_PREFLIGHT guest=") + guestMovie +
                               " mapped=" + (mapped ? "1" : "0") +
                               " present=" + (exists ? "1" : "0") +
                               " host=" + (mapped ? hostMovie.string() : "<rejected>"));
        }
        const Image image = parseImage(path);
        g_activeImageBase = static_cast<uint32_t>(image.base);
        g_activeEntryPoint = static_cast<uint32_t>(image.entry_point);
        g_activeImageSections.clear();
        g_activeImageSections.reserve(image.sections.size());
        for (const auto &section : image.sections)
            g_activeImageSections.emplace_back(static_cast<uint32_t>(section.base),
                                                static_cast<uint32_t>(section.size));
        char imageEvent[160];
        std::snprintf(imageEvent, sizeof(imageEvent),
                      "XEX2 carregado base=0x%08zX entry=0x%08zX sections=%zu",
                      image.base, image.entry_point, image.sections.size());
        recordRuntimeTrace(imageEvent);
        auto memory = std::make_shared<GuestMemory>();
        g_activeGuestMemory = memory;
        {
            std::lock_guard<std::mutex> lock(g_graphicsGuestMemoryMutex);
            g_graphicsGuestMemory = memory;
        }
        recordRuntimeTrace("XENOS_GRAPHICS_MEMORY_RETAINED after AOT lifetime; pending GPU reads remain valid");
        GuestSchedulerSessionGuard schedulerSession;
        GuestXenosPumpSessionGuard xenosPumpSession;
        g_nextVirtualAllocation = kFirstVirtualAllocation;
        g_nextPhysicalAllocation = kFirstPhysicalAllocation;
        g_nextGuestHandle = 0x100u;
        g_nextGuestEventObjectAddress = kFirstGuestEventObjectAddress;
        {
            std::lock_guard<std::mutex> stateLock(g_virtualMemoryMutex);
            g_virtualAllocations.clear();
            g_virtualCommits.clear();
            g_physicalAllocations.clear();
        }
        {
            std::lock_guard<std::mutex> objectLock(g_guestObjectMutex);
            g_guestWaitables.clear();
            g_guestObjectReferences.clear();
            g_guestReferencedWaitables.clear();
            g_guestPointerWaitables.clear();
        }
        {
            std::lock_guard<std::mutex> fileLock(g_guestFileMutex);
            g_guestFiles.clear();
            g_guestSymbolicLinks.clear();
        }
        {
            std::lock_guard<std::mutex> spinLock(g_spinLockMapMutex);
            g_guestSpinLocks.clear();
        }
        {
            std::lock_guard<std::mutex> socketLock(g_socketMutex);
            for (const auto &socket : g_guestSockets) ::close(socket.second);
            g_guestSockets.clear();
        }
        g_guestXmaContexts.clear();
        g_ioShareByFileObject.clear();
        {
            std::lock_guard<std::mutex> threadLock(g_guestThreadMutex);
            g_guestThreadsByHandle.clear();
            g_guestThreadsByObject.clear();
            g_guestThreads.clear();
        }
        copyImage(image, *memory);
        g_activeExecutionInfoAddress = allocateGuestPhysicalRange(memory->base, 0x20u, 0x1000u, 0x04u);
        if (g_activeExecutionInfoAddress != 0u) {
            uint8_t *base = memory->base;
            const uint32_t execution = g_activeExecutionInfoAddress;
            PPC_STORE_U32(execution + 0x00u, 0u); // Media ID is not used by this title.
            PPC_STORE_U32(execution + 0x04u, 0u); // XEX version.
            PPC_STORE_U32(execution + 0x08u, 0u); // Base version.
            PPC_STORE_U32(execution + 0x0Cu, kXowueTitleId);
            memory->base[execution + 0x10u] = 2u;  // Xbox 360 platform.
            memory->base[execution + 0x11u] = 0u;  // Default executable type.
            memory->base[execution + 0x12u] = 1u;
            memory->base[execution + 0x13u] = 1u;
            PPC_STORE_U32(execution + 0x14u, kXowueTitleId);
        }
        const size_t installed = installDispatchTable(*memory);
        recordRuntimeTrace("Guest memory mapeada; AOT dispatch entries=" + std::to_string(installed));
        recordRuntimeTrace("XEX TLS slots=" + std::to_string(g_tlsSlotLimit) +
                           " staticData=" + std::to_string(g_tlsStaticDataSize) +
                           " rawData=" + std::to_string(g_tlsRawDataSize) +
                           " block=" + std::to_string(g_tlsBlockSize));

        const PPCFuncMapping *entry = nullptr;
        for (const PPCFuncMapping *mapping = PPCFuncMappings; mapping->host; ++mapping) {
            if (mapping->guest == image.entry_point) {
                entry = mapping;
                break;
            }
        }
        if (!entry) throw std::runtime_error("XEX entry point is absent from the AOT function map");

        auto mainThread = std::make_shared<GuestThread>();
        mainThread->id = 1u;
        mainThread->handle = 0xFFFFFFFEu;
        mainThread->objectAddress = g_mainThreadObjectAddress;
        mainThread->pcrAddress = g_mainPcrAddress;
        mainThread->tlsAddress = g_mainTlsAddress;
        mainThread->stackBase = kInitialStackPointer - 0x10000u;
        mainThread->stackSize = 0x10000u;
        mainThread->startAddress = static_cast<uint32_t>(image.entry_point);
        mainThread->completion = std::make_shared<GuestWaitable>();
        mainThread->completion->kind = GuestWaitable::Kind::Thread;
        mainThread->completion->handle = mainThread->handle;
        mainThread->completion->objectAddress = mainThread->objectAddress;
        mainThread->completion->manualReset = true;
        mainThread->completion->signaled = false;
        initializeGuestThreadEnvironment(memory->base, mainThread->objectAddress,
                                         mainThread->pcrAddress, mainThread->tlsAddress,
                                         mainThread->stackBase, mainThread->stackSize,
                                         mainThread->id, mainThread->startAddress, 0u, 0u);
        g_mainGuestThread = mainThread;
        {
            std::lock_guard<std::mutex> objectLock(g_guestObjectMutex);
            g_guestWaitables[mainThread->handle] = mainThread->completion;
            g_guestWaitables[mainThread->objectAddress] = mainThread->completion;
        }
        recordRuntimeTrace("Main PPC thread initialized id=1 object=0x" + [&] {
            char address[16];
            std::snprintf(address, sizeof(address), "%08X", mainThread->objectAddress);
            return std::string(address);
        }() + " KPCR=0x" + [&] {
            char address[16];
            std::snprintf(address, sizeof(address), "%08X", mainThread->pcrAddress);
            return std::string(address);
        }());

        PPCContext context{};
        context.r1.u32 = kInitialStackPointer;
        context.r2.u32 = static_cast<uint32_t>(image.base);
        context.r13.u32 = mainThread->pcrAddress;
        context.lr = 0;
        char entryEvent[80];
        std::snprintf(entryEvent, sizeof(entryEvent), "Chamando PPC entry point 0x%08zX", image.entry_point);
        recordRuntimeTrace(entryEvent);
        GuestThreadBinding mainThreadBinding(mainThread.get());
        entry->host(context, memory->base);
        mainThread->exitStatus.store(context.r3.u32);
        mainThread->exited.store(true);
        signalGuestWaitable(mainThread->completion);
        schedulerSession.stop();
        recordAotExecutionSummary("entry-returned");
        g_aotExecutionTelemetryActive.store(false, std::memory_order_release);
        const std::string trace = runtimeTraceText();
        writeMessage(output, output_capacity,
                     "Entry point retornou. Funções AOT registradas: %zu. O boot não foi concluído.%s",
                     installed, trace.c_str());
        return 3;
    } catch (const GuestThreadStopRequested &) {
        // This is an intentional user exit, not an empty AOT slot or a crash.
        recordAotExecutionSummary("user-exit");
        g_aotExecutionTelemetryActive.store(false, std::memory_order_release);
        recordRuntimeTrace("XOWUE_USER_EXIT PPC stopped; scheduler guard joining guest threads");
        writeMessage(output, output_capacity, "Sessão PPC encerrada por SAIR.%s",
                     runtimeTraceText().c_str());
        return 4;
    } catch (const GuestFirmwareReturn &request) {
        recordAotExecutionSummary("firmware-return");
        g_aotExecutionTelemetryActive.store(false, std::memory_order_release);
        char event[128];
        std::snprintf(event, sizeof(event), "HalReturnToFirmware routine=0x%08X LR=0x%08X",
                      request.routine, request.returnAddress);
        recordRuntimeTrace(event);
        const std::string trace = runtimeTraceText();
        writeMessage(output, output_capacity,
                     "O XEX chamou HalReturnToFirmware (routine=0x%08X). "
                     "LR=0x%08X (retorno PPC após callsite 0x%08X). "
                     "O runtime ainda não emula ciclo de reboot/shutdown; o boot parou aqui.%s",
                     request.routine, request.returnAddress, request.returnAddress - 4u, trace.c_str());
        return 3;
    } catch (const std::exception &error) {
        return fail(output, output_capacity, error);
    } catch (...) {
        writeMessage(output, output_capacity, "Falha: erro nativo desconhecido durante o boot");
        return 2;
    }
}

static std::array<uint8_t, 20> xowueSha1(const std::vector<uint8_t> &input) {
    std::vector<uint8_t> data = input;
    const uint64_t bitLength = static_cast<uint64_t>(data.size()) * 8u;
    data.push_back(0x80u);
    while ((data.size() & 63u) != 56u) data.push_back(0u);
    for (int shift = 56; shift >= 0; shift -= 8)
        data.push_back(static_cast<uint8_t>(bitLength >> shift));
    uint32_t h0 = 0x67452301u, h1 = 0xEFCDAB89u, h2 = 0x98BADCFEu,
             h3 = 0x10325476u, h4 = 0xC3D2E1F0u;
    for (size_t block = 0; block < data.size(); block += 64u) {
        uint32_t w[80]{};
        for (uint32_t i = 0; i < 16u; ++i) {
            const size_t p = block + i * 4u;
            w[i] = (static_cast<uint32_t>(data[p]) << 24u) |
                   (static_cast<uint32_t>(data[p + 1u]) << 16u) |
                   (static_cast<uint32_t>(data[p + 2u]) << 8u) | data[p + 3u];
        }
        for (uint32_t i = 16u; i < 80u; ++i)
            w[i] = std::rotl(w[i - 3u] ^ w[i - 8u] ^ w[i - 14u] ^ w[i - 16u], 1);
        uint32_t a = h0, b = h1, c = h2, d = h3, e = h4;
        for (uint32_t i = 0; i < 80u; ++i) {
            uint32_t f = 0u, k = 0u;
            if (i < 20u) { f = (b & c) | ((~b) & d); k = 0x5A827999u; }
            else if (i < 40u) { f = b ^ c ^ d; k = 0x6ED9EBA1u; }
            else if (i < 60u) { f = (b & c) | (b & d) | (c & d); k = 0x8F1BBCDCu; }
            else { f = b ^ c ^ d; k = 0xCA62C1D6u; }
            const uint32_t temp = std::rotl(a, 5) + f + e + k + w[i];
            e = d; d = c; c = std::rotl(b, 30); b = a; a = temp;
        }
        h0 += a; h1 += b; h2 += c; h3 += d; h4 += e;
    }
    const uint32_t words[5] = {h0, h1, h2, h3, h4};
    std::array<uint8_t, 20> digest{};
    for (uint32_t i = 0; i < 5u; ++i)
        for (uint32_t j = 0; j < 4u; ++j)
            digest[i * 4u + j] = static_cast<uint8_t>(words[i] >> (24u - j * 8u));
    return digest;
}

static uint16_t loadGuestBe16Compat(uint8_t *base, uint32_t address) {
    return static_cast<uint16_t>((static_cast<uint16_t>(base[address]) << 8u) |
                                 static_cast<uint16_t>(base[address + 1u]));
}

static bool readGuestCString(uint8_t *base, uint32_t address, std::string &value,
                             size_t maximum = 4096u) {
    if (!base || address == 0u || !validGuestRange(address, 1u)) return false;
    const size_t limit = std::min<size_t>(maximum,
        static_cast<size_t>(kGuestAddressSpaceSize - address));
    const char *start = reinterpret_cast<const char *>(base + address);
    const void *terminator = std::memchr(start, 0, limit);
    if (!terminator) return false;
    value.assign(start, static_cast<const char *>(terminator) - start);
    return true;
}

static std::optional<int> lookupGuestSocket(uint32_t handle) {
    std::lock_guard<std::mutex> lock(g_socketMutex);
    const auto found = g_guestSockets.find(handle);
    if (found == g_guestSockets.end()) return std::nullopt;
    return found->second;
}

static uint32_t registerGuestSocket(int descriptor) {
    const uint32_t handle = allocateGuestHandle();
    if (handle == 0u) return 0xFFFFFFFFu;
    std::lock_guard<std::mutex> lock(g_socketMutex);
    g_guestSockets.emplace(handle, descriptor);
    return handle;
}

static int guestSocketError(int error) {
    switch (error) {
        case EACCES: return 10013;
        case EADDRINUSE: return 10048;
        case EADDRNOTAVAIL: return 10049;
        case EAFNOSUPPORT: return 10047;
        case ECONNABORTED: return 10053;
        case ECONNREFUSED: return 10061;
        case ECONNRESET: return 10054;
        case EINPROGRESS: return 10036;
        case EINVAL: return 10022;
        case EMSGSIZE: return 10040;
        case ENETDOWN: return 10050;
        case ENETUNREACH: return 10051;
        case ENOBUFS: return 10055;
        case ENOTCONN: return 10057;
        case ENOTSOCK: return 10038;
        case EOPNOTSUPP: return 10045;
        case ETIMEDOUT: return 10060;
        case EWOULDBLOCK: return 10035;
        default: return 10022;
    }
}

static bool readGuestSocketAddress(uint8_t *base, uint32_t address,
                                   uint32_t length, sockaddr_storage &storage,
                                   socklen_t &nativeLength) {
    if (!base || length < 16u || !validGuestRange(address, 16u) ||
        loadGuestBe16Compat(base, address) != AF_INET) return false;
    sockaddr_in native{};
    native.sin_family = AF_INET;
    std::memcpy(&native.sin_port, base + address + 2u, sizeof(native.sin_port));
    std::memcpy(&native.sin_addr, base + address + 4u, sizeof(native.sin_addr));
    std::memcpy(&storage, &native, sizeof(native));
    nativeLength = sizeof(native);
    return true;
}

static bool writeGuestSocketAddress(uint8_t *base, uint32_t address,
                                    uint32_t lengthPointer,
                                    const sockaddr *native,
                                    socklen_t nativeLength) {
    if (!base || !native || !validGuestRange(lengthPointer, 4u)) return false;
    const uint32_t capacity = PPC_LOAD_U32(lengthPointer);
    if (capacity < 16u || !validGuestRange(address, std::min<uint32_t>(capacity, 16u))) {
        PPC_STORE_U32(lengthPointer, 16u);
        return false;
    }
    if (native->sa_family != AF_INET || nativeLength < sizeof(sockaddr_in)) return false;
    const auto *ipv4 = reinterpret_cast<const sockaddr_in *>(native);
    std::memset(base + address, 0, 16u);
    base[address] = 0u;
    base[address + 1u] = AF_INET;
    std::memcpy(base + address + 2u, &ipv4->sin_port, sizeof(ipv4->sin_port));
    std::memcpy(base + address + 4u, &ipv4->sin_addr, sizeof(ipv4->sin_addr));
    PPC_STORE_U32(lengthPointer, 16u);
    return true;
}

static bool handleNetDllSocketImport(std::string_view api, PPCContext &context,
                                     uint8_t *base) {
    if (api == "NetDll_WSAStartup") {
        const uint32_t data = context.r5.u32;
        if (data != 0u && base && validGuestRange(data, 0x198u)) {
            std::memset(base + data, 0, 0x198u);
            PPC_STORE_U16(data, static_cast<uint16_t>(context.r4.u32));
            PPC_STORE_U16(data + 2u, static_cast<uint16_t>(context.r4.u32));
            PPC_STORE_U32(data + 0x184u, 100u);
            PPC_STORE_U32(data + 0x188u, 1024u);
        }
        context.r3.u32 = 0u;
        return true;
    }
    if (api == "NetDll_WSACleanup") { context.r3.u32 = 0u; return true; }
    if (api == "NetDll_WSAGetLastError") { context.r3.u32 = static_cast<uint32_t>(g_wsaLastError); return true; }
    if (api == "NetDll_WSASetLastError") { g_wsaLastError = static_cast<int32_t>(context.r4.u32); return true; }
    if (api == "NetDll_WSACreateEvent") {
        const uint32_t handle = allocateGuestHandle();
        auto event = std::make_shared<GuestWaitable>();
        event->kind = GuestWaitable::Kind::Event;
        event->handle = handle;
        event->manualReset = true;
        event->signaled = false;
        { std::lock_guard<std::mutex> lock(g_guestObjectMutex); g_guestWaitables[handle] = event; }
        context.r3.u32 = handle ? handle : 0xFFFFFFFFu;
        return true;
    }
    if (api == "NetDll_socket") {
        const int descriptor = ::socket(static_cast<int>(context.r4.u32),
                                        static_cast<int>(context.r5.u32),
                                        static_cast<int>(context.r6.u32));
        if (descriptor < 0) {
            g_wsaLastError = guestSocketError(errno);
            context.r3.u32 = 0xFFFFFFFFu;
            return true;
        }
#ifdef SO_NOSIGPIPE
        const int noSigPipe = 1;
        setsockopt(descriptor, SOL_SOCKET, SO_NOSIGPIPE, &noSigPipe, sizeof(noSigPipe));
#endif
        context.r3.u32 = registerGuestSocket(descriptor);
        return true;
    }

    const uint32_t handle = context.r4.u32;
    const auto descriptor = lookupGuestSocket(handle);
    auto failSocket = [&](int error) { g_wsaLastError = guestSocketError(error); context.r3.u32 = 0xFFFFFFFFu; };
    if (api == "NetDll_closesocket") {
        if (!descriptor) { failSocket(ENOTSOCK); return true; }
        { std::lock_guard<std::mutex> lock(g_socketMutex); g_guestSockets.erase(handle); }
        const int result = ::close(*descriptor);
        if (result != 0) failSocket(errno); else context.r3.u32 = 0u;
        return true;
    }
    if (api == "NetDll_bind" || api == "NetDll_connect") {
        if (!descriptor) { failSocket(ENOTSOCK); return true; }
        sockaddr_storage address{}; socklen_t addressLength = 0u;
        if (!readGuestSocketAddress(base, context.r5.u32, context.r6.u32, address, addressLength)) {
            failSocket(EINVAL); return true;
        }
        const int result = api == "NetDll_bind"
            ? ::bind(*descriptor, reinterpret_cast<sockaddr *>(&address), addressLength)
            : ::connect(*descriptor, reinterpret_cast<sockaddr *>(&address), addressLength);
        if (result != 0) failSocket(errno); else context.r3.u32 = 0u;
        return true;
    }
    if (api == "NetDll_listen") {
        if (!descriptor) { failSocket(ENOTSOCK); return true; }
        const int result = ::listen(*descriptor, static_cast<int>(context.r5.u32));
        if (result != 0) failSocket(errno); else context.r3.u32 = 0u;
        return true;
    }
    if (api == "NetDll_accept") {
        if (!descriptor) { failSocket(ENOTSOCK); return true; }
        sockaddr_storage address{}; socklen_t length = sizeof(address);
        const int accepted = ::accept(*descriptor,
                                      reinterpret_cast<sockaddr *>(&address),
                                      &length);
        if (accepted < 0) { failSocket(errno); return true; }
        if (context.r5.u32 != 0u && context.r6.u32 != 0u &&
            !writeGuestSocketAddress(base, context.r5.u32, context.r6.u32,
                                     reinterpret_cast<sockaddr *>(&address), length)) {
            ::close(accepted); failSocket(EINVAL); return true;
        }
        context.r3.u32 = registerGuestSocket(accepted);
        return true;
    }
    if (api == "NetDll_send" || api == "NetDll_recv") {
        const uint32_t buffer = context.r5.u32, length = context.r6.u32;
        if (!descriptor) { failSocket(ENOTSOCK); return true; }
        if (!base || length > 16u * 1024u * 1024u ||
            (length != 0u && !validGuestRange(buffer, length))) { failSocket(EINVAL); return true; }
        const int flags = static_cast<int>(context.r7.u32);
        const ssize_t result = api == "NetDll_send"
            ? ::send(*descriptor, base + buffer, length, flags)
            : ::recv(*descriptor, base + buffer, length, flags);
        if (result < 0) failSocket(errno); else context.r3.u32 = static_cast<uint32_t>(result);
        return true;
    }
    if (api == "NetDll_sendto" || api == "NetDll_recvfrom") {
        const uint32_t buffer = context.r5.u32, length = context.r6.u32;
        if (!descriptor) { failSocket(ENOTSOCK); return true; }
        if (!base || length > 16u * 1024u * 1024u ||
            (length != 0u && !validGuestRange(buffer, length))) { failSocket(EINVAL); return true; }
        const int flags = static_cast<int>(context.r7.u32);
        ssize_t result = -1;
        if (api == "NetDll_sendto") {
            sockaddr_storage address{}; socklen_t addressLength = 0u;
            if (!readGuestSocketAddress(base, context.r8.u32, context.r9.u32,
                                        address, addressLength)) { failSocket(EINVAL); return true; }
            result = ::sendto(*descriptor, base + buffer, length, flags,
                              reinterpret_cast<sockaddr *>(&address), addressLength);
        } else {
            sockaddr_storage address{}; socklen_t addressLength = sizeof(address);
            result = ::recvfrom(*descriptor, base + buffer, length, flags,
                                context.r8.u32 ? reinterpret_cast<sockaddr *>(&address) : nullptr,
                                context.r8.u32 ? &addressLength : nullptr);
            if (result >= 0 && context.r8.u32 && context.r9.u32 &&
                !writeGuestSocketAddress(base, context.r8.u32, context.r9.u32,
                                         reinterpret_cast<sockaddr *>(&address), addressLength)) {
                failSocket(EINVAL); return true;
            }
        }
        if (result < 0) failSocket(errno); else context.r3.u32 = static_cast<uint32_t>(result);
        return true;
    }
    if (api == "NetDll_getsockname") {
        if (!descriptor) { failSocket(ENOTSOCK); return true; }
        sockaddr_storage address{}; socklen_t length = sizeof(address);
        if (::getsockname(*descriptor, reinterpret_cast<sockaddr *>(&address), &length) != 0) {
            failSocket(errno); return true;
        }
        if (!writeGuestSocketAddress(base, context.r5.u32, context.r6.u32,
                                     reinterpret_cast<sockaddr *>(&address), length)) {
            failSocket(EINVAL); return true;
        }
        context.r3.u32 = 0u; return true;
    }
    if (api == "NetDll_getsockopt" || api == "NetDll_setsockopt") {
        if (!descriptor) { failSocket(ENOTSOCK); return true; }
        const int level = static_cast<int>(context.r5.u32);
        const int option = static_cast<int>(context.r6.u32);
        const uint32_t value = context.r7.u32;
        if (api == "NetDll_setsockopt") {
            const uint32_t length = context.r8.u32;
            if (!base || length > 65536u || !validGuestRange(value, length)) { failSocket(EINVAL); return true; }
            if (::setsockopt(*descriptor, level, option, base + value, static_cast<socklen_t>(length)) != 0)
                failSocket(errno);
            else context.r3.u32 = 0u;
            return true;
        }
        const uint32_t lengthPointer = context.r8.u32;
        if (!base || !validGuestRange(value, 4u) || !validGuestRange(lengthPointer, 4u)) { failSocket(EINVAL); return true; }
        socklen_t length = std::min<uint32_t>(PPC_LOAD_U32(lengthPointer), 65536u);
        std::vector<uint8_t> bytes(std::max<socklen_t>(length, 4u));
        if (::getsockopt(*descriptor, level, option, bytes.data(), &length) != 0) failSocket(errno);
        else {
            if (!validGuestRange(value, length)) { failSocket(EINVAL); return true; }
            std::memcpy(base + value, bytes.data(), length);
            PPC_STORE_U32(lengthPointer, length);
            context.r3.u32 = 0u;
        }
        return true;
    }
    if (api == "NetDll_ioctlsocket") {
        if (!descriptor) { failSocket(ENOTSOCK); return true; }
        const uint32_t argument = context.r6.u32;
        if (!base || !validGuestRange(argument, 4u)) { failSocket(EINVAL); return true; }
        if (context.r5.u32 == 0x8004667Eu) { // FIONBIO
            const int current = fcntl(*descriptor, F_GETFL, 0);
            if (current < 0 || fcntl(*descriptor, F_SETFL,
                                     PPC_LOAD_U32(argument) ? current | O_NONBLOCK : current & ~O_NONBLOCK) < 0)
                failSocket(errno);
            else context.r3.u32 = 0u;
        } else {
            int value = 0;
            if (::ioctl(*descriptor, context.r5.u32, &value) != 0) failSocket(errno);
            else { PPC_STORE_U32(argument, static_cast<uint32_t>(value)); context.r3.u32 = 0u; }
        }
        return true;
    }
    if (api == "NetDll_select") {
        struct GuestFdSet { uint32_t address; short events; std::vector<uint32_t> handles; };
        std::array<GuestFdSet, 3> sets{{{context.r5.u32, POLLIN, {}},
                                       {context.r6.u32, POLLOUT, {}},
                                       {context.r7.u32, POLLPRI, {}}}};
        if (!base) { failSocket(EINVAL); return true; }
        std::vector<pollfd> pollers;
        for (auto &set : sets) {
            if (!set.address) continue;
            if (!validGuestRange(set.address, 4u)) { failSocket(EINVAL); return true; }
            const uint32_t count = PPC_LOAD_U32(set.address);
            if (count > 64u || !validGuestRange(set.address + 4u, count * 4u)) { failSocket(EINVAL); return true; }
            for (uint32_t index = 0; index < count; ++index) {
                const uint32_t guestHandle = PPC_LOAD_U32(set.address + 4u + index * 4u);
                const auto fd = lookupGuestSocket(guestHandle);
                if (!fd) { failSocket(ENOTSOCK); return true; }
                set.handles.push_back(guestHandle);
                pollers.push_back({*fd, set.events, 0});
            }
        }
        int timeout = -1;
        if (context.r8.u32) {
            if (!validGuestRange(context.r8.u32, 8u)) { failSocket(EINVAL); return true; }
            const uint32_t seconds = PPC_LOAD_U32(context.r8.u32);
            const uint32_t micros = PPC_LOAD_U32(context.r8.u32 + 4u);
            const uint64_t millis = static_cast<uint64_t>(seconds) * 1000u + (micros + 999u) / 1000u;
            timeout = static_cast<int>(std::min<uint64_t>(millis, INT32_MAX));
        }
        const int result = ::poll(pollers.data(), pollers.size(), timeout);
        if (result < 0) { failSocket(errno); return true; }
        size_t pollIndex = 0u;
        uint32_t readySetCount = 0u;
        for (auto &set : sets) {
            if (!set.address) continue;
            std::vector<uint32_t> ready;
            for (uint32_t guestHandle : set.handles) {
                if (pollIndex < pollers.size() && (pollers[pollIndex].revents & (set.events | POLLERR | POLLHUP | POLLNVAL)))
                    ready.push_back(guestHandle);
                ++pollIndex;
            }
            readySetCount += static_cast<uint32_t>(ready.size());
            PPC_STORE_U32(set.address, static_cast<uint32_t>(ready.size()));
            for (size_t i = 0; i < ready.size(); ++i) PPC_STORE_U32(set.address + 4u + static_cast<uint32_t>(i * 4u), ready[i]);
        }
        context.r3.u32 = readySetCount;
        return true;
    }
    if (api == "NetDll_inet_addr") {
        std::string text;
        in_addr address{};
        if (!readGuestCString(base, context.r4.u32, text) || ::inet_pton(AF_INET, text.c_str(), &address) != 1) {
            context.r3.u32 = 0xFFFFFFFFu;
        } else {
            context.r3.u32 = ntohl(address.s_addr);
        }
        return true;
    }
    return false;
}

static uint32_t guestCallArgument(PPCContext &context, uint8_t *base,
                                  uint32_t argumentIndex) {
    switch (argumentIndex) {
        case 0u: return context.r3.u32;
        case 1u: return context.r4.u32;
        case 2u: return context.r5.u32;
        case 3u: return context.r6.u32;
        case 4u: return context.r7.u32;
        case 5u: return context.r8.u32;
        case 6u: return context.r9.u32;
        case 7u: return context.r10.u32;
        default: return guestStackArgument(context, base, argumentIndex + 1u);
    }
}

static std::string formatGuestVarargs(PPCContext &context, uint8_t *base,
                                      uint32_t formatPointer,
                                      uint32_t firstArgument,
                                      uint32_t arrayArgumentsPointer = 0u) {
    std::string format;
    if (!readGuestCString(base, formatPointer, format, 0x10000u))
        return "<invalid format string>";
    uint32_t argumentIndex = firstArgument;
    uint32_t arrayIndex = 0u;
    auto next = [&]() -> uint32_t {
        if (arrayArgumentsPointer != 0u && base &&
            validGuestRange(arrayArgumentsPointer + arrayIndex * 4u, 4u)) {
            const uint32_t value = PPC_LOAD_U32(arrayArgumentsPointer + arrayIndex * 4u);
            ++arrayIndex;
            return value;
        }
        return guestCallArgument(context, base, argumentIndex++);
    };
    std::string output;
    output.reserve(std::min<size_t>(format.size() + 32u, 0x10000u));
    for (size_t index = 0u; index < format.size() && output.size() < 0x10000u; ++index) {
        if (format[index] != '%' || index + 1u >= format.size()) {
            output.push_back(format[index]);
            continue;
        }
        if (format[index + 1u] == '%') { output.push_back('%'); ++index; continue; }
        size_t cursor = index + 1u;
        std::string flags;
        while (cursor < format.size() && std::string_view("-+ #0").find(format[cursor]) != std::string_view::npos)
            flags.push_back(format[cursor++]);
        int width = -1;
        if (cursor < format.size() && format[cursor] == '*') {
            const int32_t dynamicWidth = static_cast<int32_t>(next());
            if (dynamicWidth < 0) {
                if (flags.find('-') == std::string::npos) flags.push_back('-');
                width = static_cast<int>(std::min<int64_t>(
                    -static_cast<int64_t>(dynamicWidth), 256));
            } else {
                width = std::min(dynamicWidth, 256);
            }
            ++cursor;
        } else if (cursor < format.size() && std::isdigit(static_cast<unsigned char>(format[cursor]))) {
            width = 0;
            while (cursor < format.size() && std::isdigit(static_cast<unsigned char>(format[cursor]))) {
                width = std::min(256, width * 10 + (format[cursor++] - '0'));
            }
        }
        int precision = -1;
        if (cursor < format.size() && format[cursor] == '.') {
            ++cursor;
            if (cursor < format.size() && format[cursor] == '*') {
                precision = static_cast<int32_t>(next());
                if (precision < 0) precision = -1;
                else precision = std::min(precision, 256);
                ++cursor;
            } else {
                precision = 0;
                while (cursor < format.size() && std::isdigit(static_cast<unsigned char>(format[cursor])))
                    precision = std::min(256, precision * 10 + (format[cursor++] - '0'));
            }
        }
        bool longValue = false;
        if (cursor < format.size() && (format[cursor] == 'l' || format[cursor] == 'z' || format[cursor] == 't')) {
            longValue = true;
            if (format[cursor] == 'l' && cursor + 1u < format.size() && format[cursor + 1u] == 'l') ++cursor;
            ++cursor;
        } else if (cursor < format.size() && (format[cursor] == 'h' || format[cursor] == 'j')) {
            ++cursor;
            if (cursor < format.size() && format[cursor] == 'h') ++cursor;
        }
        if (cursor >= format.size()) break;
        const char conversion = format[cursor];
        index = cursor;
        auto appendPadded = [&](std::string value) {
            if (precision >= 0 && value.size() > static_cast<size_t>(precision))
                value.resize(static_cast<size_t>(precision));
            const size_t pad = width > 0 && static_cast<size_t>(width) > value.size()
                ? static_cast<size_t>(width) - value.size() : 0u;
            if (flags.find('-') != std::string::npos) { output += value; output.append(pad, ' '); }
            else { output.append(pad, ' '); output += value; }
        };
        if (conversion == 's' || conversion == 'S') {
            const uint32_t pointer = next();
            std::string value;
            if (!readGuestCString(base, pointer, value, 0x10000u)) value = "<invalid string>";
            appendPadded(std::move(value));
        } else if (conversion == 'c') {
            appendPadded(std::string(1u, static_cast<char>(next() & 0xFFu)));
        } else if (conversion == 'p') {
            const uint32_t value = next();
            char formatted[40];
            std::snprintf(formatted, sizeof(formatted), "%#010x", value);
            appendPadded(formatted);
        } else if (conversion == 'd' || conversion == 'i' || conversion == 'u' ||
                   conversion == 'o' || conversion == 'x' || conversion == 'X') {
            const uint32_t raw = next();
            std::string specification = "%" + flags;
            if (width >= 0) specification += std::to_string(width);
            if (precision >= 0) specification += "." + std::to_string(precision);
            specification += "ll";
            specification.push_back(conversion);
            char formatted[384];
            if (conversion == 'd' || conversion == 'i')
                std::snprintf(formatted, sizeof(formatted), specification.c_str(),
                              static_cast<long long>(static_cast<int32_t>(raw)));
            else
                std::snprintf(formatted, sizeof(formatted), specification.c_str(),
                              static_cast<unsigned long long>(raw));
            output += formatted;
        } else if (conversion == 'f' || conversion == 'g' || conversion == 'e') {
            (void)longValue;
            output += "<float>";
        } else if (conversion == 'n') {
            (void)next();
        } else {
            output.push_back('%');
            output.push_back(conversion);
        }
    }
    if (output.size() > 0x10000u) output.resize(0x10000u);
    return output;
}

void xowue_compat_import(const char *name, PPCContext &context, uint8_t *base) {
    const std::string_view api = name ? name : "";
    constexpr uint32_t kXamNoSuchUser = 0x80070490u;
    constexpr uint32_t kNotImplemented = 0x80004001u;
    constexpr uint64_t kLocalUserXuid = 0xE000000000000001ull;
    if (handleNetDllSocketImport(api, context, base)) return;
    auto clearOutput = [base](uint32_t address, uint32_t size) {
        if (base && size && validGuestRange(address, size)) std::memset(base + address, 0, size);
    };
    auto spinLockFor = [](uint32_t address) -> std::shared_ptr<std::mutex> {
        std::lock_guard<std::mutex> guard(g_spinLockMapMutex);
        auto &lock = g_guestSpinLocks[address];
        if (!lock) lock = std::make_shared<std::mutex>();
        return lock;
    };
    if (api == "KfAcquireSpinLock") {
        const uint32_t address = context.r3.u32;
        if (!base || !validGuestRange(address, 4u)) { context.r3.u32 = kNtStatusInvalidParameter; return; }
        const uint32_t previousIrql = g_guestIrql;
        g_guestIrql = 2u;
        spinLockFor(address)->lock();
        PPC_STORE_U32(address, 1u);
        context.r3.u32 = previousIrql;
        return;
    }
    if (api == "KfReleaseSpinLock") {
        const uint32_t address = context.r3.u32;
        std::shared_ptr<std::mutex> lock;
        {
            std::lock_guard<std::mutex> guard(g_spinLockMapMutex);
            const auto found = g_guestSpinLocks.find(address);
            if (found != g_guestSpinLocks.end()) lock = found->second;
        }
        if (!lock || !base || !validGuestRange(address, 4u)) {
            recordRuntimeTrace("KfReleaseSpinLock rejected an unknown lock");
            return;
        }
        PPC_STORE_U32(address, 0u);
        lock->unlock();
        const uint32_t previousIrql = context.r4.u32;
        if (previousIrql > 2u) throw std::runtime_error("KfReleaseSpinLock received an invalid IRQL");
        const uint32_t oldIrql = g_guestIrql;
        g_guestIrql = previousIrql;
        if (oldIrql > 1u && g_guestIrql <= 1u) deliverPendingGuestApcs();
        return;
    }
    if (api == "KfLowerIrql") {
        const uint32_t targetIrql = context.r3.u32;
        if (targetIrql > 2u || targetIrql > g_guestIrql)
            throw std::runtime_error("KfLowerIrql attempted to raise IRQL or use an invalid level");
        const uint32_t oldIrql = g_guestIrql;
        g_guestIrql = targetIrql;
        if (oldIrql > 1u && targetIrql <= 1u) deliverPendingGuestApcs();
        return;
    }
    if (api == "DbgBreakPoint") {
        recordRuntimeTrace("DbgBreakPoint suppressed for the hosted retail title");
        return;
    }
    if (api == "DbgPrint") {
        const std::string message = formatGuestVarargs(context, base, context.r3.u32, 1u);
        recordRuntimeTrace("DbgPrint: " + message.substr(0u, 512u));
        context.r3.u32 = kNtStatusSuccess;
        return;
    }
    if (api == "InterlockedPopEntrySList" || api == "InterlockedFlushSList") {
        const uint32_t header = context.r3.u32;
        if (!base || !validGuestRange(header, 8u)) { context.r3.u32 = 0u; return; }
        std::lock_guard<std::mutex> guard(g_slistMutex);
        const uint32_t first = PPC_LOAD_U32(header + 4u);
        if (api == "InterlockedFlushSList") {
            std::memset(base + header, 0, 8u);
            context.r3.u32 = first;
            return;
        }
        if (first == 0u || !validGuestRange(first, 4u)) { context.r3.u32 = 0u; return; }
        const uint32_t next = PPC_LOAD_U32(first);
        const uint16_t depth = loadGuestBe16Compat(base, header);
        const uint16_t sequence = loadGuestBe16Compat(base, header + 2u);
        const uint16_t nextDepth = depth == 0u ? 0u : static_cast<uint16_t>(depth - 1u);
        base[header] = static_cast<uint8_t>(nextDepth >> 8u);
        base[header + 1u] = static_cast<uint8_t>(nextDepth);
        base[header + 2u] = static_cast<uint8_t>(sequence >> 8u);
        base[header + 3u] = static_cast<uint8_t>(sequence);
        PPC_STORE_U32(header + 4u, next);
        context.r3.u32 = first;
        return;
    }
    if (api == "IoCreateDevice" || api == "StfsCreateDevice") {
        const uint32_t output = api == "IoCreateDevice" ? context.r8.u32 : context.r7.u32;
        if (!base || !validGuestRange(output, 4u)) { context.r3.u32 = kNtStatusInvalidParameter; return; }
        const uint32_t device = allocateGuestPhysicalRange(base, 0x24u, 0x1000u, 0x04u);
        const uint32_t extension = allocateGuestPhysicalRange(base, 0x1000u, 0x1000u, 0x04u);
        if (!device || !extension) {
            if (device) releaseGuestPhysicalRange(device);
            if (extension) releaseGuestPhysicalRange(extension);
            context.r3.u32 = kNtStatusNoMemory;
            return;
        }
        PPC_STORE_U32(device + 0x18u, extension);
        PPC_STORE_U32(output, device);
        context.r3.u32 = kNtStatusSuccess;
        recordRuntimeTrace(std::string(api) + " allocated an IoDevice and 4 KiB extension");
        return;
    }
    if (api == "IoDeleteDevice") {
        const uint32_t device = context.r3.u32;
        if (base && validGuestRange(device, 0x1Cu)) {
            const uint32_t extension = PPC_LOAD_U32(device + 0x18u);
            if (extension) releaseGuestPhysicalRange(extension);
            releaseGuestPhysicalRange(device);
        }
        return;
    }
    if (api == "IoInvalidDeviceRequest") { context.r3.u32 = 0xC0000010u; return; }
    if (api == "IoCompleteRequest") { context.r3.u32 = kNtStatusSuccess; return; }
    if (api == "IoDismountVolume" || api == "IoDismountVolumeByFileHandle" ||
        api == "StfsControlDevice") {
        context.r3.u32 = kNtStatusSuccess;
        recordRuntimeTrace(std::string(api) + " completed for the local read-only title volume");
        return;
    }
    if (api == "IoCheckShareAccess" || api == "IoSetShareAccess" ||
        api == "IoRemoveShareAccess") {
        const uint32_t fileObject = api == "IoRemoveShareAccess" ? context.r3.u32 : context.r5.u32;
        const uint32_t shareTable = api == "IoRemoveShareAccess" ? context.r4.u32 : context.r6.u32;
        if (!base || !validGuestRange(shareTable, 28u)) {
            context.r3.u32 = kNtStatusInvalidParameter;
            return;
        }
        std::lock_guard<std::mutex> guard(g_ioShareMutex);
        uint32_t openCount = PPC_LOAD_U32(shareTable + 0u);
        uint32_t readers = PPC_LOAD_U32(shareTable + 4u);
        uint32_t writers = PPC_LOAD_U32(shareTable + 8u);
        uint32_t deleters = PPC_LOAD_U32(shareTable + 12u);
        uint32_t sharedRead = PPC_LOAD_U32(shareTable + 16u);
        uint32_t sharedWrite = PPC_LOAD_U32(shareTable + 20u);
        uint32_t sharedDelete = PPC_LOAD_U32(shareTable + 24u);
        if (api == "IoRemoveShareAccess") {
            const auto existing = g_ioShareByFileObject.find(fileObject);
            if (existing != g_ioShareByFileObject.end()) {
                const auto [access, share] = existing->second;
                if ((access & 0x80000001u) != 0u && readers) --readers;
                if ((access & 0x40000006u) != 0u && writers) --writers;
                if ((access & 0x00010000u) != 0u && deleters) --deleters;
                if ((share & 1u) && sharedRead) --sharedRead;
                if ((share & 2u) && sharedWrite) --sharedWrite;
                if ((share & 4u) && sharedDelete) --sharedDelete;
                if (openCount) --openCount;
                g_ioShareByFileObject.erase(existing);
                PPC_STORE_U32(shareTable + 0u, openCount);
                PPC_STORE_U32(shareTable + 4u, readers);
                PPC_STORE_U32(shareTable + 8u, writers);
                PPC_STORE_U32(shareTable + 12u, deleters);
                PPC_STORE_U32(shareTable + 16u, sharedRead);
                PPC_STORE_U32(shareTable + 20u, sharedWrite);
                PPC_STORE_U32(shareTable + 24u, sharedDelete);
            }
            return;
        }
        const uint32_t access = context.r3.u32;
        const uint32_t share = context.r4.u32;
        const bool readAccess = (access & 0x80000001u) != 0u;
        const bool writeAccess = (access & 0x40000006u) != 0u;
        const bool deleteAccess = (access & 0x00010000u) != 0u;
        if ((readAccess && openCount > sharedRead) ||
            (writeAccess && openCount > sharedWrite) ||
            (deleteAccess && openCount > sharedDelete) ||
            ((share & 1u) == 0u && readers != 0u) ||
            ((share & 2u) == 0u && writers != 0u) ||
            ((share & 4u) == 0u && deleters != 0u)) {
            context.r3.u32 = 0xC0000043u; // STATUS_SHARING_VIOLATION
            return;
        }
        if (api == "IoSetShareAccess" || context.r7.u32 != 0u) {
            ++openCount;
            if (readAccess) ++readers;
            if (writeAccess) ++writers;
            if (deleteAccess) ++deleters;
            if (share & 1u) ++sharedRead;
            if (share & 2u) ++sharedWrite;
            if (share & 4u) ++sharedDelete;
            PPC_STORE_U32(shareTable + 0u, openCount);
            PPC_STORE_U32(shareTable + 4u, readers);
            PPC_STORE_U32(shareTable + 8u, writers);
            PPC_STORE_U32(shareTable + 12u, deleters);
            PPC_STORE_U32(shareTable + 16u, sharedRead);
            PPC_STORE_U32(shareTable + 20u, sharedWrite);
            PPC_STORE_U32(shareTable + 24u, sharedDelete);
            g_ioShareByFileObject[fileObject] = {access, share};
        }
        context.r3.u32 = kNtStatusSuccess;
        return;
    }
    if (api == "NetDll_XNetStartup" || api == "NetDll_XNetCleanup" ||
        api == "NetDll_XNetRegisterKey" || api == "NetDll_XNetUnregisterKey" ||
        api == "NetDll_XNetQosListen") {
        context.r3.u32 = kNtStatusSuccess;
        return;
    }
    if (api == "NetDll_XNetRandom") {
        const uint32_t output = context.r4.u32, length = context.r5.u32;
        if (!base || length > 16u * 1024u * 1024u ||
            (length != 0u && !validGuestRange(output, length))) {
            context.r3.u32 = kNtStatusInvalidParameter;
            return;
        }
        if (length) std::memset(base + output, 0xBB, length);
        context.r3.u32 = kNtStatusSuccess;
        return;
    }
    if (api == "NetDll_XNetGetEthernetLinkStatus") { context.r3.u32 = 0u; return; }
    if (api == "NetDll_XNetGetTitleXnAddr") {
        const uint32_t output = context.r4.u32;
        if (base && validGuestRange(output, 36u)) std::memset(base + output, 0, 36u);
        context.r3.u32 = 0u;
        return;
    }
    if (api == "NetDll_XNetDnsLookup") {
        const uint32_t event = context.r5.u32, outputPointer = context.r6.u32;
        const uint32_t dns = allocateGuestPhysicalRange(base, 0x100u, 0x1000u, 0x04u);
        if (base && dns) {
            PPC_STORE_U32(dns, 1u); // XNDNS status: lookup unavailable while XNet is offline.
            PPC_STORE_U32(dns + 4u, 0u);
            if (validGuestRange(outputPointer, 4u)) PPC_STORE_U32(outputPointer, dns);
        }
        if (event) signalGuestEventHandle(event);
        context.r3.u32 = dns ? kNtStatusSuccess : kNtStatusNoMemory;
        return;
    }
    if (api == "NetDll_XNetDnsRelease") {
        const uint32_t dns = context.r4.u32;
        const bool released = releaseGuestPhysicalRange(dns);
        context.r3.u32 = released || dns == 0u ? kNtStatusSuccess : kNtStatusInvalidParameter;
        return;
    }
    if (api == "NetDll_XNetQosLookup") {
        const uint32_t qosOut = context.r10.u32;
        const uint32_t qos = allocateGuestPhysicalRange(base, 0x100u, 0x1000u, 0x04u);
        if (qos && base) {
            PPC_STORE_U32(qos, 0u);
            PPC_STORE_U32(qos + 4u, 0u);
            if (validGuestRange(qosOut, 4u)) PPC_STORE_U32(qosOut, qos);
        }
        context.r3.u32 = qos ? kNtStatusSuccess : kNtStatusNoMemory;
        return;
    }
    if (api == "NetDll_XNetQosRelease") {
        const uint32_t qos = context.r4.u32;
        const bool released = releaseGuestPhysicalRange(qos);
        context.r3.u32 = released || qos == 0u ? kNtStatusSuccess : kNtStatusInvalidParameter;
        return;
    }
    if (api == "NetDll_XNetXnAddrToInAddr" || api == "NetDll_XNetServerToInAddr") {
        const uint32_t output = api == "NetDll_XNetXnAddrToInAddr" ? context.r6.u32 : context.r6.u32;
        if (base && validGuestRange(output, 4u)) PPC_STORE_U32(output, 0u);
        context.r3.u32 = 1u; // no live XNet address is available in this offline title session.
        return;
    }
    if (api == "KeBugCheck" || api == "KeBugCheckEx") {
        char event[160];
        std::snprintf(event, sizeof(event), "%.*s bugcheck code=0x%08X", static_cast<int>(api.size()), api.data(), context.r3.u32);
        throw std::runtime_error(event);
    }
    if (api == "RtlRaiseException" || api == "RtlUnwind") {
        char event[160];
        std::snprintf(event, sizeof(event), "%.*s requested guest exception/control unwind", static_cast<int>(api.size()), api.data());
        throw std::runtime_error(event);
    }
    if (api == "XeCryptSha") {
        std::vector<uint8_t> input;
        const uint32_t ptrs[] = {context.r3.u32, context.r5.u32, context.r7.u32};
        const uint32_t sizes[] = {context.r4.u32, context.r6.u32, context.r8.u32};
        if (!base) { context.r3.u32 = kNtStatusInvalidParameter; return; }
        uint64_t total = 0u;
        for (size_t i = 0; i < 3u; ++i) {
            if (sizes[i] == 0u) continue;
            if (sizes[i] > 64u * 1024u * 1024u || !validGuestRange(ptrs[i], sizes[i]) ||
                (total += sizes[i]) > 64u * 1024u * 1024u) {
                context.r3.u32 = kNtStatusInvalidParameter; return;
            }
            input.insert(input.end(), base + ptrs[i], base + ptrs[i] + sizes[i]);
        }
        const uint32_t output = context.r9.u32, outputSize = std::min<uint32_t>(context.r10.u32, 20u);
        if (outputSize != 0u && !validGuestRange(output, outputSize)) { context.r3.u32 = kNtStatusInvalidParameter; return; }
        const auto digest = xowueSha1(input);
        if (outputSize) std::memcpy(base + output, digest.data(), outputSize);
        return;
    }
    if (api == "XGetLanguage") { context.r3.u32 = 9u; return; }
    if (api == "XNetLogonGetTitleID" || api == "XamGetCurrentTitleId") { context.r3.u32 = kXowueTitleId; return; }
    if (api == "XamGetSystemVersion") { context.r3.u32 = 0u; return; }
    if (api == "XamUserGetSigninState") { context.r3.u32 = context.r3.u32 == 0u ? 1u : 0u; return; }
    if (api == "XamUserGetName") {
        const uint32_t user = context.r3.u32, output = context.r4.u32, capacity = context.r5.u32;
        if (user != 0u || !base || !validGuestRange(output, std::max(1u, capacity))) { context.r3.u32 = kXamNoSuchUser; return; }
        static constexpr char nameValue[] = "XOWUE Player";
        const uint32_t count = std::min<uint32_t>(capacity ? capacity - 1u : 0u, sizeof(nameValue) - 1u);
        if (count) std::memcpy(base + output, nameValue, count);
        if (capacity) base[output + count] = 0u;
        context.r3.u32 = kNtStatusSuccess; return;
    }
    if (api == "XamUserGetSigninInfo") {
        const uint32_t user = context.r3.u32, output = context.r5.u32;
        clearOutput(output, 40u);
        if (user != 0u || !base || !validGuestRange(output, 40u)) { context.r3.u32 = kXamNoSuchUser; return; }
        PPC_STORE_U64(output, kLocalUserXuid);
        PPC_STORE_U32(output + 12u, 1u);
        static constexpr char nameValue[] = "XOWUE Player";
        std::memcpy(base + output + 24u, nameValue, sizeof(nameValue) - 1u);
        context.r3.u32 = kNtStatusSuccess; return;
    }
    if (api == "XamUserGetXUID") {
        const uint32_t user = context.r3.u32, output = context.r5.u32;
        if (!base || !validGuestRange(output, 8u)) { context.r3.u32 = kXamErrorInvalidParameter; return; }
        PPC_STORE_U64(output, user == 0u ? kLocalUserXuid : 0u);
        context.r3.u32 = user == 0u ? kNtStatusSuccess : kXamNoSuchUser; return;
    }
    if (api == "XamUserCheckPrivilege") {
        const uint32_t output = context.r5.u32;
        if (base && validGuestRange(output, 4u)) PPC_STORE_U32(output, 0u);
        context.r3.u32 = kNtStatusSuccess; return;
    }
    if (api == "XamUserAreUsersFriends") { context.r3.u32 = 0u; return; }
    if (api == "XamUserReadProfileSettings" || api == "XamUserWriteProfileSettings") {
        context.r3.u32 = context.r3.u32 == 0u ? kNtStatusSuccess : kXamNoSuchUser; return;
    }
    if (api == "XamContentGetLicenseMask") {
        if (base && validGuestRange(context.r3.u32, 4u)) PPC_STORE_U32(context.r3.u32, 0xFFFFFFFFu);
        context.r3.u32 = kNtStatusSuccess; return;
    }
    if (api == "XamContentGetDeviceState") {
        const uint32_t device = context.r3.u32;
        const uint32_t overlapped = context.r4.u32;
        const bool connected = device == 1u || device == 2u;
        const uint32_t status = connected ? 0u : 1167u;
        if (overlapped && base && validGuestRange(overlapped, 16u)) {
            PPC_STORE_U32(overlapped + 4u, status);
            PPC_STORE_U32(overlapped + 8u, connected ? 0u : 1167u);
            PPC_STORE_U32(overlapped + 12u, 0u);
            const uint32_t event = PPC_LOAD_U32(overlapped);
            if (event) signalGuestEventHandle(event);
            context.r3.u32 = 997u; // X_ERROR_IO_PENDING after immediate completion.
        } else context.r3.u32 = status;
        return;
    }
    if (api == "XamContentGetDeviceData") {
        const uint32_t device = context.r3.u32, output = context.r4.u32;
        if (!base || !validGuestRange(output, 0x50u) || (device != 1u && device != 2u)) {
            context.r3.u32 = 1167u;
            return;
        }
        std::memset(base + output, 0, 0x50u);
        const uint64_t oneGiB = 1024ull * 1024ull * 1024ull;
        PPC_STORE_U32(output, device);
        PPC_STORE_U32(output + 4u, device == 1u ? 1u : 4u);
        PPC_STORE_U64(output + 8u, device == 1u ? 20u * oneGiB : 7u * oneGiB);
        PPC_STORE_U64(output + 16u, device == 1u ? 3u * oneGiB : 0u);
        const char *nameValue = device == 1u ? "XOWUE HDD" : "XOWUE Disc";
        for (size_t i = 0; nameValue[i] && i < 27u; ++i) {
            const uint16_t character = static_cast<uint8_t>(nameValue[i]);
            base[output + 24u + static_cast<uint32_t>(i * 2u)] =
                static_cast<uint8_t>(character >> 8u);
            base[output + 25u + static_cast<uint32_t>(i * 2u)] =
                static_cast<uint8_t>(character);
        }
        context.r3.u32 = kNtStatusSuccess;
        return;
    }
    if (api == "XamContentCreateEx") {
        const uint32_t disposition = context.r7.u32, license = context.r8.u32;
        if (base && validGuestRange(disposition, 4u)) PPC_STORE_U32(disposition, 2u);
        if (base && validGuestRange(license, 4u)) PPC_STORE_U32(license, 0xFFFFFFFFu);
        context.r3.u32 = kNtStatusSuccess;
        return;
    }
    if (api == "XamContentCreateEnumerator") {
        const uint32_t sizeOut = context.r8.u32, handleOut = context.r9.u32;
        if (base && validGuestRange(sizeOut, 4u)) PPC_STORE_U32(sizeOut, 0u);
        if (base && validGuestRange(handleOut, 4u)) PPC_STORE_U32(handleOut, 0u);
        context.r3.u32 = kNtStatusSuccess; return;
    }
    if (api == "XamEnumerate") {
        const uint32_t countOut = context.r6.u32;
        if (base && validGuestRange(countOut, 4u)) PPC_STORE_U32(countOut, 0u);
        context.r3.u32 = 0x80000006u; return;
    }
    if (api == "XamCreateEnumeratorHandle" || api == "XamGetPrivateEnumStructureFromHandle") {
        context.r3.u32 = 0u; return;
    }
    if (api == "XamLoaderGetLaunchData") {
        if (base && validGuestRange(context.r3.u32, 4u)) PPC_STORE_U32(context.r3.u32, 0u);
        context.r3.u32 = kXamNoSuchUser; return;
    }
    if (api == "XamLoaderLaunchTitle") { context.r3.u32 = kNotImplemented; return; }
    if (api == "XamTaskShouldExit") { context.r3.u32 = 0u; return; }
    if (api == "XamTaskSchedule") {
        PPCContext threadContext{};
        threadContext.r3.u32 = context.r6.u32;
        threadContext.r4.u32 = 0x00010000u;
        threadContext.r5.u32 = 0u;
        threadContext.r6.u32 = 0u;
        threadContext.r7.u32 = context.r3.u32;
        threadContext.r8.u32 = context.r4.u32;
        threadContext.r9.u32 = 0u;
        xowue_ExCreateThread(threadContext, base);
        context.r3.u32 = threadContext.r3.u32;
        if (context.r3.u32 == kNtStatusSuccess)
            recordRuntimeTrace("XamTaskSchedule dispatched callback on the guest PPC scheduler");
        return;
    }
    if (api == "XamTaskCloseHandle") {
        PPCContext closeContext{}; closeContext.r3.u32 = context.r3.u32;
        xowue_NtClose(closeContext); context.r3.u32 = closeContext.r3.u32; return;
    }
    if (api == "XamAlloc") {
        const uint32_t size = context.r3.u32;
        context.r3.u32 = allocateGuestPhysicalRange(base, size, 0x1000u, 0x04u); return;
    }
    if (api == "XamFree") {
        releaseGuestPhysicalRange(context.r3.u32); context.r3.u32 = 0u; return;
    }
    if (api == "XAudioGetSpeakerConfig") { context.r3.u32 = 0x00000003u; return; }
    if (api == "XAudioGetVoiceCategoryVolume") { context.r3.u32 = 0x3F800000u; return; }
    if (api == "XAudioGetVoiceCategoryVolumeChangeMask") { context.r3.u32 = 0u; return; }
    if (api == "XAudioRegisterRenderDriverClient" || api == "XAudioSubmitRenderDriverFrame" ||
        api == "XAudioUnregisterRenderDriverClient" || api == "XamVoiceClose" ||
        api == "XamVoiceSubmitPacket") { context.r3.u32 = 0u; return; }
    if (api == "XamVoiceCreate" || api == "XamVoiceHeadsetPresent") {
        if (api == "XamVoiceCreate" && base && validGuestRange(context.r5.u32, 4u))
            PPC_STORE_U32(context.r5.u32, 0u);
        context.r3.u32 = api == "XamVoiceCreate" ? 5u : 0u; return;
    }
    if (api == "XeKeysConsolePrivateKeySign" || api == "XeKeysConsoleSignatureVerification") {
        context.r3.u32 = 0u; return;
    }
    if (api == "XMACreateContext") {
        const uint32_t output = context.r3.u32;
        if (!base || !validGuestRange(output, 4u)) { context.r3.u32 = kNtStatusInvalidParameter; return; }
        const uint32_t contextAddress = allocateGuestPhysicalRange(base, 0x1000u, 0x1000u, 0x04u);
        if (!contextAddress) { context.r3.u32 = kNtStatusNoMemory; return; }
        g_guestXmaContexts.insert(contextAddress);
        PPC_STORE_U32(output, contextAddress);
        context.r3.u32 = kNtStatusSuccess;
        return;
    }
    if (api == "XMAReleaseContext") {
        const uint32_t contextAddress = context.r3.u32;
        const bool known = g_guestXmaContexts.erase(contextAddress) != 0u;
        if (known) releaseGuestPhysicalRange(contextAddress);
        context.r3.u32 = known ? kNtStatusSuccess : kNtStatusInvalidParameter;
        return;
    }
    if (api == "XamUserCreateAchievementEnumerator" || api == "XamUserCreateStatsEnumerator") {
        const uint32_t sizeOut = context.r9.u32, handleOut = context.r10.u32;
        if (base && validGuestRange(sizeOut, 4u)) PPC_STORE_U32(sizeOut, 0u);
        if (base && validGuestRange(handleOut, 4u)) PPC_STORE_U32(handleOut, 0u);
        context.r3.u32 = 0u;
        return;
    }
    if (api == "XamWriteGamerTile") { context.r3.u32 = kNtStatusSuccess; return; }
    if (api == "XMsgStartIORequest" || api == "XMsgStartIORequestEx" ||
        api == "XMsgInProcessCall" || api == "XMsgCancelIORequest") {
        recordRuntimeTrace(std::string(api) + " completed as an offline XAM service request");
        context.r3.u32 = kNtStatusSuccess;
        return;
    }
    if (api == "XexGetModuleHandle") {
        const uint32_t namePointer = context.r3.u32, output = context.r4.u32;
        if (!base || !validGuestRange(output, 4u)) { context.r3.u32 = kNtStatusInvalidParameter; return; }
        bool executable = namePointer == 0u;
        if (namePointer != 0u) {
            std::string moduleName;
            if (!readGuestCString(base, namePointer, moduleName, 260u)) {
                context.r3.u32 = kNtStatusInvalidParameter; return;
            }
            std::transform(moduleName.begin(), moduleName.end(), moduleName.begin(),
                [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
            executable = moduleName == "default.xex" || moduleName == "default";
        }
        PPC_STORE_U32(output, executable ? g_activeImageBase : 0u);
        context.r3.u32 = executable ? 0u : 1168u; // X_ERROR_NOT_FOUND
        return;
    }
    if (api == "XexGetModuleSection") {
        const uint32_t module = context.r3.u32, namePointer = context.r4.u32;
        const uint32_t dataOut = context.r5.u32, sizeOut = context.r6.u32;
        if (!base || (module != 0u && module != g_activeImageBase) ||
            !validGuestRange(dataOut, 4u) || !validGuestRange(sizeOut, 4u)) {
            context.r3.u32 = kNtStatusInvalidHandle; return;
        }
        std::string sectionName;
        if (!readGuestCString(base, namePointer, sectionName, 64u)) {
            context.r3.u32 = kNtStatusInvalidParameter; return;
        }
        const auto entrySection = std::find_if(g_activeImageSections.begin(), g_activeImageSections.end(),
            [](const auto &section) {
                return g_activeEntryPoint >= section.first &&
                       static_cast<uint64_t>(g_activeEntryPoint) <
                           static_cast<uint64_t>(section.first) + section.second;
            });
        if (sectionName != ".text" || entrySection == g_activeImageSections.end()) {
            PPC_STORE_U32(dataOut, 0u); PPC_STORE_U32(sizeOut, 0u);
            context.r3.u32 = 1168u;
            return;
        }
        PPC_STORE_U32(dataOut, entrySection->first);
        PPC_STORE_U32(sizeOut, entrySection->second);
        context.r3.u32 = kNtStatusSuccess;
        return;
    }
    if (api == "XexGetProcedureAddress") {
        const uint32_t module = context.r3.u32, symbol = context.r4.u32, output = context.r5.u32;
        if (!base || !validGuestRange(output, 4u) || (module != 0u && module != g_activeImageBase)) {
            context.r3.u32 = kNtStatusInvalidHandle; return;
        }
        if (symbol >= PPC_CODE_BASE && symbol - PPC_CODE_BASE < PPC_CODE_SIZE && findGuestFunction(symbol)) {
            PPC_STORE_U32(output, symbol);
            context.r3.u32 = kNtStatusSuccess;
        } else {
            // Do not manufacture an ARM64 AOT target for an unknown export.
            PPC_STORE_U32(output, 0u);
            context.r3.u32 = 127u; // X_ERROR_PROC_NOT_FOUND
            char event[180];
            std::snprintf(event,sizeof(event),
                "XexGetProcedureAddress unresolved module=%08X symbol=%08X output=%08X status=%08X",
                module,symbol,output,context.r3.u32);
            recordRuntimeTrace(event);
        }
        return;
    }
    if (api == "_snprintf" || api == "sprintf" || api == "_vsnprintf") {
        const uint32_t output = context.r3.u32;
        const uint32_t capacity = api == "sprintf" ? 0x10000u : context.r4.u32;
        const uint32_t formatPointer = api == "sprintf" ? context.r4.u32 : context.r5.u32;
        const uint32_t startIndex = api == "sprintf" ? 2u : 3u;
        const uint32_t arrayArguments = api == "_vsnprintf" ? context.r6.u32 : 0u;
        if (!base || capacity == 0u || capacity > 0x10000u ||
            !validGuestRange(output, capacity) || !validGuestRange(formatPointer, 1u)) {
            context.r3.u32 = 0xFFFFFFFFu;
            return;
        }
        const std::string result = formatGuestVarargs(context, base, formatPointer,
                                                       startIndex, arrayArguments);
        const uint32_t copied = std::min<uint32_t>(capacity ? capacity - 1u : 0u,
                                                   static_cast<uint32_t>(result.size()));
        if (copied) std::memcpy(base + output, result.data(), copied);
        base[output + copied] = 0u;
        context.r3.u32 = result.size() >= capacity ? 0xFFFFFFFFu
                                                   : static_cast<uint32_t>(result.size());
        return;
    }
    if (api.rfind("XamShow", 0u) == 0u) {
        if (api == "XamShowKeyboardUI" && base) {
            const uint32_t defaultText = context.r5.u32;
            const uint32_t output = context.r8.u32;
            const uint32_t capacity = std::min<uint32_t>(context.r9.u32, 8192u);
            if (output && capacity && validGuestRange(output, static_cast<uint64_t>(capacity) * 2u)) {
                uint32_t index = 0u;
                bool terminated = false;
                while (defaultText && index + 1u < capacity &&
                       validGuestRange(defaultText + index * 2u, 2u)) {
                    const uint16_t character = loadGuestBe16Compat(base, defaultText + index * 2u);
                    base[output + index * 2u] = static_cast<uint8_t>(character >> 8u);
                    base[output + index * 2u + 1u] = static_cast<uint8_t>(character);
                    ++index;
                    if (character == 0u) { terminated = true; break; }
                }
                if (!terminated) {
                    base[output + index * 2u] = 0u;
                    base[output + index * 2u + 1u] = 0u;
                }
            }
        }
        context.r3.u32 = kNtStatusSuccess;
        recordRuntimeTrace(std::string(api) + " completed by the local offline UI policy");
        return;
    }
    if (api == "XamNotifyCreateListener") {
        const uint32_t handle = allocateGuestHandle();
        auto listener = std::make_shared<GuestWaitable>();
        listener->kind = GuestWaitable::Kind::Event;
        listener->handle = handle;
        listener->manualReset = true;
        listener->signaled = false;
        { std::lock_guard<std::mutex> lock(g_guestObjectMutex); g_guestWaitables[handle] = listener; }
        context.r3.u32 = handle ? handle : kNtStatusNoMemory;
        return;
    }
    if (api == "XamSessionCreateHandle") {
        const uint32_t handle = allocateGuestHandle();
        auto session = std::make_shared<GuestWaitable>();
        session->kind = GuestWaitable::Kind::Event;
        session->handle = handle;
        session->manualReset = true;
        session->signaled = true;
        { std::lock_guard<std::mutex> lock(g_guestObjectMutex); g_guestWaitables[handle] = session; }
        context.r3.u32 = handle ? handle : kNtStatusNoMemory;
        return;
    }
    if (api == "XamSessionRefObjByHandle") {
        context.r3.u32 = lookupGuestWaitable(context.r3.u32)
            ? kNtStatusSuccess : kNtStatusInvalidHandle;
        return;
    }
    if (api == "XNotifyPositionUI") { context.r3.u32 = kNtStatusSuccess; return; }
    if (api == "XNotifyGetNext") { context.r3.u32 = 0x00000102u; return; }
    if (api == "ObIsTitleObject") { context.r3.u32 = 0u; return; }
    if (api == "ObReferenceObject") {
        const uint32_t object = context.r3.u32;
        if (object) { std::lock_guard<std::mutex> lock(g_guestObjectMutex); ++g_guestObjectReferences[object]; }
        return;
    }
    if (api == "__C_specific_handler") {
        recordRuntimeTrace("__C_specific_handler returned EXCEPTION_CONTINUE_SEARCH (1)");
        context.r3.u32 = 1u;
        return;
    }
    if (api == "RtlImageXexHeaderField") {
        context.r3.u32 = context.r4.u32 == 0x00040006u ? g_activeExecutionInfoAddress : 0u; return;
    }
    if (api == "VdGet") { context.r3.u32 = 0u; return; }
    if (api == "KeTls") { context.r3.u32 = 0u; return; }
    char message[256];
    std::snprintf(message, sizeof(message),
                  "XOWUE import contract failure: classified handler missing for %.*s",
                  static_cast<int>(api.size()), api.data());
    recordRuntimeTrace(message);
    throw std::runtime_error(message);
}

void xowue_ExCreateThread(PPCContext &context, uint8_t *base) {
    const uint32_t handlePointer = context.r3.u32;
    const uint32_t requestedStack = context.r4.u32;
    const uint32_t threadIdPointer = context.r5.u32;
    const uint32_t startupAddress = context.r6.u32;
    const uint32_t startAddress = context.r7.u32;
    const uint32_t startContext = context.r8.u32;
    const uint32_t creationFlags = context.r9.u32;
    if (!base || (handlePointer != 0u && handlePointer > kGuestAddressSpaceSize - 4u) ||
        (threadIdPointer != 0u && threadIdPointer > kGuestAddressSpaceSize - 4u) ||
        startAddress == 0u || !findGuestFunction(startAddress) ||
        (startupAddress != 0u && !findGuestFunction(startupAddress))) {
        context.r3.u32 = kNtStatusInvalidParameter;
        recordRuntimeTrace("ExCreateThread rejected invalid guest pointer or unmapped PPC entry");
        return;
    }
    if (g_schedulerStopRequested.load()) {
        context.r3.u32 = kNtStatusCancelled;
        recordRuntimeTrace("ExCreateThread rejected while scheduler is stopping");
        return;
    }
    const std::shared_ptr<GuestMemory> memory = g_activeGuestMemory.lock();
    if (!memory || memory->base != base) {
        context.r3.u32 = kNtStatusUnsuccessful;
        recordRuntimeTrace("ExCreateThread has no live XEX memory session");
        return;
    }

    auto thread = std::make_shared<GuestThread>();
    if (!allocateGuestThreadStack(requestedStack, thread->stackBase, thread->stackSize)) {
        context.r3.u32 = kNtStatusNoMemory;
        recordRuntimeTrace("ExCreateThread could not reserve guest PPC stack");
        return;
    }
    thread->startupAddress = startupAddress;
    thread->startAddress = startAddress;
    thread->startContext = startContext;
    thread->creationFlags = creationFlags;
    thread->completion = std::make_shared<GuestWaitable>();
    thread->completion->kind = GuestWaitable::Kind::Thread;
    thread->completion->manualReset = true;
    thread->completion->signaled = false;
    if ((creationFlags & 0x1u) != 0u) thread->suspendCount.store(1u);

    std::unique_lock<std::mutex> threadsLock(g_guestThreadMutex);
    if (g_schedulerStopRequested.load()) {
        context.r3.u32 = kNtStatusCancelled;
        return;
    }
    thread->id = g_nextGuestThreadId++;
    thread->objectAddress = g_nextGuestThreadObjectAddress;
    g_nextGuestThreadObjectAddress += 0x1000u;
    thread->pcrAddress = g_nextGuestPcrAddress;
    g_nextGuestPcrAddress += kGuestThreadMetadataStride;
    thread->tlsAddress = g_nextGuestTlsAddress;
    g_nextGuestTlsAddress += kGuestThreadTlsStride;
    if (thread->objectAddress >= 0x7E000000u ||
        thread->pcrAddress >= 0x7D000000u ||
        thread->tlsAddress >= 0x7C000000u) {
        context.r3.u32 = kNtStatusNoMemory;
        recordRuntimeTrace("ExCreateThread guest thread-object range exhausted");
        return;
    }
    initializeGuestThreadEnvironment(base, thread->objectAddress, thread->pcrAddress,
                                     thread->tlsAddress, thread->stackBase,
                                     thread->stackSize, thread->id, startAddress,
                                     creationFlags, thread->suspendCount.load());
    thread->handle = allocateGuestHandle();
    if (thread->handle == 0u) {
        context.r3.u32 = kNtStatusNoMemory;
        recordRuntimeTrace("ExCreateThread guest handle table exhausted");
        return;
    }
    thread->completion->handle = thread->handle;
    thread->completion->objectAddress = thread->objectAddress;
    g_guestThreadsByHandle[thread->handle] = thread;
    g_guestThreadsByObject[thread->objectAddress] = thread;
    g_guestThreads.push_back(thread);
    {
        std::lock_guard<std::mutex> objectsLock(g_guestObjectMutex);
        g_guestWaitables[thread->handle] = thread->completion;
        g_guestWaitables[thread->objectAddress] = thread->completion;
    }

    try {
                const uint32_t imageBase = g_activeImageBase;
        thread->hostThread = std::thread([thread, memory, imageBase, base] {
            g_currentGuestThreadId = thread->id;
            g_currentGuestThread = thread.get();
            uint32_t exitCode = kNtStatusSuccess;
            try {
                {
                    std::unique_lock<std::mutex> stateLock(thread->stateMutex);
                    thread->stateChanged.wait_for(stateLock, std::chrono::milliseconds(10), [] {
                        return g_schedulerStopRequested.load();
                    });
                }
                checkpointGuestThread();
                PPCFunc *entryFunction = findGuestFunction(
                    thread->startupAddress != 0u ? thread->startupAddress : thread->startAddress);
                if (!entryFunction) throw std::runtime_error("PPC thread entry is missing from AOT map");
                PPCContext childContext{};
                const uint32_t stackTop = thread->stackBase + thread->stackSize;
                childContext.r1.u32 = (stackTop - 0x100u) & ~0xFu;
                childContext.r2.u32 = imageBase;
                childContext.r13.u32 = thread->pcrAddress;
                childContext.lr = 0;
                PPC_STORE_U32(childContext.r1.u32, 0u);
                if (thread->startupAddress != 0u) {
                    childContext.r3.u32 = thread->startAddress;
                    childContext.r4.u32 = thread->startContext;
                } else {
                    childContext.r3.u32 = thread->startContext;
                }
                char started[160];
                std::snprintf(started, sizeof(started),
                              "PPC thread start id=%u xapi=0x%08X entry=0x%08X context=0x%08X stack=0x%08X+0x%08X",
                              thread->id, thread->startupAddress, thread->startAddress,
                              thread->startContext, thread->stackBase, thread->stackSize);
                recordRuntimeTrace(started);
                entryFunction(childContext, memory->base);
                exitCode = thread->startupAddress == 0u ? childContext.r3.u32 : 0u;
            } catch (const GuestThreadExit &exit) {
                exitCode = exit.exitCode;
            } catch (const GuestThreadStopRequested &) {
                exitCode = kNtStatusCancelled;
            } catch (const std::exception &error) {
                recordRuntimeTrace(std::string("PPC thread exception id=") +
                                   std::to_string(thread->id) + " detail=" + error.what());
                exitCode = kNtStatusUnsuccessful;
            } catch (...) {
                recordRuntimeTrace("PPC thread ended with unknown native exception");
                exitCode = kNtStatusUnsuccessful;
            }
            finishGuestThread(thread, exitCode);
            g_currentGuestThread = nullptr;
            g_currentGuestThreadId = 1u;
        });
    } catch (const std::system_error &error) {
        g_guestThreadsByHandle.erase(thread->handle);
        g_guestThreadsByObject.erase(thread->objectAddress);
        g_guestThreads.pop_back();
        {
            std::lock_guard<std::mutex> objectsLock(g_guestObjectMutex);
            g_guestWaitables.erase(thread->handle);
            g_guestWaitables.erase(thread->objectAddress);
        }
        context.r3.u32 = kNtStatusNoMemory;
        recordRuntimeTrace(std::string("ExCreateThread host thread creation failed: ") + error.what());
        return;
    }
    threadsLock.unlock();

    if (handlePointer != 0u) {
        const uint32_t outputHandle = (creationFlags & 0x80u) != 0u
            ? thread->objectAddress : thread->handle;
        PPC_STORE_U32(handlePointer, outputHandle);
    }
    if (threadIdPointer != 0u) PPC_STORE_U32(threadIdPointer, thread->id);
    context.r3.u32 = kNtStatusSuccess;
    char event[128];
    std::snprintf(event, sizeof(event), "ExCreateThread id=%u handle=0x%08X stack=0x%08X+0x%08X flags=0x%08X",
                  thread->id, thread->handle, thread->stackBase, thread->stackSize, creationFlags);
    recordRuntimeTrace(event);
}

uint32_t xowue_MmAllocatePhysicalMemoryEx(PPCContext &context, uint8_t *base) {
    const uint32_t flags = context.r3.u32;
    const uint32_t requestedSize = context.r4.u32;
    const uint32_t protection = context.r5.u32;
    const uint32_t minAddress = context.r6.u32;
    const uint32_t maxAddress = context.r7.u32;
    uint32_t alignment = context.r8.u32;
    constexpr uint32_t kPageReadOnly = 0x02u;
    constexpr uint32_t kPageReadWrite = 0x04u;
    constexpr uint32_t kPageNoCache = 0x200u;
    constexpr uint32_t kPageWriteCombine = 0x400u;
    constexpr uint32_t kLargePages = 0x20000000u;
    constexpr uint32_t kSixteenMegPages = 0x80000000u;
    if (!base || requestedSize == 0u ||
        (protection & (kPageReadOnly | kPageReadWrite)) == 0u) {
        context.r3.u32 = 0u;
        recordRuntimeTrace("MmAllocatePhysicalMemoryEx rejected size/protection");
        return 0u;
    }
    uint32_t pageSize = 0x1000u;
    if (protection & kSixteenMegPages) pageSize = 0x01000000u;
    else if (protection & kLargePages) pageSize = 0x10000u;
    if (alignment == 0u) alignment = pageSize;
    alignment = std::max(alignment, pageSize);
    const uint32_t hostProtection = protection & (kPageNoCache | kPageWriteCombine);
    const uint32_t address = allocateGuestPhysicalRange(base, requestedSize,
                                                        alignment, hostProtection);
    const uint64_t end = static_cast<uint64_t>(address) + requestedSize;
    if (address == 0u || (minAddress != 0u && address < minAddress) ||
        (maxAddress != 0u && maxAddress != 0xFFFFFFFFu && end - 1u > maxAddress)) {
        if (address != 0u) releaseGuestPhysicalRange(address);
        context.r3.u32 = 0u;
        char event[176];
        std::snprintf(event, sizeof(event),
                      "MmAllocatePhysicalMemoryEx failed flags=0x%08X size=0x%08X align=0x%08X min=0x%08X max=0x%08X",
                      flags, requestedSize, alignment, minAddress, maxAddress);
        recordRuntimeTrace(event);
        return 0u;
    }
    context.r3.u32 = address;
    char event[176];
    std::snprintf(event, sizeof(event),
                  "MmAllocatePhysicalMemoryEx flags=0x%08X size=0x%08X protect=0x%08X align=0x%08X -> 0x%08X",
                  flags, requestedSize, protection, alignment, address);
    recordRuntimeTrace(event);
    return address;
}

void xowue_MmFreePhysicalMemory(PPCContext &context) {
    const uint32_t allocationType = context.r3.u32;
    const uint32_t address = context.r4.u32;
    const bool released = releaseGuestPhysicalRange(address);
    context.r3.u32 = released ? kNtStatusSuccess : kNtStatusMemoryNotAllocated;
    char event[128];
    std::snprintf(event, sizeof(event),
                  "MmFreePhysicalMemory type=0x%08X address=0x%08X result=0x%08X",
                  allocationType, address, context.r3.u32);
    recordRuntimeTrace(event);
}

void xowue_MmGetPhysicalAddress(PPCContext &context) {
    // The guest 32-bit physical heap is represented by an identity-mapped
    // range in the 4 GiB guest address space. GPU-facing users still go through
    // Xenos packet validation before their address is consumed.
    const uint32_t address = context.r3.u32;
    char event[112];
    std::snprintf(event, sizeof(event), "MmGetPhysicalAddress virtual=0x%08X physical=0x%08X",
                  address, address);
    recordRuntimeTrace(event);
}

void xowue_MmMapIoSpace(PPCContext &context) {
    const uint32_t sourceAddress = context.r4.u32;
    const uint32_t length = context.r5.u32;
    const uint32_t flags = context.r6.u32;
    context.r3.u32 = sourceAddress;
    char event[144];
    std::snprintf(event, sizeof(event),
                  "MmMapIoSpace source=0x%08X size=0x%08X flags=0x%08X -> identity mapping",
                  sourceAddress, length, flags);
    recordRuntimeTrace(event);
}

void xowue_ExAllocatePool(PPCContext &context, uint8_t *base) {
    const uint32_t size = context.r3.u32;
    const uint32_t address = allocateGuestPhysicalRange(base, size, 0x1000u, 0x04u);
    context.r3.u32 = address;
    recordRuntimeTrace("ExAllocatePool size=0x" + [&] {
        char value[16];
        std::snprintf(value, sizeof(value), "%08X", size);
        return std::string(value);
    }() + " -> 0x" + [&] {
        char value[16];
        std::snprintf(value, sizeof(value), "%08X", address);
        return std::string(value);
    }());
}

void xowue_ExFreePool(PPCContext &context) {
    const uint32_t address = context.r3.u32;
    const bool released = releaseGuestPhysicalRange(address);
    recordRuntimeTrace("ExFreePool address=0x" + [&] {
        char value[16];
        std::snprintf(value, sizeof(value), "%08X", address);
        return std::string(value);
    }() + (released ? " released" : " ignored-unknown-range"));
}

bool validGuestRange(uint32_t address, uint64_t size) {
    return size != 0u && static_cast<uint64_t>(address) + size <= kGuestAddressSpaceSize;
}

static uint16_t loadGuestBe16(uint8_t *base, uint32_t address) {
    return static_cast<uint16_t>((static_cast<uint16_t>(base[address]) << 8u) |
                                 static_cast<uint16_t>(base[address + 1u]));
}

static void storeGuestBe16(uint8_t *base, uint32_t address, uint16_t value) {
    base[address] = static_cast<uint8_t>(value >> 8u);
    base[address + 1u] = static_cast<uint8_t>(value);
}

static bool readGuestAnsiString(uint8_t *base, uint32_t descriptor,
                                std::string &value) {
    if (!base || !validGuestRange(descriptor, 8u)) return false;
    const uint16_t length = loadGuestBe16(base, descriptor);
    const uint32_t buffer = PPC_LOAD_U32(descriptor + 4u);
    if (length > 0x4000u || (length != 0u && !validGuestRange(buffer, length)))
        return false;
    value.assign(reinterpret_cast<const char *>(base + buffer), length);
    return value.find('\0') == std::string::npos;
}

static std::string lowerGuestPath(std::string value) {
    std::replace(value.begin(), value.end(), '\\', '/');
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    return value;
}

static bool translateGuestFilePath(const std::string &guestPath, bool forWrite,
                                  std::filesystem::path &hostPath) {
    if (guestPath.empty() || guestPath.size() > 0x4000u) return false;
    std::string normalized = guestPath;
    std::replace(normalized.begin(), normalized.end(), '\\', '/');
    // NT Xbox object manager paths commonly begin with the DOS-device
    // namespace; strip only the recognized exact prefix before mapping.
    if (normalized.rfind("/??/",0u)==0u)
        normalized.erase(0u,4u);
    if (normalized.rfind("??/",0u)==0u)
        normalized.erase(0u,3u);
    const std::string lower = lowerGuestPath(normalized);
    bool saveDevice = false;
    size_t prefixLength = 0u;
    const std::array<std::string, 6> gamePrefixes = {
        "game:", "d:", "dvd:", "/device/cdrom0", "/device/harddisk0/partition1", ""
    };
    const std::array<std::string, 4> savePrefixes = {
        "u:", "t:", "cache:", "/device/harddisk0/partition2"
    };
    for (const auto &prefix : savePrefixes) {
        if (lower.rfind(prefix, 0u) == 0u) {
            saveDevice = true;
            prefixLength = prefix.size();
            break;
        }
    }
    if (prefixLength == 0u) {
        for (const auto &prefix : gamePrefixes) {
            if (!prefix.empty() && lower.rfind(prefix, 0u) == 0u) {
                prefixLength = prefix.size();
                break;
            }
        }
    }
    std::string relative = normalized.substr(prefixLength);
    while (!relative.empty() && relative.front() == '/') relative.erase(relative.begin());
    std::filesystem::path rel(relative);
    if (rel.empty()) rel = ".";
    for (const auto &part : rel) {
        if (part == ".." || part == "." || part.empty()) {
            if (part == "..") return false;
        }
    }
    const auto root = saveDevice ? g_guestSaveRoot : g_guestGameRoot;
    if (root.empty()) return false;
    hostPath = root / rel;

    // Resolve existing components case-insensitively, as Xbox file paths are
    // case-insensitive while iOS's filesystem is not.
    std::filesystem::path actual = root;
    std::error_code ec;
    for (const auto &part : rel) {
        if (part == "." || part.empty()) continue;
        std::filesystem::path match;
        if (std::filesystem::is_directory(actual, ec)) {
            const std::string wanted = lowerGuestPath(part.string());
            for (std::filesystem::directory_iterator it(actual, ec), end;
                 !ec && it != end; it.increment(ec)) {
                if (lowerGuestPath(it->path().filename().string()) == wanted) {
                    match = it->path().filename();
                    break;
                }
            }
        }
        actual /= match.empty() ? part : match;
    }
    hostPath = actual;
    const auto normalizedRoot = std::filesystem::weakly_canonical(root, ec);
    ec.clear();
    const auto normalizedTarget = std::filesystem::weakly_canonical(hostPath.parent_path(), ec);
    if (!ec) {
        auto rootIt = normalizedRoot.begin();
        auto targetIt = normalizedTarget.begin();
        for (; rootIt != normalizedRoot.end() && targetIt != normalizedTarget.end();
             ++rootIt, ++targetIt) {
            if (*rootIt != *targetIt) return false;
        }
        if (rootIt != normalizedRoot.end()) return false;
    }
    if (forWrite && !saveDevice) return false;
    return true;
}

static std::shared_ptr<GuestFile> lookupGuestFile(uint32_t handle) {
    std::lock_guard<std::mutex> lock(g_guestFileMutex);
    const auto it = g_guestFiles.find(handle);
    return it == g_guestFiles.end() ? nullptr : it->second;
}

static void writeGuestIoStatus(uint8_t *base, uint32_t address,
                               uint32_t status, uint32_t information) {
    if (!base || address == 0u || !validGuestRange(address, 8u)) return;
    PPC_STORE_U32(address, status);
    PPC_STORE_U32(address + 4u, information);
}

static bool isKnownOptionalStartupMovie(const std::string &guestPath) {
    const std::string lower = lowerGuestPath(guestPath);
    if (lower.find("wgame/movies/") == std::string::npos) return false;
    const size_t slash = lower.find_last_of('/');
    const std::string filename = slash == std::string::npos
        ? lower : lower.substr(slash + 1u);
    return filename == "ravenlogo.xxx" || filename == "blank.bik" ||
           filename == "blank.xxx" ||
           filename == "ue3_logo.xxx" || filename == "fox_logo.xxx" ||
           filename == "marvel_intro.xxx" || filename == "atvi_logo.xxx";
}

static uint32_t createGuestFile(uint8_t *base, const std::string &guestPath,
                                uint32_t desiredAccess, uint32_t disposition,
                                uint32_t options, uint32_t &handleOut,
                                uint32_t &actionOut) {
    handleOut = 0u;
    actionOut = 0u;
    const bool read = (desiredAccess & 0x80000000u) != 0u || (desiredAccess & 1u) != 0u;
    const bool write = (desiredAccess & 0x40000000u) != 0u ||
                       (desiredAccess & 2u) != 0u || (desiredAccess & 4u) != 0u;
    const bool directoryOnly = (options & 0x00000001u) != 0u;
    const bool fileOnly = (options & 0x00000040u) != 0u;
    std::filesystem::path path;
    if (!translateGuestFilePath(guestPath, write, path)) return kNtStatusInvalidParameter;
    std::error_code ec;
    bool exists = std::filesystem::exists(path, ec);
    if (ec) exists = false;

    // UE3's startup sequence may poll its movie player forever after a
    // missing optional logo/blank Bink file. Provide a zero-byte EOF stream
    // for only the known startup movies, outside the game directory, so the
    // native guest file API reports a successful open followed by EOF. Never
    // synthesize gameplay assets or modify the user's game dump.
    bool virtualStartupMovie = false;
    if (!exists && !write && !directoryOnly &&
        disposition == 1u && isKnownOptionalStartupMovie(guestPath) &&
        !g_guestSaveRoot.empty()) {
        const std::string normalized = lowerGuestPath(guestPath);
        const size_t slash = normalized.find_last_of('/');
        const std::string filename = slash == std::string::npos
            ? normalized : normalized.substr(slash + 1u);
        const std::filesystem::path virtualRoot =
            g_guestSaveRoot / ".XOWUEVirtualMedia";
        std::filesystem::create_directories(virtualRoot, ec);
        if (!ec) {
            path = virtualRoot / filename;
            if (!std::filesystem::exists(path, ec) && !ec) {
                std::ofstream emptyMovie(path, std::ios::binary);
                if (!emptyMovie) ec = std::make_error_code(std::errc::permission_denied);
            }
        }
        exists = !ec && std::filesystem::is_regular_file(path, ec);
        virtualStartupMovie = exists && !ec;
        if (virtualStartupMovie) {
            recordRuntimeTrace("XOWUE_OPTIONAL_STARTUP_MOVIE_EOF guest=" +
                               guestPath + " virtual=1 bytes=0");
        }
    }

    const bool existedBeforeOpen = exists;
    const bool createNew = disposition == 2u || disposition == 3u || disposition == 5u || disposition == 0u;
    if (!exists && disposition == 1u) return 0xC0000034u; // STATUS_OBJECT_NAME_NOT_FOUND
    if (exists && disposition == 2u) return 0xC0000035u; // STATUS_OBJECT_NAME_COLLISION
    if (!exists && !createNew) return 0xC0000034u;
    if ((directoryOnly && exists && !std::filesystem::is_directory(path, ec)) ||
        (fileOnly && exists && std::filesystem::is_directory(path, ec)))
        return kNtStatusInvalidParameter;
    if (!exists && (directoryOnly || (options & 0x00000002u) != 0u)) {
        std::filesystem::create_directories(path, ec);
    } else if (!exists && write) {
        std::filesystem::create_directories(path.parent_path(), ec);
        if (!ec) {
            std::ofstream create(path, std::ios::binary);
            if (!create) ec = std::make_error_code(std::errc::permission_denied);
        }
    }
    if (ec) return 0xC0000022u;
    exists = std::filesystem::exists(path, ec);
    if (!exists || ec) return 0xC0000034u;
    auto file = std::make_shared<GuestFile>();
    file->path = path;
    file->directory = std::filesystem::is_directory(path, ec);
    if (file->directory && fileOnly) return kNtStatusInvalidParameter;
    if (!file->directory) {
        file->readable = read || !write;
        file->writable = write;
        std::ios::openmode mode = std::ios::binary;
        if (file->readable) mode |= std::ios::in;
        if (file->writable) mode |= std::ios::out;
        if (disposition == 0u || disposition == 4u || disposition == 5u)
            mode |= std::ios::trunc;
        file->stream.open(path, mode);
        if (!file->stream && file->writable && !file->readable) {
            file->stream.clear();
            file->stream.open(path, std::ios::binary | std::ios::out |
                                      ((disposition == 4u || disposition == 5u)
                                           ? std::ios::trunc : std::ios::openmode{}));
        }
        if (!file->stream) return 0xC0000022u;
    }
    const uint32_t handle = allocateGuestHandle();
    if (handle == 0u) return kNtStatusNoMemory;
    const uint32_t objectAddress = allocateGuestEventObjectAddress();
    if (objectAddress == 0u) return kNtStatusNoMemory;
    file->completion = std::make_shared<GuestWaitable>();
    file->completion->kind = GuestWaitable::Kind::Event;
    file->completion->handle = handle;
    file->completion->objectAddress = objectAddress;
    file->completion->manualReset = true;
    file->completion->signaled = true;
    {
        std::lock_guard<std::mutex> lock(g_guestFileMutex);
        g_guestFiles[handle] = file;
    }
    {
        std::lock_guard<std::mutex> lock(g_guestObjectMutex);
        g_guestWaitables[handle] = file->completion;
        g_guestWaitables[objectAddress] = file->completion;
    }
    handleOut = handle;
    actionOut = existedBeforeOpen ? 1u : 2u;
    (void)base;
    return kNtStatusSuccess;
}

uint32_t guestStackArgument(PPCContext &context, uint8_t *base, uint32_t argumentIndex) {
    if (!base || argumentIndex < 9u || argumentIndex > 16u) return 0u;
    const uint32_t offset = 84u + (argumentIndex - 9u) * 8u;
    if (context.r1.u32 > kGuestAddressSpaceSize - offset - 4u) return 0u;
    return PPC_LOAD_U32(context.r1.u32 + offset);
}

void storeGuestFloat(uint8_t *base, uint32_t address, float value) {
    uint32_t bits = 0;
    std::memcpy(&bits, &value, sizeof(bits));
    PPC_STORE_U32(address, bits);
}

struct PM4ParseSummary {
    uint64_t packets = 0;
    uint64_t draws = 0;
    uint64_t indirectBuffers = 0;
    uint64_t swaps = 0;
    uint64_t malformed = 0;
    uint64_t frameDecodeFailures = 0;
    uint64_t guestMemoryWrites = 0;
};

void xowue_VdInitializeEngines(PPCContext &context) {
    std::lock_guard<std::mutex> lock(g_xenosMutex);
    g_xenosFrontend.enginesInitialized = true;
    context.r3.u32 = 1u;
    recordRuntimeTrace("VdInitializeEngines accepted; engine flag set only; ring pump awaits guest WPTR/checkpoint or VdSwap; no draw or frame implied");
}

void xowue_VdShutdownEngines() {
    std::lock_guard<std::mutex> lock(g_xenosMutex);
    g_xenosFrontend.enginesInitialized = false;
    recordRuntimeTrace("VdShutdownEngines completed");
}

void xowue_VdInitializeRingBuffer(PPCContext &context, uint8_t *base) {
    const uint32_t address = context.r3.u32;
    const uint32_t log2 = context.r4.u32;
    if (!base || address == 0u || log2 > 26u) {
        context.r3.u32 = 0u;
        recordRuntimeTrace("VdInitializeRingBuffer rejected address or size_log2");
        return;
    }
    const uint32_t size = uint32_t{1} << (log2 + 3u);
    if (!validGuestRange(address, size)) {
        context.r3.u32 = 0u;
        recordRuntimeTrace("VdInitializeRingBuffer range exceeds guest memory");
        return;
    }
    std::memset(base + address, 0, size);
    {
        std::lock_guard<std::mutex> pumpLock(g_xenosPumpMutex);
        std::lock_guard<std::mutex> lock(g_xenosMutex);
        g_xenosFrontend.ringBufferAddress = address;
        g_xenosFrontend.ringBufferSize = size;
        g_xenosFrontend.ringReadPointer = 0u;
        g_xenosFrontend.swapFetch = {};
        g_xenosFrontend.swapFetchMask = 0u;
        g_xenosFrontend.swapFetchValid = false;
    }
    context.r3.u32 = 0u;
    char event[112];
    std::snprintf(event, sizeof(event), "VdInitializeRingBuffer address=0x%08X size=0x%08X log2=%u",
                  address, size, log2);
    recordRuntimeTrace(event);
}

void xowue_VdEnableRingBufferRPtrWriteBack(PPCContext &context) {
    const uint32_t address = context.r3.u32;
    const uint32_t blockLog2 = context.r4.u32;
    if (address >= kGuestAddressSpaceSize - 4u || blockLog2 > 19u) {
        context.r3.u32 = kNtStatusInvalidParameter;
        recordRuntimeTrace("VdEnableRingBufferRPtrWriteBack rejected pointer/log2");
        return;
    }
    {
        std::lock_guard<std::mutex> lock(g_xenosMutex);
        g_xenosFrontend.readPointerWritebackAddress = address;
        g_xenosFrontend.readPointerBlockSizeLog2 = blockLog2;
    }
    context.r3.u32 = kNtStatusSuccess;
    recordRuntimeTrace("VdEnableRingBufferRPtrWriteBack address=0x" + [&] {
        char value[16];
        std::snprintf(value, sizeof(value), "%08X", address);
        return std::string(value);
    }() + " block_log2=" + std::to_string(blockLog2));
}

void xowue_VdGetSystemCommandBuffer(PPCContext &context, uint8_t *base) {
    const uint32_t commandBuffer = context.r3.u32;
    const uint32_t sentinel = context.r4.u32;
    if (!base || commandBuffer == 0u || sentinel == 0u ||
        !validGuestRange(commandBuffer, 0x94u) || !validGuestRange(sentinel, 4u)) {
        context.r3.u32 = kNtStatusInvalidParameter;
        return;
    }
    std::memset(base + commandBuffer, 0, 0x94u);
    PPC_STORE_U32(commandBuffer, 0xBEEF0000u);
    PPC_STORE_U32(sentinel, 0xBEEF0001u);
    context.r3.u32 = kNtStatusSuccess;
    recordRuntimeTrace("VdGetSystemCommandBuffer initialized 0x94-byte sentinel buffer");
}

void xowue_VdSetSystemCommandBufferGpuIdentifierAddress(PPCContext &context) {
    std::lock_guard<std::mutex> lock(g_xenosMutex);
    g_xenosFrontend.systemCommandBufferGpuAddress = context.r3.u32;
    recordRuntimeTrace("VdSetSystemCommandBufferGpuIdentifierAddress address=0x" + [&] {
        char value[16];
        std::snprintf(value, sizeof(value), "%08X", context.r3.u32);
        return std::string(value);
    }());
}

void xowue_VdSetGraphicsInterruptCallback(PPCContext &context) {
    std::lock_guard<std::mutex> lock(g_xenosMutex);
    g_xenosFrontend.graphicsInterruptCallback = context.r3.u32;
    g_xenosFrontend.graphicsInterruptContext = context.r4.u32;
    recordRuntimeTrace("VdSetGraphicsInterruptCallback callback=0x" + [&] {
        char value[16];
        std::snprintf(value, sizeof(value), "%08X", context.r3.u32);
        return std::string(value);
    }());
}

static uint64_t xenosTiledOffset2D(uint32_t x, uint32_t y,
                                   uint32_t pitchAligned,
                                   uint32_t bytesPerPixelLog2) {
    const uint64_t outerBlocks =
        ((static_cast<uint64_t>(y >> 5u) * (pitchAligned >> 5u)) + (x >> 5u)) << 6u;
    const uint64_t innerBlocks = (((y >> 1u) & 7u) << 3u) | (x & 7u);
    const uint64_t outerInnerBytes = (outerBlocks | innerBlocks) << bytesPerPixelLog2;
    const uint32_t bank = (y >> 4u) & 1u;
    const uint32_t pipe = ((x >> 3u) & 3u) ^ (((y >> 3u) & 1u) << 1u);
    return ((y & 1u) << 4u) | (pipe << 6u) | (bank << 11u) |
           (outerInnerBytes & 0xFu) |
           (((outerInnerBytes >> 4u) & 1u) << 5u) |
           (((outerInnerBytes >> 5u) & 7u) << 8u) |
           (outerInnerBytes >> 8u << 12u);
}

static void swapXenosPixelEndian(uint8_t *pixel, uint32_t bytesPerPixel,
                                 uint32_t endian) {
    if (endian == 1u) {
        for (uint32_t i = 0; i + 1u < bytesPerPixel; i += 2u)
            std::swap(pixel[i], pixel[i + 1u]);
    } else if (endian == 2u) {
        for (uint32_t i = 0; i + 3u < bytesPerPixel; i += 4u) {
            std::swap(pixel[i], pixel[i + 3u]);
            std::swap(pixel[i + 1u], pixel[i + 2u]);
        }
    } else if (endian == 3u) {
        for (uint32_t i = 0; i + 3u < bytesPerPixel; i += 4u) {
            std::swap(pixel[i], pixel[i + 2u]);
            std::swap(pixel[i + 1u], pixel[i + 3u]);
        }
    }
}

static bool decodeXenosSwapTexture(uint8_t *base, const uint32_t fetchWords[6],
                                   uint32_t textureFormat,
                                   uint32_t width, uint32_t height,
                                   uint32_t &frontbufferAddress,
                                   std::vector<uint8_t> &rgba) {
    if (!base || width == 0u || height == 0u ||
        static_cast<uint64_t>(width) * height > 4u * 1024u * 1024u)
        return false;
    const uint32_t fetchFormat = fetchWords[1] & 0x3Fu;
    // Xenos format 54 is k_2_10_10_10_AS_16_16_16_16, an alias decoded as
    // R10G10B10A2_UNORM. It is still one 32-bit texel, not four 16-bit lanes.
    const uint32_t formatBytes =
        (fetchFormat==2u || fetchFormat==8u || fetchFormat==9u) ? 1u :
        (fetchFormat==10u) ? 2u :
        (fetchFormat==6u || fetchFormat==7u ||
         fetchFormat==25u || fetchFormat==54u) ? 4u :
        (fetchFormat==32u) ? 8u : 0u;
    if (formatBytes==0u || textureFormat!=fetchFormat) return false;

    const uint32_t fetchWidth = (fetchWords[2] & 0x1FFFu) + 1u;
    const uint32_t fetchHeight = ((fetchWords[2] >> 13u) & 0x1FFFu) + 1u;
    if (fetchWidth != width || fetchHeight != height)
        return false;

    const uint32_t fetchPage = (fetchWords[1] >> 12u) & 0xFFFFFu;
    frontbufferAddress = fetchPage << 12u;
    if (!validGuestRange(frontbufferAddress, 4u))
        return false;

    const bool tiled = (fetchWords[0] >> 31u) != 0u;
    uint32_t pitchPixels = ((fetchWords[0] >> 22u) & 0x1FFu) << 5u;
    if (pitchPixels < width) {
        if (tiled) pitchPixels = (width + 31u) & ~31u;
        else pitchPixels = (((width * formatBytes) + 255u) & ~255u) / formatBytes;
    }
    const uint32_t pitchAligned = (pitchPixels + 31u) & ~31u;
    const uint32_t endian = (fetchWords[1] >> 6u) & 3u;
    const uint32_t bytesPerPixelLog2 = std::countr_zero(formatBytes);
    const uint32_t guestSwizzle = (fetchWords[3] >> 1u) & 0xFFFu;
    const uint64_t pixelCount = static_cast<uint64_t>(width) * height;
    rgba.resize(static_cast<size_t>(pixelCount) * 4u);

    for (uint32_t y = 0; y < height; ++y) {
        for (uint32_t x = 0; x < width; ++x) {
            const uint64_t pixelOffset = tiled
                ? xenosTiledOffset2D(x, y, pitchAligned, bytesPerPixelLog2)
                : static_cast<uint64_t>(y) * pitchPixels * formatBytes +
                    static_cast<uint64_t>(x) * formatBytes;
            const uint64_t address = static_cast<uint64_t>(frontbufferAddress) + pixelOffset;
            if (address > std::numeric_limits<uint32_t>::max() ||
                !validGuestRange(static_cast<uint32_t>(address), formatBytes))
                return false;
            uint8_t pixel[8] = {};
            std::memcpy(pixel, base + address, formatBytes);
            swapXenosPixelEndian(pixel, formatBytes, endian);

            uint8_t sourceChannels[4]{};
            if (fetchFormat == 6u) {
                for (uint32_t c=0;c<4u;++c) sourceChannels[c]=pixel[c];
            } else if (formatBytes==1u) {
                sourceChannels[0]=sourceChannels[1]=sourceChannels[2]=pixel[0];
                sourceChannels[3]=255u;
            } else if (fetchFormat==10u) {
                sourceChannels[0]=pixel[0];sourceChannels[1]=pixel[1];
                sourceChannels[2]=0u;sourceChannels[3]=255u;
            } else if (fetchFormat==25u) {
                uint32_t a=uint32_t(pixel[0])|(uint32_t(pixel[1])<<8u);
                uint32_t b=uint32_t(pixel[2])|(uint32_t(pixel[3])<<8u);
                sourceChannels[0]=static_cast<uint8_t>((a*255u+32767u)/65535u);
                sourceChannels[1]=static_cast<uint8_t>((b*255u+32767u)/65535u);
                sourceChannels[2]=0u;sourceChannels[3]=255u;
            } else if (fetchFormat==32u) {
                for (uint32_t c=0;c<4u;++c) {
                    const uint16_t half=uint16_t(pixel[c*2u])|
                        (uint16_t(pixel[c*2u+1u])<<8u);
                    const uint32_t exp=(half>>10u)&31u;
                    uint32_t mantissa=half&1023u;
                    uint32_t bits=uint32_t(half&0x8000u)<<16u;
                    if(exp==31u)bits|=0x7F800000u|(mantissa<<13u);
                    else if(exp)bits|=((exp+112u)<<23u)|(mantissa<<13u);
                    else if(mantissa) {
                        int32_t power=-14;
                        while((mantissa&1024u)==0u){mantissa<<=1u;--power;}
                        bits|=(uint32_t(power+127)<<23u)|((mantissa&1023u)<<13u);
                    }
                    float f=std::bit_cast<float>(bits);
                    sourceChannels[c]=!(f>0.0f)?0u:f>=1.0f?255u:
                        static_cast<uint8_t>(f*255.0f+0.5f);
                }
            } else {
                uint32_t packed=uint32_t(pixel[0])|(uint32_t(pixel[1])<<8u)|
                    (uint32_t(pixel[2])<<16u)|(uint32_t(pixel[3])<<24u);
                for(uint32_t c=0;c<3u;++c)
                    sourceChannels[c]=static_cast<uint8_t>(((packed>>(10u*c))&1023u)*255u/1023u);
                sourceChannels[3]=static_cast<uint8_t>(((packed>>30u)&3u)*255u/3u);
            }
            const size_t destination = (static_cast<size_t>(y) * width + x) * 4u;
            for (uint32_t channel = 0; channel < 4u; ++channel) {
                uint32_t selector = (guestSwizzle >> (channel * 3u)) & 7u;
                if (selector >= 6u) selector &= 5u;
                rgba[destination + channel] = selector < 4u
                    ? sourceChannels[selector]
                    : static_cast<uint8_t>(selector == 5u ? 255u : 0u);
            }
        }
    }
    return true;
}


static bool decodeXenosBCTexture(uint8_t* base,const uint32_t fetchWords[6],
                                 uint32_t width,uint32_t height,
                                 std::vector<uint8_t>& rgba) {
    const uint32_t format=fetchWords[1]&63u;
    const bool bc1=(format==18u||format==51u);
    const bool bc2=(format==19u||format==52u);
    const bool bc3=(format==20u||format==53u);
    if(!base || (!bc1&&!bc2&&!bc3) || width==0u || height==0u ||
       width>2048u || height>2048u) return false;
    const uint32_t blockBytes=bc1?8u:16u;
    const uint32_t blocksX=(width+3u)/4u,blocksY=(height+3u)/4u;
    const uint32_t fetchPage=(fetchWords[1]>>12u)&0xFFFFFu;
    const uint64_t addressBase=uint64_t(fetchPage)<<12u;
    const bool tiled=(fetchWords[0]>>31u)!=0u;
    uint32_t pitchPixels=((fetchWords[0]>>22u)&0x1FFu)<<5u;
    if(pitchPixels<width)pitchPixels=(width+31u)&~31u;
    const uint32_t pitchBlocks=(pitchPixels+3u)/4u;
    const uint32_t alignedPitch=(pitchBlocks+31u)&~31u;
    const uint32_t endian=(fetchWords[1]>>6u)&3u;
    const uint32_t swizzle=(fetchWords[3]>>1u)&0xFFFu;
    rgba.assign(size_t(width)*height*4u,0u);
    for(uint32_t by=0;by<blocksY;++by)for(uint32_t bx=0;bx<blocksX;++bx) {
       const uint64_t offset=tiled?
         xenosTiledOffset2D(bx,by,alignedPitch,bc1?3u:4u):
         (uint64_t(by)*pitchBlocks+bx)*blockBytes;
       const uint64_t guest=addressBase+offset;
       if(guest>UINT32_MAX||!validGuestRange(uint32_t(guest),blockBytes))return false;
       uint8_t block[16]{};
       std::memcpy(block,base+guest,blockBytes);
       swapXenosPixelEndian(block,blockBytes,endian);
       uint8_t texels[64]{};
       if(!xowue::graphics::DecodeBCBlock(block,format,texels))return false;
       for(uint32_t iy=0;iy<4u;++iy)for(uint32_t ix=0;ix<4u;++ix){
          uint32_t x=bx*4u+ix,y=by*4u+iy;
          if(x>=width||y>=height)continue;
          const uint8_t* rgbaIn=texels+(iy*4u+ix)*4u;
          uint8_t* rgbaOut=rgba.data()+(size_t(y)*width+x)*4u;
          for(uint32_t c=0;c<4u;++c){
             uint32_t selector=(swizzle>>(c*3u))&7u;
             if(selector>=6u)selector&=5u;
             rgbaOut[c]=selector<4u?rgbaIn[selector]:
                        uint8_t(selector==5u?255u:0u);
          }
       }
    }
    return true;
}

extern "C" bool xowue_xenos_copy_guest_texture2d(
    const uint32_t fetch[6], void *rgba, size_t bytes) {
    if (!fetch || !rgba) return false;
    const uint32_t width = (fetch[2] & 0x1FFFu) + 1u;
    const uint32_t height = ((fetch[2] >> 13u) & 0x1FFFu) + 1u;
    if (width > 2048u || height > 2048u ||
        static_cast<uint64_t>(width) * height * 4u != bytes) return false;
    const auto memory = acquireGraphicsGuestMemory();
    if (!memory || !memory->base) return false;
    std::vector<uint8_t> decoded;
    uint32_t physical = 0;
    const uint32_t format = fetch[1] & 0x3Fu;
    const bool ok=(format==18u||format==19u||format==20u||
                   format==51u||format==52u||format==53u)
       ? decodeXenosBCTexture(memory->base,fetch,width,height,decoded)
       : decodeXenosSwapTexture(memory->base,fetch,format,
                               width,height,physical,decoded);
    if(!ok||decoded.size()!=bytes)return false;
    std::memcpy(rgba, decoded.data(), bytes);
    return true;
}

static uint32_t loadGuestBe32(const uint8_t *base, uint32_t address) {
    return (static_cast<uint32_t>(base[address]) << 24u) |
           (static_cast<uint32_t>(base[address + 1u]) << 16u) |
           (static_cast<uint32_t>(base[address + 2u]) << 8u) |
           static_cast<uint32_t>(base[address + 3u]);
}

static void storeGuestBe32(uint8_t *base, uint32_t address, uint32_t value) {
    base[address] = static_cast<uint8_t>(value >> 24u);
    base[address + 1u] = static_cast<uint8_t>(value >> 16u);
    base[address + 2u] = static_cast<uint8_t>(value >> 8u);
    base[address + 3u] = static_cast<uint8_t>(value);
}

static bool executeGuestPM4Words(uint8_t *base,
                                 const std::vector<uint32_t> &words,
                                 uint32_t depth,
                                 XenosFrontendState &frontend,
                                 PM4ParseSummary &summary) {
    if (!base || depth > 8u) {
        ++summary.malformed;
        return false;
    }
    size_t offset = 0u;
    while (offset < words.size()) {
        const uint32_t header = words[offset];
        const uint32_t type = header >> 30u;
        uint32_t payloadCount = 0u;
        if (type == 2u) {
            ++summary.packets;
            ++offset;
            continue;
        } else if (type == 0u || type == 3u) {
            payloadCount = ((header >> 16u) & 0x3FFFu) + 1u;
        } else if (type == 1u) {
            payloadCount = 2u;
        } else {
            ++summary.malformed;
            return false;
        }
        const size_t packetWords = static_cast<size_t>(payloadCount) + 1u;
        if (packetWords > words.size() - offset) {
            ++summary.malformed;
            return false;
        }

        ++summary.packets;
        if (type == 0u) {
            const uint32_t firstRegister = header & 0x7FFFu;
            const bool writeOneRegister = (header & 0x00008000u) != 0u;
            for (uint32_t i = 0; i < payloadCount; ++i) {
                const uint32_t reg = writeOneRegister ? firstRegister : firstRegister + i;
                xowue::xenos::WriteRegister(reg, words[offset + 1u + i]);
                if (reg >= kXenosShaderConstantFetchRegister &&
                    reg < kXenosShaderConstantFetchRegister + frontend.swapFetch.size()) {
                    frontend.swapFetch[reg - kXenosShaderConstantFetchRegister] =
                        words[offset + 1u + i];
                    frontend.swapFetchMask |= static_cast<uint8_t>(
                        1u << (reg - kXenosShaderConstantFetchRegister));
                    frontend.swapFetchValid = frontend.swapFetchMask == 0x3Fu;
                }
            }
        } else if (type == 1u) {
            xowue::xenos::WriteRegister(header & 0x7FFu, words[offset + 1u]);
            xowue::xenos::WriteRegister((header >> 11u) & 0x7FFu, words[offset + 2u]);
        } else if (type == 3u) {
            const uint32_t opcode = (header >> 8u) & 0x7Fu;
            auto writeConstantRange = [&](uint32_t first, size_t start, size_t count) {
                for (size_t n = 0; n < count; ++n)
                    xowue::xenos::WriteRegister(first + static_cast<uint32_t>(n),
                                                words[offset + start + n]);
            };
            auto loadShaderWords = [&](uint32_t stage, const std::vector<uint32_t>& code) {
                const auto result = xowue::xenos::LoadShader(stage, code.data(), code.size());
                if (!result.valid) {
                    char event[220];
                    std::snprintf(event, sizeof(event),
                       "Xenos shader translation rejected stage=%u dwords=%zu hash=%016llX reason=%s",
                       stage, code.size(), static_cast<unsigned long long>(result.hash),
                       result.error.c_str());
                    recordRuntimeTrace(event);
                }
            };
            if ((opcode == 0x2Du || opcode == 0x55u || opcode == 0x56u) && payloadCount >= 2u) {
                uint32_t first = words[offset + 1u] & (opcode == 0x2Du ? 0x7FFu : 0xFFFFu);
                if (opcode == 0x2Du) {
                    const uint32_t kind = (words[offset + 1u] >> 16u) & 0xFFu;
                    constexpr uint32_t bases[] = {0x4000u, 0x4800u, 0x4900u, 0x4908u, 0x2000u};
                    if (kind < 5u) writeConstantRange(first + bases[kind], 2u, payloadCount - 1u);
                } else {
                    writeConstantRange(first, 2u, payloadCount - 1u);
                }
            } else if (opcode == 0x27u && payloadCount >= 2u) {
                const uint32_t address = words[offset + 1u] & ~3u;
                const uint32_t stage = words[offset + 1u] & 3u;
                const uint32_t codeWords = words[offset + 2u] & 0xFFFFu;
                if (stage <= 1u && codeWords != 0u && codeWords <= 65536u &&
                    validGuestRange(address, static_cast<uint64_t>(codeWords) * 4u)) {
                    std::vector<uint32_t> code;
                    code.reserve(codeWords);
                    for (uint32_t n = 0; n < codeWords; ++n)
                        code.push_back(loadGuestBe32(base, address + n * 4u));
                    loadShaderWords(stage, code);
                } else {
                    ++summary.malformed;
                }
            } else if (opcode == 0x2Bu && payloadCount >= 2u) {
                const uint32_t stage = words[offset + 1u] & 3u;
                const uint32_t codeWords = words[offset + 2u] & 0xFFFFu;
                if (stage <= 1u && codeWords != 0u && codeWords <= payloadCount - 2u) {
                    std::vector<uint32_t> code(
                        words.begin() + static_cast<std::ptrdiff_t>(offset + 3u),
                        words.begin() + static_cast<std::ptrdiff_t>(offset + 3u + codeWords));
                    loadShaderWords(stage, code);
                } else {
                    ++summary.malformed;
                }
            } else if (opcode == 0x21u && payloadCount >= 3u) { // REG_RMW
                const uint32_t descriptor = words[offset + 1u];
                const uint32_t reg = descriptor & 0x1FFFu;
                const uint32_t source = xowue::xenos::ReadRegister(reg);
                const uint32_t andValue = (descriptor & (1u << 31u))
                    ? xowue::xenos::ReadRegister(words[offset + 2u] & 0x1FFFu)
                    : words[offset + 2u];
                const uint32_t orValue = (descriptor & (1u << 30u))
                    ? xowue::xenos::ReadRegister(words[offset + 3u] & 0x1FFFu)
                    : words[offset + 3u];
                xowue::xenos::WriteRegister(reg, (source & andValue) | orValue);
            } else if (opcode == 0x3Du && payloadCount >= 2u) { // MEM_WRITE
                const uint32_t address = words[offset + 1u] & ~3u;
                const uint64_t writeBytes = static_cast<uint64_t>(payloadCount - 1u) * 4u;
                if (validGuestRange(address, writeBytes)) {
                    for (uint32_t n = 0; n < payloadCount - 1u; ++n) {
                        storeGuestBe32(base, address + n * 4u, words[offset + 2u + n]);
                        ++summary.guestMemoryWrites;
                    }
                } else {
                    ++summary.malformed;
                }
            } else if (opcode == 0x3Eu && payloadCount >= 2u) { // REG_TO_MEM
                const uint32_t address = words[offset + 2u] & ~3u;
                if (validGuestRange(address, 4u)) {
                    const uint32_t value = xowue::xenos::ReadRegister(
                        words[offset + 1u] & 0x1FFFu);
                    storeGuestBe32(base, address, value);
                    ++summary.guestMemoryWrites;
                } else {
                    ++summary.malformed;
                }
            } else if (opcode == 0x58u && payloadCount >= 3u) { // EVENT_WRITE_SHD
                const uint32_t initiator = words[offset + 1u];
                const uint32_t address = words[offset + 2u] & ~3u;
                if ((initiator & 0x80000000u) == 0u && validGuestRange(address, 4u)) {
                    storeGuestBe32(base, address, words[offset + 3u]);
                    ++summary.guestMemoryWrites;
                } else {
                    // Counter-based events require the GPU timeline; do not
                    // fabricate the fence value for unsupported variants.
                    ++summary.malformed;
                }
            }
            if (opcode == kXenosPm4DrawIndexOpcode || opcode == kXenosPm4DrawIndex2Opcode ||
                opcode == kXenosPm4DrawIndexBinOpcode || opcode == kXenosPm4DrawIndex2BinOpcode) {
                ++summary.draws;
                const size_t initiatorWord = offset + (opcode == kXenosPm4DrawIndexOpcode ? 2u : 1u);
                if (initiatorWord < offset + 1u + payloadCount) {
                    const uint32_t initiator = words[initiatorWord];
                    const uint32_t indices = initiator >> 16u;
                    // SourceSelect bits 6:7; kAutoIndex=2, kDMA=0.
                    const uint32_t sourceSelect = (initiator >> 6u) & 3u;
                    // DMA data follows the index initiator in PM4_DRAW_INDX.
                    const uint32_t dmaAddress = opcode == kXenosPm4DrawIndexOpcode &&
                        payloadCount >= 4u ? words[offset + 3u] & 0x1FFFFFFFu : 0u;
                    const uint32_t dmaInfo = opcode == kXenosPm4DrawIndexOpcode &&
                        payloadCount >= 5u ? words[offset + 4u] : 0u;
                    xowue::xenos::QueueDraw(initiator, indices,
                        sourceSelect == 0u ? dmaAddress : 0u, dmaInfo, 0u);
                } else {
                    ++summary.malformed;
                }
            } else if (opcode == kXenosPm4IndirectBufferOpcode) {
                ++summary.indirectBuffers;
                if (payloadCount >= 2u && depth < 8u) {
                    const uint32_t address = words[offset + 1u];
                    const uint32_t count = words[offset + 2u] & 0x000FFFFFu;
                    if (count != 0u && count <= (1u << 20u) &&
                        validGuestRange(address, static_cast<uint64_t>(count) * 4u)) {
                        std::vector<uint32_t> indirectWords;
                        indirectWords.reserve(count);
                        for (uint32_t i = 0; i < count; ++i)
                            indirectWords.push_back(loadGuestBe32(base, address + i * 4u));
                        executeGuestPM4Words(base, indirectWords, depth + 1u,
                                             frontend, summary);
                    } else {
                        ++summary.malformed;
                    }
                }
            } else if (opcode == kXenosPm4SwapOpcode && payloadCount >= 4u &&
                       words[offset + 1u] == 0x53574150u) {
                ++summary.swaps;
                const uint32_t frontbuffer = words[offset + 2u];
                const uint32_t width = words[offset + 3u];
                const uint32_t height = words[offset + 4u];
                frontend.latestFrontbufferAddress = frontbuffer;
                frontend.latestWidth = width;
                frontend.latestHeight = height;
                frontend.lastSwapTimestampNs = static_cast<uint64_t>(
                    std::chrono::duration_cast<std::chrono::nanoseconds>(
                        std::chrono::steady_clock::now().time_since_epoch()).count());
                if (!frontend.swapFetchValid) {
                    ++summary.frameDecodeFailures;
                    offset += packetWords;
                    continue;
                }
                const uint32_t textureFormat = frontend.swapFetch[1] & 0x3Fu;
                std::vector<uint8_t> rgba;
                uint32_t decodedAddress = 0u;
                if (decodeXenosSwapTexture(base, frontend.swapFetch.data(),
                                           textureFormat, width, height,
                                           decodedAddress, rgba)) {
                    frontend.latestFrontbufferAddress = frontbuffer;
                    frontend.latestWidth = width;
                    frontend.latestHeight = height;
                    ++frontend.decodedFrames;
                    if (xowue_vulkan_backend_guest_swap)
                        xowue_vulkan_backend_guest_swap(frontbuffer, width, height);
                    if (xowue_vulkan_backend_guest_frame_rgba)
                        xowue_vulkan_backend_guest_frame_rgba(
                            decodedAddress, width, height, textureFormat,
                            rgba.data(), rgba.size());
                } else {
                    ++summary.frameDecodeFailures;
                }
            }
        }
        offset += packetWords;
    }
    return true;
}

void pumpGuestXenosRingBuffer() {
    std::lock_guard<std::mutex> pumpLock(g_xenosPumpMutex);
    const auto memory = g_activeGuestMemory.lock();
    if (!memory || !memory->base) return;

    XenosFrontendState frontend;
    {
        std::lock_guard<std::mutex> lock(g_xenosMutex);
        frontend = g_xenosFrontend;
    }
    const uint32_t ringWords = frontend.ringBufferSize / 4u;
    if (!frontend.enginesInitialized || frontend.ringBufferAddress == 0u ||
        ringWords < 2u || (ringWords & (ringWords - 1u)) != 0u ||
        !validGuestRange(frontend.ringBufferAddress, frontend.ringBufferSize))
        return;

    const uint32_t writeRegister = kXenosGpuRegisterBase +
                                   kXenosCommandProcessorWritePointerOffset;
    if (!validGuestRange(writeRegister, 4u)) return;
    const uint32_t writePointer = loadGuestBe32(memory->base, writeRegister) &
                                  (ringWords - 1u);
    uint32_t readPointer = frontend.ringReadPointer & (ringWords - 1u);
    uint32_t available = (writePointer - readPointer) & (ringWords - 1u);
    if (available == 0u) return;

    constexpr uint32_t kMaximumDwordsPerPump = 1u << 20u;
    available = std::min(available, kMaximumDwordsPerPump);
    std::vector<uint32_t> words;
    words.reserve(available);
    const uint32_t ringMask = ringWords - 1u;
    for (uint32_t i = 0; i < available; ++i) {
        const uint32_t index = (readPointer + i) & ringMask;
        words.push_back(loadGuestBe32(memory->base,
            frontend.ringBufferAddress + index * 4u));
    }

    PM4ParseSummary summary;
    const uint64_t decodedFramesBefore = frontend.decodedFrames;
    executeGuestPM4Words(memory->base, words, 0u, frontend, summary);
    // CP_RB_WPTR advances only after the title has written a complete kick.
    // Retire the captured span even if an unknown packet was found so one bad
    // command cannot hold the guest's entire ring forever.
    const uint32_t consumed = static_cast<uint32_t>(words.size());
    readPointer = (readPointer + consumed) & ringMask;
    frontend.ringReadPointer = readPointer;
    {
        std::lock_guard<std::mutex> lock(g_xenosMutex);
        g_xenosFrontend.ringReadPointer = readPointer;
        g_xenosFrontend.swapFetch = frontend.swapFetch;
        g_xenosFrontend.swapFetchMask = frontend.swapFetchMask;
        g_xenosFrontend.swapFetchValid = frontend.swapFetchValid;
        g_xenosFrontend.packets += summary.packets;
        g_xenosFrontend.draws += summary.draws;
        g_xenosFrontend.indirectBuffers += summary.indirectBuffers;
        g_xenosFrontend.swaps += summary.swaps;
        g_xenosFrontend.malformedPackets += summary.malformed;
        const uint64_t decodedFrameDelta = frontend.decodedFrames - decodedFramesBefore;
        g_xenosFrontend.decodedFrames += decodedFrameDelta;
        if (summary.swaps != 0u || decodedFrameDelta != 0u) {
            g_xenosFrontend.latestFrontbufferAddress = frontend.latestFrontbufferAddress;
            g_xenosFrontend.latestWidth = frontend.latestWidth;
            g_xenosFrontend.latestHeight = frontend.latestHeight;
            g_xenosFrontend.lastSwapTimestampNs = frontend.lastSwapTimestampNs;
        }
    }

    if (frontend.readPointerWritebackAddress != 0u &&
        validGuestRange(frontend.readPointerWritebackAddress, 4u)) {
        storeGuestBe32(memory->base, frontend.readPointerWritebackAddress, readPointer);
    }
    char event[192];
    std::snprintf(event, sizeof(event),
                  "Xenos ring kick rptr=%u wptr=%u words=%u packets=%llu draws=%llu swaps=%llu frames=%llu guest_sync_writes=%llu malformed=%llu decode_failures=%llu",
                  frontend.ringReadPointer, writePointer, consumed,
                  static_cast<unsigned long long>(summary.packets),
                  static_cast<unsigned long long>(summary.draws),
                  static_cast<unsigned long long>(summary.swaps),
                  static_cast<unsigned long long>(frontend.decodedFrames),
                  static_cast<unsigned long long>(summary.guestMemoryWrites),
                  static_cast<unsigned long long>(summary.malformed),
                  static_cast<unsigned long long>(summary.frameDecodeFailures));
    recordRuntimeTrace(event);
}

void xowue_VdSwap(PPCContext &context, uint8_t *base) {
    const uint32_t commandBuffer = context.r3.u32;
    const uint32_t fetch = context.r4.u32;
    const uint32_t frontbufferPointer = context.r8.u32;
    const uint32_t textureFormatPointer = context.r9.u32;
    const uint32_t colorSpacePointer = context.r10.u32;
    const uint32_t widthPointer = guestStackArgument(context, base, 9u);
    const uint32_t heightPointer = guestStackArgument(context, base, 10u);
    if (!base || !validGuestRange(commandBuffer, 64u * 4u) ||
        !validGuestRange(fetch, 6u * 4u) || !validGuestRange(frontbufferPointer, 4u) ||
        !validGuestRange(textureFormatPointer, 4u) || !validGuestRange(colorSpacePointer, 4u) ||
        !validGuestRange(widthPointer, 4u) || !validGuestRange(heightPointer, 4u)) {
        std::lock_guard<std::mutex> lock(g_xenosMutex);
        ++g_xenosFrontend.malformedPackets;
        recordRuntimeTrace("VdSwap rejected invalid guest pointer or stack argument");
        return;
    }
    const uint32_t frontbufferVirtualAddress = PPC_LOAD_U32(frontbufferPointer);
    const uint32_t textureFormat = PPC_LOAD_U32(textureFormatPointer);
    const uint32_t colorSpace = PPC_LOAD_U32(colorSpacePointer);
    const uint32_t width = PPC_LOAD_U32(widthPointer);
    const uint32_t height = PPC_LOAD_U32(heightPointer);
    uint32_t fetchWords[6]{};
    for (uint32_t i = 0; i < 6u; ++i)
        fetchWords[i] = PPC_LOAD_U32(fetch + i * 4u);
    const uint32_t frontbufferPhysicalAddress =
        ((fetchWords[1] >> 12u) & 0xFFFFFu) << 12u;
    if (frontbufferVirtualAddress != frontbufferPhysicalAddress) {
        recordRuntimeTrace("VdSwap frontbuffer pointer differs from Xenos fetch base; identity physical mapping retained");
    }
    for (uint32_t i = 0; i < 64u; ++i) PPC_STORE_U32(commandBuffer + i * 4u, 0x80000000u);
    PPC_STORE_U32(commandBuffer + 0u, (5u << 16u) | 0x4800u); // Type 0, six fetch dwords.
    for (uint32_t i = 0; i < 6u; ++i)
        PPC_STORE_U32(commandBuffer + (i + 1u) * 4u, fetchWords[i]);
    PPC_STORE_U32(commandBuffer + 7u * 4u,
                  (3u << 30u) | (3u << 16u) | (kXenosPm4SwapOpcode << 8u));
    PPC_STORE_U32(commandBuffer + 8u * 4u, 0x53574150u); // 'SWAP'.
    PPC_STORE_U32(commandBuffer + 9u * 4u, frontbufferPhysicalAddress);
    PPC_STORE_U32(commandBuffer + 10u * 4u, width);
    PPC_STORE_U32(commandBuffer + 11u * 4u, height);

    // VdSwap is the title's presentation boundary. The system command buffer
    // is not necessarily linked into the guest ring buffer on this runtime,
    // so decode and present the supplied Xenos fetch directly as well.
    std::vector<uint8_t> rgba;
    uint32_t decodedAddress = 0u;
    const bool decoded = decodeXenosSwapTexture(base, fetchWords, textureFormat,
                                                 width, height, decodedAddress,
                                                 rgba);
    {
        std::lock_guard<std::mutex> lock(g_xenosMutex);
        ++g_xenosFrontend.swaps;
        g_xenosFrontend.latestFrontbufferAddress = frontbufferPhysicalAddress;
        g_xenosFrontend.latestWidth = width;
        g_xenosFrontend.latestHeight = height;
        g_xenosFrontend.lastSwapTimestampNs = static_cast<uint64_t>(
            std::chrono::duration_cast<std::chrono::nanoseconds>(
                std::chrono::steady_clock::now().time_since_epoch()).count());
        if (decoded) ++g_xenosFrontend.decodedFrames;
        else ++g_xenosFrontend.malformedPackets;
    }
    if (decoded) {
        if (xowue_vulkan_backend_guest_swap)
            xowue_vulkan_backend_guest_swap(frontbufferPhysicalAddress, width, height);
        if (xowue_vulkan_backend_guest_frame_rgba)
            xowue_vulkan_backend_guest_frame_rgba(decodedAddress, width, height,
                                                  textureFormat, rgba.data(), rgba.size());
    }

    char event[256];
    std::snprintf(event, sizeof(event),
                  "VdSwap %s width=%u height=%u frontbuffer=0x%08X format=0x%08X colorspace=%u",
                  decoded ? "decoded and presented guest framebuffer" : "framebuffer decode rejected",
                  width, height, frontbufferPhysicalAddress, textureFormat, colorSpace);
    recordRuntimeTrace(event);
}

void xowue_VdInitializeScalerCommandBuffer(PPCContext &context, uint8_t *base) {
    const uint32_t destination = guestStackArgument(context, base, 11u);
    const uint32_t wordCount = guestStackArgument(context, base, 12u);
    if (!base || wordCount > 0x100000u ||
        (wordCount != 0u && !validGuestRange(destination, static_cast<uint64_t>(wordCount) * 4u))) {
        context.r3.u32 = 0u;
        recordRuntimeTrace("VdInitializeScalerCommandBuffer rejected destination/size");
        return;
    }
    for (uint32_t i = 0; i < wordCount; ++i) PPC_STORE_U32(destination + i * 4u, 0x80000000u);
    context.r3.u32 = wordCount;
    recordRuntimeTrace("VdInitializeScalerCommandBuffer filled " + std::to_string(wordCount) + " NOP dwords");
}

bool writeGuestVideoMode(uint8_t *base, uint32_t address) {
    if (!base || address == 0u || !validGuestRange(address, 48u)) return false;
    std::memset(base + address, 0, 48u);
    PPC_STORE_U32(address + 0x00u, 1280u);
    PPC_STORE_U32(address + 0x04u, 720u);
    PPC_STORE_U32(address + 0x08u, 0u);
    PPC_STORE_U32(address + 0x0Cu, 1u);
    PPC_STORE_U32(address + 0x10u, 1u);
    storeGuestFloat(base, address + 0x14u, 60.0f);
    PPC_STORE_U32(address + 0x18u, 1u);
    PPC_STORE_U32(address + 0x1Cu, 0x4Au);
    PPC_STORE_U32(address + 0x20u, 1u);
    return true;
}

void xowue_VdQueryVideoMode(PPCContext &context, uint8_t *base) {
    const uint32_t address = context.r3.u32;
    if (!writeGuestVideoMode(base, address)) {
        context.r3.u32 = kNtStatusInvalidParameter;
        recordRuntimeTrace("VdQueryVideoMode rejected output pointer");
        return;
    }
    context.r3.u32 = kNtStatusSuccess;
    recordRuntimeTrace("VdQueryVideoMode -> 1280x720 progressive widescreen 60Hz");
}

void xowue_XGetVideoMode(PPCContext &context, uint8_t *base) {
    const uint32_t address = context.r3.u32;
    if (!writeGuestVideoMode(base, address)) {
        recordRuntimeTrace("XGetVideoMode rejected output pointer");
        return;
    }
    // XGetVideoMode is a void XAM wrapper; preserve the output pointer in r3.
    context.r3.u32 = address;
    recordRuntimeTrace("XGetVideoMode -> 1280x720 progressive widescreen 60Hz");
}

void xowue_ExGetXConfigSetting(PPCContext &context, uint8_t *base) {
    const uint32_t category = context.r3.u32;
    const uint32_t setting = context.r4.u32;
    const uint32_t bufferAddress = context.r5.u32;
    const uint16_t bufferSize = static_cast<uint16_t>(context.r6.u32);
    const uint32_t requiredSizeAddress = context.r7.u32;
    uint16_t settingSize = 0;
    uint32_t value = 0;
    uint8_t byteValue = 0;
    bool byteSetting = false;
    uint32_t status = kNtStatusSuccess;

    if (category == 0x0002u && setting == 0x0002u) {
        settingSize = 4u;
        value = 0x00001000u; // Xenia's retail-safe NTSC AV region default.
    } else if (category == 0x0003u) {
        switch (setting) {
        case 0x0001u: case 0x0002u: case 0x0003u: case 0x0004u:
        case 0x0005u: case 0x0006u: case 0x0007u:
            settingSize = 4u;
            value = 0u;
            break;
        case 0x0009u: // Portuguese, matching the supplied PT-BR title build.
            settingSize = 4u;
            value = 9u;
            break;
        case 0x000Au: // XCONFIG_USER_VIDEO_FLAGS: widescreen/HD capable.
            settingSize = 4u;
            value = 0x00040000u;
            break;
        case 0x000Cu:
            settingSize = 4u;
            value = 0u;
            break;
        case 0x000Eu: // Brazil.
            settingSize = 1u;
            byteValue = 13u;
            byteSetting = true;
            break;
        default:
            status = kNtStatusInvalidParameter2;
            break;
        }
    } else if (category != 0x0002u) {
        status = kNtStatusInvalidParameter1;
    } else {
        status = kNtStatusInvalidParameter2;
    }

    if (status == kNtStatusSuccess && !base) {
        status = kNtStatusInvalidParameter3;
    }
    if (status == kNtStatusSuccess) {
        if (bufferAddress == 0u) {
            if (bufferSize != 0u) status = kNtStatusInvalidParameter3;
        } else if (!validGuestRange(bufferAddress, settingSize)) {
            status = kNtStatusInvalidParameter3;
        } else if (bufferSize < settingSize) {
            status = kNtStatusBufferTooSmall;
        } else if (byteSetting) {
            base[bufferAddress] = byteValue;
        } else {
            PPC_STORE_U32(bufferAddress, value);
        }
    }

    if (base && requiredSizeAddress != 0u && validGuestRange(requiredSizeAddress, 2u)) {
        // Xenia reports the recognized setting's size even when the caller's
        // destination is too small; callers use this to retry with a buffer.
        PPC_STORE_U16(requiredSizeAddress,
                      status == kNtStatusInvalidParameter1 ||
                              status == kNtStatusInvalidParameter2
                          ? 0u
                          : settingSize);
    }
    context.r3.u32 = status;
    char event[160];
    std::snprintf(event, sizeof(event),
                  "ExGetXConfigSetting category=0x%04X setting=0x%04X size=%u value=0x%08X status=0x%08X",
                  category, setting, settingSize, value, status);
    recordRuntimeTrace(event);
}

static uint32_t writeTouchGamepadState(uint8_t *base, uint32_t userIndex,
                                       uint32_t address) {
    if (userIndex > 3u) {
        return kXInputErrorDeviceNotConnected;
    }
    if (address == 0u) return kNtStatusSuccess;
    if (!base || !validGuestRange(address, 16u)) {
        return kXInputErrorBadArguments;
    }
    TouchControllerState state;
    {
        std::lock_guard<std::mutex> lock(g_touchControllerMutex);
        state = g_touchController;
    }
    // Confirm *consumption* of touch input by the guest, not merely that
    // Swift emitted a button press. Log each changed packet only once.
    static std::atomic<uint32_t> lastObservedPacket{0u};
    const uint32_t previouslyObserved = lastObservedPacket.exchange(
        state.packetNumber, std::memory_order_relaxed);
    if (state.packetNumber && state.packetNumber != previouslyObserved) {
        char inputEvent[160];
        std::snprintf(inputEvent, sizeof(inputEvent),
                      "XOWUE_INPUT_POLLED packet=%u buttons=0x%04X triggers=%u,%u",
                      state.packetNumber, state.buttons & 0xFFFFu,
                      state.leftTrigger, state.rightTrigger);
        recordRuntimeTrace(inputEvent);
    }
    PPC_STORE_U32(address, state.packetNumber);
    PPC_STORE_U16(address + 4u, static_cast<uint16_t>(state.buttons));
    base[address + 6u] = state.leftTrigger;
    base[address + 7u] = state.rightTrigger;
    PPC_STORE_U16(address + 8u, static_cast<uint16_t>(state.leftX));
    PPC_STORE_U16(address + 10u, static_cast<uint16_t>(state.leftY));
    PPC_STORE_U16(address + 12u, static_cast<uint16_t>(state.rightX));
    PPC_STORE_U16(address + 14u, static_cast<uint16_t>(state.rightY));
    return kNtStatusSuccess;
}

static uint32_t writeTouchGamepadCapabilities(uint8_t *base, uint32_t userIndex,
                                              uint32_t address) {
    if (userIndex != 0u) {
        return kXInputErrorDeviceNotConnected;
    }
    if (address == 0u || !base || !validGuestRange(address, 20u))
        return kXInputErrorBadArguments;
    std::memset(base + address, 0, 20u);
    base[address] = 1u;     // XINPUT_DEVTYPE_GAMEPAD
    base[address + 1u] = 1u; // XINPUT_DEVSUBTYPE_GAMEPAD
    PPC_STORE_U16(address + 4u, 0xFFFFu);
    base[address + 6u] = 0xFFu;
    base[address + 7u] = 0xFFu;
    for (uint32_t offset = 8u; offset <= 14u; offset += 2u)
        PPC_STORE_U16(address + offset, 0xFFFFu);
    return kNtStatusSuccess;
}

void xowue_XInputGetState(PPCContext &context, uint8_t *base) {
    context.r3.u32 = writeTouchGamepadState(base, context.r3.u32, context.r4.u32);
}

void xowue_XamInputGetState(PPCContext &context, uint8_t *base) {
    context.r3.u32 = writeTouchGamepadState(base, context.r3.u32, context.r5.u32);
}

void xowue_XInputGetCapabilities(PPCContext &context, uint8_t *base) {
    context.r3.u32 = writeTouchGamepadCapabilities(base, context.r3.u32, context.r5.u32);
}

void xowue_XamInputGetCapabilities(PPCContext &context, uint8_t *base) {
    xowue_XInputGetCapabilities(context, base);
}

void xowue_XamInputGetCapabilitiesEx(PPCContext &context, uint8_t *base) {
    context.r3.u32 = writeTouchGamepadCapabilities(base, context.r4.u32, context.r6.u32);
}

void xowue_XInputSetState(PPCContext &context, uint8_t *base) {
    const uint32_t userIndex = context.r3.u32;
    const uint32_t vibration = context.r4.u32;
    context.r3.u32 = vibration == 0u || !validGuestRange(vibration, 4u)
        ? kXInputErrorBadArguments
        : (userIndex == 0u ? kNtStatusSuccess : kXInputErrorDeviceNotConnected);
    (void)base;
}

void xowue_XamInputSetState(PPCContext &context, uint8_t *base) {
    const uint32_t userIndex = context.r3.u32;
    const uint32_t vibration = context.r5.u32;
    context.r3.u32 = vibration == 0u || !base || !validGuestRange(vibration, 4u)
        ? kXInputErrorBadArguments
        : (userIndex == 0u ? kNtStatusSuccess : kXInputErrorDeviceNotConnected);
}

void xowue_VdQueryVideoFlags(PPCContext &context) { context.r3.u32 = 3u; }

void xowue_VdGetCurrentDisplayGamma(PPCContext &context, uint8_t *base) {
    if (!base || context.r3.u32 == 0u || context.r4.u32 == 0u ||
        !validGuestRange(context.r3.u32, 4u) || !validGuestRange(context.r4.u32, 4u)) {
        context.r3.u32 = kNtStatusInvalidParameter;
        return;
    }
    PPC_STORE_U32(context.r3.u32, 2u);
    storeGuestFloat(base, context.r4.u32, 2.2222223f);
    context.r3.u32 = kNtStatusSuccess;
}

void xowue_VdGetCurrentDisplayInformation(PPCContext &context, uint8_t *base) {
    const uint32_t address = context.r3.u32;
    if (!base || address == 0u || !validGuestRange(address, 0x58u)) {
        context.r3.u32 = kNtStatusInvalidParameter;
        return;
    }
    std::memset(base + address, 0, 0x58u);
    PPC_STORE_U16(address + 0x00u, 1280u);
    PPC_STORE_U16(address + 0x02u, 720u);
    PPC_STORE_U32(address + 0x10u, 1280u);
    PPC_STORE_U32(address + 0x14u, 720u);
    PPC_STORE_U32(address + 0x18u, 1280u);
    PPC_STORE_U32(address + 0x1Cu, 720u);
    PPC_STORE_U32(address + 0x20u, 1u);
    PPC_STORE_U32(address + 0x30u, 1u);
    PPC_STORE_U16(address + 0x40u, 320u);
    PPC_STORE_U16(address + 0x42u, 180u);
    PPC_STORE_U16(address + 0x44u, 320u);
    PPC_STORE_U16(address + 0x46u, 180u);
    PPC_STORE_U16(address + 0x48u, 1280u);
    PPC_STORE_U16(address + 0x4Au, 720u);
    storeGuestFloat(base, address + 0x4Cu, 60.0f);
    PPC_STORE_U32(address + 0x50u, 0u);
    PPC_STORE_U16(address + 0x56u, 1280u);
    context.r3.u32 = kNtStatusSuccess;
}

void xowue_VdSetDisplayMode(PPCContext &context) {
    recordRuntimeTrace("VdSetDisplayMode flags=0x" + [&] {
        char value[16];
        std::snprintf(value, sizeof(value), "%08X", context.r3.u32);
        return std::string(value);
    }());
    context.r3.u32 = 0u;
}

void xowue_VdSetDisplayModeOverride(PPCContext &context) { context.r3.u32 = 0u; }
void xowue_VdIsHSIOTrainingSucceeded(PPCContext &context) { context.r3.u32 = 1u; }
void xowue_VdEnableDisableClockGating(PPCContext &context) { context.r3.u32 = 0u; }
void xowue_VdPersistDisplay(PPCContext &context) { context.r3.u32 = 1u; }
void xowue_VdRetrainEDRAM(PPCContext &context) { context.r3.u32 = 0u; }
void xowue_VdRetrainEDRAMWorker(PPCContext &context) { context.r3.u32 = 0u; }
void xowue_VdCallGraphicsNotificationRoutines(PPCContext &context) { context.r3.u32 = 0u; }

void xowue_ExTerminateThread(PPCContext &context) {
    if (!g_currentGuestThread) {
        throw std::runtime_error("ExTerminateThread foi chamado fora de uma thread PPC criada pelo guest");
    }
    throw GuestThreadExit(context.r3.u32);
}

void xowue_NtClose(PPCContext &context) {
    const uint32_t handle = context.r3.u32;
    {
        std::lock_guard<std::mutex> lock(g_guestFileMutex);
        const auto file = g_guestFiles.find(handle);
        if (file != g_guestFiles.end()) {
            const auto completion = file->second->completion;
            g_guestFiles.erase(file);
            std::lock_guard<std::mutex> objectLock(g_guestObjectMutex);
            g_guestWaitables.erase(handle);
            if (completion) {
                const bool aliased = std::any_of(g_guestFiles.begin(), g_guestFiles.end(),
                    [&completion](const auto &entry) { return entry.second->completion == completion; });
                if (!aliased) g_guestWaitables.erase(completion->objectAddress);
            }
            context.r3.u32 = kNtStatusSuccess;
            recordRuntimeTrace("NtClose file handle closed");
            return;
        }
    }
    std::shared_ptr<GuestThread> thread = lookupGuestThread(handle);
    std::shared_ptr<GuestWaitable> waitable = lookupGuestWaitable(handle);
    {
        std::lock_guard<std::mutex> lock(g_guestObjectMutex);
        if (g_guestWaitables.erase(handle) == 0u) {
            context.r3.u32 = kNtStatusInvalidHandle;
            recordRuntimeTrace("NtClose invalid handle=0x" + std::to_string(handle));
            return;
        }
        if (waitable && waitable->objectAddress != 0u) {
            g_guestWaitables.erase(waitable->objectAddress);
        } else if (thread) {
            g_guestWaitables.erase(thread->objectAddress);
        }
    }
    if (thread) {
        std::lock_guard<std::mutex> lock(g_guestThreadMutex);
        g_guestThreadsByHandle.erase(handle);
        g_guestThreadsByObject.erase(thread->objectAddress);
    }
    context.r3.u32 = kNtStatusSuccess;
    recordRuntimeTrace("NtClose handle closed");
}

static bool getGuestObjectPath(uint8_t *base, uint32_t attributes,
                               std::string &path) {
    if (!base || !validGuestRange(attributes, 12u)) return false;
    // Xbox 360 X_OBJECT_ATTRIBUTES (12 bytes) is NOT Win32 OBJECT_ATTRIBUTES:
    // 0x00 root_directory, 0x04 name_ptr (X_ANSI_STRING*), 0x08 attributes.
    // In Wolverine: root=FFFFFFFD (ObDosDevices), name=guest stack,
    // flags=0x40. The old code read flags as name -> NtCreateFile always failed.
    const uint32_t rootHandle = PPC_LOAD_U32(attributes);
    const uint32_t nameDescriptor = PPC_LOAD_U32(attributes + 4u);
    const uint32_t objectFlags = PPC_LOAD_U32(attributes + 8u);
    // Preserve all attribute flag bits; Xbox object manager defines the
    // contract. Do not reject future flags merely for being unfamiliar.
    (void)objectFlags;
    // Xbox X_OBJECT_ATTRIBUTES permits a null ObjectName when reopening the
    // object designated by an existing root directory handle.
    // A root handle names an Xbox device object, while GuestFile::path
    // stores its resolved iOS path. Do not prepend that absolute iOS path
    // to another Xbox guest string and feed it to the Xbox path resolver.
    auto translateRoot=[&](const std::shared_ptr<GuestFile>& root,
                           std::string& translated)->bool {
        if(!root)return false;
        const auto absolute=root->path.lexically_normal();
        auto convert=[&](const std::filesystem::path& deviceRoot,
                         const char* devicePrefix)->bool{
            if(deviceRoot.empty())return false;
            const auto relative=absolute.lexically_relative(deviceRoot.lexically_normal());
            if(relative.empty())return false;
            for(const auto& part:relative)if(part=="..")return false;
            translated=std::string(devicePrefix);
            if(relative!=".") {
                translated+=relative.generic_string();
                if(translated.back()!='/') translated+='/';
            }
            return true;
        };
        return convert(g_guestGameRoot,"game:/") ||
               convert(g_guestSaveRoot,"t:/");
    };
    if(nameDescriptor==0u && rootHandle!=0u && rootHandle!=0xFFFFFFFDu) {
        return translateRoot(lookupGuestFile(rootHandle),path);
    }
    if (!readGuestAnsiString(base,nameDescriptor,path)) return false;
    if (rootHandle!=0u && rootHandle!=0xFFFFFFFDu) {
        const auto root=lookupGuestFile(rootHandle);
        if (!root || !root->directory)return false;
        std::string prefix;
        if(!translateRoot(root,prefix))return false;
        if(!path.empty() && path[0]=='/')path.erase(0u,1u);
        path=prefix+path;
    }
    return true;
}

void xowue_NtCreateFile(PPCContext &context, uint8_t *base) {
    const uint32_t handleOutAddress = context.r3.u32;
    const uint32_t desiredAccess = context.r4.u32;
    const uint32_t objectAttributes = context.r5.u32;
    const uint32_t ioStatusAddress = context.r6.u32;
    const uint32_t disposition = context.r10.u32;
    const uint32_t createOptions = guestStackArgument(context, base, 9u);
    std::string guestPath;
    if (!base || !validGuestRange(handleOutAddress, 4u) ||
        !getGuestObjectPath(base, objectAttributes, guestPath)) {
        context.r3.u32 = kNtStatusInvalidParameter;
        writeGuestIoStatus(base, ioStatusAddress, context.r3.u32, 0u);
        const bool attrsValid=base&&validGuestRange(objectAttributes,12u);
        const uint32_t root=attrsValid?PPC_LOAD_U32(objectAttributes):0u;
        const uint32_t name=attrsValid?PPC_LOAD_U32(objectAttributes+4u):0u;
        const uint32_t flags=attrsValid?PPC_LOAD_U32(objectAttributes+8u):0u;
        const bool nameValid=attrsValid && name && validGuestRange(name,8u);
        const uint16_t len=nameValid?loadGuestBe16(base,name):0u;
        const uint32_t buf=nameValid?PPC_LOAD_U32(name+4u):0u;
        char details[350];
        std::snprintf(details,sizeof(details),
           "NtCreateFile rejected Xbox X_OBJECT_ATTRIBUTES out=%08X attrs=%08X root=%08X name=%08X flags=%08X name_len=%u name_buf=%08X io=%08X access=%08X disposition=%08X",
           handleOutAddress,objectAttributes,root,name,flags,len,buf,
           ioStatusAddress,desiredAccess,disposition);
        recordRuntimeTrace(details);
        return;
    }
    uint32_t handle = 0u, action = 0u;
    const uint32_t status = createGuestFile(base, guestPath, desiredAccess,
                                            disposition, createOptions, handle, action);
    if (status == kNtStatusSuccess) PPC_STORE_U32(handleOutAddress, handle);
    else PPC_STORE_U32(handleOutAddress, 0u);
    writeGuestIoStatus(base, ioStatusAddress, status, action);
    context.r3.u32 = status;
    recordRuntimeTrace("NtCreateFile path=" + guestPath + " status=0x" + [&] {
        char value[16]; std::snprintf(value, sizeof(value), "%08X", status);
        return std::string(value);
    }() + (status == kNtStatusSuccess ? " opened under game/save root" : " open failed"));
}

void xowue_NtOpenFile(PPCContext &context, uint8_t *base) {
    const uint32_t handleOutAddress = context.r3.u32;
    const uint32_t ioStatusAddress = context.r6.u32;
    std::string guestPath;
    if (!base || !validGuestRange(handleOutAddress, 4u) ||
        !getGuestObjectPath(base, context.r5.u32, guestPath)) {
        context.r3.u32 = kNtStatusInvalidParameter;
        writeGuestIoStatus(base, ioStatusAddress, context.r3.u32, 0u);
        return;
    }
    uint32_t handle = 0u, action = 0u;
    const uint32_t status = createGuestFile(base, guestPath, context.r4.u32,
                                            1u, context.r7.u32, handle, action);
    PPC_STORE_U32(handleOutAddress, status == kNtStatusSuccess ? handle : 0u);
    writeGuestIoStatus(base, ioStatusAddress, status, action);
    context.r3.u32 = status;
}

static uint64_t guestFileOffset(uint8_t *base, uint32_t address,
                                const std::shared_ptr<GuestFile> &file,
                                bool output) {
    if (address != 0u && validGuestRange(address, 8u)) {
        const uint64_t requested = PPC_LOAD_U64(address);
        if (requested != std::numeric_limits<uint64_t>::max()) return requested;
    }
    (void)base;
    const auto position = output ? file->stream.tellp() : file->stream.tellg();
    return position < 0 ? 0u : static_cast<uint64_t>(position);
}

void xowue_NtReadFile(PPCContext &context, uint8_t *base) {
    GuestEventSignalOnReturn signal(context.r4.u32);
    const uint32_t handle = context.r3.u32;
    const uint32_t ioStatus = context.r7.u32;
    const uint32_t buffer = context.r8.u32;
    const uint32_t length = context.r9.u32;
    const uint32_t offsetPointer = context.r10.u32;
    const auto file = lookupGuestFile(handle);
    if (!base || !file || file->directory || !file->readable || length > 64u * 1024u * 1024u ||
        (length != 0u && !validGuestRange(buffer, length))) {
        context.r3.u32 = file ? kNtStatusInvalidParameter : kNtStatusInvalidHandle;
        writeGuestIoStatus(base, ioStatus, context.r3.u32, 0u);
        return;
    }
    std::lock_guard<std::mutex> lock(file->mutex);
    const uint64_t offset = guestFileOffset(base, offsetPointer, file, false);
    file->stream.clear();
    file->stream.seekg(static_cast<std::streamoff>(offset), std::ios::beg);
    if (!file->stream) {
        context.r3.u32 = kNtStatusUnsuccessful;
        writeGuestIoStatus(base, ioStatus, context.r3.u32, 0u);
        return;
    }
    file->stream.read(reinterpret_cast<char *>(base + buffer), length);
    const uint32_t bytesRead = static_cast<uint32_t>(file->stream.gcount());
    file->stream.clear();
    if (offsetPointer == 0u) file->stream.seekg(static_cast<std::streamoff>(offset + bytesRead));
    queueGuestApc(g_currentGuestThread, context.r5.u32, context.r6.u32, ioStatus, 0u);
    context.r3.u32 = kNtStatusSuccess;
    writeGuestIoStatus(base, ioStatus, kNtStatusSuccess, bytesRead);
}

void xowue_NtWriteFile(PPCContext &context, uint8_t *base) {
    GuestEventSignalOnReturn signal(context.r4.u32);
    const uint32_t handle = context.r3.u32;
    const uint32_t ioStatus = context.r7.u32;
    const uint32_t buffer = context.r8.u32;
    const uint32_t length = context.r9.u32;
    const uint32_t offsetPointer = context.r10.u32;
    const auto file = lookupGuestFile(handle);
    if (!base || !file || file->directory || !file->writable || length > 64u * 1024u * 1024u ||
        (length != 0u && !validGuestRange(buffer, length))) {
        context.r3.u32 = file ? kNtStatusInvalidParameter : kNtStatusInvalidHandle;
        writeGuestIoStatus(base, ioStatus, context.r3.u32, 0u);
        return;
    }
    std::lock_guard<std::mutex> lock(file->mutex);
    const uint64_t offset = guestFileOffset(base, offsetPointer, file, true);
    file->stream.clear();
    file->stream.seekp(static_cast<std::streamoff>(offset), std::ios::beg);
    file->stream.write(reinterpret_cast<const char *>(base + buffer), length);
    if (!file->stream) {
        context.r3.u32 = kNtStatusUnsuccessful;
        writeGuestIoStatus(base, ioStatus, context.r3.u32, 0u);
        return;
    }
    if (offsetPointer == 0u) file->stream.seekp(static_cast<std::streamoff>(offset + length));
    queueGuestApc(g_currentGuestThread, context.r5.u32, context.r6.u32, ioStatus, 0u);
    context.r3.u32 = kNtStatusSuccess;
    writeGuestIoStatus(base, ioStatus, kNtStatusSuccess, length);
}

void xowue_NtFlushBuffersFile(PPCContext &context, uint8_t *base) {
    const auto file = lookupGuestFile(context.r3.u32);
    const uint32_t status = file ? kNtStatusSuccess : kNtStatusInvalidHandle;
    if (file) { std::lock_guard<std::mutex> lock(file->mutex); file->stream.flush(); }
    writeGuestIoStatus(base, context.r4.u32, status, 0u);
    context.r3.u32 = status;
}

void xowue_NtQueryInformationFile(PPCContext &context, uint8_t *base) {
    const auto file = lookupGuestFile(context.r3.u32);
    const uint32_t ioStatus = context.r4.u32;
    const uint32_t output = context.r5.u32;
    const uint32_t length = context.r6.u32;
    const uint32_t infoClass = context.r7.u32;
    if (!base || !file || length > 0x10000u || !validGuestRange(output, length)) {
        context.r3.u32 = file ? kNtStatusInvalidParameter : kNtStatusInvalidHandle;
        writeGuestIoStatus(base, ioStatus, context.r3.u32, 0u);
        return;
    }
    std::error_code ec;
    const bool directory = file->directory;
    const uint64_t size = directory ? 0u : std::filesystem::file_size(file->path, ec);
    const uint64_t allocation = (size + 0xFFFu) & ~uint64_t{0xFFFu};
    uint32_t required = 0u;
    std::memset(base + output, 0, length);
    if (infoClass == 4u) { // FILE_BASIC_INFORMATION
        required = 40u;
        if (length >= required) PPC_STORE_U32(output + 32u, directory ? 0x10u : 0x20u);
    } else if (infoClass == 5u) { // FILE_STANDARD_INFORMATION
        required = 24u;
        if (length >= required) {
            PPC_STORE_U64(output, allocation); PPC_STORE_U64(output + 8u, size);
            PPC_STORE_U32(output + 16u, 1u); base[output + 21u] = directory ? 1u : 0u;
        }
    } else if (infoClass == 14u) { // FILE_POSITION_INFORMATION
        required = 8u;
        if (length >= required) {
            std::lock_guard<std::mutex> lock(file->mutex);
            const auto position = file->stream.tellg();
            PPC_STORE_U64(output, position < 0 ? 0u : static_cast<uint64_t>(position));
        }
    } else if (infoClass == 34u) { // FILE_NETWORK_OPEN_INFORMATION
        required = 56u;
        if (length >= required) {
            PPC_STORE_U64(output + 32u, allocation); PPC_STORE_U64(output + 40u, size);
            PPC_STORE_U32(output + 48u, directory ? 0x10u : 0x20u);
        }
    } else {
        context.r3.u32 = kNtStatusInvalidParameter;
        writeGuestIoStatus(base, ioStatus, context.r3.u32, 0u);
        return;
    }
    const uint32_t status = length < required ? kNtStatusBufferTooSmall : kNtStatusSuccess;
    context.r3.u32 = status;
    writeGuestIoStatus(base, ioStatus, status, status == kNtStatusSuccess ? required : 0u);
}

void xowue_NtQueryFullAttributesFile(PPCContext &context, uint8_t *base) {
    std::string name;
    std::filesystem::path path;
    const uint32_t output = context.r4.u32;
    if (!base || !validGuestRange(output, 56u) ||
        !getGuestObjectPath(base, context.r3.u32, name) ||
        !translateGuestFilePath(name, false, path)) {
        context.r3.u32 = kNtStatusInvalidParameter;
        return;
    }
    std::error_code ec;
    if (!std::filesystem::exists(path, ec) || ec) {
        context.r3.u32 = 0xC000000Fu; // STATUS_NO_SUCH_FILE
        return;
    }
    const bool directory = std::filesystem::is_directory(path, ec);
    const uint64_t size = directory ? 0u : std::filesystem::file_size(path, ec);
    std::memset(base + output, 0, 56u);
    PPC_STORE_U64(output + 32u, (size + 0xFFFu) & ~uint64_t{0xFFFu});
    PPC_STORE_U64(output + 40u, size);
    PPC_STORE_U32(output + 48u, directory ? 0x10u : 0x20u);
    context.r3.u32 = kNtStatusSuccess;
}

void xowue_NtDuplicateObject(PPCContext &context, uint8_t *base) {
    const uint32_t sourceHandle = context.r3.u32;
    const uint32_t outputAddress = context.r4.u32;
    const uint32_t options = context.r5.u32;
    if (!base || (outputAddress != 0u && !validGuestRange(outputAddress, 4u))) {
        context.r3.u32 = kNtStatusInvalidParameter; return;
    }
    if (outputAddress == 0u) {
        PPCContext closeContext{}; closeContext.r3.u32 = sourceHandle;
        xowue_NtClose(closeContext); context.r3.u32 = closeContext.r3.u32; return;
    }
    const auto file = lookupGuestFile(sourceHandle);
    if (file) {
        const uint32_t duplicate = allocateGuestHandle();
        if (!duplicate) { context.r3.u32 = kNtStatusNoMemory; return; }
        { std::lock_guard<std::mutex> lock(g_guestFileMutex); g_guestFiles[duplicate] = file; }
        { std::lock_guard<std::mutex> lock(g_guestObjectMutex); g_guestWaitables[duplicate] = file->completion; }
        PPC_STORE_U32(outputAddress, duplicate);
        context.r3.u32 = kNtStatusSuccess;
    } else {
        const auto thread = lookupGuestThread(sourceHandle);
        const auto waitable = thread ? thread->completion : lookupGuestWaitable(sourceHandle);
        if (!waitable) { context.r3.u32 = kNtStatusInvalidHandle; return; }
        const uint32_t duplicate = allocateGuestHandle();
        if (!duplicate) { context.r3.u32 = kNtStatusNoMemory; return; }
        {
            std::lock_guard<std::mutex> lock(g_guestObjectMutex);
            g_guestWaitables[duplicate] = waitable;
        }
        PPC_STORE_U32(outputAddress, duplicate);
        context.r3.u32 = kNtStatusSuccess;
    }
    if (context.r3.u32 == kNtStatusSuccess && (options & 1u) != 0u) {
        PPCContext closeContext{}; closeContext.r3.u32 = sourceHandle;
        xowue_NtClose(closeContext);
    }
}

static bool guestWildcardMatch(const std::string &patternValue,
                               const std::string &nameValue) {
    const std::string pattern = lowerGuestPath(patternValue.empty() ? "*" : patternValue);
    const std::string name = lowerGuestPath(nameValue);
    size_t p = 0u, n = 0u, star = std::string::npos, retry = 0u;
    while (n < name.size()) {
        if (p < pattern.size() && (pattern[p] == '?' || pattern[p] == name[n])) {
            ++p; ++n;
        } else if (p < pattern.size() && pattern[p] == '*') {
            star = p++; retry = n;
        } else if (star != std::string::npos) {
            p = star + 1u; n = ++retry;
        } else return false;
    }
    while (p < pattern.size() && pattern[p] == '*') ++p;
    return p == pattern.size();
}

static uint32_t guestFileAttribute(const std::filesystem::path &path) {
    std::error_code ec;
    return std::filesystem::is_directory(path, ec) ? 0x10u : 0x20u;
}

void xowue_NtQueryDirectoryFile(PPCContext &context, uint8_t *base) {
    GuestEventSignalOnReturn signal(context.r4.u32);
    const auto file = lookupGuestFile(context.r3.u32);
    const uint32_t ioStatus = context.r7.u32;
    const uint32_t output = context.r8.u32;
    const uint32_t length = context.r9.u32;
    const uint32_t namePointer = guestStackArgument(context, base, 9u);
    const uint32_t restart = guestStackArgument(context, base, 10u);
    std::string pattern = "*";
    if (namePointer != 0u && !readGuestAnsiString(base, namePointer, pattern)) {
        context.r3.u32 = kNtStatusInvalidParameter;
        writeGuestIoStatus(base, ioStatus, context.r3.u32, 0u);
        return;
    }
    if (!base || !file || !file->directory || length < 72u || length > 1u * 1024u * 1024u ||
        !validGuestRange(output, length)) {
        context.r3.u32 = file ? kNtStatusInvalidParameter : kNtStatusInvalidHandle;
        writeGuestIoStatus(base, ioStatus, context.r3.u32, 0u);
        return;
    }
    std::lock_guard<std::mutex> lock(file->mutex);
    if (restart != 0u) {
        file->entries.clear();
        file->directoryCursor = 0u;
        std::error_code ec;
        for (std::filesystem::directory_iterator it(file->path, ec), end;
             !ec && it != end; it.increment(ec)) file->entries.push_back(it->path());
        std::sort(file->entries.begin(), file->entries.end(), [](const auto &a, const auto &b) {
            return lowerGuestPath(a.filename().string()) < lowerGuestPath(b.filename().string());
        });
    }
    while (file->directoryCursor < file->entries.size() &&
           !guestWildcardMatch(pattern, file->entries[file->directoryCursor].filename().string()))
        ++file->directoryCursor;
    if (file->directoryCursor >= file->entries.size()) {
        context.r3.u32 = 0x80000006u; // STATUS_NO_MORE_FILES
        writeGuestIoStatus(base, ioStatus, context.r3.u32, 0u);
        return;
    }
    const auto entry = file->entries[file->directoryCursor++];
    const std::string leaf = entry.filename().string();
    const uint32_t utf16Bytes = static_cast<uint32_t>(leaf.size() * 2u);
    if (64u + utf16Bytes > length) {
        context.r3.u32 = kNtStatusBufferTooSmall;
        writeGuestIoStatus(base, ioStatus, context.r3.u32, 0u);
        return;
    }
    std::memset(base + output, 0, length);
    std::error_code ec;
    const bool isDirectory = std::filesystem::is_directory(entry, ec);
    const uint64_t size = isDirectory ? 0u : std::filesystem::file_size(entry, ec);
    PPC_STORE_U64(output + 40u, size);
    PPC_STORE_U64(output + 48u, (size + 0xFFFu) & ~uint64_t{0xFFFu});
    PPC_STORE_U32(output + 56u, isDirectory ? 0x10u : 0x20u);
    PPC_STORE_U32(output + 60u, utf16Bytes);
    for (size_t index = 0; index < leaf.size(); ++index)
        storeGuestBe16(base, output + 64u + static_cast<uint32_t>(index * 2u),
                       static_cast<uint8_t>(leaf[index]));
    context.r3.u32 = kNtStatusSuccess;
    writeGuestIoStatus(base, ioStatus, kNtStatusSuccess, 64u + utf16Bytes);
}

void xowue_NtQueryVolumeInformationFile(PPCContext &context, uint8_t *base) {
    const auto file = lookupGuestFile(context.r3.u32);
    const uint32_t ioStatus = context.r4.u32, output = context.r5.u32;
    const uint32_t length = context.r6.u32, infoClass = context.r7.u32;
    if (!base || !file || length > 0x10000u || !validGuestRange(output, length)) {
        context.r3.u32 = file ? kNtStatusInvalidParameter : kNtStatusInvalidHandle;
        writeGuestIoStatus(base, ioStatus, context.r3.u32, 0u);
        return;
    }
    uint32_t required = 0u;
    if (infoClass == 1u) required = 24u; // FILE_FS_VOLUME_INFORMATION
    else if (infoClass == 3u) required = 24u; // FILE_FS_SIZE_INFORMATION
    else if (infoClass == 4u) required = 32u; // FILE_FS_DEVICE_INFORMATION
    else {
        context.r3.u32 = kNtStatusInvalidParameter;
        writeGuestIoStatus(base, ioStatus, context.r3.u32, 0u);
        return;
    }
    if (length >= required) {
        std::memset(base + output, 0, length);
        if (infoClass == 1u) PPC_STORE_U32(output + 16u, 0u);
        if (infoClass == 3u) {
            PPC_STORE_U64(output, 0x100000u); PPC_STORE_U64(output + 8u, 0x100000u);
            PPC_STORE_U32(output + 16u, 512u);
        }
        if (infoClass == 4u) PPC_STORE_U32(output + 4u, 7u);
    }
    const uint32_t status = length < required ? kNtStatusBufferTooSmall : kNtStatusSuccess;
    context.r3.u32 = status;
    writeGuestIoStatus(base, ioStatus, status, status == kNtStatusSuccess ? required : 0u);
}

void xowue_NtFlushBuffersFile(PPCContext &context, uint8_t *base);

void xowue_NtSetInformationFile(PPCContext &context, uint8_t *base) {
    const auto file = lookupGuestFile(context.r3.u32);
    const uint32_t ioStatus = context.r4.u32, info = context.r5.u32;
    const uint32_t length = context.r6.u32, infoClass = context.r7.u32;
    if (!base || !file || length == 0u || !validGuestRange(info, length)) {
        context.r3.u32 = file ? kNtStatusInvalidParameter : kNtStatusInvalidHandle;
        writeGuestIoStatus(base, ioStatus, context.r3.u32, 0u);
        return;
    }
    if (infoClass == 14u && length >= 8u) {
        const uint64_t offset = PPC_LOAD_U64(info);
        std::lock_guard<std::mutex> lock(file->mutex);
        file->stream.clear(); file->stream.seekg(static_cast<std::streamoff>(offset));
        file->stream.seekp(static_cast<std::streamoff>(offset));
        context.r3.u32 = kNtStatusSuccess;
        writeGuestIoStatus(base, ioStatus, context.r3.u32, 0u);
        return;
    }
    if (infoClass == 13u && length >= 1u) {
        if (base[info] != 0u) {
            const auto root = std::filesystem::weakly_canonical(g_guestSaveRoot);
            const auto parent = std::filesystem::weakly_canonical(file->path.parent_path());
            auto a = root.begin(), b = parent.begin();
            for (; a != root.end() && b != parent.end() && *a == *b; ++a, ++b) {}
            if (a == root.end()) {
                std::error_code ec; std::filesystem::remove(file->path, ec);
                context.r3.u32 = ec ? kNtStatusUnsuccessful : kNtStatusSuccess;
            } else context.r3.u32 = 0xC0000022u;
        } else context.r3.u32 = kNtStatusSuccess;
        writeGuestIoStatus(base, ioStatus, context.r3.u32, 0u);
        return;
    }
    context.r3.u32 = kNtStatusInvalidParameter;
    writeGuestIoStatus(base, ioStatus, context.r3.u32, 0u);
}

void xowue_NtReadFileScatter(PPCContext &context, uint8_t *base) {
    GuestEventSignalOnReturn signal(context.r4.u32);
    const auto file = lookupGuestFile(context.r3.u32);
    const uint32_t ioStatus = context.r7.u32, segments = context.r8.u32;
    const uint32_t length = context.r9.u32, offsetPointer = context.r10.u32;
    if (!base || !file || file->directory || !file->readable || length > 64u * 1024u * 1024u ||
        (length && !validGuestRange(segments, static_cast<uint64_t>((length + 4095u) / 4096u) * 8u))) {
        context.r3.u32 = file ? kNtStatusInvalidParameter : kNtStatusInvalidHandle;
        writeGuestIoStatus(base, ioStatus, context.r3.u32, 0u);
        return;
    }
    std::lock_guard<std::mutex> lock(file->mutex);
    const uint64_t offset = guestFileOffset(base, offsetPointer, file, false);
    file->stream.clear(); file->stream.seekg(static_cast<std::streamoff>(offset));
    uint32_t total = 0u;
    while (total < length) {
        const uint32_t segment = PPC_LOAD_U32(segments + (total / 4096u) * 8u);
        const uint32_t chunk = std::min<uint32_t>(4096u, length - total);
        if (!validGuestRange(segment, chunk)) break;
        file->stream.read(reinterpret_cast<char *>(base + segment), chunk);
        const uint32_t read = static_cast<uint32_t>(file->stream.gcount());
        total += read;
        if (read != chunk) break;
    }
    file->stream.clear();
    queueGuestApc(g_currentGuestThread, context.r5.u32, context.r6.u32, ioStatus, 0u);
    context.r3.u32 = kNtStatusSuccess;
    writeGuestIoStatus(base, ioStatus, kNtStatusSuccess, total);
}

void xowue_NtDeviceIoControlFile(PPCContext &context, uint8_t *base) {
    GuestEventSignalOnReturn signal(context.r4.u32);
    const uint32_t ioStatus = context.r7.u32, code = context.r8.u32;
    const uint32_t output = guestStackArgument(context, base, 9u);
    const uint32_t outputLength = guestStackArgument(context, base, 10u);
    uint32_t status = kNtStatusSuccess, information = 0u;
    if (code == 0x00070000u) { // DISK_GET_DRIVE_GEOMETRY
        if (!validGuestRange(output, 8u) || outputLength < 8u) status = kNtStatusBufferTooSmall;
        else { PPC_STORE_U32(output, 0x7F8u); PPC_STORE_U32(output + 4u, 512u); information = 8u; }
    } else if (code == 0x00074004u) { // DISK_GET_PARTITION_INFO
        if (!validGuestRange(output, 16u) || outputLength < 16u) status = kNtStatusBufferTooSmall;
        else { PPC_STORE_U64(output, 0u); PPC_STORE_U64(output + 8u, 0xFF000u); information = 16u; }
    } else status = kNtStatusInvalidParameter;
    writeGuestIoStatus(base, ioStatus, status, information);
    context.r3.u32 = status;
}

void xowue_NtSetEvent(PPCContext &context, uint8_t *base) {
    const uint32_t handle = context.r3.u32;
    const uint32_t previousStatePointer = context.r4.u32;
    auto waitable = lookupGuestWaitable(handle);
    if (!waitable || waitable->kind != GuestWaitable::Kind::Event) {
        context.r3.u32 = kNtStatusInvalidHandle;
        return;
    }
    if (previousStatePointer != 0u &&
        (!base || !validGuestRange(previousStatePointer, 4u))) {
        context.r3.u32 = kNtStatusInvalidParameter;
        return;
    }
    bool previous = false;
    {
        std::lock_guard<std::mutex> lock(waitable->mutex);
        previous = waitable->signaled;
        waitable->signaled = true;
        syncGuestDispatcherSignalState(waitable);
    }
    if (previousStatePointer != 0u) {
        PPC_STORE_U32(previousStatePointer, previous ? 1u : 0u);
    }
    waitable->changed.notify_all();
    g_waitSetChanged.notify_all();
    context.r3.u32 = kNtStatusSuccess;
}

void xowue_NtClearEvent(PPCContext &context) {
    auto waitable = lookupGuestWaitable(context.r3.u32);
    if (!waitable || waitable->kind != GuestWaitable::Kind::Event) {
        context.r3.u32 = kNtStatusInvalidHandle;
        return;
    }
    std::lock_guard<std::mutex> lock(waitable->mutex);
    waitable->signaled = false;
    syncGuestDispatcherSignalState(waitable);
    context.r3.u32 = kNtStatusSuccess;
}

void xowue_NtPulseEvent(PPCContext &context, uint8_t *base) {
    const uint32_t handle = context.r3.u32;
    const uint32_t previousStatePointer = context.r4.u32;
    auto waitable = lookupGuestWaitable(handle);
    if (!waitable || waitable->kind != GuestWaitable::Kind::Event) {
        context.r3.u32 = kNtStatusInvalidHandle;
        return;
    }
    if (previousStatePointer != 0u &&
        (!base || !validGuestRange(previousStatePointer, 4u))) {
        context.r3.u32 = kNtStatusInvalidParameter;
        return;
    }
    bool previous = false;
    {
        std::lock_guard<std::mutex> lock(waitable->mutex);
        previous = waitable->signaled;
        ++waitable->pulseGeneration;
        waitable->signaled = previous;
        syncGuestDispatcherSignalState(waitable);
    }
    if (previousStatePointer != 0u) {
        PPC_STORE_U32(previousStatePointer, previous ? 1u : 0u);
    }
    waitable->changed.notify_all();
    g_waitSetChanged.notify_all();
    recordRuntimeTrace("NtPulseEvent delivered as a one-shot pulse to waiters already blocked on the event");
    context.r3.u32 = kNtStatusSuccess;
}

void xowue_KeSetEvent(PPCContext &context, uint8_t *base) {
    auto waitable = ensurePointerWaitable(context.r3.u32, base);
    if (!waitable) {
        context.r3.u32 = kNtStatusInvalidParameter;
        return;
    }
    bool previous = false;
    {
        std::lock_guard<std::mutex> lock(waitable->mutex);
        previous = waitable->signaled;
        waitable->signaled = true;
        syncGuestDispatcherSignalState(waitable);
    }
    waitable->changed.notify_all();
    g_waitSetChanged.notify_all();
    context.r3.u32 = previous ? 1u : 0u;
}

void xowue_KeResetEvent(PPCContext &context, uint8_t *base) {
    auto waitable = ensurePointerWaitable(context.r3.u32, base);
    if (!waitable) {
        context.r3.u32 = 0u;
        return;
    }
    std::lock_guard<std::mutex> lock(waitable->mutex);
    context.r3.u32 = waitable->signaled ? 1u : 0u;
    waitable->signaled = false;
    syncGuestDispatcherSignalState(waitable);
}

void xowue_NtWaitForSingleObjectEx(PPCContext &context, uint8_t *base) {
    GuestTimeout timeout;
    if (!readGuestTimeout(base, context.r6.u32, timeout)) {
        context.r3.u32 = kNtStatusInvalidParameter;
        return;
    }
    context.r3.u32 = waitGuestObject(lookupGuestWaitable(context.r3.u32), timeout,
                                     context.r5.u32 != 0u);
}

void xowue_KeWaitForSingleObject(PPCContext &context, uint8_t *base) {
    GuestTimeout timeout;
    if (!readGuestTimeout(base, context.r7.u32, timeout)) {
        context.r3.u32 = kNtStatusInvalidParameter;
        return;
    }
    context.r3.u32 = waitGuestObject(ensurePointerWaitable(context.r3.u32, base), timeout,
                                     context.r6.u32 != 0u);
}

void xowue_NtWaitForMultipleObjectsEx(PPCContext &context, uint8_t *base) {
    const uint32_t count = context.r3.u32;
    const uint32_t handlesPointer = context.r4.u32;
    const uint32_t waitType = context.r5.u32;
    GuestTimeout timeout;
    if (!base || count == 0u || count > 64u ||
        static_cast<uint64_t>(handlesPointer) + static_cast<uint64_t>(count) * 4u > kGuestAddressSpaceSize ||
        !readGuestTimeout(base, context.r8.u32, timeout)) {
        context.r3.u32 = kNtStatusInvalidParameter;
        return;
    }
    std::vector<std::shared_ptr<GuestWaitable>> waitables;
    waitables.reserve(count);
    for (uint32_t index = 0; index < count; ++index) {
        waitables.push_back(lookupGuestWaitable(PPC_LOAD_U32(handlesPointer + index * 4u)));
    }
    context.r3.u32 = waitGuestObjects(waitables, waitType, timeout,
                                      context.r7.u32 != 0u);
}

void xowue_KeWaitForMultipleObjects(PPCContext &context, uint8_t *base) {
    const uint32_t count = context.r3.u32;
    const uint32_t objectsPointer = context.r4.u32;
    const uint32_t waitType = context.r5.u32;
    GuestTimeout timeout;
    if (!base || count == 0u || count > 64u ||
        static_cast<uint64_t>(objectsPointer) + static_cast<uint64_t>(count) * 4u > kGuestAddressSpaceSize ||
        !readGuestTimeout(base, context.r9.u32, timeout)) {
        context.r3.u32 = kNtStatusInvalidParameter;
        return;
    }
    std::vector<std::shared_ptr<GuestWaitable>> waitables;
    waitables.reserve(count);
    for (uint32_t index = 0; index < count; ++index) {
        waitables.push_back(ensurePointerWaitable(PPC_LOAD_U32(objectsPointer + index * 4u), base));
    }
    context.r3.u32 = waitGuestObjects(waitables, waitType, timeout,
                                      context.r8.u32 != 0u);
}

void xowue_NtResumeThread(PPCContext &context, uint8_t *base) {
    auto thread = lookupGuestThread(context.r3.u32);
    if (!thread) {
        context.r3.u32 = kNtStatusInvalidHandle;
        return;
    }
    uint32_t previous = thread->suspendCount.load();
    while (previous != 0u && !thread->suspendCount.compare_exchange_weak(previous, previous - 1u)) {}
    if (context.r4.u32 != 0u) {
        if (!base || context.r4.u32 > kGuestAddressSpaceSize - 4u) {
            context.r3.u32 = kNtStatusInvalidParameter;
            return;
        }
        PPC_STORE_U32(context.r4.u32, previous);
    }
    thread->stateChanged.notify_all();
    context.r3.u32 = kNtStatusSuccess;
}

void xowue_NtSuspendThread(PPCContext &context, uint8_t *base) {
    auto thread = lookupGuestThread(context.r3.u32);
    if (!thread) {
        context.r3.u32 = kNtStatusInvalidHandle;
        return;
    }
    const uint32_t previous = thread->suspendCount.fetch_add(1u);
    if (context.r4.u32 != 0u) {
        if (!base || context.r4.u32 > kGuestAddressSpaceSize - 4u) {
            context.r3.u32 = kNtStatusInvalidParameter;
            return;
        }
        PPC_STORE_U32(context.r4.u32, previous);
    }
    context.r3.u32 = kNtStatusSuccess;
}

void xowue_KeResumeThread(PPCContext &context) {
    auto thread = lookupGuestThread(context.r3.u32);
    if (!thread) {
        context.r3.u32 = kNtStatusInvalidHandle;
        return;
    }
    uint32_t previous = thread->suspendCount.load();
    while (previous != 0u && !thread->suspendCount.compare_exchange_weak(previous, previous - 1u)) {}
    thread->stateChanged.notify_all();
    context.r3.u32 = kNtStatusSuccess;
}

void xowue_KeSetAffinityThread(PPCContext &context, uint8_t *base) {
    const uint32_t affinity = context.r4.u32;
    const uint32_t previousPointer = context.r5.u32;
    if (affinity == 0u || (previousPointer != 0u &&
        (!base || previousPointer > kGuestAddressSpaceSize - 4u))) {
        context.r3.u32 = kNtStatusInvalidParameter;
        return;
    }
    if (previousPointer != 0u) PPC_STORE_U32(previousPointer, 1u);
    context.r3.u32 = kNtStatusSuccess;
    recordRuntimeTrace("KeSetAffinityThread accepted; single-host-CPU affinity policy applied");
}

void xowue_KeSetBasePriorityThread(PPCContext &context) {
    context.r3.u32 = 0u;
    recordRuntimeTrace("KeSetBasePriorityThread accepted; guest priority is advisory on this host");
}

void xowue_KeDelayExecutionThread(PPCContext &context, uint8_t *base) {
    const uint32_t intervalPointer = context.r5.u32;
    if (!base || intervalPointer > kGuestAddressSpaceSize - sizeof(uint64_t)) {
        context.r3.u32 = kNtStatusInvalidParameter;
        return;
    }
    const int64_t interval = static_cast<int64_t>(PPC_LOAD_U64(intervalPointer));
    if (interval < 0) {
        const int64_t ticks = interval == std::numeric_limits<int64_t>::min()
            ? 864000000000LL : std::min<int64_t>(-interval, 864000000000LL);
        std::unique_lock<std::mutex> lock(g_waitSetMutex);
        g_waitSetChanged.wait_for(lock, std::chrono::nanoseconds(ticks * 100), [] {
            return g_schedulerStopRequested.load();
        });
    }
    if (g_schedulerStopRequested.load() && g_currentGuestThreadId != 1u) {
        throw GuestThreadStopRequested{};
    }
    context.r3.u32 = kNtStatusSuccess;
}

void xowue_ExRegisterTitleTerminateNotification(PPCContext &context) {
    context.r3.u32 = kNtStatusSuccess;
    recordRuntimeTrace("ExRegisterTitleTerminateNotification accepted; host app lifecycle owns shutdown");
}

void xowue_XamLoaderTerminateTitle(PPCContext &context) {
    context.r3.u32 = kNtStatusSuccess;
    recordRuntimeTrace("XamLoaderTerminateTitle requested guest title shutdown");
}

void xowue_KeGetCurrentProcessType(PPCContext &context) {
    // The game entry point runs as an Xbox user process (X_PROCTYPE_USER = 1).
    context.r3.u32 = 1;
    recordRuntimeTrace("KeGetCurrentProcessType -> X_PROCTYPE_USER (1)");
}

void xowue_KiApcNormalRoutineNop(PPCContext &context) {
    // Xenia exports this kernel routine as a stub returning zero.
    context.r3.u32 = 0;
    recordRuntimeTrace("KiApcNormalRoutineNop -> 0 (Xenia-compatible stub)");
}

void xowue_RtlInitializeCriticalSection(PPCContext &context, uint8_t *base) {
    const uint32_t address = context.r3.u32;
    constexpr uint32_t kXboxCriticalSectionSize = 28;
    if (!base || address > kGuestAddressSpaceSize - kXboxCriticalSectionSize) {
        throw std::runtime_error("RtlInitializeCriticalSection recebeu endereço fora da memória convidada");
    }
    auto sectionLock = criticalSectionLock(address);
    std::lock_guard<std::recursive_mutex> held(*sectionLock);
    std::memset(base + address, 0, kXboxCriticalSectionSize);
    base[address] = 1; // X_DISPATCH_HEADER.type = EventSynchronizationObject.
    PPC_STORE_U32(address + 0x10, 0xFFFFFFFFu); // lock_count = -1.
    PPC_STORE_U32(address + 0x14, 0);            // recursion_count = 0.
    PPC_STORE_U32(address + 0x18, 0);            // owning_thread = nullptr.
    char event[100];
    std::snprintf(event, sizeof(event), "RtlInitializeCriticalSection guest=0x%08X size=28", address);
    recordRuntimeTrace(event);
}

void xowue_RtlInitializeCriticalSectionAndSpinCount(PPCContext &context, uint8_t *base) {
    const uint32_t address = context.r3.u32;
    const uint32_t spinCount = context.r4.u32;
    constexpr uint32_t kXboxCriticalSectionSize = 28;
    if (!base || address > kGuestAddressSpaceSize - kXboxCriticalSectionSize) {
        throw std::runtime_error("RtlInitializeCriticalSectionAndSpinCount recebeu endereço inválido");
    }
    const uint32_t packedSpinCount = std::min<uint32_t>((spinCount + 255u) >> 8, 255u);
    auto sectionLock = criticalSectionLock(address);
    std::lock_guard<std::recursive_mutex> held(*sectionLock);
    std::memset(base + address, 0, kXboxCriticalSectionSize);
    base[address] = 1;
    base[address + 1] = static_cast<uint8_t>(packedSpinCount);
    PPC_STORE_U32(address + 0x10, 0xFFFFFFFFu);
    PPC_STORE_U32(address + 0x14, 0);
    PPC_STORE_U32(address + 0x18, 0);
    context.r3.u32 = kNtStatusSuccess;
    const size_t initialized = g_criticalSectionInitCount.fetch_add(1u) + 1u;
    if (initialized <= 2u) {
        recordRuntimeTrace("RtlInitializeCriticalSectionAndSpinCount inicializada");
    }
}

void xowue_RtlEnterCriticalSection(PPCContext &context, uint8_t *base) {
    const uint32_t address = context.r3.u32;
    constexpr uint32_t kXboxCriticalSectionSize = 28;
    if (!base || address > kGuestAddressSpaceSize - kXboxCriticalSectionSize) {
        throw std::runtime_error("RtlEnterCriticalSection recebeu endereço inválido");
    }
    auto sectionLock = criticalSectionLock(address);
    sectionLock->lock();
    const uint32_t owner = PPC_LOAD_U32(address + 0x18);
    int32_t lockCount = static_cast<int32_t>(PPC_LOAD_U32(address + 0x10));
    uint32_t recursion = PPC_LOAD_U32(address + 0x14);
    if (owner == g_currentGuestThreadId) {
        ++lockCount;
        ++recursion;
    } else {
        if (lockCount < -1) {
            sectionLock->unlock();
            throw std::runtime_error("critical section lock_count inválido");
        }
        ++lockCount;
        recursion = 1;
        PPC_STORE_U32(address + 0x18, g_currentGuestThreadId);
    }
    PPC_STORE_U32(address + 0x10, static_cast<uint32_t>(lockCount));
    PPC_STORE_U32(address + 0x14, recursion);
    char event[128];
    std::snprintf(event, sizeof(event), "RtlEnterCriticalSection guest=0x%08X recursion=%u", address, recursion);
    recordRuntimeTrace(event);
}

void xowue_RtlTryEnterCriticalSection(PPCContext &context, uint8_t *base) {
    const uint32_t address = context.r3.u32;
    constexpr uint32_t kXboxCriticalSectionSize = 28;
    if (!base || address > kGuestAddressSpaceSize - kXboxCriticalSectionSize) {
        throw std::runtime_error("RtlTryEnterCriticalSection recebeu endereço inválido");
    }
    auto sectionLock = criticalSectionLock(address);
    if (!sectionLock->try_lock()) {
        context.r3.u32 = 0u;
        recordRuntimeTrace("RtlTryEnterCriticalSection -> busy");
        return;
    }
    const uint32_t owner = PPC_LOAD_U32(address + 0x18);
    int32_t lockCount = static_cast<int32_t>(PPC_LOAD_U32(address + 0x10));
    uint32_t recursion = PPC_LOAD_U32(address + 0x14);
    (void)owner;
    ++lockCount;
    ++recursion;
    PPC_STORE_U32(address + 0x10, static_cast<uint32_t>(lockCount));
    PPC_STORE_U32(address + 0x14, recursion);
    PPC_STORE_U32(address + 0x18, g_currentGuestThreadId);
    context.r3.u32 = 1;
    recordRuntimeTrace("RtlTryEnterCriticalSection -> acquired");
}

void xowue_RtlLeaveCriticalSection(PPCContext &context, uint8_t *base) {
    const uint32_t address = context.r3.u32;
    constexpr uint32_t kXboxCriticalSectionSize = 28;
    if (!base || address > kGuestAddressSpaceSize - kXboxCriticalSectionSize) {
        throw std::runtime_error("RtlLeaveCriticalSection recebeu endereço inválido");
    }
    auto sectionLock = criticalSectionLock(address);
    const uint32_t owner = PPC_LOAD_U32(address + 0x18);
    int32_t lockCount = static_cast<int32_t>(PPC_LOAD_U32(address + 0x10));
    uint32_t recursion = PPC_LOAD_U32(address + 0x14);
    if (owner != g_currentGuestThreadId || recursion == 0) {
        throw std::runtime_error("RtlLeaveCriticalSection sem proprietário na thread PPC ativa");
    }
    --recursion;
    --lockCount;
    PPC_STORE_U32(address + 0x10, static_cast<uint32_t>(lockCount));
    PPC_STORE_U32(address + 0x14, recursion);
    if (recursion == 0) PPC_STORE_U32(address + 0x18, 0);
    sectionLock->unlock();
    char event[128];
    std::snprintf(event, sizeof(event), "RtlLeaveCriticalSection guest=0x%08X recursion=%u", address, recursion);
    recordRuntimeTrace(event);
}

void xowue_KeQueryPerformanceFrequency(PPCContext &context) {
    context.r3.u32 = kXbox360PerformanceFrequency;
    recordRuntimeTrace("KeQueryPerformanceFrequency -> 50000000 Hz");
}

void xowue_KeEnterCriticalRegion(PPCContext &, uint8_t *base) {
    if (!base || !g_currentGuestThread ||
        !validGuestRange(g_currentGuestThread->objectAddress + kGuestKThreadApcDisableOffset, 4u))
        throw std::runtime_error("KeEnterCriticalRegion has no current guest KTHREAD");
    const uint32_t address = g_currentGuestThread->objectAddress + kGuestKThreadApcDisableOffset;
    const int32_t count = static_cast<int32_t>(PPC_LOAD_U32(address));
    if (count == std::numeric_limits<int32_t>::min())
        throw std::runtime_error("KeEnterCriticalRegion APC disable count underflow");
    PPC_STORE_U32(address, static_cast<uint32_t>(count - 1));
}

void xowue_KeLeaveCriticalRegion(PPCContext &, uint8_t *base) {
    if (!base || !g_currentGuestThread ||
        !validGuestRange(g_currentGuestThread->objectAddress + kGuestKThreadApcDisableOffset, 4u))
        throw std::runtime_error("KeLeaveCriticalRegion has no current guest KTHREAD");
    const uint32_t address = g_currentGuestThread->objectAddress + kGuestKThreadApcDisableOffset;
    const int32_t count = static_cast<int32_t>(PPC_LOAD_U32(address));
    if (count == std::numeric_limits<int32_t>::max())
        throw std::runtime_error("KeLeaveCriticalRegion APC disable count overflow");
    const int32_t next = count + 1;
    PPC_STORE_U32(address, static_cast<uint32_t>(next));
    if (next == 0) {
        const bool delivered = deliverPendingGuestApcs();
        recordRuntimeTrace(delivered ? "KeLeaveCriticalRegion delivered queued APCs"
                                    : "KeLeaveCriticalRegion APC delivery point reached");
    }
}

void xowue_KeRaiseIrqlToDpcLevel(PPCContext &context) {
    context.r3.u32 = g_guestIrql;
    g_guestIrql = 2u;
}

void xowue_KeAcquireSpinLockAtRaisedIrql(PPCContext &context, uint8_t *base) {
    const uint32_t address = context.r3.u32;
    std::shared_ptr<std::mutex> lock;
    {
        std::lock_guard<std::mutex> mapLock(g_spinLockMapMutex);
        auto &entry = g_guestSpinLocks[address];
        if (!entry) entry = std::make_shared<std::mutex>();
        lock = entry;
    }
    lock->lock();
    if (validGuestRange(address, 4u)) PPC_STORE_U32(address, 1u);
}

void xowue_KeReleaseSpinLockFromRaisedIrql(PPCContext &context, uint8_t *base) {
    const uint32_t address = context.r3.u32;
    std::shared_ptr<std::mutex> lock;
    {
        std::lock_guard<std::mutex> mapLock(g_spinLockMapMutex);
        const auto it = g_guestSpinLocks.find(address);
        if (it != g_guestSpinLocks.end()) lock = it->second;
    }
    if (!lock) {
        recordRuntimeTrace("KeReleaseSpinLockFromRaisedIrql ignored an unlocked spinlock");
        return;
    }
    if (validGuestRange(address, 4u)) PPC_STORE_U32(address, 0u);
    lock->unlock();
}

void xowue_KeLockL2(PPCContext &) { g_l2Mutex.lock(); }
void xowue_KeUnlockL2(PPCContext &) { g_l2Mutex.unlock(); }
void xowue_KeEnableFpuExceptions(PPCContext &) {}

void xowue_KeQuerySystemTime(PPCContext &context, uint8_t *base) {
    const uint32_t output = context.r3.u32;
    if (base && validGuestRange(output, 8u)) {
        constexpr uint64_t kUnixToFileTimeTicks = 116444736000000000ull;
        const auto now = std::chrono::system_clock::now().time_since_epoch();
        const uint64_t ticks = kUnixToFileTimeTicks + static_cast<uint64_t>(
            std::chrono::duration_cast<std::chrono::nanoseconds>(now).count() / 100);
        PPC_STORE_U64(output, ticks);
    }
}

void xowue_KeInitializeSemaphore(PPCContext &context, uint8_t *base) {
    const uint32_t address = context.r3.u32;
    const int32_t count = static_cast<int32_t>(context.r4.u32);
    const int32_t limit = static_cast<int32_t>(context.r5.u32);
    if (!base || !validGuestRange(address, 20u) || count < 0 || limit <= 0 || count > limit) {
        recordRuntimeTrace("KeInitializeSemaphore rejected guest layout or count/limit");
        return;
    }
    auto semaphore = std::make_shared<GuestWaitable>();
    semaphore->kind = GuestWaitable::Kind::Semaphore;
    semaphore->manualReset = false;
    semaphore->signaled = count > 0;
    semaphore->semaphoreCount = count;
    semaphore->semaphoreLimit = limit;
    semaphore->objectAddress = address;
    {
        std::lock_guard<std::mutex> lock(g_guestObjectMutex);
        g_guestPointerWaitables[address] = semaphore;
        g_guestWaitables[address] = semaphore;
    }
    std::memset(base + address, 0, 20u);
    PPC_STORE_U32(address, 5u);
    PPC_STORE_U32(address + 4u, static_cast<uint32_t>(count));
    PPC_STORE_U32(address + 16u, static_cast<uint32_t>(limit));
}

void xowue_KeReleaseSemaphore(PPCContext &context, uint8_t *base) {
    const uint32_t address = context.r3.u32;
    const int32_t adjustment = static_cast<int32_t>(context.r5.u32);
    const auto semaphore = lookupGuestWaitable(address);
    if (!base || !semaphore || semaphore->kind != GuestWaitable::Kind::Semaphore || adjustment < 0) {
        context.r3.u32 = 0u;
        return;
    }
    int32_t previous = 0;
    {
        std::lock_guard<std::mutex> lock(semaphore->mutex);
        previous = semaphore->semaphoreCount;
        if (adjustment > semaphore->semaphoreLimit - semaphore->semaphoreCount) {
            context.r3.u32 = 0u;
            return;
        }
        semaphore->semaphoreCount += adjustment;
        semaphore->signaled = semaphore->semaphoreCount > 0;
        writeGuestDispatcherSignalState(semaphore, semaphore->semaphoreCount);
    }
    context.r3.u32 = static_cast<uint32_t>(previous);
    semaphore->changed.notify_all();
    g_waitSetChanged.notify_all();
}

void xowue_NtCreateSemaphore(PPCContext &context, uint8_t *base) {
    const uint32_t output = context.r3.u32;
    const int32_t initialCount = static_cast<int32_t>(context.r5.u32);
    const int32_t limit = static_cast<int32_t>(context.r6.u32);
    if (!base || !validGuestRange(output, 4u) || initialCount < 0 || limit <= 0 ||
        initialCount > limit) {
        context.r3.u32 = kNtStatusInvalidParameter;
        return;
    }
    const uint32_t handle = allocateGuestHandle();
    const uint32_t object = allocateGuestEventObjectAddress();
    if (!handle || !object) { context.r3.u32 = kNtStatusNoMemory; return; }
    auto semaphore = std::make_shared<GuestWaitable>();
    semaphore->kind = GuestWaitable::Kind::Semaphore;
    semaphore->handle = handle; semaphore->objectAddress = object;
    semaphore->manualReset = false; semaphore->signaled = initialCount > 0;
    semaphore->semaphoreCount = initialCount; semaphore->semaphoreLimit = limit;
    {
        std::lock_guard<std::mutex> lock(g_guestObjectMutex);
        g_guestWaitables[handle] = semaphore; g_guestWaitables[object] = semaphore;
    }
    std::memset(base + object, 0, 20u);
    PPC_STORE_U32(object, 5u);
    PPC_STORE_U32(object + 4u, static_cast<uint32_t>(initialCount));
    PPC_STORE_U32(object + 16u, static_cast<uint32_t>(limit));
    PPC_STORE_U32(output, handle);
    context.r3.u32 = kNtStatusSuccess;
}

void xowue_NtReleaseSemaphore(PPCContext &context, uint8_t *base) {
    const auto semaphore = lookupGuestWaitable(context.r3.u32);
    const int32_t releaseCount = static_cast<int32_t>(context.r4.u32);
    const uint32_t previousPointer = context.r5.u32;
    if (!base || !semaphore || semaphore->kind != GuestWaitable::Kind::Semaphore ||
        releaseCount <= 0) {
        context.r3.u32 = semaphore ? kNtStatusInvalidParameter : kNtStatusInvalidHandle;
        return;
    }
    int32_t previous = 0;
    {
        std::lock_guard<std::mutex> lock(semaphore->mutex);
        previous = semaphore->semaphoreCount;
        if (releaseCount > semaphore->semaphoreLimit - previous) {
            context.r3.u32 = kNtStatusInvalidParameter;
            return;
        }
        semaphore->semaphoreCount += releaseCount;
        semaphore->signaled = semaphore->semaphoreCount > 0;
        writeGuestDispatcherSignalState(semaphore, semaphore->semaphoreCount);
    }
    if (previousPointer && validGuestRange(previousPointer, 4u))
        PPC_STORE_U32(previousPointer, static_cast<uint32_t>(previous));
    context.r3.u32 = kNtStatusSuccess;
    semaphore->changed.notify_all(); g_waitSetChanged.notify_all();
}

void xowue_NtCreateMutant(PPCContext &context, uint8_t *base) {
    const uint32_t output = context.r3.u32;
    if (!base || !validGuestRange(output, 4u)) { context.r3.u32 = kNtStatusInvalidParameter; return; }
    const uint32_t handle = allocateGuestHandle();
    const uint32_t object = allocateGuestEventObjectAddress();
    if (!handle || !object) { context.r3.u32 = kNtStatusNoMemory; return; }
    auto mutant = std::make_shared<GuestWaitable>();
    mutant->kind = GuestWaitable::Kind::Mutant;
    mutant->handle = handle; mutant->objectAddress = object;
    mutant->manualReset = true;
    mutant->ownerThread = context.r5.u32 ? g_currentGuestThreadId : 0u;
    mutant->recursion = context.r5.u32 ? 1u : 0u;
    mutant->signaled = context.r5.u32 == 0u;
    {
        std::lock_guard<std::mutex> lock(g_guestObjectMutex);
        g_guestWaitables[handle] = mutant; g_guestWaitables[object] = mutant;
    }
    std::memset(base + object, 0, 0x18u);
    PPC_STORE_U32(object, 2u);
    writeGuestDispatcherSignalState(mutant, guestDispatcherSignalState(*mutant));
    PPC_STORE_U32(output, handle);
    context.r3.u32 = kNtStatusSuccess;
}

void xowue_NtReleaseMutant(PPCContext &context) {
    const auto mutant = lookupGuestWaitable(context.r3.u32);
    if (!mutant || mutant->kind != GuestWaitable::Kind::Mutant) {
        context.r3.u32 = kNtStatusInvalidHandle; return;
    }
    {
        std::lock_guard<std::mutex> lock(mutant->mutex);
        if (mutant->ownerThread != g_currentGuestThreadId || mutant->recursion == 0u) {
            context.r3.u32 = 0xC0000046u; // STATUS_MUTANT_NOT_OWNED
            return;
        }
        if (--mutant->recursion == 0u) {
            mutant->ownerThread = 0u; mutant->signaled = true;
        }
        writeGuestDispatcherSignalState(mutant, guestDispatcherSignalState(*mutant));
    }
    context.r3.u32 = kNtStatusSuccess;
    mutant->changed.notify_all(); g_waitSetChanged.notify_all();
}

void xowue_NtCreateTimer(PPCContext &context, uint8_t *base) {
    const uint32_t output = context.r3.u32;
    const uint32_t timerType = context.r5.u32;
    if (!base || !validGuestRange(output, 4u) || timerType > 1u) {
        context.r3.u32 = kNtStatusInvalidParameter; return;
    }
    const uint32_t handle = allocateGuestHandle();
    const uint32_t object = allocateGuestEventObjectAddress();
    if (!handle || !object) { context.r3.u32 = kNtStatusNoMemory; return; }
    auto timer = std::make_shared<GuestWaitable>();
    timer->kind = GuestWaitable::Kind::Timer; timer->handle = handle;
    timer->objectAddress = object; timer->manualReset = timerType == 0u;
    timer->signaled = false;
    {
        std::lock_guard<std::mutex> lock(g_guestObjectMutex);
        g_guestWaitables[handle] = timer; g_guestWaitables[object] = timer;
    }
    std::memset(base + object, 0, 0x18u);
    PPC_STORE_U32(object, 8u);
    writeGuestDispatcherSignalState(timer, 0);
    PPC_STORE_U32(output, handle); context.r3.u32 = kNtStatusSuccess;
}

void xowue_NtSetTimerEx(PPCContext &context, uint8_t *base) {
    const auto timer = lookupGuestWaitable(context.r3.u32);
    const uint32_t duePointer = context.r4.u32;
    if (!base || !timer || timer->kind != GuestWaitable::Kind::Timer ||
        !validGuestRange(duePointer, 8u)) {
        context.r3.u32 = timer ? kNtStatusInvalidParameter : kNtStatusInvalidHandle; return;
    }
    const int64_t due = static_cast<int64_t>(PPC_LOAD_U64(duePointer));
    const uint32_t periodMs = context.r9.u32;
    uint64_t generation = 0u;
    {
        std::lock_guard<std::mutex> lock(timer->mutex);
        generation = ++timer->timerGeneration; timer->signaled = false;
        syncGuestDispatcherSignalState(timer);
    }
    int64_t delayTicks = due < 0 ? (due == std::numeric_limits<int64_t>::min()
        ? 86400LL * 10000000LL : -due) : 0;
    if (due > 0) {
        constexpr int64_t epoch = 116444736000000000LL;
        const auto now = std::chrono::system_clock::now().time_since_epoch();
        const int64_t nowTicks = epoch +
            std::chrono::duration_cast<std::chrono::nanoseconds>(now).count() / 100;
        delayTicks = std::max<int64_t>(0, due - nowTicks);
    }
    delayTicks = std::clamp<int64_t>(delayTicks, 0, 86400LL * 10000000LL);
    std::weak_ptr<GuestWaitable> weakTimer = timer;
    std::thread([weakTimer, generation, delayTicks, periodMs] {
        int64_t nextDelay = delayTicks;
        for (;;) {
            std::this_thread::sleep_for(std::chrono::nanoseconds(nextDelay * 100));
            const auto current = weakTimer.lock();
            if (!current) return;
            {
                std::lock_guard<std::mutex> lock(current->mutex);
                if (current->timerGeneration != generation) return;
                current->signaled = true;
                syncGuestDispatcherSignalState(current);
            }
            current->changed.notify_all(); g_waitSetChanged.notify_all();
            if (periodMs == 0u) return;
            nextDelay = static_cast<int64_t>(periodMs) * 10000LL;
        }
    }).detach();
    context.r3.u32 = kNtStatusSuccess;
}

void xowue_NtCancelTimer(PPCContext &context, uint8_t *base) {
    const auto timer = lookupGuestWaitable(context.r3.u32);
    if (!timer || timer->kind != GuestWaitable::Kind::Timer) {
        context.r3.u32 = kNtStatusInvalidHandle; return;
    }
    const uint32_t output = context.r4.u32;
    {
        std::lock_guard<std::mutex> lock(timer->mutex);
        if (output && base && validGuestRange(output, 4u))
            PPC_STORE_U32(output, timer->signaled ? 1u : 0u);
        ++timer->timerGeneration; timer->signaled = false;
        syncGuestDispatcherSignalState(timer);
    }
    context.r3.u32 = kNtStatusSuccess;
}

void xowue_ObCreateSymbolicLink(PPCContext &context, uint8_t *base) {
    std::string path, target;
    if (!readGuestAnsiString(base, context.r3.u32, path) ||
        !readGuestAnsiString(base, context.r4.u32, target)) {
        context.r3.u32 = kNtStatusInvalidParameter; return;
    }
    path = lowerGuestPath(path); target = lowerGuestPath(target);
    if (path.rfind("/??/", 0u) == 0u) path.erase(0u, 4u);
    std::lock_guard<std::mutex> lock(g_guestFileMutex);
    if (g_guestSymbolicLinks.contains(path)) { context.r3.u32 = kNtStatusUnsuccessful; return; }
    g_guestSymbolicLinks[path] = target;
    context.r3.u32 = kNtStatusSuccess;
}

void xowue_ObDeleteSymbolicLink(PPCContext &context, uint8_t *base) {
    std::string path;
    if (!readGuestAnsiString(base, context.r3.u32, path)) { context.r3.u32 = kNtStatusInvalidParameter; return; }
    std::lock_guard<std::mutex> lock(g_guestFileMutex);
    const bool removed = g_guestSymbolicLinks.erase(lowerGuestPath(path)) != 0u;
    context.r3.u32 = removed ? kNtStatusSuccess : kNtStatusUnsuccessful;
}

void xowue_FscSetCacheElementCount(PPCContext &context) {
    const uint32_t cacheClass = context.r3.u32;
    const uint32_t elementCount = context.r4.u32;
    context.r3.u32 = kNtStatusSuccess;
    char event[128];
    std::snprintf(event, sizeof(event),
                  "FscSetCacheElementCount class=%u count=%u -> STATUS_SUCCESS (no-op)",
                  cacheClass, elementCount);
    recordRuntimeTrace(event);
}

void xowue_NtCreateEvent(PPCContext &context, uint8_t *base) {
    const uint32_t handlePointer = context.r3.u32;
    const uint32_t objectAttributes = context.r4.u32;
    const uint32_t eventType = context.r5.u32;
    const uint32_t initialState = context.r6.u32;
    if (!base || (handlePointer != 0u && handlePointer > kGuestAddressSpaceSize - sizeof(uint32_t)) || eventType > 1u) {
        context.r3.u32 = kNtStatusInvalidParameter;
        recordRuntimeTrace("NtCreateEvent invalid parameters");
        return;
    }
    const uint32_t handle = allocateGuestHandle();
    if (handle == 0u) {
        context.r3.u32 = kNtStatusNoMemory;
        recordRuntimeTrace("NtCreateEvent handle space exhausted");
        return;
    }
    const uint32_t objectAddress = allocateGuestEventObjectAddress();
    if (objectAddress == 0u) {
        context.r3.u32 = kNtStatusNoMemory;
        recordRuntimeTrace("NtCreateEvent guest object range exhausted");
        return;
    }
    auto waitable = std::make_shared<GuestWaitable>();
    waitable->kind = GuestWaitable::Kind::Event;
    waitable->handle = handle;
    waitable->objectAddress = objectAddress;
    waitable->manualReset = eventType == 0u;
    waitable->signaled = initialState != 0u;
    {
        std::lock_guard<std::mutex> lock(g_guestObjectMutex);
        g_guestWaitables[handle] = waitable;
        g_guestWaitables[objectAddress] = waitable;
    }
    std::memset(base + objectAddress, 0, 0x18u);
    base[objectAddress] = static_cast<uint8_t>(eventType);
    syncGuestDispatcherSignalState(waitable);
    if (handlePointer != 0u) PPC_STORE_U32(handlePointer, handle);
    context.r3.u32 = kNtStatusSuccess;
    char event[144];
    std::snprintf(event, sizeof(event),
                  "NtCreateEvent handle=0x%08X type=%u manualReset=%u initial=%u named=%u",
                  handle, eventType, eventType == 0u ? 1u : 0u, initialState != 0u ? 1u : 0u,
                  objectAttributes != 0 ? 1u : 0u);
    recordRuntimeTrace(event);
}


void xowue_ObReferenceObjectByHandle(PPCContext &context, uint8_t *base) {
    const uint32_t handle = context.r3.u32;
    const uint32_t objectType = context.r4.u32;
    const uint32_t outputPointer = context.r5.u32;
    if (!base || (outputPointer != 0u &&
                  outputPointer > kGuestAddressSpaceSize - sizeof(uint32_t))) {
        context.r3.u32 = kNtStatusInvalidParameter;
        recordRuntimeTrace("ObReferenceObjectByHandle rejected output pointer");
        return;
    }

    const std::shared_ptr<GuestThread> thread = lookupGuestThread(handle);
    const std::shared_ptr<GuestWaitable> waitable =
        thread ? thread->completion : lookupGuestWaitable(handle);
    if (!waitable) {
        context.r3.u32 = kNtStatusInvalidHandle;
        recordRuntimeTrace("ObReferenceObjectByHandle invalid handle=0x" + [&] {
            char value[16];
            std::snprintf(value, sizeof(value), "%08X", handle);
            return std::string(value);
        }());
        return;
    }

    const bool isThread = waitable->kind == GuestWaitable::Kind::Thread;
    const uint32_t objectAddress = thread ? thread->objectAddress : waitable->objectAddress;
    if (objectAddress == 0u) {
        context.r3.u32 = kNtStatusInvalidHandle;
        recordRuntimeTrace("ObReferenceObjectByHandle object has no guest address");
        return;
    }
    const bool knownEventType = objectType == kXboxEventObjectType;
    const bool knownThreadType = objectType == kXboxThreadObjectType;
    const bool knownSemaphoreType = objectType == kXboxSemaphoreObjectType;
    const bool isSemaphore = waitable->kind == GuestWaitable::Kind::Semaphore;
    if ((knownEventType && (isThread || isSemaphore)) ||
        (knownThreadType && !isThread) || (knownSemaphoreType && !isSemaphore)) {
        context.r3.u32 = kNtStatusObjectTypeMismatch;
        recordRuntimeTrace("ObReferenceObjectByHandle object type mismatch");
        return;
    }

    {
        std::lock_guard<std::mutex> lock(g_guestObjectMutex);
        ++g_guestObjectReferences[objectAddress];
        g_guestReferencedWaitables[objectAddress] = waitable;
    }
    if (outputPointer != 0u) PPC_STORE_U32(outputPointer, objectAddress);
    context.r3.u32 = kNtStatusSuccess;
    char event[184];
    std::snprintf(event, sizeof(event),
                  "ObReferenceObjectByHandle handle=0x%08X type=0x%08X object=0x%08X kind=%s typeCheck=%s",
                  handle, objectType, objectAddress, isThread ? "Thread" :
                      isSemaphore ? "Semaphore" : "Synchronization",
                  (knownEventType || knownThreadType || knownSemaphoreType || objectType == 0u)
                      ? "recognized" : "opaque-export");
    recordRuntimeTrace(event);
}

void xowue_ObDereferenceObject(PPCContext &context) {
    const uint32_t objectAddress = context.r3.u32;
    bool knownReference = false;
    bool releasedFinalReference = false;
    {
        std::lock_guard<std::mutex> lock(g_guestObjectMutex);
        const auto reference = g_guestObjectReferences.find(objectAddress);
        if (reference != g_guestObjectReferences.end()) {
            knownReference = true;
            if (reference->second > 1u) {
                --reference->second;
            } else {
                g_guestObjectReferences.erase(reference);
                g_guestReferencedWaitables.erase(objectAddress);
                releasedFinalReference = true;
            }
        }
    }
    context.r3.u32 = 0u;
    recordRuntimeTrace(std::string("ObDereferenceObject object=0x") + [&] {
        char value[16];
        std::snprintf(value, sizeof(value), "%08X", objectAddress);
        return std::string(value);
    }() + (releasedFinalReference ? " released final reference" :
           knownReference ? " released reference" : " untracked reference ignored"));
}

void xowue_ObOpenObjectByPointer(PPCContext &context, uint8_t *base) {
    const uint32_t objectAddress = context.r3.u32;
    const uint32_t outputPointer = context.r4.u32;
    if (!base || outputPointer == 0u ||
        outputPointer > kGuestAddressSpaceSize - sizeof(uint32_t)) {
        context.r3.u32 = kNtStatusInvalidParameter;
        recordRuntimeTrace("ObOpenObjectByPointer rejected output pointer");
        return;
    }

    const std::shared_ptr<GuestThread> thread = lookupGuestThread(objectAddress);
    const std::shared_ptr<GuestWaitable> waitable =
        thread ? thread->completion : lookupGuestWaitable(objectAddress);
    const uint32_t handle = thread ? thread->handle : (waitable ? waitable->handle : 0u);
    if (handle == 0u) {
        context.r3.u32 = kNtStatusUnsuccessful;
        recordRuntimeTrace("ObOpenObjectByPointer unknown guest object");
        return;
    }

    {
        std::lock_guard<std::mutex> lock(g_guestObjectMutex);
        g_guestWaitables[handle] = waitable;
        g_guestWaitables[objectAddress] = waitable;
    }
    PPC_STORE_U32(outputPointer, handle);
    context.r3.u32 = kNtStatusSuccess;
    recordRuntimeTrace("ObOpenObjectByPointer returned existing guest handle");
}

void xowue_XexCheckExecutablePrivilege(PPCContext &context) {
    const uint32_t privilege = context.r3.u32;
    const bool allowed = privilege < 32 && (g_xexSystemFlags & (uint32_t{1} << privilege)) != 0;
    context.r3.u32 = allowed ? 1u : 0u;
    char event[140];
    std::snprintf(event, sizeof(event),
                  "XexCheckExecutablePrivilege privilege=%u systemFlags=0x%08X result=%u",
                  privilege, g_xexSystemFlags, allowed ? 1u : 0u);
    recordRuntimeTrace(event);
}

void xowue_XGetAVPack(PPCContext &context) {
    // Xenia's default Xbox 360 AV pack is VGA (6), which is a conservative
    // signal for software that only uses this value to select video output.
    context.r3.u32 = 6;
    recordRuntimeTrace("XGetAVPack -> VGA (6)");
}

void xowue_XGetGameRegion(PPCContext &context) {
    context.r3.u32 = 0xFFFFu;
    recordRuntimeTrace("XGetGameRegion -> all regions (0xFFFF)");
}

void xowue_KeTlsAlloc(PPCContext &context) {
    std::lock_guard<std::mutex> lock(g_tlsMutex);
    for (size_t index = 0; index < g_tlsSlotLimit; ++index) {
        if (!g_tlsAllocated[index]) {
            g_tlsAllocated[index] = true;
            if (g_tlsGenerations[index] == 0u) g_tlsGenerations[index] = 1u;
            g_tlsValues[index] = 0;
            g_tlsValueGenerations[index] = g_tlsGenerations[index];
            context.r3.u32 = static_cast<uint32_t>(index);
            recordRuntimeTrace("KeTlsAlloc -> slot " + std::to_string(index));
            return;
        }
    }
    context.r3.u32 = kTlsOutOfIndexes;
    recordRuntimeTrace("KeTlsAlloc -> sem slots livres");
}

void xowue_KeTlsFree(PPCContext &context) {
    const uint32_t index = context.r3.u32;
    std::lock_guard<std::mutex> lock(g_tlsMutex);
    const bool valid = index < g_tlsSlotLimit && g_tlsAllocated[index];
    if (valid) {
        g_tlsAllocated[index] = false;
        ++g_tlsGenerations[index];
        if (g_tlsGenerations[index] == 0u) g_tlsGenerations[index] = 1u;
        g_tlsValues[index] = 0;
        g_tlsValueGenerations[index] = 0u;
    }
    context.r3.u32 = valid ? 1u : 0u;
    recordRuntimeTrace("KeTlsFree slot=" + std::to_string(index) + " result=" + (valid ? "1" : "0"));
}

void xowue_KeTlsGetValue(PPCContext &context) {
    const uint32_t index = context.r3.u32;
    bool allocated = false;
    uint32_t generation = 0u;
    {
        std::lock_guard<std::mutex> lock(g_tlsMutex);
        allocated = index < g_tlsSlotLimit && g_tlsAllocated[index];
        if (allocated) generation = g_tlsGenerations[index];
    }
    context.r3.u32 = allocated && g_tlsValueGenerations[index] == generation
        ? g_tlsValues[index] : 0u;
}

void xowue_KeTlsSetValue(PPCContext &context) {
    const uint32_t index = context.r3.u32;
    const uint32_t value = context.r4.u32;
    bool allocated = false;
    uint32_t generation = 0u;
    {
        std::lock_guard<std::mutex> lock(g_tlsMutex);
        allocated = index < g_tlsSlotLimit && g_tlsAllocated[index];
        if (allocated) generation = g_tlsGenerations[index];
    }
    if (allocated) {
        g_tlsValues[index] = value;
        g_tlsValueGenerations[index] = generation;
        context.r3.u32 = 1;
    } else {
        context.r3.u32 = 0;
    }
}

void xowue_RtlNtStatusToDosError(PPCContext &context) {
    const uint32_t status = context.r3.u32;
    uint32_t result = 317; // ERROR_MR_MID_NOT_FOUND, Xenia's fallback.
    if (status == 0 || (status & 0x20000000u)) {
        result = status;
    } else if ((status >> 16) == 0x8007u) {
        result = status & 0xFFFFu;
    } else {
        switch (status) {
        case 0xC0000005u: result = 998; break; // ERROR_NOACCESS
        case 0xC000000Du: result = 87; break;  // ERROR_INVALID_PARAMETER
        case 0xC0000017u: result = 8; break;   // ERROR_NOT_ENOUGH_MEMORY
        case 0xC0000022u: result = 5; break;   // ERROR_ACCESS_DENIED
        case 0xC0000034u: result = 2; break;   // ERROR_FILE_NOT_FOUND
        case 0xC0000035u: result = 183; break; // ERROR_ALREADY_EXISTS
        case 0xC0000001u: result = 31; break;  // ERROR_GEN_FAILURE
        default: break;
        }
    }
    context.r3.u32 = result;
    char event[120];
    std::snprintf(event, sizeof(event), "RtlNtStatusToDosError 0x%08X -> %u", status, result);
    recordRuntimeTrace(event);
}

void xowue_RtlCompareMemoryUlong(PPCContext &context, uint8_t *base) {
    const uint32_t source = context.r3.u32, length = context.r4.u32;
    const uint32_t pattern = context.r5.u32;
    if (!base || (source & 3u) != 0u || (length & 3u) != 0u ||
        (length != 0u && !validGuestRange(source, length))) {
        context.r3.u32 = 0u; return;
    }
    uint32_t matches = 0u;
    for (uint32_t offset = 0u; offset < length; offset += 4u)
        if (PPC_LOAD_U32(source + offset) == pattern) ++matches;
    context.r3.u32 = matches;
}

void xowue_RtlFillMemoryUlong(PPCContext &context, uint8_t *base) {
    const uint32_t destination = context.r3.u32, length = context.r4.u32;
    const uint32_t pattern = context.r5.u32;
    if (!base || (length != 0u && !validGuestRange(destination, length))) return;
    for (uint32_t offset = 0u; offset + 4u <= length; offset += 4u)
        PPC_STORE_U32(destination + offset, pattern);
}

void xowue_RtlCompareStringN(PPCContext &context, uint8_t *base) {
    const uint32_t first = context.r3.u32, firstLengthArg = context.r4.u32;
    const uint32_t second = context.r5.u32, secondLengthArg = context.r6.u32;
    const bool insensitive = context.r7.u32 != 0u;
    auto lengthFor = [base](uint32_t address, uint32_t given, uint32_t &length) {
        if (given != 0xFFFFu) { length = given; return true; }
        if (!base || address >= kGuestAddressSpaceSize) return false;
        length = 0u;
        while (length < 0x10000u && address + length < kGuestAddressSpaceSize &&
               base[address + length] != 0u) ++length;
        return length < 0x10000u;
    };
    uint32_t firstLength = 0u, secondLength = 0u;
    if (!base || !lengthFor(first, firstLengthArg, firstLength) ||
        !lengthFor(second, secondLengthArg, secondLength) ||
        (firstLength && !validGuestRange(first, firstLength)) ||
        (secondLength && !validGuestRange(second, secondLength))) {
        context.r3.u32 = static_cast<uint32_t>(-1); return;
    }
    const uint32_t common = std::min(firstLength, secondLength);
    for (uint32_t i = 0; i < common; ++i) {
        unsigned char a = base[first + i], b = base[second + i];
        if (insensitive) { a = static_cast<unsigned char>(std::tolower(a)); b = static_cast<unsigned char>(std::tolower(b)); }
        if (a != b) { context.r3.u32 = static_cast<uint32_t>(static_cast<int32_t>(a) - static_cast<int32_t>(b)); return; }
    }
    context.r3.u32 = firstLength == secondLength ? 0u :
        static_cast<uint32_t>(firstLength < secondLength ? -1 : 1);
}

void xowue_RtlInitAnsiString(PPCContext &context, uint8_t *base) {
    const uint32_t descriptor = context.r3.u32, source = context.r4.u32;
    if (!base || !validGuestRange(descriptor, 8u) ||
        (source != 0u && source >= kGuestAddressSpaceSize)) return;
    uint32_t length = 0u;
    if (source != 0u) {
        while (length < 0xFFFFu && source + length < kGuestAddressSpaceSize && base[source + length]) ++length;
        if (length == 0xFFFFu) length = 0xFFFEu;
    }
    storeGuestBe16(base, descriptor, static_cast<uint16_t>(source ? length : 0u));
    storeGuestBe16(base, descriptor + 2u, static_cast<uint16_t>(source ? std::min<uint32_t>(length + 1u, 0xFFFFu) : 0u));
    PPC_STORE_U32(descriptor + 4u, source);
}

void xowue_RtlInitUnicodeString(PPCContext &context, uint8_t *base) {
    const uint32_t descriptor = context.r3.u32, source = context.r4.u32;
    if (!base || !validGuestRange(descriptor, 8u) ||
        (source != 0u && source >= kGuestAddressSpaceSize)) return;
    uint32_t length = 0u;
    if (source != 0u) {
        while (length < 0x7FFFu && static_cast<uint64_t>(source) + length * 2u + 1u < kGuestAddressSpaceSize &&
               PPC_LOAD_U16(source + length * 2u) != 0u) ++length;
    }
    const uint32_t bytes = source ? length * 2u : 0u;
    storeGuestBe16(base, descriptor, static_cast<uint16_t>(bytes));
    storeGuestBe16(base, descriptor + 2u, static_cast<uint16_t>(source ? std::min<uint32_t>(bytes + 2u, 0xFFFFu) : 0u));
    PPC_STORE_U32(descriptor + 4u, source);
}

void xowue_RtlFreeAnsiString(PPCContext &context, uint8_t *base) {
    const uint32_t descriptor = context.r3.u32;
    if (!base || !validGuestRange(descriptor, 8u)) return;
    const uint32_t buffer = PPC_LOAD_U32(descriptor + 4u);
    if (buffer) releaseGuestPhysicalRange(buffer);
    std::memset(base + descriptor, 0, 8u);
}

static void appendUtf8(std::string &out, uint16_t character) {
    if (character < 0x80u) out.push_back(static_cast<char>(character));
    else if (character < 0x800u) {
        out.push_back(static_cast<char>(0xC0u | (character >> 6u)));
        out.push_back(static_cast<char>(0x80u | (character & 0x3Fu)));
    } else {
        out.push_back(static_cast<char>(0xE0u | (character >> 12u)));
        out.push_back(static_cast<char>(0x80u | ((character >> 6u) & 0x3Fu)));
        out.push_back(static_cast<char>(0x80u | (character & 0x3Fu)));
    }
}

void xowue_RtlUnicodeStringToAnsiString(PPCContext &context, uint8_t *base) {
    const uint32_t destination = context.r3.u32, source = context.r4.u32;
    const bool allocate = context.r5.u32 != 0u;
    if (!base || !validGuestRange(destination, 8u) || !validGuestRange(source, 8u)) {
        context.r3.u32 = kNtStatusInvalidParameter; return;
    }
    const uint16_t sourceLength = loadGuestBe16(base, source);
    const uint16_t sourceMax = loadGuestBe16(base, source + 2u);
    const uint32_t sourceBuffer = PPC_LOAD_U32(source + 4u);
    if ((sourceLength & 1u) || sourceLength > sourceMax ||
        (sourceLength && !validGuestRange(sourceBuffer, sourceLength))) {
        context.r3.u32 = kNtStatusInvalidParameter; return;
    }
    std::string converted;
    converted.reserve(sourceLength);
    for (uint32_t i = 0; i < sourceLength; i += 2u)
        appendUtf8(converted, PPC_LOAD_U16(sourceBuffer + i));
    uint32_t destinationBuffer = PPC_LOAD_U32(destination + 4u);
    uint16_t capacity = loadGuestBe16(base, destination + 2u);
    if (allocate) {
        destinationBuffer = allocateGuestPhysicalRange(base,
            static_cast<uint32_t>(converted.size() + 1u), 0x1000u, 0x04u);
        if (!destinationBuffer) { context.r3.u32 = kNtStatusNoMemory; return; }
        capacity = static_cast<uint16_t>(std::min<size_t>(converted.size() + 1u, 0xFFFFu));
    }
    if (!validGuestRange(destinationBuffer, std::min<size_t>(capacity, converted.size() + 1u))) {
        context.r3.u32 = kNtStatusInvalidParameter; return;
    }
    const size_t count = std::min<size_t>(converted.size(), capacity ? capacity - 1u : 0u);
    std::memcpy(base + destinationBuffer, converted.data(), count);
    if (capacity > count) base[destinationBuffer + count] = 0u;
    storeGuestBe16(base, destination, static_cast<uint16_t>(count));
    storeGuestBe16(base, destination + 2u, capacity);
    PPC_STORE_U32(destination + 4u, destinationBuffer);
    context.r3.u32 = count == converted.size() ? kNtStatusSuccess : kNtStatusBufferTooSmall;
}

void xowue_RtlUpcaseUnicodeChar(PPCContext &context) {
    uint32_t c = context.r3.u32 & 0xFFFFu;
    if (c >= 'a' && c <= 'z') c -= 0x20u;
    else if ((c >= 0x00E0u && c <= 0x00F6u) || (c >= 0x00F8u && c <= 0x00FEu)) c -= 0x20u;
    else if (c == 0x00FFu) c = 0x0178u;
    context.r3.u32 = c;
}

void xowue_RtlTimeFieldsToTime(PPCContext &context, uint8_t *base) {
    const uint32_t fields = context.r3.u32, output = context.r4.u32;
    if (!base || !validGuestRange(fields, 16u) || !validGuestRange(output, 8u)) { context.r3.u32 = 0u; return; }
    const int year = loadGuestBe16(base, fields), month = loadGuestBe16(base, fields + 2u);
    const int day = loadGuestBe16(base, fields + 4u), hour = loadGuestBe16(base, fields + 6u);
    const int minute = loadGuestBe16(base, fields + 8u), second = loadGuestBe16(base, fields + 10u);
    const int millis = loadGuestBe16(base, fields + 12u);
    if (year < 1601 || month < 1 || month > 12 || hour > 23 || minute > 59 || second > 59 || millis > 999) { context.r3.u32 = 0u; return; }
    const std::chrono::year_month_day ymd{std::chrono::year{year}, std::chrono::month{static_cast<unsigned>(month)}, std::chrono::day{static_cast<unsigned>(day)}};
    if (!ymd.ok()) { context.r3.u32 = 0u; return; }
    const auto point = std::chrono::sys_days{ymd} + std::chrono::hours{hour} +
        std::chrono::minutes{minute} + std::chrono::seconds{second} + std::chrono::milliseconds{millis};
    constexpr int64_t epochTicks = 116444736000000000LL;
    const auto unixNs = std::chrono::duration_cast<std::chrono::nanoseconds>(point.time_since_epoch()).count();
    const uint64_t ticks = static_cast<uint64_t>(epochTicks + unixNs / 100);
    PPC_STORE_U64(output, ticks); context.r3.u32 = 1u;
}

void xowue_RtlTimeToTimeFields(PPCContext &context, uint8_t *base) {
    const uint32_t input = context.r3.u32, fields = context.r4.u32;
    if (!base || !validGuestRange(input, 8u) || !validGuestRange(fields, 16u)) return;
    constexpr int64_t epochTicks = 116444736000000000LL;
    const int64_t ticks = static_cast<int64_t>(PPC_LOAD_U64(input));
    const auto ns = std::chrono::nanoseconds{(ticks - epochTicks) * 100};
    const auto point = std::chrono::sys_time<std::chrono::nanoseconds>{ns};
    const auto dayPoint = std::chrono::floor<std::chrono::days>(point);
    const std::chrono::year_month_day ymd{dayPoint};
    const std::chrono::weekday weekday{dayPoint};
    const auto time = std::chrono::hh_mm_ss{std::chrono::floor<std::chrono::milliseconds>(point - dayPoint)};
    storeGuestBe16(base, fields, static_cast<uint16_t>(static_cast<int>(ymd.year())));
    storeGuestBe16(base, fields + 2u, static_cast<uint16_t>(static_cast<unsigned>(ymd.month())));
    storeGuestBe16(base, fields + 4u, static_cast<uint16_t>(static_cast<unsigned>(ymd.day())));
    storeGuestBe16(base, fields + 6u, static_cast<uint16_t>(time.hours().count()));
    storeGuestBe16(base, fields + 8u, static_cast<uint16_t>(time.minutes().count()));
    storeGuestBe16(base, fields + 10u, static_cast<uint16_t>(time.seconds().count()));
    storeGuestBe16(base, fields + 12u, static_cast<uint16_t>(time.subseconds().count()));
    storeGuestBe16(base, fields + 14u, static_cast<uint16_t>(weekday.c_encoding()));
}

void xowue_XamGetExecutionId(PPCContext &context, uint8_t *base) {
    const uint32_t output = context.r3.u32;
    if (!base || !validGuestRange(output, 4u) || g_activeExecutionInfoAddress == 0u) {
        context.r3.u32 = kNtStatusInvalidParameter; return;
    }
    PPC_STORE_U32(output, g_activeExecutionInfoAddress);
    context.r3.u32 = kNtStatusSuccess;
}

void xowue_XamGetSystemVersion(PPCContext &context) {
    context.r3.u32 = 0u; // Same conservative value used by Xenia for symbol probing.
}

void xowue_XGetLanguage(PPCContext &context) {
    context.r3.u32 = 9u; // XLanguage::kPortuguese
}

void xowue_RtlImageXexHeaderField(PPCContext &context) {
    const uint32_t field = context.r4.u32;
    context.r3.u32 = field == 0x00040006u ? g_activeExecutionInfoAddress : 0u;
}

void xowue_RtlUnicodeToMultiByteN(PPCContext &context, uint8_t *base) {
    const uint32_t destination = context.r3.u32;
    const uint32_t destinationLength = context.r4.u32;
    const uint32_t written = context.r5.u32;
    const uint32_t source = context.r6.u32;
    const uint32_t sourceLength = context.r7.u32;
    const uint32_t count = std::min(sourceLength / 2u, destinationLength);
    if (!base ||
        static_cast<uint64_t>(source) + static_cast<uint64_t>(count) * 2u > kGuestAddressSpaceSize ||
        static_cast<uint64_t>(destination) + count > kGuestAddressSpaceSize ||
        (written != 0 && written > kGuestAddressSpaceSize - sizeof(uint32_t))) {
        context.r3.u32 = kNtStatusInvalidParameter;
        return;
    }
    for (uint32_t index = 0; index < count; ++index) {
        const uint16_t character = PPC_LOAD_U16(source + index * 2u);
        base[destination + index] = character < 256u ? static_cast<uint8_t>(character) : static_cast<uint8_t>('?');
    }
    if (written != 0) PPC_STORE_U32(written, count);
    context.r3.u32 = kNtStatusSuccess;
    recordRuntimeTrace("RtlUnicodeToMultiByteN copied=" + std::to_string(count));
}

void xowue_RtlMultiByteToUnicodeN(PPCContext &context, uint8_t *base) {
    const uint32_t destination = context.r3.u32;
    const uint32_t destinationLength = context.r4.u32;
    const uint32_t written = context.r5.u32;
    const uint32_t source = context.r6.u32;
    const uint32_t sourceLength = context.r7.u32;
    const uint32_t count = std::min(destinationLength / 2u, sourceLength);
    if (!base ||
        static_cast<uint64_t>(destination) + static_cast<uint64_t>(count) * 2u > kGuestAddressSpaceSize ||
        static_cast<uint64_t>(source) + count > kGuestAddressSpaceSize ||
        (written != 0 && written > kGuestAddressSpaceSize - sizeof(uint32_t))) {
        context.r3.u32 = kNtStatusInvalidParameter;
        return;
    }
    for (uint32_t index = 0; index < count; ++index) {
        const uint8_t character = base[source + index];
        base[destination + index * 2u] = 0;
        base[destination + index * 2u + 1u] = character;
    }
    if (written != 0) PPC_STORE_U32(written, count * 2u);
    context.r3.u32 = kNtStatusSuccess;
    recordRuntimeTrace("RtlMultiByteToUnicodeN copied=" + std::to_string(count));
}

void xowue_XamLoaderGetLaunchDataSize(PPCContext &context, uint8_t *base) {
    const uint32_t sizeAddress = context.r3.u32;
    if (sizeAddress == 0) {
        context.r3.u32 = kXamErrorInvalidParameter;
        recordRuntimeTrace("XamLoaderGetLaunchDataSize null size pointer -> 0x80070057");
        return;
    }
    if (!base || sizeAddress > kGuestAddressSpaceSize - sizeof(uint32_t)) {
        context.r3.u32 = kXamErrorInvalidParameter;
        recordRuntimeTrace("XamLoaderGetLaunchDataSize invalid guest pointer -> 0x80070057");
        return;
    }
    PPC_STORE_U32(sizeAddress, 0);
    context.r3.u32 = kXamErrorNotFound;
    recordRuntimeTrace("XamLoaderGetLaunchDataSize -> no launch payload (0x80070490)");
}

void xowue_NtQueryVirtualMemory(PPCContext &context, uint8_t *base) {
    std::lock_guard<std::mutex> stateLock(g_virtualMemoryMutex);
    const uint32_t requested=context.r3.u32;
    const uint32_t information=context.r4.u32;
    const uint32_t regionType=context.r5.u32;
    constexpr uint32_t kInfoSize=28u;
    constexpr uint32_t kCommit=0x1000u,kReserve=0x2000u,kPrivate=0x20000u;
    if(!base || !validGuestRange(information,kInfoSize) || regionType>2u ||
       requested>=kGuestAddressSpaceSize) {
        context.r3.u32=kNtStatusInvalidParameter;
        return;
    }
    const auto reservation=std::find_if(
        g_virtualAllocations.begin(),g_virtualAllocations.end(),
        [requested](const auto &it) {
            return requested>=it.address &&
                uint64_t(requested)<uint64_t(it.address)+it.size;
        });
    if(reservation==g_virtualAllocations.end()) {
        context.r3.u32=kNtStatusInvalidParameter;
        return;
    }
    // MEMORY_BASIC_INFORMATION BaseAddress is the queried page, not the
    // allocation base. RegionSize spans matching contiguous page states from
    // this page onward, without crossing a different committed subregion.
    constexpr uint32_t pageSize=0x1000u;
    const uint32_t regionBase=requested&~(pageSize-1u);
    const uint64_t reservationEnd=uint64_t(reservation->address)+reservation->size;
    auto findCommit=[](uint32_t p) {
        return std::find_if(g_virtualCommits.begin(),g_virtualCommits.end(),
            [p](const auto &c) {
                return p>=c.address&&uint64_t(p)<uint64_t(c.address)+c.size;
            });
    };
    const auto first=findCommit(regionBase);
    const bool committed=first!=g_virtualCommits.end();
    const uint32_t protect=committed?first->protection:0u;
    uint64_t end=reservationEnd;
    if(committed)end=std::min(end,uint64_t(first->address)+first->size);
    else for(const auto &c:g_virtualCommits)
        if(c.address>regionBase)end=std::min(end,uint64_t(c.address));
    if(end<=regionBase || end>kGuestAddressSpaceSize) {
        context.r3.u32=kNtStatusInvalidParameter;
        return;
    }
    PPC_STORE_U32(information+0x00u,regionBase);
    PPC_STORE_U32(information+0x04u,reservation->address);
    PPC_STORE_U32(information+0x08u,reservation->protection);
    PPC_STORE_U32(information+0x0Cu,static_cast<uint32_t>(end-regionBase));
    PPC_STORE_U32(information+0x10u,committed?kCommit:kReserve);
    PPC_STORE_U32(information+0x14u,protect);
    PPC_STORE_U32(information+0x18u,kPrivate);
    context.r3.u32=kNtStatusSuccess;
    char event[200];
    std::snprintf(event,sizeof(event),
        "NtQueryVirtualMemory queried=%08X page=%08X allocation=%08X size=%08X state=%08X protection=%08X",
        requested,regionBase,reservation->address,
        static_cast<uint32_t>(end-regionBase),committed?kCommit:kReserve,protect);
    recordRuntimeTrace(event);
}

void xowue_MmQueryAddressProtect(PPCContext &context) {
    const uint32_t address = context.r3.u32;
    std::lock_guard<std::mutex> lock(g_virtualMemoryMutex);
    const auto commit = std::find_if(g_virtualCommits.begin(), g_virtualCommits.end(),
        [address](const auto &item) {
            return address >= item.address &&
                static_cast<uint64_t>(address) < static_cast<uint64_t>(item.address) + item.size;
        });
    context.r3.u32 = commit == g_virtualCommits.end() ? 0u : commit->protection;
}

void xowue_MmSetAddressProtect(PPCContext &context) {
    const uint32_t address = context.r3.u32;
    const uint32_t size = context.r4.u32;
    const uint32_t protection = context.r5.u32;
    if (size == 0u || !validGuestRange(address, size)) {
        recordRuntimeTrace("MmSetAddressProtect rejected invalid range");
        return;
    }
    std::lock_guard<std::mutex> lock(g_virtualMemoryMutex);
    bool found = false;
    for (auto &commit : g_virtualCommits) {
        const uint64_t commitEnd = static_cast<uint64_t>(commit.address) + commit.size;
        const uint64_t requestEnd = static_cast<uint64_t>(address) + size;
        if (address < commitEnd && requestEnd > commit.address) {
            commit.protection = protection;
            found = true;
        }
    }
    for (auto &allocation : g_virtualAllocations) {
        const uint64_t allocationEnd = static_cast<uint64_t>(allocation.address) + allocation.size;
        const uint64_t requestEnd = static_cast<uint64_t>(address) + size;
        if (address < allocationEnd && requestEnd > allocation.address)
            allocation.protection = protection;
    }
    if (!found) recordRuntimeTrace("MmSetAddressProtect range is reserved but has no committed pages");
}

void xowue_MmQueryStatistics(PPCContext &context, uint8_t *base) {
    const uint32_t address = context.r3.u32;
    constexpr uint32_t kStatsSize = 104u;
    if (!base || !validGuestRange(address, kStatsSize)) {
        context.r3.u32 = kNtStatusInvalidParameter;
        return;
    }
    if (PPC_LOAD_U32(address) != kStatsSize) {
        context.r3.u32 = kNtStatusBufferTooSmall;
        return;
    }
    uint64_t usedPages = 0u;
    {
        std::lock_guard<std::mutex> lock(g_virtualMemoryMutex);
        for (const auto &commit : g_virtualCommits)
            usedPages += (static_cast<uint64_t>(commit.size) + 0xFFFu) / 0x1000u;
    }
    const uint32_t totalPages = 0x20000u;
    const uint32_t available = usedPages >= totalPages ? 0u :
        totalPages - static_cast<uint32_t>(usedPages);
    std::memset(base + address, 0, kStatsSize);
    PPC_STORE_U32(address, kStatsSize);
    PPC_STORE_U32(address + 4u, totalPages);
    PPC_STORE_U32(address + 8u, 0x300u);
    PPC_STORE_U32(address + 12u, available);
    PPC_STORE_U32(address + 16u, 0x2FFF0000u);
    PPC_STORE_U32(address + 20u, 0x00160000u);
    PPC_STORE_U32(address + 24u, 0x1000u);
    PPC_STORE_U32(address + 28u, 0x10u);
    PPC_STORE_U32(address + 32u, 0x100u);
    PPC_STORE_U32(address + 36u, 0x100u);
    PPC_STORE_U32(address + 40u, 0x100u);
    PPC_STORE_U32(address + 44u, 0x100u);
    PPC_STORE_U32(address + 48u, 0x100u);
    PPC_STORE_U32(address + 52u, 0x100u);
    PPC_STORE_U32(address + 56u, 0u);
    PPC_STORE_U32(address + 100u, totalPages - 1u);
    context.r3.u32 = kNtStatusSuccess;
}

void xowue_NtAllocateVirtualMemory(PPCContext &context, uint8_t *base) {
    std::lock_guard<std::mutex> stateLock(g_virtualMemoryMutex);
    const uint32_t basePointer = context.r3.u32;
    const uint32_t sizePointer = context.r4.u32;
    const uint32_t allocationType = context.r5.u32;
    const uint32_t protection = context.r6.u32;
    const uint32_t debugMemory = context.r7.u32;
    uint32_t requestedBase = 0;
    uint32_t requestedSize = 0;
    auto failWith = [&context, basePointer, sizePointer, allocationType, protection, debugMemory,
                     &requestedBase, &requestedSize](uint32_t status) {
        char event[220];
        std::snprintf(event, sizeof(event),
                      "NtAllocate basePtr=0x%08X sizePtr=0x%08X requested=0x%08X size=0x%08X flags=0x%08X protect=0x%08X debug=0x%08X status=0x%08X next_virtual=0x%08X next_physical=0x%08X",
                      basePointer, sizePointer, requestedBase, requestedSize, allocationType,
                      protection, debugMemory, status, g_nextVirtualAllocation, g_nextPhysicalAllocation);
        recordRuntimeTrace(event);
        context.r3.u32 = status;
    };
    if (!base || basePointer > kGuestAddressSpaceSize - sizeof(uint32_t) ||
        sizePointer > kGuestAddressSpaceSize - sizeof(uint32_t) ||
        basePointer == sizePointer || debugMemory != 0) {
        failWith(kNtStatusInvalidParameter);
        return;
    }

    requestedBase = PPC_LOAD_U32(basePointer);
    requestedSize = PPC_LOAD_U32(sizePointer);
    constexpr uint32_t kMemCommit = 0x00001000u;
    constexpr uint32_t kMemReserve = 0x00002000u;
    const bool commit = (allocationType & kMemCommit) != 0;
    const bool reserve = (allocationType & kMemReserve) != 0;
    if (requestedSize == 0 || (!commit && !reserve)) {
        failWith(kNtStatusInvalidParameter);
        return;
    }

    const uint32_t pageSize = (allocationType & 0x20000000u) ? 0x10000u : 0x1000u;
    if (requestedBase != 0) requestedBase &= ~(pageSize - 1u);
    const uint64_t adjustedSize64 =
        (static_cast<uint64_t>(requestedSize) + pageSize - 1u) & ~static_cast<uint64_t>(pageSize - 1u);
    if (adjustedSize64 == 0 || adjustedSize64 > std::numeric_limits<uint32_t>::max()) {
        failWith(kNtStatusInvalidParameter);
        return;
    }
    const uint32_t adjustedSize = static_cast<uint32_t>(adjustedSize64);

    uint32_t address = requestedBase;
    const bool automaticAddress = address == 0;
    if (automaticAddress) {
        const uint64_t candidate = (static_cast<uint64_t>(g_nextVirtualAllocation) + pageSize - 1u) &
                                   ~static_cast<uint64_t>(pageSize - 1u);
        const uint64_t next = candidate + adjustedSize;
        if (candidate < kFirstVirtualAllocation || next > kLastVirtualAllocation) {
            failWith(kNtStatusNoMemory);
            return;
        }
        address = static_cast<uint32_t>(candidate);
        g_nextVirtualAllocation = static_cast<uint32_t>(next);
    }
    if (address == 0) {
        failWith(kNtStatusInvalidParameter);
        return;
    }

    const uint64_t allocationEnd = static_cast<uint64_t>(address) + adjustedSize;
    const uint64_t imageEnd = static_cast<uint64_t>(PPC_IMAGE_BASE) + PPC_IMAGE_SIZE;
    const uint64_t dispatchEnd = imageEnd + static_cast<uint64_t>(PPC_CODE_SIZE) * 2;
    const uint64_t stackBegin = kInitialStackPointer - 0x100000u;
    if (allocationEnd > kGuestAddressSpaceSize ||
        (address < imageEnd && allocationEnd > PPC_IMAGE_BASE) ||
        (address < dispatchEnd && allocationEnd > imageEnd) ||
        (address < kInitialStackPointer && allocationEnd > stackBegin)) {
        failWith(kNtStatusNoMemory);
        return;
    }

    const auto containingReservation = std::find_if(
        g_virtualAllocations.begin(), g_virtualAllocations.end(),
        [address, allocationEnd](const auto &item) {
            const uint64_t reservationEnd = static_cast<uint64_t>(item.address) + item.size;
            return address >= item.address && allocationEnd <= reservationEnd;
        });

    if (!reserve && !automaticAddress) {
        // Xbox titles commonly reserve a large arena, then commit pages inside
        // it. A commit is valid when the whole requested range is reserved.
        if (containingReservation == g_virtualAllocations.end()) {
            failWith(kNtStatusMemoryNotAllocated);
            return;
        }
    } else {
        for (const auto &allocation : g_virtualAllocations) {
            const uint64_t allocatedEnd = static_cast<uint64_t>(allocation.address) + allocation.size;
            if (address < allocatedEnd && allocationEnd > allocation.address) {
                failWith(kNtStatusNoMemory);
                return;
            }
        }
    }

    if (commit && (allocationType & 0x00800000u) == 0) {
        std::memset(base + address, 0, adjustedSize);
    }

    PPC_STORE_U32(basePointer, address);
    PPC_STORE_U32(sizePointer, adjustedSize);
    requestedBase = address;
    requestedSize = adjustedSize;
    if (reserve || automaticAddress) g_virtualAllocations.push_back({address, adjustedSize, protection});
    if (commit) g_virtualCommits.push_back({address, adjustedSize, protection});
    (void)protection; // Host guest memory is uniformly readable/writable at this stage.
    failWith(kNtStatusSuccess);
}

void xowue_NtFreeVirtualMemory(PPCContext &context, uint8_t *base) {
    std::lock_guard<std::mutex> stateLock(g_virtualMemoryMutex);
    const uint32_t basePointer = context.r3.u32;
    const uint32_t sizePointer = context.r4.u32;
    const uint32_t freeType = context.r5.u32;
    const uint32_t debugMemory = context.r6.u32;
    uint32_t address = 0;
    uint32_t requestedSize = 0;

    auto failWith = [&context, basePointer, sizePointer, freeType, debugMemory,
                     &address, &requestedSize](uint32_t status) {
        char event[240];
        std::snprintf(event, sizeof(event),
                      "NtFree basePtr=0x%08X sizePtr=0x%08X address=0x%08X size=0x%08X type=0x%08X debug=0x%08X status=0x%08X",
                      basePointer, sizePointer, address, requestedSize, freeType, debugMemory, status);
        recordRuntimeTrace(event);
        context.r3.u32 = status;
    };
    if (!base || basePointer > kGuestAddressSpaceSize - sizeof(uint32_t) ||
        sizePointer > kGuestAddressSpaceSize - sizeof(uint32_t) ||
        basePointer == sizePointer || debugMemory != 0) {
        failWith(kNtStatusInvalidParameter);
        return;
    }

    address = PPC_LOAD_U32(basePointer);
    requestedSize = PPC_LOAD_U32(sizePointer);
    if (address == 0) {
        failWith(kNtStatusMemoryNotAllocated);
        return;
    }

    // MEM_RELEASE size=0 is an exact reservation-base operation. Using an
    // inclusive range-end search selected the PREVIOUS reservation when the
    // requested address equaled its end (seen 144 times in Build 33).
    const auto allocation = std::find_if(
        g_virtualAllocations.begin(), g_virtualAllocations.end(),
        [address, requestedSize, freeType](const auto &item) {
            if (freeType == 0x00008000u) return address == item.address;
            const uint64_t rangeEnd = uint64_t(address) + requestedSize;
            const uint64_t reservationEnd = uint64_t(item.address) + item.size;
            return requestedSize != 0u && address >= item.address &&
                   uint64_t(address) < reservationEnd && rangeEnd <= reservationEnd;
        });
    if (allocation == g_virtualAllocations.end()) {
        failWith(kNtStatusUnsuccessful);
        return;
    }

    const uint32_t allocationAddress = allocation->address;
    const uint32_t allocationSize = allocation->size;
    uint32_t resultSize = requestedSize;
    if (freeType == 0x00004000u) { // MEM_DECOMMIT
        const uint64_t allocationEnd = static_cast<uint64_t>(allocationAddress) + allocationSize;
        const uint64_t requestedEnd = static_cast<uint64_t>(address) + requestedSize;
        if (requestedSize == 0 || requestedEnd > allocationEnd) {
            failWith(kNtStatusInvalidParameter);
            return;
        }
        const uint64_t alignedStart=uint64_t(address)&~uint64_t{0xFFFu};
        const uint64_t alignedEnd=(requestedEnd+0xFFFu)&~uint64_t{0xFFFu};
        if(alignedStart<allocationAddress || alignedEnd>allocationEnd) {
            failWith(kNtStatusInvalidParameter);
            return;
        }
        resultSize=static_cast<uint32_t>(alignedEnd-alignedStart);
        std::memset(base+alignedStart,0u,resultSize);
    } else if (freeType == 0x00008000u) { // MEM_RELEASE
        if (address != allocationAddress) {
            char event[200];
            std::snprintf(event,sizeof(event),
                "NtFree MEM_RELEASE rejected interior address=%08X reservation=%08X size=%08X (release must start at reservation base)",
                address,allocationAddress,allocationSize);
            recordRuntimeTrace(event);
            failWith(kNtStatusInvalidParameter);
            return;
        }
        g_virtualAllocations.erase(allocation);
        if (static_cast<uint64_t>(allocationAddress) + allocationSize == g_nextVirtualAllocation) {
            g_nextVirtualAllocation = allocationAddress;
        }
        std::memset(base + allocationAddress, 0, allocationSize);
        resultSize = 0;
    } else {
        failWith(kNtStatusInvalidParameter);
        return;
    }

    if (freeType == 0x00004000u) {
        const uint64_t decommitStart = uint64_t(address)&~uint64_t{0xFFFu};
        const uint64_t decommitEnd = decommitStart+resultSize;
        std::vector<GuestCommit> remaining;
        for (const auto &commit : g_virtualCommits) {
            const uint64_t commitStart = commit.address;
            const uint64_t commitEnd = static_cast<uint64_t>(commit.address) + commit.size;
            if (commitEnd <= decommitStart || commitStart >= decommitEnd) {
                remaining.push_back(commit);
                continue;
            }
            if (commitStart < decommitStart) {
                remaining.push_back({commit.address, static_cast<uint32_t>(decommitStart - commitStart), commit.protection});
            }
            if (commitEnd > decommitEnd) {
                remaining.push_back({static_cast<uint32_t>(decommitEnd), static_cast<uint32_t>(commitEnd - decommitEnd), commit.protection});
            }
        }
        g_virtualCommits.swap(remaining);
    } else if (freeType == 0x00008000u) {
        g_virtualCommits.erase(
            std::remove_if(g_virtualCommits.begin(), g_virtualCommits.end(),
                           [allocationAddress, allocationSize](const auto &commit) {
                               const uint64_t end = static_cast<uint64_t>(allocationAddress) + allocationSize;
                               return commit.address >= allocationAddress &&
                                      static_cast<uint64_t>(commit.address) + commit.size <= end;
                           }),
            g_virtualCommits.end());
    }

    PPC_STORE_U32(basePointer, address);
    PPC_STORE_U32(sizePointer, resultSize);
    failWith(kNtStatusSuccess);
}

[[noreturn]] void xowue_HalReturnToFirmware(PPCContext &context, uint8_t *) {
    throw GuestFirmwareReturn(context);
}

[[noreturn]] void xowue_untranslated_tail(uint32_t guest_address) {
    char message[160];
    std::snprintf(message, sizeof(message),
                  "instrução PPC não decodificada no trecho final .text: 0x%08X", guest_address);
    throw std::runtime_error(message);
}

