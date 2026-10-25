#include "XOWUEPathContainment.h"

#include <cassert>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <system_error>

int main() {
    namespace fs = std::filesystem;
    const fs::path sandbox =
        fs::temp_directory_path() / "xowue-path-containment-smoke";
    const fs::path root = sandbox / "cache";
    const fs::path child = root / "nested";
    const fs::path outside = sandbox / "cache-escape";
    std::error_code error;
    fs::remove_all(sandbox, error);
    error.clear();
    fs::create_directories(child, error);
    assert(!error);
    fs::create_directories(outside, error);
    assert(!error);

    {
        std::ofstream file(child / "present.bin", std::ios::binary);
        assert(file.good());
        file << 'x';
    }
    {
        std::ofstream file(outside / "outside.bin", std::ios::binary);
        assert(file.good());
        file << 'x';
    }

    // Regression for NtOpenFile("cache:\\"): opening the device root itself
    // must be accepted, not rejected because its parent lies outside the root.
    assert(xowue::path::isWithinRoot(root, root));
    assert(xowue::path::isWithinRoot(root, child / "present.bin"));
    assert(xowue::path::isWithinRoot(root, root / "not-created-yet.bin"));
    assert(!xowue::path::isWithinRoot(root, outside / "outside.bin"));
    assert(!xowue::path::isWithinRoot(root, root / ".." / "cache-escape" /
                                                   "outside.bin"));

    fs::create_directory_symlink(outside, root / "escape", error);
    if (!error) {
        assert(!xowue::path::isWithinRoot(root, root / "escape" / "outside.bin"));
    }

    fs::remove_all(sandbox, error);
    std::cout << "XOWUE_PATH_CONTAINMENT_SMOKE_PASS\n";
    return 0;
}
