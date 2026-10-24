// Xbox 360 BC1/BC2/BC3 block data -> native host RGBA8. No fake texels.
#pragma once
#include <cstddef>
#include <cstdint>

namespace xowue::graphics {
inline uint8_t Expand5(uint32_t v) { return static_cast<uint8_t>((v<<3)|(v>>2)); }
inline uint8_t Expand6(uint32_t v) { return static_cast<uint8_t>((v<<2)|(v>>4)); }
inline void Decode565(uint16_t v,uint8_t rgba[4]) {
  rgba[0]=Expand5((v>>11)&31u);
  rgba[1]=Expand6((v>>5)&63u);
  rgba[2]=Expand5(v&31u);
  rgba[3]=255u;
}
inline bool DecodeBCBlock(const uint8_t* block,uint32_t format,uint8_t pixels[64]) {
  if(!block||!pixels||!(format==18u||format==19u||format==20u||
                         format==51u||format==52u||format==53u))return false;
  const bool bc1=(format==18u||format==51u);
  const bool bc2=(format==19u||format==52u);
  const uint8_t* color=block+(bc1?0u:8u);
  const uint16_t c0=uint16_t(color[0])|(uint16_t(color[1])<<8u);
  const uint16_t c1=uint16_t(color[2])|(uint16_t(color[3])<<8u);
  uint8_t palette[4][4]{};
  Decode565(c0,palette[0]);Decode565(c1,palette[1]);
  const bool opaque=!bc1||c0>c1;
  for(unsigned c=0;c<3;++c) {
    palette[2][c]=static_cast<uint8_t>((opaque
      ? 2u*palette[0][c]+palette[1][c]
      : uint32_t(palette[0][c])+palette[1][c])/(opaque?3u:2u));
    palette[3][c]=opaque?
      static_cast<uint8_t>((palette[0][c]+2u*palette[1][c])/3u):0u;
  }
  palette[2][3]=255u;palette[3][3]=opaque?255u:0u;
  const uint32_t indices=uint32_t(color[4])|(uint32_t(color[5])<<8u)|
    (uint32_t(color[6])<<16u)|(uint32_t(color[7])<<24u);
  uint8_t alpha[8]{};
  uint64_t alphaBits=0u;
  if(!bc1&&!bc2) {
    alpha[0]=block[0];alpha[1]=block[1];
    for(unsigned k=2;k<8;++k) {
      if(alpha[0]>alpha[1])
        alpha[k]=static_cast<uint8_t>(((8u-k)*alpha[0]+(k-1u)*alpha[1])/7u);
      else if(k<6u)
        alpha[k]=static_cast<uint8_t>(((6u-k)*alpha[0]+(k-1u)*alpha[1])/5u);
      else alpha[k]=k==6u?0u:255u;
    }
    for(unsigned k=0;k<6;++k) alphaBits|=uint64_t(block[k+2])<<(8u*k);
  }
  for(unsigned i=0;i<16;++i) {
    unsigned ci=(indices>>(2u*i))&3u;
    for(unsigned c=0;c<4;++c)pixels[i*4u+c]=palette[ci][c];
    if(bc2) {
      const unsigned a=(block[i/2u]>>((i&1u)*4u))&15u;
      pixels[i*4u+3u]=static_cast<uint8_t>(a*17u);
    } else if(!bc1) pixels[i*4u+3u]=alpha[(alphaBits>>(3u*i))&7u];
  }
  return true;
}
} // namespace xowue::graphics
