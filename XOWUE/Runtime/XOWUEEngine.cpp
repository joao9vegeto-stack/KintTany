#include "xowue_engine.h"

#include "image.h"
#include "ppc_recomp_shared.h"
#include "xex.h"

#include <algorithm>
#include <array>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include <sys/mman.h>
#include <unistd.h>

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
struct GuestEvent {
    uint32_t handle;
    bool manualReset;
    bool signaled;
};
uint32_t g_nextVirtualAllocation = kFirstVirtualAllocation;
uint32_t g_nextGuestHandle = 0x100u;
std::vector<GuestReservation> g_virtualAllocations;
std::vector<GuestCommit> g_virtualCommits;
std::vector<GuestEvent> g_guestEvents;
std::vector<std::string> g_runtimeTrace;
uint32_t g_xexSystemFlags = 0;
constexpr size_t kTlsSlotCount = 64;
constexpr uint32_t kTlsOutOfIndexes = 0xFFFFFFFFu;
std::array<bool, kTlsSlotCount> g_tlsAllocated{};
std::array<uint32_t, kTlsSlotCount> g_tlsValues{};
size_t g_criticalSectionInitCount = 0;

void recordRuntimeTrace(const std::string &event) {
    constexpr size_t kMaxTraceEvents = 128;
    if (g_runtimeTrace.size() == kMaxTraceEvents) g_runtimeTrace.erase(g_runtimeTrace.begin());
    g_runtimeTrace.push_back(event);
}

