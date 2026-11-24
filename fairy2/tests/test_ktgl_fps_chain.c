#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "../scripts/ktgl_fps_chain.h"
static uint64_t root=0x2000, nested=0x3000;
static uint32_t fps=30;
static int rd(uint64_t addr,void *out,size_t n) {
    if(addr==0x1000 && n==8)memcpy(out,&root,8);
    else if(addr==0x2170 && n==8)memcpy(out,&nested,8);
    else if(addr==0x318c && n==4)memcpy(out,&fps,4);
    else return 0;
    return 1;
}
int main(void) {
    uint64_t a=0;uint32_t v=0;
    assert(f2_fps_resolve(rd,0x1000,0x170,0x18c,&a,&v)&&a==0x318c&&v==30);
    fps=60;assert(f2_fps_resolve(rd,0x1000,0x170,0x18c,&a,&v)&&v==60);
    fps=0;assert(!f2_fps_resolve(rd,0x1000,0x170,0x18c,&a,&v));
    fps=30;nested=0;assert(!f2_fps_resolve(rd,0x1000,0x170,0x18c,&a,&v));
    nested=0x3001;assert(!f2_fps_resolve(rd,0x1000,0x170,0x18c,&a,&v));
    nested=0x4000;assert(!f2_fps_resolve(rd,0x1000,0x170,0x18c,&a,&v));
    nested=0x3000;root=0;assert(!f2_fps_resolve(rd,0x1000,0x170,0x18c,&a,&v));
    root=UINT64_MAX-7;assert(!f2_fps_resolve(rd,0x1000,0x170,0x18c,&a,&v));
    return 0;
}
