#include "XOWUEVdSwapPacket.hpp"

#include <array>
#include <cassert>
#include <cstdint>
#include <iostream>

int main() {
    // The D3D9 header contains a virtual base; VdSwap receives that same
    // address separately and must translate/rewrite it before the Type-0.
    std::array<uint32_t, 6> fetch{
        0x00000000u,
        0x403D0056u, // virtual base 0x403D0000, Xenos format low bits 0x16
        (719u << 13u) | 1279u,
        0x00000000u,
        0x00000000u,
        0x00000000u
    };
    constexpr uint32_t virtualBase = 0x403D0000u;
    constexpr uint32_t physicalBase = 0x103D0000u;
    assert(xowue::translateVdSwapFetchBase(fetch, virtualBase, physicalBase));
    assert(fetch[1] == 0x103D0056u); // only base_address[31:12] was rewritten

    const auto packet = xowue::buildVdSwapPacket(fetch, physicalBase, 1280u, 720u);

    // Exact packet contract from Xenia's xboxkrnl_video.cc.
    assert(packet[0] == 0x00054800u); // Type-0, six registers from 0x4800.
    for (size_t i = 0; i < fetch.size(); ++i)
        assert(packet[1u + i] == fetch[i]);

    assert(packet[7] == 0xC0036400u); // Type-3 PM4_XE_SWAP, four payload dwords.
    assert(packet[8] == xowue::kVdSwapSignature);
    assert(packet[9] == physicalBase);
    assert(packet[10] == 1280u);
    assert(packet[11] == 720u);

    // A mismatching D3D9 header must not silently submit a stale descriptor.
    auto mismatch = fetch;
    assert(!xowue::translateVdSwapFetchBase(
        mismatch, 0x403E0000u, 0x103E0000u));
    assert(mismatch == fetch);
    assert(!xowue::translateVdSwapFetchBase(
        mismatch, virtualBase, 0x103D0001u));
    assert(mismatch == fetch);

    // Verify every unused reserved dword remains a Type-2 NOP.
    for (size_t i = 12u; i < packet.size(); ++i)
        assert(packet[i] == xowue::kVdSwapType2Nop);

    // A second mapping guards against stale base bits from the first swap.
    auto nextFetch = fetch;
    nextFetch[1] = 0x40400056u;
    assert(xowue::translateVdSwapFetchBase(
        nextFetch, 0x40400000u, 0x10400000u));
    const auto next = xowue::buildVdSwapPacket(
        nextFetch, 0x10400000u, 640u, 360u);
    assert(next[1] == nextFetch[0]);
    assert(next[2] == 0x10400056u);
    assert(next[9] == 0x10400000u);
    assert(next[10] == 640u && next[11] == 360u);
    for (size_t i = 12u; i < next.size(); ++i)
        assert(next[i] == xowue::kVdSwapType2Nop);

    std::cout << "PASS: VdSwap validates and translates the fetch base before PM4_XE_SWAP\n";
    return 0;
}
