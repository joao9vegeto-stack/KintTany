#include "xowue_engine.h"

#include "image.h"
#include "ppc_recomp_shared.h"
#include "xex.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cstdarg>
#include <condition_variable>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <limits>
#include <memory>
#include <mutex>
#include <optional>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <utility>
#include <vector>

#include <sys/mman.h>
#include <unistd.h>

extern "C" void xowue_vulkan_backend_guest_swap(uint32_t frontbuffer,
                                                 uint32_t width,
                                                 uint32_t height)
    __attribute__((weak));

namespace {
constexpr size_t kGuestAddressSpaceSize = static_cast<size_t>(PPC_MEMORY_SIZE);
constexpr uint32_t kInitialStackPointer = 0x7FFF0000u;
constexpr uint32_t kFirstVirtualAllocation = 0x10000000u;
constexpr uint32_t kLastVirtualAllocation = 0x70000000u;
constexpr uint32_t kNtStatusSuccess = 0x00000000u;
constexpr uint32_t kNtStatusInvalidParameter = 0xC000000Du;
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
constexpr uint32_t kGuestThreadMetadataStride = 0x1000u;
constexpr uint32_t kXenosRingBufferRegister = 0x4800u;
constexpr uint32_t kXenosPm4SwapOpcode = 0x64u;
constexpr uint32_t kXenosPm4IndirectBufferOpcode = 0x3Fu;
constexpr uint32_t kXenosPm4DrawIndexOpcode = 0x22u;
constexpr uint32_t kXenosPm4DrawIndex2Opcode = 0x36u;
constexpr uint32_t kXenosPm4DrawIndexBinOpcode = 0x34u;
constexpr uint32_t kXenosPm4DrawIndex2BinOpcode = 0x35u;
constexpr uint32_t kXenosPm4EventWriteOpcode = 0x46u;

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
    enum class Kind { Event, Thread };
    Kind kind = Kind::Event;
    uint32_t handle = 0;
    uint32_t objectAddress = 0;
    bool manualReset;
    bool signaled;
    std::mutex mutex;
    std::condition_variable changed;
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
    std::condition_variable stateChanged;
    std::condition_variable exitChanged;
    std::shared_ptr<GuestWaitable> completion;
    std::thread hostThread;
};

struct XenosFrontendState {
    uint32_t ringBufferAddress = 0;
    uint32_t ringBufferSize = 0;
    uint32_t readPointerWritebackAddress = 0;
    uint32_t readPointerBlockSizeLog2 = 0;
    uint32_t systemCommandBufferGpuAddress = 0;
    uint32_t graphicsInterruptCallback = 0;
    uint32_t graphicsInterruptContext = 0;
    uint32_t latestFrontbufferAddress = 0;
    uint32_t latestWidth = 0;
    uint32_t latestHeight = 0;
    uint64_t packets = 0;
    uint64_t draws = 0;
    uint64_t indirectBuffers = 0;
    uint64_t swaps = 0;
    uint64_t malformedPackets = 0;
    uint64_t lastSwapTimestampNs = 0;
    bool enginesInitialized = false;
};

uint32_t g_nextVirtualAllocation = kFirstVirtualAllocation;
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
std::mutex g_tlsMutex;
std::mutex g_virtualMemoryMutex;
std::mutex g_guestObjectMutex;
std::mutex g_guestThreadMutex;
std::mutex g_guestStackMutex;
std::mutex g_criticalSectionMapMutex;
std::mutex g_waitSetMutex;
std::mutex g_xenosMutex;
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

