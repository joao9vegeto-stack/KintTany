/* M7.44: native C->Apple ARM64 translation of two authentic NPUA80918
 * PowerPC64 instructions at the last observed iPhone blockade:
 * 0x003F2860 cror 2,0,5 ; 0x003F2864 bc 12,2,+8.
 * No JIT or runtime instruction decoder is used by this AOT entry.
 * Requires the previously verified SHA-256 GOWA.ELF gate AND exact guest
 * executable bytes + loaded VM confirmation before registration.
 */
#include <stdint.h>
#include <stddef.h>
#include "ppu_bridge.h"
extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);

#define AR_M744_PC UINT32_C(0x003f2860)
#define AR_M744_CROR UINT32_C(0x4c402b82)
#define AR_M744_BEQ UINT32_C(0x41820008)

int ar_m744_native_003f2860(ppu_context *c){
 if(!c)return AR_BAD_ARGS;
 /* PPC CR bit 0 and bit 5 are stored at host bits 31 and 26.
  * CROR BT=2,BA=0,BB=5 writes only host CR bit 29. */
 const uint32_t old_cr=c->cr;
 const uint32_t cond=((old_cr>>31u)|(old_cr>>26u))&1u;
 c->cr=(old_cr&~(UINT32_C(1)<<29u))|(cond<<29u);
 /* bc BO=12 BI=2, relative +8, no CTR decrement, no LK.
  * True branch skips the ADDIC at 0x003F2868. LR/CTR/XER untouched. */
 c->cia=cond?UINT32_C(0x003f286c):UINT32_C(0x003f2868);
 return AR_TAIL;
}

int ar_m744_register_owner(const uint8_t *elf,size_t len){
 if(!elf||len<64u)return AR_BAD_ARGS;
 uint32_t words[6]={0};
 if(ar_m712_exec_window(elf,len,AR_M744_PC,words)!=AR_OK ||
    words[4]<2u || !(words[5]&1u) ||
    words[0]!=AR_M744_CROR || words[1]!=AR_M744_BEQ)
   return AR_BAD_ARGS;
 if(ar_read32(AR_M744_PC)!=AR_M744_CROR ||
    ar_read32(AR_M744_PC+4u)!=AR_M744_BEQ ||
    ar_last_error()!=AR_OK)return AR_BAD_ARGS;
 return ar_register(AR_M744_PC,ar_m744_native_003f2860);
}
