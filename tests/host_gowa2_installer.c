/* Synthetic-only digest/registration orchestration test. No game code. */
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
extern int ar_gowa2_offline_aot_install_sha256(const uint8_t *,size_t);
enum { AR_OK=0, AR_BAD_ARGS=-1 };
static int calls[9];
#define MOCK(I) int ar_gowa2_register_chunk_##I(void) { calls[(int)(0x##I)]++; return AR_OK; }
/* Decimal indices, not hex parsing of leading-zero tokens. */
#define STUB(N,I) int ar_gowa2_register_chunk_##N(void){ calls[I]++;return 0; }
STUB(00,0) STUB(01,1) STUB(02,2) STUB(03,3) STUB(04,4)
STUB(05,5) STUB(06,6) STUB(07,7) STUB(08,8)
int main(void){
 const uint8_t sha[32]={0x4b,0xf7,0x5c,0x89,0x7b,0x82,0xd1,0xbe,
  0xb2,0x55,0x14,0xcb,0xad,0xaf,0xf3,0xd0,
  0x3e,0x1b,0x0c,0x7b,0xf8,0x49,0xfa,0x5d,
  0x28,0x9b,0xe4,0xf9,0x18,0x34,0x62,0xb5};
 uint8_t bad[32];for(int i=0;i<32;i++)bad[i]=sha[i];bad[0]^=1;
 if(ar_gowa2_offline_aot_install_sha256(NULL,32)!=AR_BAD_ARGS)return 1;
 if(ar_gowa2_offline_aot_install_sha256(sha,31)!=AR_BAD_ARGS)return 2;
 if(ar_gowa2_offline_aot_install_sha256(bad,32)!=AR_BAD_ARGS)return 3;
 for(int i=0;i<9;i++)if(calls[i])return 4;
 if(ar_gowa2_offline_aot_install_sha256(sha,32)!=AR_OK)return 5;
 for(int i=0;i<9;i++)if(calls[i]!=1)return 6;
 puts("GOWA2 installer digest regression: bad hash and length rejected, all 9 valid chunks installed only after matching SHA-256 PASS");
 return 0;
}