#include "xowue_engine.h"

#include "image.h"
#include "ppc_recomp_shared.h"

#include <algorithm>
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
uint32_t g_nextVirtualAllocation = kFirstVirtualAllocation;
std::vector<std::pair<uint32_t, uint32_t>> g_virtualAllocations;

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
    explicit GuestFirmwareReturn(uint32_t value)
        : std::runtime_error("guest requested a firmware return"), routine(value) {}
    uint32_t routine;
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
    writeMessage(output, capacity, "Falha: %s", error.what());
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
        const Image image = parseImage(path);
        GuestMemory memory;
        g_nextVirtualAllocation = kFirstVirtualAllocation;
        g_virtualAllocations.clear();
        copyImage(image, memory);
        const size_t installed = installDispatchTable(memory);

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
        entry->host(context, memory.base);
        writeMessage(output, output_capacity,
                     "Entry point retornou. Funções AOT registradas: %zu. O boot não foi concluído.", installed);
        return 3;
    } catch (const GuestFirmwareReturn &request) {
        writeMessage(output, output_capacity,
                     "O XEX chamou HalReturnToFirmware (routine=0x%08X). "
                     "O runtime ainda não emula ciclo de reboot/shutdown; o boot parou aqui.",
                     request.routine);
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
                  "Xbox kernel/XAM import ainda não implementado: %s (LR=0x%08X)",
                  name ? name : "?", static_cast<uint32_t>(context.lr));
    throw std::runtime_error(message);
}

void xowue_NtAllocateVirtualMemory(PPCContext &context, uint8_t *base) {
    const uint32_t basePointer = context.r3.u32;
    const uint32_t sizePointer = context.r4.u32;
    const uint32_t allocationType = context.r5.u32;
    const uint32_t protection = context.r6.u32;
    const uint32_t debugMemory = context.r7.u32;

    auto failWith = [&context](uint32_t status) { context.r3.u32 = status; };
    if (!base || basePointer > kGuestAddressSpaceSize - sizeof(uint32_t) ||
        sizePointer > kGuestAddressSpaceSize - sizeof(uint32_t) ||
        basePointer == sizePointer || debugMemory != 0) {
        failWith(kNtStatusInvalidParameter);
        return;
    }

    uint32_t requestedBase = PPC_LOAD_U32(basePointer);
    uint32_t requestedSize = PPC_LOAD_U32(sizePointer);
    if (requestedSize == 0 ||
        (allocationType & (0x00001000u | 0x00002000u | 0x00080000u)) == 0 ||
        (allocationType & 0x00080000u && allocationType != 0x00080000u)) {
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
    if (address == 0) {
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
    for (const auto &[allocatedAddress, allocatedSize] : g_virtualAllocations) {
        const uint64_t allocatedEnd = static_cast<uint64_t>(allocatedAddress) + allocatedSize;
        if (address < allocatedEnd && allocationEnd > allocatedAddress) {
            failWith(kNtStatusNoMemory);
            return;
        }
    }
    if ((allocationType & 0x00001000u) != 0 && (allocationType & 0x00800000u) == 0) {
        std::memset(base + address, 0, adjustedSize);
    }

    PPC_STORE_U32(basePointer, address);
    PPC_STORE_U32(sizePointer, adjustedSize);
    g_virtualAllocations.emplace_back(address, adjustedSize);
    (void)protection; // Host guest memory is uniformly readable/writable at this stage.
    failWith(kNtStatusSuccess);
}

void xowue_NtFreeVirtualMemory(PPCContext &context, uint8_t *base) {
    const uint32_t basePointer = context.r3.u32;
    const uint32_t sizePointer = context.r4.u32;
    const uint32_t freeType = context.r5.u32;
    const uint32_t debugMemory = context.r6.u32;

    auto failWith = [&context](uint32_t status) { context.r3.u32 = status; };
    if (!base || basePointer > kGuestAddressSpaceSize - sizeof(uint32_t) ||
        sizePointer > kGuestAddressSpaceSize - sizeof(uint32_t) ||
        basePointer == sizePointer || debugMemory != 0) {
        failWith(kNtStatusInvalidParameter);
        return;
    }

    const uint32_t address = PPC_LOAD_U32(basePointer);
    const uint32_t requestedSize = PPC_LOAD_U32(sizePointer);
    if (address == 0) {
        failWith(kNtStatusMemoryNotAllocated);
        return;
    }

    const auto allocation = std::find_if(
        g_virtualAllocations.begin(), g_virtualAllocations.end(),
        [address](const auto &item) { return item.first == address; });
    if (allocation == g_virtualAllocations.end()) {
        failWith(kNtStatusUnsuccessful);
        return;
    }

    const uint32_t allocationSize = allocation->second;
    uint32_t resultSize = allocationSize;
    if (freeType == 0x00004000u) { // MEM_DECOMMIT
        if (requestedSize == 0 || requestedSize > allocationSize) {
            failWith(kNtStatusInvalidParameter);
            return;
        }
        const uint64_t adjusted =
            (static_cast<uint64_t>(requestedSize) + 0xFFFu) & ~uint64_t{0xFFFu};
        resultSize = static_cast<uint32_t>(std::min<uint64_t>(adjusted, allocationSize));
        std::memset(base + address, 0, resultSize);
    } else if (freeType == 0x00008000u) { // MEM_RELEASE
        g_virtualAllocations.erase(allocation);
        if (static_cast<uint64_t>(address) + allocationSize == g_nextVirtualAllocation) {
            g_nextVirtualAllocation = address;
        }
        std::memset(base + address, 0, allocationSize);
    } else {
        failWith(kNtStatusInvalidParameter);
        return;
    }

    PPC_STORE_U32(basePointer, address);
    PPC_STORE_U32(sizePointer, resultSize);
    failWith(kNtStatusSuccess);
}

[[noreturn]] void xowue_HalReturnToFirmware(PPCContext &context, uint8_t *) {
    throw GuestFirmwareReturn(context.r3.u32);
}

[[noreturn]] void xowue_untranslated_tail(uint32_t guest_address) {
    char message[160];
    std::snprintf(message, sizeof(message),
                  "instrução PPC não decodificada no trecho final .text: 0x%08X", guest_address);
    throw std::runtime_error(message);
}
