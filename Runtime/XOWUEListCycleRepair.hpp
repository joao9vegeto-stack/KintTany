#pragma once

#include <cstdint>
#include <unordered_set>

namespace xowue {

struct GuestListCycleRepairResult {
    uint32_t steps = 0;
    uint32_t cycleFrom = 0;
    uint32_t cycleTo = 0;
    uint32_t badAddress = 0;
    bool cycle = false;
    bool repaired = false;
    bool invalidNext = false;
    bool truncated = false;
};

// Repairs only a cycle in a list whose guest consumer explicitly terminates
// on a NULL next pointer. The predecessor edge is cut, retaining each unique
// node and its original order. Invalid and over-limit chains are never mutated.
template <typename Load32, typename Store32, typename ValidRange>
GuestListCycleRepairResult repairNullTerminatedGuestListCycle(
    uint32_t root, uint32_t linkOffset, uint32_t nodeSize, uint32_t maxNodes,
    Load32 load32, Store32 store32, ValidRange validRange) {
    GuestListCycleRepairResult result{};
    if (maxNodes == 0u || !validRange(root, nodeSize)) {
        result.invalidNext = true;
        result.badAddress = root;
        return result;
    }

    std::unordered_set<uint32_t> visited;
    visited.reserve(maxNodes);
    uint32_t current = root;
    uint32_t previous = 0u;
    for (uint32_t index = 0u; index < maxNodes; ++index) {
        if (!validRange(current, nodeSize)) {
            result.invalidNext = true;
            result.badAddress = current;
            return result;
        }
        const auto [_, inserted] = visited.insert(current);
        if (!inserted) {
            result.cycle = true;
            result.cycleFrom = previous;
            result.cycleTo = current;
            if (previous == 0u || !validRange(previous, nodeSize)) {
                result.invalidNext = true;
                result.badAddress = previous;
                return result;
            }
            store32(previous + linkOffset, 0u);
            result.repaired = true;
            return result;
        }

        ++result.steps;
        const uint32_t next = load32(current + linkOffset);
        if (next == 0u) return result;
        if (!validRange(next, nodeSize)) {
            result.invalidNext = true;
            result.badAddress = next;
            return result;
        }
        previous = current;
        current = next;
    }

    result.truncated = true;
    return result;
}

}  // namespace xowue
