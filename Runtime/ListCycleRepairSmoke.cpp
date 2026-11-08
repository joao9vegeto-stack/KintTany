#include "XOWUEListCycleRepair.hpp"

#include <array>
#include <cassert>
#include <cstdint>

namespace {
constexpr uint32_t kBase = 0x40000000u;
constexpr uint32_t kLink = 0x28u;
std::array<uint8_t, 0x400> memory{};

bool valid(uint32_t address, uint32_t size) {
    return address >= kBase && address + size >= address &&
           address + size <= kBase + memory.size();
}
uint32_t load(uint32_t address) {
    assert(valid(address, 4u));
    return (uint32_t(memory[address - kBase]) << 24u) |
           (uint32_t(memory[address - kBase + 1u]) << 16u) |
           (uint32_t(memory[address - kBase + 2u]) << 8u) |
            uint32_t(memory[address - kBase + 3u]);
}
void store(uint32_t address, uint32_t value) {
    assert(valid(address, 4u));
    memory[address - kBase] = uint8_t(value >> 24u);
    memory[address - kBase + 1u] = uint8_t(value >> 16u);
    memory[address - kBase + 2u] = uint8_t(value >> 8u);
    memory[address - kBase + 3u] = uint8_t(value);
}
void reset() { memory.fill(0u); }
}

int main() {
    // Normal NULL-terminated list: no writes.
    reset();
    constexpr uint32_t a = kBase + 0x20u, b = kBase + 0x80u, c = kBase + 0xE0u;
    store(a + kLink, b);
    store(b + kLink, c);
    const auto normal = xowue::repairNullTerminatedGuestListCycle(
        a, kLink, 0xA0u, 32u, load, store, valid);
    assert(!normal.cycle && !normal.repaired && !normal.invalidNext && !normal.truncated);
    assert(load(a + kLink) == b && load(b + kLink) == c && load(c + kLink) == 0u);

    // A -> B -> C -> B: preserve A/B/C and cut only C's cycle edge.
    reset();
    store(a + kLink, b);
    store(b + kLink, c);
    store(c + kLink, b);
    const auto cycle = xowue::repairNullTerminatedGuestListCycle(
        a, kLink, 0xA0u, 32u, load, store, valid);
    assert(cycle.cycle && cycle.repaired && cycle.cycleFrom == c && cycle.cycleTo == b);
    assert(load(a + kLink) == b && load(b + kLink) == c && load(c + kLink) == 0u);

    // A self-cycle is repaired without dropping the root node.
    reset();
    store(a + kLink, a);
    const auto self = xowue::repairNullTerminatedGuestListCycle(
        a, kLink, 0xA0u, 32u, load, store, valid);
    assert(self.repaired && self.cycleFrom == a && self.cycleTo == a && load(a + kLink) == 0u);

    // Invalid pointers and over-limit lists must remain byte-for-byte intact.
    reset();
    store(a + kLink, 0x1234u);
    const auto invalid = xowue::repairNullTerminatedGuestListCycle(
        a, kLink, 0xA0u, 32u, load, store, valid);
    assert(invalid.invalidNext && !invalid.repaired && load(a + kLink) == 0x1234u);

    reset();
    store(a + kLink, b);
    store(b + kLink, c);
    const auto truncated = xowue::repairNullTerminatedGuestListCycle(
        a, kLink, 0xA0u, 2u, load, store, valid);
    assert(truncated.truncated && !truncated.repaired && load(a + kLink) == b && load(b + kLink) == c);

    return 0;
}
