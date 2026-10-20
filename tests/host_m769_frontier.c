/* M7.69: real owner PPC 0x0053979C lifted to C; host uses synthetic guest RAM. */
#include "ppu_bridge.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static uint8_t ram[11u*1024u*1024u];static int err;
static uint64_t rd(uint64_t a,unsigned n){if(a>=sizeof ram||n>sizeof ram-a){err=1;return 0;}uint64_t x=0;for(unsigned i=0;i<n;i++)x=(x<<8)|ram[a+i];return x;}
static void wr(uint64_t a,uint64_t x,unsigned n){if(a>=sizeof ram||n>sizeof ram-a){err=1;return;}for(unsigned i=n;i;i--){ram[a+i-1]=(uint8_t)x;x>>=8;}}
uint8_t ar_read8(uint64_t a){return rd(a,1);}
uint16_t ar_read16(uint64_t a){return rd(a,2);}
uint32_t ar_read32(uint64_t a){return rd(a,4);}
uint64_t ar_read64(uint64_t a){return rd(a,8);}
void ar_write8(uint64_t a,uint8_t x){wr(a,x,1);}
void ar_write16(uint64_t a,uint16_t x){wr(a,x,2);}
void ar_write32(uint64_t a,uint32_t x){wr(a,x,4);}
void ar_write64(uint64_t a,uint64_t x){wr(a,x,8);}
int ar_last_error(void){return err?AR_MEM_FAULT:AR_OK;}
int ar_guest_syscall(ppu_context*c){(void)c;return AR_BAD_ARGS;}
void ar_ppc_note_syscall_pc(uint32_t p){(void)p;}
extern int ar_m769_native_0053979c(ppu_context*);
extern int ar_m769_native_005397bc(ppu_context*);
#define CK(v) do{if(!(v))return __LINE__;}while(0)
int main(void){
 ppu_context c;memset(&c,0,sizeof(c));
 uint64_t sp=0xa87c20u,toc=0x83f2b0u;
 wr(toc-22428u,0xa38a28u,4);wr(toc-22432u,0xa38888u,4);
 c.gpr[1]=sp;c.gpr[2]=toc;c.lr=0x539644u;c.cr=0x22000042u;
 CK(ar_m769_native_0053979c(&c)==AR_TAIL);
 CK(c.cia==0x669a84u&&c.lr==0x5397bcu);
 CK(c.gpr[3]==0xa38a40u&&c.gpr[4]==0xa38898u);
 CK(c.gpr[1]==sp-112u&&rd(sp-112u,8)==sp&&rd(sp+16u,8)==0x539644u);
 c.gpr[3]=0;CK(ar_m769_native_005397bc(&c)==AR_TAIL&&c.cia==0x5397c8u);
 c.gpr[3]=1;CK(ar_m769_native_005397bc(&c)==AR_TAIL&&c.cia==0x5397e4u);
 CK(!err);
 puts("M7.69 owner PPC BE LWZ/STDU/STD/BL/CR branch native host PASS");
 return 0;
}
