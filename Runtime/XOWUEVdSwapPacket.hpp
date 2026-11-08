#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace xowue {

inline constexpr uint32_t kVdSwapReservedDwords = 64u;
inline constexpr uint32_t kVdSwapFetchRegister = 0x4800u;
inline constexpr uint32_t kVdSwapOpcode = 0x64u;
inline constexpr uint32_t kVdSwapSignature = 0x53574150u;
inline constexpr uint32_t kVdSwapType2Nop = 0x80000000u;

// Rewrite the Xenos texture-fetch base after checking the D3D9 header address.
// The Xenos base_address is a 20-bit page number in dword_1[31:12].
inline bool translateVdSwapFetchBase(
    std::array<uint32_t, 6>& fetch,
    uint32_t frontbufferVirtualAddress,
    uint32_t frontbufferPhysicalAddress) {
    const uint32_t descriptorVirtualAddress =
        ((fetch[1] >> 12u) & 0xFFFFFu) << 12u;
    if (frontbufferVirtualAddress != descriptorVirtualAddress ||
        (frontbufferPhysicalAddress & 0xFFFu) != 0u ||
        (frontbufferPhysicalAddress >> 12u) > 0xFFFFFu) {
        return false;
    }
    fetch[1] = (fetch[1] & 0x00000FFFu) |
               ((frontbufferPhysicalAddress >> 12u) << 12u);
    return true;
}

// Construct the same GPU command sequence as Xenia's xboxkrnl VdSwap:
// Type-0 write of six fetch words, followed by Type-3 PM4_XE_SWAP.
inline std::array<uint32_t, kVdSwapReservedDwords> buildVdSwapPacket(
    const std::array<uint32_t, 6>& fetch,
    uint32_t frontbufferPhysicalAddress,
    uint32_t width,
    uint32_t height) {
    std::array<uint32_t, kVdSwapReservedDwords> packet{};
    packet.fill(kVdSwapType2Nop);

    // Type-0: (count - 1) in bits 16..29, register index in bits 0..14.
    packet[0] = ((static_cast<uint32_t>(fetch.size()) - 1u) << 16u) |
                (kVdSwapFetchRegister & 0x7FFFu);
    for (size_t i = 0; i < fetch.size(); ++i)
        packet[1u + i] = fetch[i];

    // Type-3: four payload dwords: signature, frontbuffer, width, height.
    packet[7] = (3u << 30u) | (3u << 16u) | (kVdSwapOpcode << 8u);
    packet[8] = kVdSwapSignature;
    packet[9] = frontbufferPhysicalAddress;
    packet[10] = width;
    packet[11] = height;
    return packet;
}

}  // namespace xowue