void recordRuntimeTrace(const std::string &event) {
    constexpr size_t kMaxTraceEvents = 128;
    std::lock_guard<std::mutex> lock(g_runtimeTraceMutex);
    const std::string tagged = "thread=" + std::to_string(g_currentGuestThreadId) + " " + event;
    if (g_runtimeTrace.size() == kMaxTraceEvents) g_runtimeTrace.erase(g_runtimeTrace.begin());
    g_runtimeTrace.push_back(tagged);
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
    char value[320];
    std::snprintf(value, sizeof(value), "%08X size=0x%08X readback=0x%08X swaps=%llu packets=%llu draws=%llu indirect=%llu malformed=%llu last=%ux%u frontbuffer=0x%08X",
                  graphics.ringBufferAddress, graphics.ringBufferSize,
                  graphics.readPointerWritebackAddress,
                  static_cast<unsigned long long>(graphics.swaps),
                  static_cast<unsigned long long>(graphics.packets),
                  static_cast<unsigned long long>(graphics.draws),
                  static_cast<unsigned long long>(graphics.indirectBuffers),
                  static_cast<unsigned long long>(graphics.malformedPackets),
                  graphics.latestWidth, graphics.latestHeight,
                  graphics.latestFrontbufferAddress);
    result += value;
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
uint32_t g_activeImageBase = 0;

struct GuestThreadStopRequested final {};
struct GuestThreadExit final {
    explicit GuestThreadExit(uint32_t code) : exitCode(code) {}
    uint32_t exitCode;
};

using GuestTimeout = std::optional<std::chrono::nanoseconds>;

PPCFunc *findGuestFunction(uint32_t address) {
    for (const PPCFuncMapping *mapping = PPCFuncMappings; mapping->host; ++mapping) {
        if (mapping->guest == address) return mapping->host;
    }
    return nullptr;
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
                         const GuestTimeout &timeout) {
    if (!waitable) return kNtStatusInvalidHandle;
    std::unique_lock<std::mutex> lock(waitable->mutex);
    const auto ready = [&] {
        return waitable->signaled || g_schedulerStopRequested.load();
    };
    bool completed = true;
    if (timeout) completed = waitable->changed.wait_for(lock, *timeout, ready);
    else waitable->changed.wait(lock, ready);
    if (g_schedulerStopRequested.load() && g_currentGuestThreadId != 1u) {
        throw GuestThreadStopRequested{};
    }
    if (!completed || !waitable->signaled) return kNtStatusTimeout;
    if (!waitable->manualReset) waitable->signaled = false;
    return kNtStatusSuccess;
}

uint32_t waitGuestObjects(const std::vector<std::shared_ptr<GuestWaitable>> &waitables,
                          uint32_t waitType, const GuestTimeout &timeout) {
    if (waitables.empty() || waitables.size() > 64u || waitType > 1u) {
        return kNtStatusInvalidParameter;
    }
    const auto readyIndex = [&]() -> int32_t {
        int32_t firstReady = -1;
        bool allReady = true;
        for (size_t index = 0; index < waitables.size(); ++index) {
            if (!waitables[index]) return -2;
            std::lock_guard<std::mutex> objectLock(waitables[index]->mutex);
            const bool signaled = waitables[index]->signaled;
            if (!signaled) allReady = false;
            else if (firstReady < 0) firstReady = static_cast<int32_t>(index);
        }
        if (waitType == 0u) return allReady ? 0 : -1; // WaitAll.
        return firstReady; // WaitAny.
    };

    const auto deadline = timeout ? std::optional<std::chrono::steady_clock::time_point>(
        std::chrono::steady_clock::now() + *timeout) : std::nullopt;
    for (;;) {
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
                        if (!waitable->manualReset) waitable->signaled = false;
                    }
                    return kNtStatusWait0;
                }
                auto &waitable = waitables[static_cast<size_t>(selected)];
                std::lock_guard<std::mutex> objectLock(waitable->mutex);
                if (!waitable->manualReset) waitable->signaled = false;
                return kNtStatusWait0 + static_cast<uint32_t>(selected);
            }
            if (deadline) {
                if (std::chrono::steady_clock::now() >= *deadline) return kNtStatusTimeout;
                g_waitSetChanged.wait_until(waitLock, *deadline, [&] {
                    return g_schedulerStopRequested.load() || readyIndex() >= 0;
                });
            } else {
                g_waitSetChanged.wait(waitLock, [&] {
                    return g_schedulerStopRequested.load() || readyIndex() >= 0;
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
    }
    waitable->changed.notify_all();
    g_waitSetChanged.notify_all();
}

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
    uint64_t candidate = (static_cast<uint64_t>(g_nextVirtualAllocation) + alignment - 1u) &
                         ~static_cast<uint64_t>(alignment - 1u);
    while (candidate + size <= kLastVirtualAllocation) {
        bool moved = false;
        for (const auto &allocation : g_virtualAllocations) {
            const uint64_t allocationEnd = static_cast<uint64_t>(allocation.address) + allocation.size;
            if (candidate < allocationEnd && candidate + size > allocation.address) {
                candidate = (allocationEnd + alignment - 1u) &
                            ~static_cast<uint64_t>(alignment - 1u);
                moved = true;
                break;
            }
        }
        if (moved) continue;
        if (candidate < kFirstVirtualAllocation || candidate + size > kLastVirtualAllocation) return 0u;
        const uint32_t address = static_cast<uint32_t>(candidate);
        g_virtualAllocations.push_back({address, size, protection});
        g_virtualCommits.push_back({address, size, protection});
        g_nextVirtualAllocation = static_cast<uint32_t>(candidate + size);
        std::memset(base + address, 0, size);
        return address;
    }
    return 0u;
}

