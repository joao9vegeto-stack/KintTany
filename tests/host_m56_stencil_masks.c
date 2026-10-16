/* M5.6 host register contract; pixel correctness is tested on iPhone. */
#include <stdint.h>
#include <stdio.h>
#include "rsx_dispatch.h"
int main(void) {
    rsx_dispatch s;
    rsx_dispatch_init(&s,NULL);
    rsx_dispatch_method(&s,0x0328u,1u);
    rsx_dispatch_method(&s,0x0338u,0xffu);
    rsx_dispatch_method(&s,0x032cu,0x0fu);
    if(rsx_dsp_reg(&s,0x0338u)!=0xffu ||
       rsx_dsp_reg(&s,0x032cu)!=0x0fu) return 1;
    rsx_dispatch_method(&s,0x032cu,0xf0u);
    if(rsx_dsp_reg(&s,0x0338u)!=0xffu ||
       rsx_dsp_reg(&s,0x032cu)!=0xf0u) return 2;
    rsx_dispatch_method(&s,0x0338u,0x0fu);
    if(rsx_dsp_reg(&s,0x0338u)!=0x0fu ||
       rsx_dsp_reg(&s,0x032cu)!=0xf0u) return 3;
    puts("M5.6 independent RSX stencil masks PASS");
    return 0;
}
