/* Exact FPSLocker v4 address evaluation, bounded to game-owned memory.
 * Old values are evidence, not a gate: the reference's evaluate_write
 * does not require the field to already contain 30 or 60.
 * Return distinct stages, never an unvalidated destination.
 */
enum f2_status {
    F2_OK=0, F2_ROOT_READ, F2_ROOT_RANGE, F2_NESTED_READ, F2_NESTED_RANGE,
    F2_FIELD_READ, F2_CHANGED, F2_WRITE, F2_READBACK
};
typedef struct { uint64_t root,nested,address; uint32_t value; } f2_chain;
typedef int (*f2_read)(uint64_t,void *,size_t);
typedef int (*f2_span)(uint64_t,size_t,int);
typedef int (*f2_write)(uint64_t,const void *,size_t);
static int f2_fps_resolve(f2_read read_mem,f2_span valid,
                          uint64_t global,uint32_t indirect,uint32_t field,
                          f2_chain *q) {
    *q=(f2_chain){0};
    if (!valid(global,8,0) || !read_mem(global,&q->root,8)) return F2_ROOT_READ;
    if (!q->root || q->root>UINT64_MAX-indirect ||
        !valid(q->root+indirect,8,0)) return F2_ROOT_RANGE;
    if (!read_mem(q->root+indirect,&q->nested,8)) return F2_NESTED_READ;
    if (!q->nested || q->nested>UINT64_MAX-field ||
        !valid(q->nested+field,4,1)) return F2_NESTED_RANGE;
    q->address=q->nested+field;
    if (!read_mem(q->address,&q->value,4)) return F2_FIELD_READ;
    return F2_OK;
}
static int f2_fps_apply(f2_read rd,f2_span valid,f2_write wr,
                        uint64_t global,uint32_t indirect,uint32_t field,
                        uint32_t want,f2_chain *q,uint32_t *applied) {
    *applied=0;
    int st=f2_fps_resolve(rd,valid,global,indirect,field,q);
    if (st!=F2_OK) return st;
    if (want!=30 && want!=60) return F2_WRITE;
    if (q->value!=want) {
        f2_chain again;
        st=f2_fps_resolve(rd,valid,global,indirect,field,&again);
        if (st!=F2_OK) return st;
        if (again.root!=q->root || again.nested!=q->nested ||
            again.address!=q->address) return F2_CHANGED;
        if (again.value!=want && !wr(q->address,&want,4)) return F2_WRITE;
    }
    if (!rd(q->address,applied,4) || *applied!=want) return F2_READBACK;
    return F2_OK;
}
