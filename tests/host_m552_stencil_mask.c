/* M5.5.2 proof against PINNED upstream rsx_dispatch.c.
 * Setting STENCIL_FUNC_MASK (0x0338, read mask) must NOT be confused
 * with STENCIL_MASK (0x032C, actual stencil WRITEmask).
 */
#include <stdint.h>
#include <stdio.h>
#include "rsx_dispatch.h"

int main(void) {
    rsx_dispatch s;
    rsx_dispatch_init(&s, NULL);
    rsx_dispatch_method(&s, 0x00000328u, 1u);
    rsx_dispatch_method(&s, 0x00000330u, 0x0207u);
    rsx_dispatch_method(&s, 0x00000334u, 1u);
    rsx_dispatch_method(&s, 0x00000338u, 0xffu);
    if(rsx_dsp_reg(&s,0x032Cu)!=0u) {
        fputs("FAIL: stencil write mask not initially zero\n",stderr);
        return 1;
    }
    rsx_dispatch_method(&s, 0x0000032Cu, 0xffu);
    if(rsx_dsp_reg(&s,0x032Cu)!=0xffu ||
       rsx_dsp_reg(&s,0x0338u)!=0xffu ||
       rsx_dsp_reg(&s,0x0328u)!=1u ||
       rsx_dsp_reg(&s,0x0334u)!=1u) {
        fputs("FAIL: decoded guest stencil registers disagree\n",stderr);
        return 2;
    }
    puts("M5.5.2 stencil mask register PASS");
    return 0;
}
