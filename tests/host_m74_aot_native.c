/* M7.4: REAL host-native AOT functions GENERATED from synthetic PPC64 words.
 * This test NEVER calls the PowerPC interpreter. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include "ppu_bridge.h"
#include "m74_digest.h"
extern int ar_private_aot_install_sha256(const unsigned char*,size_t);
int main(void) {
    static const unsigned char digest[32] = AR_M74_DIGEST;
    unsigned char invalid[32];
    for (unsigned i=0;i<32;i++) invalid[i] = digest[i]^0xffu;
    if(ar_bridge_init(0x20000u)!=AR_OK) return 1;
    ppu_context cpu; ppu_context_init(&cpu);
    if(ar_run(&cpu,0x10000u,64u)!=AR_UNRESOLVED ||
       ar_last_unresolved()!=0x10000u || ar_registered_count()!=0u)
        return 2;
    if(ar_private_aot_install_sha256(invalid,32u)!=AR_BAD_ARGS ||
       ar_registered_count()!=0u) return 3;
    if(ar_private_aot_install_sha256(digest,31u)!=AR_BAD_ARGS ||
       ar_registered_count()!=0u) return 4;
    if(ar_private_aot_install_sha256(digest,32u)!=AR_OK ||
       ar_registered_count()!=2u) return 5;
    ppu_context_init(&cpu);
    if(ar_run(&cpu,0x10000u,64u)!=AR_OK || cpu.gpr[3]!=7u)
        return 6;
    ppu_context_init(&cpu);
    if(ar_run(&cpu,0x10010u,64u)!=AR_OK || cpu.gpr[3]!=7u)
        return 7;
    ar_bridge_shutdown();
    if(ar_registered_count()!=0u) return 8;
    puts("M7.4 generated PPC functions executed as host-native AOT via dispatch PASS");
    return 0;
}
