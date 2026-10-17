/* M7.17 bounded static guest PPC reachability, not execution or AOT. */
#ifndef AR_M717_GRAPH_H
#define AR_M717_GRAPH_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define AR_M717_MAX_CALLS 64u
#define AR_M717_MAX_NODES 2048u
typedef struct {
 uint32_t inspected, edges, direct_calls, conditional, indirect;
 uint32_t syscalls, invalid_pc, saturated, call_count;
 uint32_t calls[AR_M717_MAX_CALLS]; /* validated possible direct call targets */
} ar_m717_graph;
int ar_m717_walk(const uint8_t *elf,size_t length,const uint32_t *roots,
                 size_t nroots,uint32_t node_budget,ar_m717_graph *out);
#ifdef __cplusplus
}
#endif
#endif
