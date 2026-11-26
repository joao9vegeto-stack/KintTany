#include <stdint.h>
#include <stddef.h>
#include <string.h>
typedef struct { const uint8_t *p; size_t remaining; unsigned bit; } Bits;
static int get(Bits *b, unsigned n, unsigned *v) {
    *v=0;
    while(n--) {
        if(!b->remaining) return 0;
        *v=(*v<<1)|((b->p[b->remaining-1]>>(7-b->bit))&1u);
        if(++b->bit==8){ b->bit=0; --b->remaining; }
    }
    return 1;
}
static uint32_t le(const uint8_t *p) { return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24; }
int nier_crilayla(const uint8_t *c,size_t cn,uint8_t *out,size_t on) {
    if(cn<272 || on<256 || memcmp(c,"CRILAYLA",8)) return 1;
    size_t us=le(c+8), cs=le(c+12);
    if(us!=on-256 || cs>cn-272) return 2;
    memcpy(out,c+16+cs,256);
    Bits b={c+16,cs,0}; size_t w=on;
    while(w>256){
        unsigned flag,x,v;
        if(!get(&b,1,&flag))return 3;
        if(!flag){if(!get(&b,8,&x))return 3;out[--w]=(uint8_t)x;continue;}
        if(!get(&b,13,&x)||!get(&b,2,&v))return 3;
        size_t back=x+3,len=3+v;
        if(v==3){if(!get(&b,3,&v))return 3;len+=v;
            if(v==7){if(!get(&b,5,&v))return 3;len+=v;
                if(v==31) do {if(!get(&b,8,&v))return 3;len+=v;if(len>w-256)return 4;}while(v==255);
            }
        }
        if(len>w-256||back>on-w)return 4;
        if(back>=len){memcpy(out+w-len,out+w+back-len,len);w-=len;}
        else while(len--){--w;out[w]=out[w+back];}
    }
    return 0;
}
