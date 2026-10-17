/* M7.29 synthetic PPC64 FPR memory, convert, divide and FPSCR tests.
 * No private game code, ELF payload, firmware or keys.
 */
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include "ppu_bridge.h"
#include "ppu_fp_scalar.h"
static void b16(uint8_t*p,uint16_t n){p[0]=n>>8;p[1]=(uint8_t)n;}
static void b32(uint8_t*p,uint32_t n){p[0]=n>>24;p[1]=n>>16;p[2]=n>>8;p[3]=(uint8_t)n;}
static void b64(uint8_t*p,uint64_t n){b32(p,(uint32_t)(n>>32));b32(p+4,(uint32_t)n);}
static uint32_t d(unsigned op,unsigned rt,unsigned ra,unsigned disp){
 return (op<<26)|(rt<<21)|(ra<<16)|(disp&65535u);
}
static uint32_t f(unsigned ft,unsigned fa,unsigned fb,unsigned xo,unsigned rc){
 return (63u<<26)|(ft<<21)|(fa<<16)|(fb<<11)|(xo<<1)|rc;
}
static int step(uint8_t*elf,ppu_context*c,uint32_t word){
 b32(elf+0x200,word);
 if(ar_vm_load(0x1000,elf+0x200,4)!=AR_OK)return -99;
 uint32_t observed=0;
 int result=ar_ppc_fallback_step(c,elf,1024,0x1000,&observed);
 return observed==word?result:-98;
}
int main(void){
 uint8_t elf[1024]={0};
 memcpy(elf,"\177ELF",4);elf[4]=2;elf[5]=2;elf[6]=1;
 b16(elf+16,2);b16(elf+18,21);b32(elf+20,1);
 b64(elf+32,64);b16(elf+54,56);b16(elf+56,1);
 uint8_t*ph=elf+64;b32(ph,1);b32(ph+4,5);
 b64(ph+8,0x200);b64(ph+16,0x1000);
 b64(ph+32,0x100);b64(ph+40,0x100);
 if(ar_bridge_init(0x4000)!=AR_OK)return 1;
 uint32_t script[]={d(50,0,1,128),f(13,0,0,846,0),d(48,0,2,0),
                   f(0,13,0,18,0),d(54,0,11,0),0x4e800020};
 for(unsigned i=0;i<6;i++)b32(elf+0x200+4*i,script[i]);
 if(ar_vm_load(0x1000,elf+0x200,24)!=AR_OK ||
    ar_ppc_fallback_attach(elf,sizeof(elf),64,ar_ppc_fallback_step)!=AR_OK)return 2;
 uint8_t num[8]={0,0,0,0,0x04,0xc1,0xa6,0xc0}; /* 79800000 */
 uint8_t den[4]={0x40,0,0,0}; /* float 2.0 */
 if(ar_vm_load(0x1880,num,8)!=AR_OK ||
    ar_vm_load(0x1900,den,4)!=AR_OK)return 3;
 ppu_context c={0};c.lr=0x1100;c.gpr[1]=0x1800;
 c.gpr[2]=0x1900;c.gpr[11]=0x1a00;
 if(ar_run(&c,0x1000,64)!=AR_OK)return 4;
 if(c.fpr[13]!=79800000.0||c.fpr[0]!=39900000.0 ||
    ar_read64(0x1a00)!=UINT64_C(0x4183069b00000000)||
    (c.fpscr&UINT32_C(0x1f000))!=UINT32_C(0x4000)||
    (c.fpscr&UINT32_C(0x82060000))!=0)return 5;
 ar_aot_trace t={0};ar_trace_snapshot(&t);
 if(t.fp_loads!=2||t.fp_stores!=1||t.fp_converts!=1||t.fp_divides!=1||
    t.fp_last_pc!=0x1010||t.fallback_steps!=6||t.aot_dispatches!=0)return 6;
 /* FCFID input bits mean signed i64, not double! */
 uint64_t raw=42u;memcpy(&c.fpr[0],&raw,8);
 c.fpscr=0;
 if(step(elf,&c,f(13,0,0,846,0))!=AR_TAIL||c.fpr[13]!=42.0)return 7;
 raw=UINT64_C(0x7fffffffffffffff);memcpy(&c.fpr[0],&raw,8);
 c.fpr[13]=99.0;
 if(step(elf,&c,f(13,0,0,846,0))!=AR_PPC_UNSUPPORTED||c.fpr[13]!=99.0)return 8;
 /* Division by zero must not modify result or FPSCR. */
 c.fpr[13]=14;c.fpr[0]=0;c.fpr[1]=33;c.fpscr=0;
 if(step(elf,&c,f(1,13,0,18,0))!=AR_PPC_UNSUPPORTED||
    c.fpr[1]!=33||c.fpscr!=0)return 9;
 c.fpr[0]=2.0;c.fpscr=1;
 if(step(elf,&c,f(1,13,0,18,0))!=AR_PPC_UNSUPPORTED||
    c.fpr[1]!=33||c.fpscr!=1)return 10;
 c.fpscr=0;c.cr=UINT32_C(0xaabbccdd);
 if(step(elf,&c,f(1,13,0,18,1))!=AR_PPC_UNSUPPORTED ||
    c.cr!=UINT32_C(0xaabbccdd))return 11;
 /* Inexact quotient updates sticky XX, FX plus FI. */
 c.fpr[13]=1.0;c.fpr[0]=3.0;c.fpscr=0;
 if(step(elf,&c,f(1,13,0,18,0))!=AR_TAIL||
    !(c.fpr[1]>0.333&&c.fpr[1]<0.334)||
    (c.fpscr&UINT32_C(0x82020000))!=UINT32_C(0x82020000))return 12;
 ar_bridge_shutdown();
 puts("M7.29 PPC64 raw FPR lfd/fcfid/lfs/fdiv/stfd + FPSCR and fail-closed PASS");
 return 0;
}
