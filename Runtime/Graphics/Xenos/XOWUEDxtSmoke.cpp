#include "XOWUEDxt.h"
#include <cassert>
#include <cstdio>
int main() {
  uint8_t pixels[64]{};
  uint8_t bc1[8]={0x00,0xF8,0xE0,0x07,0,0,0,0}; // RGB565 red/green
  assert(xowue::graphics::DecodeBCBlock(bc1,18u,pixels));
  assert(pixels[0]==255u&&pixels[1]==0u&&pixels[2]==0u&&pixels[3]==255u);
  uint8_t bc2[16]={0};
  for(int i=0;i<8;++i)bc2[i]=0xFF;
  for(int i=0;i<8;++i)bc2[i+8]=bc1[i];
  assert(xowue::graphics::DecodeBCBlock(bc2,19u,pixels));
  assert(pixels[3]==255u && pixels[63]==255u);
  uint8_t bc3[16]={0};
  bc3[0]=255u;bc3[1]=0u;
  for(int i=0;i<8;++i)bc3[i+8]=bc1[i];
  assert(xowue::graphics::DecodeBCBlock(bc3,20u,pixels));
  assert(pixels[3]==255u);
  assert(!xowue::graphics::DecodeBCBlock(bc1,6u,pixels));
  std::puts("PASS: native BC1 BC2 BC3 RGBA decoding");
}
