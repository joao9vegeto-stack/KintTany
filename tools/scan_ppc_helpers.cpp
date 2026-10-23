#include <cstdint>
#include <cstring>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>
#include "file.h"
#include "image.h"

struct Pattern { const char* name; std::vector<uint8_t> bytes; };

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "Usage: scan_ppc_helpers <default.xex>\n";
        return 2;
    }
    const auto file = LoadFile(argv[1]);
    const auto image = Image::ParseImage(file.data(), file.size());
    std::vector<Pattern> patterns = {
        {"restgprlr_14", {0xe9,0xc1,0xff,0x68}},
        {"savegprlr_14", {0xf9,0xc1,0xff,0x68}},
        {"restfpr_14", {0xc9,0xcc,0xff,0x70}},
        {"savefpr_14", {0xd9,0xcc,0xff,0x70}},
        {"restvmx_14", {0x39,0x60,0xfe,0xe0,0x7d,0xcb,0x60,0xce}},
        {"savevmx_14", {0x39,0x60,0xfe,0xe0,0x7d,0xcb,0x61,0xce}},
        {"restvmx_64", {0x39,0x60,0xfc,0x00,0x10,0x0b,0x60,0xcb}},
        {"savevmx_64", {0x39,0x60,0xfc,0x00,0x10,0x0b,0x61,0xcb}},
    };
    for (const auto& section : image.sections) {
        std::cout << "SECTION " << section.name << " base=0x" << std::hex << section.base
                  << " size=0x" << section.size << " flags=0x" << unsigned(section.flags) << std::dec << "\n";
        if (!(section.flags & SectionFlags_Code)) continue;
        for (const auto& pattern : patterns) {
            size_t matches = 0;
            for (size_t offset = 0; offset + pattern.bytes.size() <= section.size; ++offset) {
                if (std::memcmp(section.data + offset, pattern.bytes.data(), pattern.bytes.size()) == 0) {
                    std::cout << pattern.name << " 0x" << std::hex << section.base + offset << std::dec << "\n";
                    ++matches;
                }
            }
            if (!matches) std::cout << pattern.name << " NOT_FOUND\n";
        }
    }
}