bool releaseGuestPhysicalRange(uint32_t address) {
    std::lock_guard<std::mutex> lock(g_virtualMemoryMutex);
    const auto allocation = std::find_if(g_virtualAllocations.begin(), g_virtualAllocations.end(),
        [address](const auto &item) { return item.address == address; });
    if (allocation == g_virtualAllocations.end()) return false;
    const uint32_t size = allocation->size;
    g_virtualAllocations.erase(allocation);
    g_virtualCommits.erase(std::remove_if(g_virtualCommits.begin(), g_virtualCommits.end(),
        [address, size](const auto &item) { return item.address == address && item.size == size; }),
        g_virtualCommits.end());
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

struct GuestThreadBinding final {
    GuestThread *previousThread = nullptr;
    uint32_t previousId = 1u;
    explicit GuestThreadBinding(GuestThread *thread)
        : previousThread(g_currentGuestThread), previousId(g_currentGuestThreadId) {
        g_currentGuestThread = thread;
        g_currentGuestThreadId = thread ? thread->id : 1u;
    }
    ~GuestThreadBinding() {
        g_currentGuestThread = previousThread;
        g_currentGuestThreadId = previousId;
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
    for (const PPCFuncMapping *mapping = PPCFuncMappings; mapping->host; ++mapping) {
        if (mapping->guest < PPC_CODE_BASE) continue;
        const uint64_t codeOffset = mapping->guest - PPC_CODE_BASE;
        if (codeOffset >= PPC_CODE_SIZE) continue;
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
    const std::string trace = runtimeTraceText();
    writeMessage(output, capacity, "Falha: %s%s", error.what(), trace.c_str());
    return 1;
}
} // namespace

void xowue_thread_checkpoint() { checkpointGuestThread(); }

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

extern "C" int xowue_boot_xex(const char *path, char *output, size_t output_capacity) {
    try {
        if (g_runtimeSessionPoisoned.load()) {
            throw std::runtime_error("uma thread PPC não encerrou após o limite de parada; feche e reabra o app para iniciar outra sessão");
        }
        {
            std::lock_guard<std::mutex> traceLock(g_runtimeTraceMutex);
            g_runtimeTrace.clear();
        }
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
        g_mainThreadObjectAddress = kFirstGuestThreadObjectAddress - kGuestThreadMetadataStride;
        g_mainPcrAddress = kFirstGuestPcrAddress - kGuestThreadMetadataStride;
        g_mainTlsAddress = kMainGuestTlsAddress;
        {
            std::lock_guard<std::mutex> graphicsLock(g_xenosMutex);
            g_xenosFrontend = {};
        }
        const Image image = parseImage(path);
        g_activeImageBase = static_cast<uint32_t>(image.base);
        char imageEvent[160];
        std::snprintf(imageEvent, sizeof(imageEvent),
                      "XEX2 carregado base=0x%08zX entry=0x%08zX sections=%zu",
                      image.base, image.entry_point, image.sections.size());
        recordRuntimeTrace(imageEvent);
        auto memory = std::make_shared<GuestMemory>();
        g_activeGuestMemory = memory;
        GuestSchedulerSessionGuard schedulerSession;
        g_nextVirtualAllocation = kFirstVirtualAllocation;
        g_nextGuestHandle = 0x100u;
        g_nextGuestEventObjectAddress = kFirstGuestEventObjectAddress;
        {
            std::lock_guard<std::mutex> stateLock(g_virtualMemoryMutex);
            g_virtualAllocations.clear();
            g_virtualCommits.clear();
        }
        {
            std::lock_guard<std::mutex> objectLock(g_guestObjectMutex);
            g_guestWaitables.clear();
            g_guestObjectReferences.clear();
            g_guestReferencedWaitables.clear();
            g_guestPointerWaitables.clear();
        }
        {
            std::lock_guard<std::mutex> threadLock(g_guestThreadMutex);
            g_guestThreadsByHandle.clear();
            g_guestThreadsByObject.clear();
            g_guestThreads.clear();
        }
        copyImage(image, *memory);
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
        const std::string trace = runtimeTraceText();
        writeMessage(output, output_capacity,
                     "Entry point retornou. Funções AOT registradas: %zu. O boot não foi concluído.%s",
                     installed, trace.c_str());
        return 3;
    } catch (const GuestFirmwareReturn &request) {
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

/* The generated import adapters route here until a kernel/XAM implementation exists. */
[[noreturn]] void xowue_unsupported_import(const char *name, const PPCContext &context) {
    char message[256];
    std::snprintf(message, sizeof(message),
                  "Xbox kernel/XAM import ainda não implementado: %s (LR=0x%08X; r3-r10=%08X,%08X,%08X,%08X,%08X,%08X,%08X,%08X)",
                  name ? name : "?", static_cast<uint32_t>(context.lr),
                  context.r3.u32, context.r4.u32, context.r5.u32, context.r6.u32,
                  context.r7.u32, context.r8.u32, context.r9.u32, context.r10.u32);
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
};

PM4ParseSummary parseGuestPM4(uint8_t *base, uint32_t address, uint32_t wordCount) {
    PM4ParseSummary summary;
    if (!base || !validGuestRange(address, static_cast<uint64_t>(wordCount) * 4u)) {
        summary.malformed = 1u;
        return summary;
    }
    uint32_t offset = 0u;
    while (offset < wordCount) {
        const uint32_t header = PPC_LOAD_U32(address + offset * 4u);
        const uint32_t type = header >> 30u;
        if (type == 2u) {
            ++summary.packets;
            ++offset;
            continue;
        }
        uint32_t payloadCount = 0u;
        if (type == 0u || type == 3u) {
            payloadCount = ((header >> 16u) & 0x3FFFu) + 1u;
        } else if (type == 1u) {
            payloadCount = 2u;
        } else {
            ++summary.malformed;
            break;
        }
        const uint64_t packetWords = static_cast<uint64_t>(payloadCount) + 1u;
        if (packetWords > wordCount - offset) {
            ++summary.malformed;
            break;
        }
        ++summary.packets;
        if (type == 3u) {
            const uint32_t opcode = (header >> 8u) & 0x7Fu;
            if (opcode == kXenosPm4DrawIndexOpcode || opcode == kXenosPm4DrawIndex2Opcode ||
                opcode == kXenosPm4DrawIndexBinOpcode || opcode == kXenosPm4DrawIndex2BinOpcode) {
                ++summary.draws;
            } else if (opcode == kXenosPm4IndirectBufferOpcode) {
                ++summary.indirectBuffers;
            } else if (opcode == kXenosPm4SwapOpcode) {
                ++summary.swaps;
            }
        }
        offset += static_cast<uint32_t>(packetWords);
    }
    return summary;
}

void xowue_VdInitializeEngines(PPCContext &context) {
    std::lock_guard<std::mutex> lock(g_xenosMutex);
    g_xenosFrontend.enginesInitialized = true;
    context.r3.u32 = 1u;
    recordRuntimeTrace("VdInitializeEngines accepted; Xenos command frontend active, shader translation pending");
}

void xowue_VdShutdownEngines() {
    std::lock_guard<std::mutex> lock(g_xenosMutex);
    g_xenosFrontend.enginesInitialized = false;
    recordRuntimeTrace("VdShutdownEngines completed");
}

void xowue_VdInitializeRingBuffer(PPCContext &context, uint8_t *base) {
    const uint32_t address = context.r3.u32;
    const uint32_t log2 = context.r4.u32;
    if (!base || log2 > 26u) {
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
    {
        std::lock_guard<std::mutex> lock(g_xenosMutex);
        g_xenosFrontend.ringBufferAddress = address;
        g_xenosFrontend.ringBufferSize = size;
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
    const uint32_t frontbufferAddress = PPC_LOAD_U32(frontbufferPointer);
    const uint32_t textureFormat = PPC_LOAD_U32(textureFormatPointer);
    const uint32_t colorSpace = PPC_LOAD_U32(colorSpacePointer);
    const uint32_t width = PPC_LOAD_U32(widthPointer);
    const uint32_t height = PPC_LOAD_U32(heightPointer);
    for (uint32_t i = 0; i < 64u; ++i) PPC_STORE_U32(commandBuffer + i * 4u, 0x80000000u);
    PPC_STORE_U32(commandBuffer + 0u, (5u << 16u) | 0x4800u); // Type 0, six fetch dwords.
    for (uint32_t i = 0; i < 6u; ++i) {
        PPC_STORE_U32(commandBuffer + (i + 1u) * 4u, PPC_LOAD_U32(fetch + i * 4u));
    }
    PPC_STORE_U32(commandBuffer + 7u * 4u,
                  (3u << 30u) | (3u << 16u) | (kXenosPm4SwapOpcode << 8u));
    PPC_STORE_U32(commandBuffer + 8u * 4u, 0x53574150u); // 'SWAP'.
    PPC_STORE_U32(commandBuffer + 9u * 4u, frontbufferAddress);
    PPC_STORE_U32(commandBuffer + 10u * 4u, width);
    PPC_STORE_U32(commandBuffer + 11u * 4u, height);

    const PM4ParseSummary parsed = parseGuestPM4(base, commandBuffer, 64u);
    {
        std::lock_guard<std::mutex> lock(g_xenosMutex);
        ++g_xenosFrontend.swaps;
        g_xenosFrontend.packets += parsed.packets;
        g_xenosFrontend.draws += parsed.draws;
        g_xenosFrontend.indirectBuffers += parsed.indirectBuffers;
        g_xenosFrontend.malformedPackets += parsed.malformed;
        g_xenosFrontend.latestFrontbufferAddress = frontbufferAddress;
        g_xenosFrontend.latestWidth = width;
        g_xenosFrontend.latestHeight = height;
        g_xenosFrontend.lastSwapTimestampNs = static_cast<uint64_t>(
            std::chrono::duration_cast<std::chrono::nanoseconds>(
                std::chrono::steady_clock::now().time_since_epoch()).count());
    }
    char event[256];
    std::snprintf(event, sizeof(event),
                  "VdSwap emitted PM4 swap width=%u height=%u frontbuffer=0x%08X format=0x%08X colorspace=%u packets=%llu draws=%llu; Xenos shader/tiling translation not yet reached",
                  width, height, frontbufferAddress, textureFormat, colorSpace,
                  static_cast<unsigned long long>(parsed.packets),
                  static_cast<unsigned long long>(parsed.draws));
    recordRuntimeTrace(event);
    if (xowue_vulkan_backend_guest_swap) {
        xowue_vulkan_backend_guest_swap(frontbufferAddress, width, height);
    }
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

void xowue_VdQueryVideoMode(PPCContext &context, uint8_t *base) {
    const uint32_t address = context.r3.u32;
    if (!base || address == 0u || !validGuestRange(address, 48u)) {
        context.r3.u32 = kNtStatusInvalidParameter;
        return;
    }
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
    context.r3.u32 = kNtStatusSuccess;
    recordRuntimeTrace("VdQueryVideoMode -> 1280x720 progressive widescreen 60Hz");
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

void xowue_NtSetEvent(PPCContext &context, uint8_t *base) {
    const uint32_t handle = context.r3.u32;
    const uint32_t previousStatePointer = context.r4.u32;
    auto waitable = lookupGuestWaitable(handle);
    if (!waitable || waitable->kind != GuestWaitable::Kind::Event) {
        context.r3.u32 = kNtStatusInvalidHandle;
        return;
    }
    bool previous = false;
    {
        std::lock_guard<std::mutex> lock(waitable->mutex);
        previous = waitable->signaled;
        waitable->signaled = true;
    }
    if (previousStatePointer != 0u) {
        if (!base || previousStatePointer > kGuestAddressSpaceSize - 4u) {
            context.r3.u32 = kNtStatusInvalidParameter;
            return;
        }
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
    bool previous = false;
    {
        std::lock_guard<std::mutex> lock(waitable->mutex);
        previous = waitable->signaled;
        waitable->signaled = true;
    }
    if (previousStatePointer != 0u) {
        if (!base || previousStatePointer > kGuestAddressSpaceSize - 4u) {
            context.r3.u32 = kNtStatusInvalidParameter;
            return;
        }
        PPC_STORE_U32(previousStatePointer, previous ? 1u : 0u);
    }
    waitable->changed.notify_all();
    g_waitSetChanged.notify_all();
    recordRuntimeTrace("NtPulseEvent delivered as a signal; reset when an auto-reset waiter consumes it");
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
}

void xowue_NtWaitForSingleObjectEx(PPCContext &context, uint8_t *base) {
    GuestTimeout timeout;
    if (!readGuestTimeout(base, context.r6.u32, timeout)) {
        context.r3.u32 = kNtStatusInvalidParameter;
        return;
    }
    context.r3.u32 = waitGuestObject(lookupGuestWaitable(context.r3.u32), timeout);
}

void xowue_KeWaitForSingleObject(PPCContext &context, uint8_t *base) {
    GuestTimeout timeout;
    if (!readGuestTimeout(base, context.r7.u32, timeout)) {
        context.r3.u32 = kNtStatusInvalidParameter;
        return;
    }
    context.r3.u32 = waitGuestObject(ensurePointerWaitable(context.r3.u32, base), timeout);
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
    context.r3.u32 = waitGuestObjects(waitables, waitType, timeout);
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
    context.r3.u32 = waitGuestObjects(waitables, waitType, timeout);
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
    if ((knownEventType && isThread) || (knownThreadType && !isThread) ||
        knownSemaphoreType) {
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
                  handle, objectType, objectAddress, isThread ? "Thread" : "Event",
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
    const uint32_t address = context.r3.u32;
    const uint32_t information = context.r4.u32;
    constexpr uint32_t kInformationSize = 7 * sizeof(uint32_t);
    constexpr uint32_t kMemCommit = 0x00001000u;
    constexpr uint32_t kMemReserve = 0x00002000u;
    constexpr uint32_t kMemPrivate = 0x00020000u;
    if (!base || information > kGuestAddressSpaceSize - kInformationSize) {
        context.r3.u32 = kNtStatusInvalidParameter;
        return;
    }
    const auto reservation = std::find_if(
        g_virtualAllocations.begin(), g_virtualAllocations.end(),
        [address](const auto &item) {
            return address >= item.address &&
                   static_cast<uint64_t>(address) < static_cast<uint64_t>(item.address) + item.size;
        });
    if (reservation == g_virtualAllocations.end()) {
        context.r3.u32 = kNtStatusInvalidParameter;
        return;
    }
    const auto commit = std::find_if(
        g_virtualCommits.begin(), g_virtualCommits.end(),
        [address](const auto &item) {
            return address >= item.address &&
                   static_cast<uint64_t>(address) < static_cast<uint64_t>(item.address) + item.size;
        });

    uint32_t regionBase = reservation->address;
    uint32_t regionSize = reservation->size;
    uint32_t state = kMemReserve;
    uint32_t protection = 0;
    if (commit != g_virtualCommits.end()) {
        regionBase = commit->address;
        regionSize = commit->size;
        state = kMemCommit;
        protection = commit->protection;
    }

    PPC_STORE_U32(information + 0x00, regionBase);
    PPC_STORE_U32(information + 0x04, reservation->address);
    PPC_STORE_U32(information + 0x08, reservation->protection);
    PPC_STORE_U32(information + 0x0C, regionSize);
    PPC_STORE_U32(information + 0x10, state);
    PPC_STORE_U32(information + 0x14, protection);
    PPC_STORE_U32(information + 0x18, kMemPrivate);
    context.r3.u32 = kNtStatusSuccess;
    char event[128];
    std::snprintf(event, sizeof(event), "NtQueryVirtualMemory address=0x%08X state=0x%08X region=0x%08X+0x%08X",
                  address, state, regionBase, regionSize);
    recordRuntimeTrace(event);
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
                      "NtAllocate basePtr=0x%08X sizePtr=0x%08X requested=0x%08X size=0x%08X flags=0x%08X protect=0x%08X debug=0x%08X status=0x%08X",
                      basePointer, sizePointer, requestedBase, requestedSize, allocationType,
                      protection, debugMemory, status);
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

    const auto allocation = std::find_if(
        g_virtualAllocations.begin(), g_virtualAllocations.end(),
        [address, requestedSize](const auto &item) {
            const uint64_t rangeEnd = static_cast<uint64_t>(address) + requestedSize;
            const uint64_t reservationEnd = static_cast<uint64_t>(item.address) + item.size;
            return address >= item.address && rangeEnd <= reservationEnd;
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
        const uint64_t adjusted =
            (static_cast<uint64_t>(requestedSize) + 0xFFFu) & ~uint64_t{0xFFFu};
        resultSize = static_cast<uint32_t>(std::min<uint64_t>(adjusted, allocationSize));
        std::memset(base + address, 0, resultSize);
    } else if (freeType == 0x00008000u) { // MEM_RELEASE
        if (address != allocationAddress) {
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
        const uint64_t decommitStart = address;
        const uint64_t decommitEnd = static_cast<uint64_t>(address) + resultSize;
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

