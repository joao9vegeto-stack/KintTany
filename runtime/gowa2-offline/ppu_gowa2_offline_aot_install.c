/* Generated PPU AOT registration batch for prefix gowa2. */
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "ppu_bridge.h"
extern int ar_gowa2_register_chunk_00(void);
extern int ar_gowa2_register_chunk_01(void);
extern int ar_gowa2_register_chunk_02(void);
extern int ar_gowa2_register_chunk_03(void);
extern int ar_gowa2_register_chunk_04(void);
extern int ar_gowa2_register_chunk_05(void);
extern int ar_gowa2_register_chunk_06(void);
extern int ar_gowa2_register_chunk_07(void);
extern int ar_gowa2_register_chunk_08(void);
static const uint8_t source_sha256[32]={0x4b, 0xf7, 0x5c, 0x89, 0x7b, 0x82, 0xd1, 0xbe, 0xb2, 0x55, 0x14, 0xcb, 0xad, 0xaf, 0xf3, 0xd0, 0x3e, 0x1b, 0x0c, 0x7b, 0xf8, 0x49, 0xfa, 0x5d, 0x28, 0x9b, 0xe4, 0xf9, 0x18, 0x34, 0x62, 0xb5};
int ar_gowa2_offline_aot_install_sha256(const uint8_t *digest,size_t size){
  if(!digest||size!=32u||memcmp(digest,source_sha256,32u))return AR_BAD_ARGS;
  {int rc=ar_gowa2_register_chunk_00();if(rc!=AR_OK)return rc;}
  {int rc=ar_gowa2_register_chunk_01();if(rc!=AR_OK)return rc;}
  {int rc=ar_gowa2_register_chunk_02();if(rc!=AR_OK)return rc;}
  {int rc=ar_gowa2_register_chunk_03();if(rc!=AR_OK)return rc;}
  {int rc=ar_gowa2_register_chunk_04();if(rc!=AR_OK)return rc;}
  {int rc=ar_gowa2_register_chunk_05();if(rc!=AR_OK)return rc;}
  {int rc=ar_gowa2_register_chunk_06();if(rc!=AR_OK)return rc;}
  {int rc=ar_gowa2_register_chunk_07();if(rc!=AR_OK)return rc;}
  {int rc=ar_gowa2_register_chunk_08();if(rc!=AR_OK)return rc;}
  return AR_OK;
}