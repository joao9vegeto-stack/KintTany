#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <type_traits>

namespace xowue_dispatch_guard {

enum class Result {
    ok,
    null_base,
    target_below_code,
    target_out_of_code,
    target_unaligned,
    table_out_of_memory,
    empty_slot,
};

template <typename Function>
Result resolve(const std::uint8_t *base, std::size_t memorySize,
               std::uint32_t target, std::uint32_t codeBase,
               std::uint32_t codeSize, std::uint64_t tableStart,
               Function *&function) noexcept {
    static_assert(std::is_function_v<Function>);
    function = nullptr;
    if (!base) return Result::null_base;
    if (target < codeBase) return Result::target_below_code;
    const std::uint64_t codeOffset = static_cast<std::uint64_t>(target) - codeBase;
    if (codeOffset >= codeSize) return Result::target_out_of_code;
    if ((target & 3u) != 0u) return Result::target_unaligned;

    const std::uint64_t memoryBytes = static_cast<std::uint64_t>(memorySize);
    if (tableStart > memoryBytes || memoryBytes - tableStart < sizeof(Function *))
        return Result::table_out_of_memory;
    const std::uint64_t maxCodeOffset =
        (memoryBytes - tableStart - sizeof(Function *)) / 2u;
    if (codeOffset > maxCodeOffset) return Result::table_out_of_memory;
    const std::uint64_t slotOffset = tableStart + codeOffset * 2u;

    Function *candidate = nullptr;
    std::memcpy(&candidate, base + slotOffset, sizeof(candidate));
    if (!candidate) return Result::empty_slot;
    function = candidate;
    return Result::ok;
}

}  // namespace xowue_dispatch_guard
