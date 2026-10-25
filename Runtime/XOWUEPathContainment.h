#pragma once

#include <filesystem>
#include <system_error>

namespace xowue::path {

// Resolve both sides, including existing symlinks, then compare path
// components. The root itself is a valid target (Xbox device-root opens use
// this), and non-existent final files remain checkable via weakly_canonical.
inline bool isWithinRoot(const std::filesystem::path &root,
                         const std::filesystem::path &target) {
    std::error_code error;
    const auto canonicalRoot = std::filesystem::weakly_canonical(root, error);
    if (error) return false;

    const auto canonicalTarget = std::filesystem::weakly_canonical(target, error);
    if (error) return false;

    auto rootIt = canonicalRoot.begin();
    auto targetIt = canonicalTarget.begin();
    for (; rootIt != canonicalRoot.end() && targetIt != canonicalTarget.end();
         ++rootIt, ++targetIt) {
        if (*rootIt != *targetIt) return false;
    }
    return rootIt == canonicalRoot.end();
}

} // namespace xowue::path
