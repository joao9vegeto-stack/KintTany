/* M5.1.3 host proof against the PINNED upstream RSX dispatcher.
 * The bug was sending all VP words to lane0, never finishing an instruction.
 * This checks 0/4/8/12 lane sequencing and the guest FP MAIN address bit. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "rsx_dispatch.h"
#include "rsx_commands.h"
#include "rsx_test_programs.h"

int main(void) {
    rsx_dispatch state;
    rsx_dispatch_init(&state, NULL);
    uint8_t vp[32];
    rsx_test_vp_mov_out(vp, 0, RSX_TEST_VP_SWZ_IDENT, 0, 0);
    rsx_test_vp_mov_out(vp+16, 8, RSX_TEST_VP_SWZ_IDENT, 7, 1);
    rsx_dispatch_method(&state, NV4097_SET_TRANSFORM_PROGRAM_LOAD, 0u);
    for (unsigned i=0; i<8; i++) {
        const uint32_t w = (uint32_t)vp[4*i] |
            ((uint32_t)vp[4*i+1]<<8) | ((uint32_t)vp[4*i+2]<<16) |
            ((uint32_t)vp[4*i+3]<<24);
        rsx_dispatch_method(&state,
            NV4097_SET_TRANSFORM_PROGRAM+(i&3u)*4u,w);
        if (state.vp[i] != w) {
            fprintf(stderr,"FAILED word %u stored %08X expected %08X\n",
                    i,state.vp[i],w);
            return 1;
        }
    }
    if (rsx_dsp_reg(&state,NV4097_SET_TRANSFORM_PROGRAM_LOAD)!=2u)
        return 2;
    rsx_dispatch_method(&state,NV4097_SET_TRANSFORM_PROGRAM_START,0u);
    if (rsx_dsp_vp_start(&state)!=0u) return 3;
    rsx_dispatch_method(&state,NV4097_SET_SHADER_PROGRAM,0x002B0002u);
    uint32_t loc=99u;
    const uint32_t off=rsx_dsp_fragment_program(&state,&loc);
    if (loc!=RSX_LOCATION_MAIN || off!=0x002B0000u) {
        fprintf(stderr,"FP mismatch location %u offset %08X\n",loc,off);
        return 4;
    }
    puts("M5.1.3 NV40 guest upload PASS: VP 2 complete instructions, FP MAIN");
    return 0;
}
