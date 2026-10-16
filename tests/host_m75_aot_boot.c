/* M7.5 public synthetic regression: a registered NATIVE AOT entry must
 * perform its own TLS initialization, not inherit the M7.0 smoke's r13.
 * No game code, no commercial ELF, no PowerPC interpreter. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <CommonCrypto/CommonDigest.h>
#include "ppu_bridge.h"

extern int ar_m70_native_runtime_probe(const uint8_t*,size_t,uint32_t,uint32_t[16]);
static unsigned char expected_digest[CC_SHA256_DIGEST_LENGTH];
static unsigned actual_native_calls;
static unsigned native_calls_with_clean_tls;
static unsigned native_hle_calls;

static int test_native_ppu_entry(ppu_context *c) {
    actual_native_calls++;
    /* A pre-run TLS smoke would contaminate the execution: this must be 0. */
    if(c->gpr[13]!=0 || c->gpr[7]!=1u || c->gpr[8]!=0x20050u ||
       c->gpr[9]!=4u || c->gpr[10]!=16u ||
       c->gpr[12]!=0x100000u || c->gpr[2]!=0x20010u)
        return AR_BAD_ARGS;
    native_calls_with_clean_tls++;
    c->gpr[3]=c->gpr[7]; c->gpr[4]=c->gpr[8];
    c->gpr[5]=c->gpr[9]; c->gpr[6]=c->gpr[10];
    c->lr=0x10004u;
    const int rc=ar_guest_call(c,0x10060u);
    if(rc)return rc;
    if(c->gpr[13]!=0x28000u || c->gpr[3]!=0u)
        return AR_BAD_ARGS;
    native_hle_calls++;
    return AR_OK;
}
int ar_private_aot_install_sha256(const unsigned char *digest,size_t n){
    if(!digest || n!=sizeof(expected_digest) ||
       memcmp(digest,expected_digest,sizeof(expected_digest)))
        return AR_BAD_ARGS;
    return ar_register(0x10000u,test_native_ppu_entry);
}
static void put16(uint8_t*d,unsigned p,uint16_t v){
    d[p]=(uint8_t)(v>>8);d[p+1]=(uint8_t)v;
}
static void put32(uint8_t*d,unsigned p,uint32_t v){
    d[p]=(uint8_t)(v>>24);d[p+1]=(uint8_t)(v>>16);
    d[p+2]=(uint8_t)(v>>8);d[p+3]=(uint8_t)v;
}
static void put64(uint8_t*d,unsigned p,uint64_t v){
    put32(d,p,(uint32_t)(v>>32));put32(d,p+4u,(uint32_t)v);
}
static void synthetic_guest(uint8_t*d,size_t len) {
    memset(d,0,len);
    memcpy(d,"\177ELF",4);d[4]=2;d[5]=2;d[6]=1;d[7]=0x66;
    put16(d,16,2);put16(d,18,21);put32(d,20,1);
    put64(d,24,0x20000);put64(d,32,64);
    put16(d,52,64);put16(d,54,56);put16(d,56,3);
    put32(d,64,1);put32(d,68,5);put64(d,72,0x100);
    put64(d,80,0x10000);put64(d,96,0xc0);put64(d,104,0xc0);
    put32(d,120,1);put32(d,124,6);put64(d,128,0x240);
    put64(d,136,0x20000);put64(d,152,0x240);put64(d,160,0x240);
    put32(d,176,0x60000002u);put32(d,180,4);put64(d,184,0x2c0);
    put64(d,192,0x20080);put64(d,208,32);put64(d,216,32);
    put32(d,0x100,0x60000000u);
    put32(d,0x240,0x10000);put32(d,0x244,0x20010);
    /* Synthetic PRX import table, exact same structure as M7.0 fixture */
    put32(d,0x260,0x10060);
    put32(d,0x290,0xdeadbeefu);
    put32(d,0x2c4,0x1b434cecu);
    put32(d,0x2d8,0x200a0);put32(d,0x2dc,0x200cc);
    d[0x2e0]=0x2c;put16(d,0x2e6,1);
    put32(d,0x2f0,0x200d0);put32(d,0x2f4,0x20100);
    put32(d,0x2f8,0x20120);
    memcpy(d+0x310,"sysPrxForUser",14);
    put32(d,0x340,0x744680a2u);put32(d,0x360,0x10060);
    memcpy(d+0x500,d+64,3u*56u);
    put64(d,32,0x500);put16(d,56,4);
    const unsigned p=0x500u+3u*56u;
    put32(d,p,7);put32(d,p+4u,4);
    put64(d,p+8u,0x290u);put64(d,p+16u,0x20050u);
    put64(d,p+32u,4u);put64(d,p+40u,16u);
}
int main(void){
    uint8_t elf[0x900];
    uint32_t out[16]={0};
    synthetic_guest(elf,sizeof(elf));
    if(!CC_SHA256(elf,(CC_LONG)sizeof(elf),expected_digest))return 1;
    int rc=ar_m70_native_runtime_probe(elf,sizeof(elf),0x10060u,out);
    if(rc || (int32_t)out[0] || out[5]!=1u || (int32_t)out[6]!=AR_OK ||
       out[7]!=0u || (int32_t)out[8] || (int32_t)out[9] ||
       (int32_t)out[10] || out[11]!=0u || out[12]!=0x28000u ||
       out[15]!=3u || actual_native_calls!=1u ||
       native_calls_with_clean_tls!=1u || native_hle_calls!=1u){
        fprintf(stderr,"M7.5 AOT+TLS rc=%d loader=%d fn=%u dispatch=%d missing=%x import=%d bind=%d HLE=%d smoke=%d r13=%x bits=%x calls=%u/%u/%u\\n",
            rc,(int32_t)out[0],out[5],(int32_t)out[6],out[7],
            (int32_t)out[8],(int32_t)out[9],(int32_t)out[10],
            (int32_t)out[11],out[12],out[15],actual_native_calls,
            native_calls_with_clean_tls,native_hle_calls);
        return 2;
    }
    /* Authentic ELF validation: a different binary must never register AOT. */
    elf[0x880]^=1u;
    rc=ar_m70_native_runtime_probe(elf,sizeof(elf),0x10060u,out);
    if(rc!=-29 || actual_native_calls!=1u)return 3;
    elf[0x880]^=1u;
    /* No bind means genuine native guest import remains unresolved. */
    rc=ar_m70_native_runtime_probe(elf,sizeof(elf),0u,out);
    if(rc || out[5]!=1u || (int32_t)out[6]!=AR_UNRESOLVED ||
       out[7]!=0x10060u || out[11]!=0u)return 4;
    puts("M7.5 signed AOT entry isolates TLS smoke and runs genuine guest HLE PASS");
    return 0;
}
