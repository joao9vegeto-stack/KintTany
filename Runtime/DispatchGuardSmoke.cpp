#include "XOWUEDispatchGuard.h"

#include <array>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string_view>

namespace {
void mappedTarget() {}
void anotherTarget() {}

using ProbeFunction = void();

void require(bool condition, std::string_view message) {
    if (!condition) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(1);
    }
}
}

int main() {
    constexpr std::uint32_t codeBase = 0x82000000u;
    constexpr std::uint32_t codeSize = 0x100u;
    constexpr std::uint64_t tableStart = 128u;
    constexpr std::uint32_t target = codeBase + 0x20u;
    std::array<std::uint8_t, 512> memory{};
    ProbeFunction *resolved = nullptr;
    const std::uint64_t slot = tableStart + (target - codeBase) * 2u;
    ProbeFunction *expected = &mappedTarget;
    std::memcpy(memory.data() + slot, &expected, sizeof(expected));

    auto result = xowue_dispatch_guard::resolve<ProbeFunction>(
        memory.data(), memory.size(), target, codeBase, codeSize,
        tableStart, resolved);
    require(result == xowue_dispatch_guard::Result::ok && resolved == expected,
            "valid guest function resolves to the installed AOT target");

    result = xowue_dispatch_guard::resolve<ProbeFunction>(
        memory.data(), memory.size(), target + 1u, codeBase, codeSize,
        tableStart, resolved);
    require(result == xowue_dispatch_guard::Result::target_unaligned && !resolved,
            "unaligned PPC branch is rejected before pointer lookup");

    result = xowue_dispatch_guard::resolve<ProbeFunction>(
        memory.data(), memory.size(), codeBase - 4u, codeBase, codeSize,
        tableStart, resolved);
    require(result == xowue_dispatch_guard::Result::target_below_code && !resolved,
            "branch below the linked code window is rejected");

    result = xowue_dispatch_guard::resolve<ProbeFunction>(
        memory.data(), memory.size(), codeBase + codeSize, codeBase, codeSize,
        tableStart, resolved);
    require(result == xowue_dispatch_guard::Result::target_out_of_code && !resolved,
            "branch at the end of the linked code window is rejected");

    std::memset(memory.data() + slot, 0, sizeof(expected));
    result = xowue_dispatch_guard::resolve<ProbeFunction>(
        memory.data(), memory.size(), target, codeBase, codeSize,
        tableStart, resolved);
    require(result == xowue_dispatch_guard::Result::empty_slot && !resolved,
            "missing AOT mapping is reported instead of calling address zero");

    expected = &anotherTarget;
    std::memcpy(memory.data() + slot, &expected, sizeof(expected));
    result = xowue_dispatch_guard::resolve<ProbeFunction>(
        memory.data(), memory.size(), target, codeBase, codeSize,
        tableStart, resolved);
    require(result == xowue_dispatch_guard::Result::ok && resolved == expected,
            "lookup returns the actual installed slot so runtime can compare map identity");

    result = xowue_dispatch_guard::resolve<ProbeFunction>(
        memory.data(), 256u, target, codeBase, codeSize, 250u, resolved);
    require(result == xowue_dispatch_guard::Result::table_out_of_memory && !resolved,
            "dispatch slot bounds are checked against the mapped guest memory");

    result = xowue_dispatch_guard::resolve<ProbeFunction>(
        nullptr, memory.size(), target, codeBase, codeSize, tableStart, resolved);
    require(result == xowue_dispatch_guard::Result::null_base && !resolved,
            "null guest memory is rejected");

    std::cout << "PASS: 8 PPC AOT dispatch guard cases\n";
    return 0;
}
