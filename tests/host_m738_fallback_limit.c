/* M7.38 regression: the user-observed loader=-38 happened because the
 * installer asked for 16384 PPC fallback steps but runtime rejected >4096.
 * Exercise the *actual* ar_ppc_fallback_attach and ar_run paths on Mac.
 * Synthetic PPC evaluator only; not authenticated owner game execution.
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
static int synthetic(ppu_context *c,const uint8_t *elf,size_t elf_len,
                     uint32_t pc,uint32_t *word){
  if(!c||!elf||elf_len<64u||!word)return AR_BAD_ARGS;
  *word=UINT32_C(0x60000000);
  c->cia=pc+4u;return AR_TAIL;
}
int main(void){
  uint8_t fake[64]={0};memcpy(fake,"\177ELF",4);
  if(AR_PPC_FALLBACK_MAX_STEPS!=16384u)return 1;
  if(ar_ppc_fallback_attach(fake,sizeof(fake),16384u,synthetic)!=AR_BAD_ARGS)
     return 2; /* must initialize the VM first */
  if(ar_bridge_init(0x4000u)!=AR_OK)return 3;
  if(ar_ppc_fallback_attach(fake,sizeof(fake),0u,synthetic)!=AR_BAD_ARGS ||
     ar_ppc_fallback_attach(fake,sizeof(fake),16385u,synthetic)!=AR_BAD_ARGS)
     return 4;
  if(ar_ppc_fallback_attach(fake,sizeof(fake),4096u,synthetic)!=AR_OK)
     return 5; /* previous stable limit still works */
  if(ar_ppc_fallback_attach(fake,sizeof(fake),
                           AR_PPC_FALLBACK_MAX_STEPS,synthetic)!=AR_OK)
     return 6; /* M7.37 failure -38 must be fixed here */
  ppu_context cpu={0};cpu.gpr[1]=0x3000u;
  const int rc=ar_run(&cpu,0x1000u,32768u);
  ar_aot_trace trace={0};ar_trace_snapshot(&trace);
  if(rc!=AR_PPC_LIMIT||trace.fallback_steps!=16384u||
     trace.fallback_step_limit!=16384u||trace.aot_dispatches!=0u||
     trace.unique_aot!=0u||ar_last_unresolved()!=0x11000u)
     return 7;
  ar_bridge_shutdown();
  if(ar_ppc_fallback_attach(fake,sizeof(fake),16384u,synthetic)!=AR_BAD_ARGS)
     return 8;
  puts("M7.38 real runtime attach 16384 cap, reject 16385, 16384 PPC fallback steps with separate zero-AOT trace, -38 prevented PASS");
  return 0;
}
