/* M7.89 registry for the exact C8 WWS policy image captured on iPhone. */
#include <stdint.h>
#include "spu_workload.h"

extern void spu_begin_image(int image_id);
extern void wws_pm_c8d774_spu_func_00000A00(spu_context*);
extern void wws_pm_c8d774_spu_recomp_register(void);

void gowa_spu_register_c8_wws_pm(void)
{
    /* Image 5 remains reserved for the separate NPUA WWS module. */
    spu_begin_image(6);
    wws_pm_c8d774_spu_recomp_register();
    spu_workload_register_img(UINT64_C(0xC8D774963A96DCF2),
                              wws_pm_c8d774_spu_func_00000A00,
                              6, "wws_pm_c8d774_12288");
    spu_begin_image(0);
}