std::string runtimeTraceText() {
    std::string result = "\n\nEVENTOS PPC RECENTES:";
    result += "\n- RtlInitializeCriticalSection calls=" + std::to_string(g_criticalSectionInitCount);
    for (const auto &event : g_runtimeTrace) {
        result += "\n- ";
        result += event;
    }
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
    if (const void *flags = getOptHeaderPtr(file.data(), XEX_HEADER_SYSTEM_FLAGS)) {
        g_xexSystemFlags = static_cast<const be<uint32_t> *>(flags)->get();
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

extern "C" int xowue_boot_xex(const char *path, char *output, size_t output_capacity) {
    try {
        g_runtimeTrace.clear();
        g_tlsAllocated.fill(false);
        g_tlsValues.fill(0);
        g_criticalSectionInitCount = 0;
        const Image image = parseImage(path);
        char imageEvent[160];
        std::snprintf(imageEvent, sizeof(imageEvent),
                      "XEX2 carregado base=0x%08zX entry=0x%08zX sections=%zu",
                      image.base, image.entry_point, image.sections.size());
        recordRuntimeTrace(imageEvent);
        GuestMemory memory;
        g_nextVirtualAllocation = kFirstVirtualAllocation;
        g_nextGuestHandle = 0x100u;
        g_virtualAllocations.clear();
        g_virtualCommits.clear();
        g_guestEvents.clear();
        copyImage(image, memory);
        const size_t installed = installDispatchTable(memory);
        recordRuntimeTrace("Guest memory mapeada; AOT dispatch entries=" + std::to_string(installed));

        const PPCFuncMapping *entry = nullptr;
        for (const PPCFuncMapping *mapping = PPCFuncMappings; mapping->host; ++mapping) {
            if (mapping->guest == image.entry_point) {
                entry = mapping;
                break;
            }
        }
        if (!entry) throw std::runtime_error("XEX entry point is absent from the AOT function map");

        PPCContext context{};
        context.r1.u32 = kInitialStackPointer;
        context.r2.u32 = static_cast<uint32_t>(image.base);
        context.r13.u32 = static_cast<uint32_t>(image.base);
        context.lr = 0;
        char entryEvent[80];
        std::snprintf(entryEvent, sizeof(entryEvent), "Chamando PPC entry point 0x%08zX", image.entry_point);
        recordRuntimeTrace(entryEvent);
        entry->host(context, memory.base);
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
    std::memset(base + address, 0, kXboxCriticalSectionSize);
    base[address] = 1;
    base[address + 1] = static_cast<uint8_t>(packedSpinCount);
    PPC_STORE_U32(address + 0x10, 0xFFFFFFFFu);
    PPC_STORE_U32(address + 0x14, 0);
    PPC_STORE_U32(address + 0x18, 0);
    context.r3.u32 = kNtStatusSuccess;
    ++g_criticalSectionInitCount;
    if (g_criticalSectionInitCount <= 2) {
        recordRuntimeTrace("RtlInitializeCriticalSectionAndSpinCount inicializada");
    }
}

void xowue_RtlEnterCriticalSection(PPCContext &context, uint8_t *base) {
    const uint32_t address = context.r3.u32;
    constexpr uint32_t kXboxCriticalSectionSize = 28;
    constexpr uint32_t kBootThreadId = 1;
    if (!base || address > kGuestAddressSpaceSize - kXboxCriticalSectionSize) {
        throw std::runtime_error("RtlEnterCriticalSection recebeu endereço inválido");
    }
    const uint32_t owner = PPC_LOAD_U32(address + 0x18);
    int32_t lockCount = static_cast<int32_t>(PPC_LOAD_U32(address + 0x10));
    uint32_t recursion = PPC_LOAD_U32(address + 0x14);
    if (owner == kBootThreadId) {
        ++lockCount;
        ++recursion;
    } else {
        // XOWUE currently runs one PPC thread. The Xbox waiter/scheduler path
        // is not present yet, so an unowned lock is acquired by that boot thread.
        if (lockCount < -1) throw std::runtime_error("critical section lock_count inválido");
        ++lockCount;
        recursion = 1;
        PPC_STORE_U32(address + 0x18, kBootThreadId);
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
    constexpr uint32_t kBootThreadId = 1;
    if (!base || address > kGuestAddressSpaceSize - kXboxCriticalSectionSize) {
        throw std::runtime_error("RtlTryEnterCriticalSection recebeu endereço inválido");
    }
    const uint32_t owner = PPC_LOAD_U32(address + 0x18);
    int32_t lockCount = static_cast<int32_t>(PPC_LOAD_U32(address + 0x10));
    uint32_t recursion = PPC_LOAD_U32(address + 0x14);
    if (owner != 0 && owner != kBootThreadId) {
        context.r3.u32 = 0;
        recordRuntimeTrace("RtlTryEnterCriticalSection -> busy");
        return;
    }
    ++lockCount;
    ++recursion;
    PPC_STORE_U32(address + 0x10, static_cast<uint32_t>(lockCount));
    PPC_STORE_U32(address + 0x14, recursion);
    PPC_STORE_U32(address + 0x18, kBootThreadId);
    context.r3.u32 = 1;
    recordRuntimeTrace("RtlTryEnterCriticalSection -> acquired");
}

void xowue_RtlLeaveCriticalSection(PPCContext &context, uint8_t *base) {
    const uint32_t address = context.r3.u32;
    constexpr uint32_t kXboxCriticalSectionSize = 28;
    constexpr uint32_t kBootThreadId = 1;
    if (!base || address > kGuestAddressSpaceSize - kXboxCriticalSectionSize) {
        throw std::runtime_error("RtlLeaveCriticalSection recebeu endereço inválido");
    }
    const uint32_t owner = PPC_LOAD_U32(address + 0x18);
    int32_t lockCount = static_cast<int32_t>(PPC_LOAD_U32(address + 0x10));
    uint32_t recursion = PPC_LOAD_U32(address + 0x14);
    if (owner != kBootThreadId || recursion == 0) {
        throw std::runtime_error("RtlLeaveCriticalSection sem proprietário na thread PPC ativa");
    }
    --recursion;
    --lockCount;
    PPC_STORE_U32(address + 0x10, static_cast<uint32_t>(lockCount));
    PPC_STORE_U32(address + 0x14, recursion);
    if (recursion == 0) PPC_STORE_U32(address + 0x18, 0);
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
    if (!base || handlePointer == 0 ||
        handlePointer > kGuestAddressSpaceSize - sizeof(uint32_t) || eventType > 1u) {
        context.r3.u32 = kNtStatusInvalidParameter;
        recordRuntimeTrace("NtCreateEvent invalid parameters");
        return;
    }
    if (g_nextGuestHandle == 0xFFFFFFFFu) {
        context.r3.u32 = kNtStatusNoMemory;
        recordRuntimeTrace("NtCreateEvent handle space exhausted");
        return;
    }
    const uint32_t handle = g_nextGuestHandle++;
    g_guestEvents.push_back({handle, eventType == 0u, initialState != 0u});
    PPC_STORE_U32(handlePointer, handle);
    context.r3.u32 = kNtStatusSuccess;
    char event[144];
    std::snprintf(event, sizeof(event),
                  "NtCreateEvent handle=0x%08X type=%u manualReset=%u initial=%u named=%u",
                  handle, eventType, eventType == 0u ? 1u : 0u, initialState != 0u ? 1u : 0u,
                  objectAttributes != 0 ? 1u : 0u);
    recordRuntimeTrace(event);
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
    for (size_t index = 0; index < kTlsSlotCount; ++index) {
        if (!g_tlsAllocated[index]) {
            g_tlsAllocated[index] = true;
            g_tlsValues[index] = 0;
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
    const bool valid = index < kTlsSlotCount && g_tlsAllocated[index];
    if (valid) {
        g_tlsAllocated[index] = false;
        g_tlsValues[index] = 0;
    }
    context.r3.u32 = valid ? 1u : 0u;
    recordRuntimeTrace("KeTlsFree slot=" + std::to_string(index) + " result=" + (valid ? "1" : "0"));
}

void xowue_KeTlsGetValue(PPCContext &context) {
    const uint32_t index = context.r3.u32;
    context.r3.u32 = index < kTlsSlotCount ? g_tlsValues[index] : 0;
}

void xowue_KeTlsSetValue(PPCContext &context) {
    const uint32_t index = context.r3.u32;
    const uint32_t value = context.r4.u32;
    if (index < kTlsSlotCount) {
        g_tlsValues[index] = value;
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
