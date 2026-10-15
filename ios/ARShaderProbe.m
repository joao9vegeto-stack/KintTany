/* M5.0: actual PS3 RSX NV40 microcode -> HLSL -> SPIR-V -> MSL
 * -> native iPhone Metal shader compilation. No game bytes or fixed MSL.
 * This is a per-stage compilation probe, NOT a textured guest DRAW yet.
 */
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "rsx_vp_decompiler.h"
#include "rsx_fp_decompiler.h"
#include "rsx_shader_msl.h"
#include "rsx_test_programs.h"

static int ar_shader_error(char *details, size_t cap, int rc, const char *kind,
                           const char *reason) {
    if (details && cap)
        snprintf(details, cap, "%s: %.170s", kind, reason ? reason : "erro desconhecido");
    return rc;
}

static int ar_compile_guest_stage(id<MTLDevice> dev, const char *hlsl, int stage,
                                  char *details, size_t cap) {
    char msl[256 * 1024] = {0};
    char log[4096] = {0};
    if (rsx_hlsl_to_msl(hlsl, stage, msl, sizeof(msl), log, sizeof(log)) != 0)
        return ar_shader_error(details, cap, -3, "HLSL->MSL", log);
    NSString *source = [NSString stringWithUTF8String:msl];
    NSError *error = nil;
    id<MTLLibrary> lib = [dev newLibraryWithSource:source options:nil error:&error];
    if (!lib)
        return ar_shader_error(details, cap, -4, "Metal MSL",
                               [[error localizedDescription] UTF8String]);
    id<MTLFunction> fn = [lib newFunctionWithName:@"main0"];
    const MTLFunctionType expected = stage == RSX_SHADER_STAGE_VERTEX ?
        MTLFunctionTypeVertex : MTLFunctionTypeFragment;
    if (!fn || fn.functionType != expected)
        return ar_shader_error(details, cap, -5, "Metal entrypoint", "main0 ausente/tipo errado");
    if (stage == RSX_SHADER_STAGE_FRAGMENT && strstr(hlsl, "rsx_tex[0].Sample(")) {
        if (!strstr(msl, "[[texture(0)]]") || !strstr(msl, "[[sampler(0)]]"))
            return ar_shader_error(details, cap, -6, "TEX0 bindings", "textura/sampler fora do slot 0");
    }
    return 0;
}

/* Returns 0 only when VP MOV, FP MOV and FP TEX compile as genuine Metal
 * functions on the device. No fake success for absent translator. */
int ar_probe_guest_shader_compile(char *details, size_t cap) {
    if (details && cap) details[0] = 0;
    if (!rsx_hlsl_to_msl_available())
        return ar_shader_error(details, cap, -1, "translator", "glslang/spirv-cross ausentes");
    id<MTLDevice> device = MTLCreateSystemDefaultDevice();
    if (!device)
        return ar_shader_error(details, cap, -2, "Metal", "dispositivo indisponivel");

    char hlsl[128 * 1024] = {0};
    u8 vp[32];
    rsx_test_vp_mov_out(vp, 0, RSX_TEST_VP_SWZ_IDENT, 0, 0);
    rsx_test_vp_mov_out(vp + 16, 3, RSX_TEST_VP_SWZ_IDENT, 1, 1);
    if (rsx_vp_decompile(vp, sizeof(vp), hlsl, sizeof(hlsl)) != 2)
        return ar_shader_error(details, cap, -7, "VP", "decompiler de microcodigo");
    int rc = ar_compile_guest_stage(device, hlsl, RSX_SHADER_STAGE_VERTEX, details, cap);
    if (rc) return rc;

    u8 fp[16];
    rsx_test_fp_mov_r0_col0(fp, RSX_TEST_FP_SWZ_IDENT);
    if (rsx_fp_decompile_buffered_ex(fp, sizeof(fp), 0x40, 0, hlsl, sizeof(hlsl), NULL) != 1)
        return ar_shader_error(details, cap, -8, "FP MOV", "decompiler de microcodigo");
    rc = ar_compile_guest_stage(device, hlsl, RSX_SHADER_STAGE_FRAGMENT, details, cap);
    if (rc) return rc;

    rsx_test_fp_tex_r0_tc0(fp, 0);
    if (rsx_fp_decompile_buffered_ex(fp, sizeof(fp), 0x40, 0, hlsl, sizeof(hlsl), NULL) != 1)
        return ar_shader_error(details, cap, -9, "FP TEX", "decompiler de microcodigo");
    rc = ar_compile_guest_stage(device, hlsl, RSX_SHADER_STAGE_FRAGMENT, details, cap);
    if (rc) return rc;
    if (details && cap) snprintf(details, cap,
        "VP MOV + FP MOV + FP TEX0 (texture/sampler 0): Metal main0 OK");
    return 0;
}
