/* M7.61 host execution of the SAME 18 genuine PPC words at 0x003E16E0.
 * Exercises STDU/STD/LD + LR/BL/BLR + guest BE LWZ/STW, no PPC runtime.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "ppu_bridge.h"
extern int ar_m761_native_003e16e0(ppu_context *);
static uint64_t stack1_addr,stack1_value,stack2_addr,stack2_value;
static uint32_t store1_addr,store1_val,store2_addr,store2_val;
static uint32_t called_target,calls;
int ar_last_error(void){return AR_OK;}
uint32_t ar_read32(uint64_t va) {
 assert(va==UINT64_C(0x009c57a0));
 return UINT32_C(0x00123456);
}
uint64_t ar_read64(uint64_t va) {
 if(va==stack1_addr)return stack1_value;
 if(va==stack2_addr)return stack2_value;
 assert(!"unexpected guest LD");return 0;
}
void ar_write64(uint64_t va,uint64_t value) {
 if(!stack1_addr){stack1_addr=va;stack1_value=value;return;}
 stack2_addr=va;stack2_value=value;
}
void ar_write32(uint64_t va,uint32_t value) {
 if(!store1_addr){store1_addr=(uint32_t)va;store1_val=value;return;}
 store2_addr=(uint32_t)va;store2_val=value;
}
int ar_guest_call(ppu_context *c,uint64_t target) {
 calls++; called_target=(uint32_t)target;
 assert(target==UINT64_C(0x003c5218));
 assert(c->lr==UINT64_C(0x003e1700));
 return AR_OK;
}
int main(void) {
 ppu_context ctx;memset(&ctx,0,sizeof(ctx));
 const uint64_t original_sp=UINT64_C(0x00a88000);
 const uint64_t original_lr=UINT64_C(0x002c1708);
 ctx.gpr[1]=original_sp;
 ctx.lr=original_lr;
 const int result=ar_m761_native_003e16e0(&ctx);
 assert(result==AR_OK);
 assert(calls==1 && called_target==UINT32_C(0x003c5218));
 assert(stack1_addr==original_sp-0x70u && stack1_value==original_sp);
 assert(stack2_addr==original_sp+0x10u && stack2_value==original_lr);
 assert(ctx.gpr[1]==original_sp && ctx.lr==original_lr &&
        ctx.cia==original_lr);
 assert(store1_addr==UINT32_C(0x009c8114) && store1_val==UINT32_C(0x00123456));
 assert(store2_addr==UINT32_C(0x0084b9fc) && store2_val==UINT32_C(0x00127456));
 printf("M7.61 PPC STOP native host: 18 PPC / BL->0x003C5218 / LR-STACK-VM preserved PASS\n");
 return 0;
}
