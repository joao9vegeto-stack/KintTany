/* M7.31: authenticated native ARM64 frontier, a real PPU guest block.
 *
 * The owner-original ELF is imported locally, never checked into GitHub.
 * This contains generic Power ISA CR transfer semantics, no ELF bytes.
 * Called only after the private whole-ELF SHA-256 AOT gate succeeded.
 *
 * This TWO-INSTRUCTION block is a beginning, not complete game recompilation:
 * MT(O)CRF FXM=0x08,RS=r12 (CR4) followed by BLR.
 */
#include <stdint.h>
#include <stddef.h>
#include "ppu_bridge.h"
extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);

#define AR_M731_PC UINT32_C(0x0052da5c)
#define AR_M731_CR4 UINT32_C(0x0000f000)

int ar_m731_native_0052da5c(ppu_context *c){
 if(!c)return AR_BAD_ARGS;
 /* L=1 is mtocrf: GPR[12] field CR4 replaces only bits 12..15.
  * PPC CR4 corresponds to FXM bit 0x08; preserve other CR fields. */
 c->cr=(c->cr&~AR_M731_CR4)|((uint32_t)c->gpr[12]&AR_M731_CR4);
 /* Exact authenticated second word is BLR. Preserve LR and all GPRs.
  * Returning AR_OK unwinds this guest function, as other native AOT do. */
 c->cia=c->lr&~UINT64_C(3);
 return AR_OK;
}

/* Independent ELF provenance: verify exact canonical ISA fields at the
 * observed executable guest PC without copying proprietary game bytes.
 * The private SHA-256 installer must have succeeded before calling this. */
int ar_m731_register_frontier(const uint8_t *elf,size_t length){
 if(!elf||length<64u)return AR_BAD_ARGS;
 uint32_t got[6]={0};
 if(ar_m712_exec_window(elf,length,AR_M731_PC,got)!=AR_OK ||
    got[4]<2u || !(got[5]&1u))return AR_BAD_ARGS;
 const uint32_t mt=got[0],ret=got[1];
 if((mt>>26)!=31u || ((mt>>1)&1023u)!=144u ||
    ((mt>>21)&31u)!=12u || ((mt>>12)&255u)!=8u ||
    ((mt>>20)&1u)!=1u || (mt&UINT32_C(0x00000801)) ||
    ret!=UINT32_C(0x4e800020))return AR_BAD_ARGS;
 /* Cross-check loaded guest bytes: don't execute stale/unmapped code. */
 if(ar_read32(AR_M731_PC)!=mt ||
    ar_read32(AR_M731_PC+4u)!=ret ||
    ar_last_error()!=AR_OK)return AR_BAD_ARGS;
 return ar_register(AR_M731_PC,ar_m731_native_0052da5c);
}
