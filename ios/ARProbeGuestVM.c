/* Minimal real bounded host VM for GPU probe, with NO PS3 image loaded.

 * The upstream RSX draw engine tests vm_base and ppu_vm_size whenever it
 * fetches guest memory. These are normally in the per-game PPU loader,
 * which is deliberately absent from this game-free diagnostic.
 * Any attempt to read outside this 16 MiB region fails the RSX bound check.
 */
#include <stdint.h>
#include <stdlib.h>
#ifdef __cplusplus
extern "C" {
#endif
uint8_t *vm_base=0;
/* M7.72: ppu_vm_size is owned by the PS3Recomp per-game PPU loader. */
extern uint32_t ppu_vm_size;
int ar_probe_vm_init(void) {
    if (vm_base) return 0;
    const size_t n=16u*1024u*1024u;
    uint8_t *region=(uint8_t*)calloc(n,1);
    if (!region) return -1;
    vm_base=region;
    ppu_vm_size=(uint32_t)n;
    return 0;
}
void ar_probe_vm_shutdown(void) {
    uint8_t *old=vm_base;
    vm_base=0;ppu_vm_size=0;
    free(old);
}
#ifdef __cplusplus
}
#endif
