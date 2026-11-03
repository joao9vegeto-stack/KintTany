/* SPDX-License-Identifier: GPL-2.0-or-later
 * iOS bridge for bloodborne-native/bloodborne-recomp bbcpu.
 * Adapted for SpartanPort from the pinned gow3-macos-arm64 AOT integration.
 */
#include "SpartanIOSAOTRuntime.h"
#include "ThirdParty/bbcpu.h"
#include <dlfcn.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

extern int bbcpu_recomp_count;
static int s_registered;
static uintptr_t s_image_base;
static size_t s_executable_size;

int SpartanIOSAOTRegister(uintptr_t image_base, size_t executable_size, const char *library_path) {
    struct stat st;
    if (!image_base || !executable_size || !library_path || !*library_path) return EINVAL;
    if (s_registered) return (s_image_base == image_base && s_executable_size == executable_size) ? 0 : EALREADY;
    if (stat(library_path, &st) != 0 || !S_ISREG(st.st_mode) || st.st_size <= 0) return errno ? errno : ENOENT;
    if (setenv("BB_RECOMP_LIB", library_path, 1) != 0) return errno;
    bbcpu_add_guest_code(image_base, executable_size);
    bbcpu_recomp_load(image_base);
    if (bbcpu_recomp_count <= 0) {
        fprintf(stderr, "SpartanPort AOT: no generated game functions registered from %s\n", library_path);
        return ENOEXEC;
    }
    s_image_base = image_base;
    s_executable_size = executable_size;
    s_registered = 1;
    fprintf(stderr, "SpartanPort AOT: registered %d generated ARM64 game functions\n", bbcpu_recomp_count);
    return 0;
}

uint64_t SpartanIOSAOTCall(uintptr_t entry, const uint64_t *arguments, int argument_count,
                           void *guest_stack, size_t guest_stack_size) {
    if (!s_registered || !entry || !guest_stack || !guest_stack_size ||
        argument_count < 0 || argument_count > 6 || (argument_count && !arguments)) return 0;
    return bbcpu_call_on_stack(entry, argument_count, arguments, guest_stack, guest_stack_size);
}

void SpartanIOSAOTSetThreadPointer(uintptr_t guest_tcb) {
    bbcpu_set_thread_pointer(guest_tcb);
}

int SpartanIOSAOTIsRegistered(void) { return s_registered; }
int SpartanIOSAOTFunctionCount(void) { return bbcpu_recomp_count; }
