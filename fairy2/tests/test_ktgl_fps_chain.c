#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "../scripts/ktgl_fps_chain.h"
static uint64_t root=0x2000,nested=0x3000;
static uint32_t fps=30;
static int writes,fail_write,fail_readback,swap_root,root_reads;
static int valid(uint64_t a,size_t n,int write) {
    if (write) return a>=0x3100 && a+n<=0x3200;
    return a>=0x1000 && a+n<=0x4000;
}
static int rd(uint64_t a,void *p,size_t n) {
    if(a==0x1000 && n==8) {
        uint64_t v=(swap_root && ++root_reads>1)?0x2100:root;
        memcpy(p,&v,8);
    } else if((a==0x2170 || a==0x2270) && n==8) memcpy(p,&nested,8);
    else if(a==nested+0x18c && n==4) {
        if(fail_readback && writes)return 0;
        memcpy(p,&fps,4);
    } else return 0;
    return 1;
}
static int wr(uint64_t a,const void *p,size_t n) {
    if(fail_write || a!=nested+0x18c || n!=4)return 0;
    memcpy(&fps,p,n);writes++;return 1;
}
int main(void) {
    f2_chain q;uint32_t applied;
    assert(f2_fps_apply(rd,valid,wr,0x1000,0x170,0x18c,60,&q,&applied)==F2_OK);
    assert(q.value==30 && applied==60 && writes==1);
    uint32_t values[]={0,1,15,24,25,30,45,60,120,UINT32_MAX};
    for(size_t i=0;i<sizeof values/sizeof values[0];i++) {
        fps=values[i];assert(f2_fps_apply(rd,valid,wr,0x1000,0x170,0x18c,60,&q,&applied)==F2_OK && fps==60);
    }
    assert(f2_fps_apply(rd,valid,wr,0x1000,0x170,0x18c,30,&q,&applied)==F2_OK && fps==30);
    nested=0;assert(f2_fps_resolve(rd,valid,0x1000,0x170,0x18c,&q)==F2_NESTED_RANGE);
    nested=0x3001;assert(f2_fps_resolve(rd,valid,0x1000,0x170,0x18c,&q)==F2_OK);
    nested=0x4000;assert(f2_fps_resolve(rd,valid,0x1000,0x170,0x18c,&q)==F2_NESTED_RANGE);
    nested=0x3000;root=0;assert(f2_fps_resolve(rd,valid,0x1000,0x170,0x18c,&q)==F2_ROOT_RANGE);
    root=UINT64_MAX-7;assert(f2_fps_resolve(rd,valid,0x1000,0x170,0x18c,&q)==F2_ROOT_RANGE);
    root=0x2000;fps=30;fail_write=1;
    assert(f2_fps_apply(rd,valid,wr,0x1000,0x170,0x18c,60,&q,&applied)==F2_WRITE && fps==30);
    fail_write=0;swap_root=1;root_reads=0;
    assert(f2_fps_apply(rd,valid,wr,0x1000,0x170,0x18c,60,&q,&applied)==F2_CHANGED && fps==30);
    swap_root=0;fail_readback=1;writes=0;
    assert(f2_fps_apply(rd,valid,wr,0x1000,0x170,0x18c,60,&q,&applied)==F2_READBACK);
    return 0;
}
