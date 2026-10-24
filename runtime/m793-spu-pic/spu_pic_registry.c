/* ASCENSION_M793_SPU_PIC_RUNTIME_V1
 * One device-captured ELF-backed WWS branch is lifted natively.
 * Dynamic PM save/restore stubs without an ELF origin remain separate.
 */
#include "spu_context.h"
extern void pic_006E7220_register(void);
void ascension_spu_pic_register_all(void)
{
    pic_006E7220_register();
}
