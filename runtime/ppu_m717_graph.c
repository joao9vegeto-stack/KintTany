/* M7.17: bounded, strictly read-only traversal of executable PPC64/BE ELF.
 * Direct edges are syntactically discovered; they are NOT proven executable
 * at runtime, not validated function boundaries, and not ARM64 compiled.
 */
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "ppu_m717_graph.h"
extern int ar_m712_exec_window(const uint8_t*,size_t,uint32_t,uint32_t[6]);

static int contains(const uint32_t *v,uint32_t n,uint32_t x) {
 for(uint32_t i=0;i<n;i++)if(v[i]==x)return 1;
 return 0;
}
static void enqueue(uint32_t *queue,uint32_t *count,uint32_t pc,
                    ar_m717_graph *out) {
 if(!pc || (pc&3u)) {out->invalid_pc++;return;}
 if(contains(queue,*count,pc))return;
 if(*count>=AR_M717_MAX_NODES){out->saturated=1u;return;}
 queue[(*count)++]=pc;
}
static uint32_t calc_target(uint32_t pc,uint32_t word,int32_t disp) {
 const int64_t addr=(word&2u) ? (int64_t)disp : (int64_t)pc+(int64_t)disp;
 if(addr<0 || addr>UINT32_MAX)return 0u;
 return (uint32_t)addr;
}
int ar_m717_walk(const uint8_t *elf,size_t length,const uint32_t *roots,
                 size_t nroots,uint32_t node_budget,ar_m717_graph *out) {
 if(!out)return -1;
 memset(out,0,sizeof(*out));
 if(!elf || !roots || !nroots || nroots>16u ||
    !node_budget || node_budget>AR_M717_MAX_NODES)return -1;
 uint32_t queue[AR_M717_MAX_NODES]={0};
 uint32_t tail=0u,head=0u;
 for(size_t i=0;i<nroots;i++)enqueue(queue,&tail,roots[i],out);
 while(head<tail && out->inspected<node_budget) {
   const uint32_t pc=queue[head++];
   uint32_t op[6]={0};
   if(ar_m712_exec_window(elf,length,pc,op)!=0 ||
      op[4]<1u || !(op[5]&1u)) {
      out->invalid_pc++;
      continue;
   }
   out->inspected++;
   const uint32_t w=op[0],primary=w>>26;
   const uint32_t next=pc<=UINT32_MAX-4u?pc+4u:0u;
   if(primary==18u) {
      /* b/bl: I-form signed 26-bit displacement including the bottom 00. */
      int32_t off=(int32_t)(w & UINT32_C(0x03fffffc));
      if(off & INT32_C(0x02000000))off-=INT32_C(0x04000000);
      const uint32_t target=calc_target(pc,w,off);
      enqueue(queue,&tail,target,out);
      out->edges++;
      if(w&1u) {
         out->direct_calls++;
         /* Call target is executable PT_LOAD only if individually verified. */
         uint32_t candidate[6]={0};
         if(target && !ar_m712_exec_window(elf,length,target,candidate)
           && (candidate[5]&1u) && candidate[4]) {
             if(!contains(out->calls,out->call_count,target) &&
                out->call_count<AR_M717_MAX_CALLS)
                 out->calls[out->call_count++]=target;
         }
         enqueue(queue,&tail,next,out);
         out->edges++;
      }
      continue;
   }
   if(primary==16u) {
      const int32_t off=(int16_t)(w&UINT32_C(0xfffc));
      const uint32_t target=calc_target(pc,w,off);
      out->conditional++;
      enqueue(queue,&tail,target,out);
      enqueue(queue,&tail,next,out);
      out->edges+=2u;
      continue;
   }
   if(primary==19u) {
      const uint32_t xo=(w>>1)&1023u;
      if(xo==16u || xo==528u) {
          out->indirect++;
          /* BCLR/BCCTR can be conditional. Its dynamic target is unknown. */
          const uint32_t bo=(w>>21)&31u;
          if((bo&20u)!=20u) {enqueue(queue,&tail,next,out);out->edges++;}
          continue;
      }
   }
   if(primary==17u) out->syscalls++;
   /* Other opcodes, including unsupported ISA, are only *inventoried*.
    * This deliberately makes no semantic assertion about their effects. */
   enqueue(queue,&tail,next,out);
   out->edges++;
 }
 if(head<tail)out->saturated=1u;
 return 0;
}
