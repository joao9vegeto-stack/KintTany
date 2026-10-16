/* M7.6 synthetic test: native AOT basic blocks can cross signed
 * function boundaries with AR_TAIL and call authenticated HLE. */
#include <stdint.h>
#include <stdio.h>
#include "ppu_bridge.h"

static unsigned visited[3], hle_count;
static int block0(ppu_context *c) {
  visited[0]++;
  if(c->gpr[13] != 0u)return AR_BAD_ARGS;
  c->gpr[3]=7u;
  c->cia=0x10010u;
  return AR_TAIL;
}
static int block1(ppu_context *c) {
  visited[1]++;
  if(c->gpr[3]!=7u)return AR_BAD_ARGS;
  c->gpr[3]=9u;
  c->cia=0x10020u;
  return AR_TAIL;
}
static int block2(ppu_context *c) {
  visited[2]++;
  if(c->gpr[3]!=9u)return AR_BAD_ARGS;
  c->cia=0x10040u;
  return AR_TAIL;
}
static int tls_stub(ppu_context *c){
  hle_count++;
  if(c->gpr[3]!=9u || c->gpr[13]!=0u)return AR_BAD_ARGS;
  c->gpr[13]=0x28000u;c->gpr[3]=0u;
  return AR_OK;
}
static int unknown(ppu_context *c) {
  c->cia=0x10048u;return AR_TAIL;
}
int main(void){
  ppu_context cpu;ppu_context_init(&cpu);
  if(ar_bridge_init(0x40000)!=AR_OK)return 1;
  if(ar_register(0x10000u,block0)!=AR_OK ||
     ar_register(0x10010u,block1)!=AR_OK ||
     ar_register(0x10020u,block2)!=AR_OK ||
     ar_bind_import(0x10040u,0x7abcd123u)!=AR_OK ||
     ar_bind_hle(0x7abcd123u,tls_stub)!=AR_OK)return 2;
  cpu.gpr[2]=0x1234u;
  int rc=ar_run(&cpu,0x10000u,16u);
  if(rc!=AR_OK || visited[0]!=1u || visited[1]!=1u || visited[2]!=1u ||
     hle_count!=1u || cpu.gpr[13]!=0x28000u ||
     cpu.gpr[2]!=0x1234u || ar_last_unresolved()!=0u ||
     ar_registered_count()!=3u){
    fprintf(stderr,"tail HLE failed rc=%d visited=%u,%u,%u hle=%u r13=%llx\n",
            rc,visited[0],visited[1],visited[2],hle_count,
            (unsigned long long)cpu.gpr[13]);return 3;
  }
  if(ar_register(0x10030u,unknown)!=AR_OK)return 4;
  cpu.cia=0u;
  rc=ar_run(&cpu,0x10030u,16u);
  if(rc!=AR_UNRESOLVED || ar_last_unresolved()!=0x10048u)return 5;
  ar_bridge_shutdown();
  if(ar_registered_count()!=0u || ar_last_unresolved()!=0u)return 6;
  puts("M7.6 signed AOT multi-block tail dispatch HLE and unresolved PASS");
  return 0;
}
