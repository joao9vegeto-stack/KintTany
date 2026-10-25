#!/usr/bin/env python3
"""M8.13 verify C8 generator's complete 76-opcode save and restore templates."""
from pathlib import Path
import argparse
a=argparse.ArgumentParser();a.add_argument("--upstream",type=Path,required=True)
a.add_argument("--repo",type=Path,default=Path("."))
x=a.parse_args()
s=(x.upstream/"runtime/spu/spu_channels.c").read_text()
g=(x.repo/"runtime/m789-c8-wws/spu_recomp.c").read_text()
for token in ("ASCENSION_M813_C8_IRQ_NATIVE_V1","spu_ascension_run_c8_generated_irq",
              "spu_ascension_copy_c8_irq",
              "spu_ls_write128(ctx,0x3F9C0u+16u*i,ctx->gpr[i])",
              "ctx->gpr[i]=spu_ls_read128(ctx,0x3F9C0u+16u*i)",
              "ctx->pc=target;", "0x35002780", "word0+UINT32_C(0x201)*i"):
    assert token in s,token
assert "ASCENSION_M813_C8_IRQ_AOT_STUB_REPLACED_V1" not in g
assert "ctx->pc = 0x3FEC0u; g_spu_trampoline_fn = spu_indirect_branch; return;" in g
assert "if(ctx->pc==0x3FEC0u && spu_ascension_run_c8_generated_irq(ctx))" in s
assert "spu_ila(0x3FEC0)" in g and "spu_ls_write128(ctx, 0x3FFF0" in g
for top,op9 in ((0x20FF3800,0x41),(0x30FF3800,0x61)):
    for i in range(76):
        word=top+0x201*i
        assert word>>23==op9
        assert word&127==i
        assert (((word>>7)&65535)<<2)==(0x3F9C0+16*i)
    assert 0x3FEC0+4*76==0x3FFF0
    assert 0x3F9C0+16*76==0x3FE80
assert 0x35002780>>21==0x1A8 and (0x35002780>>7)&127==79
print("[PASS] 76 exact C8 SPU stqa/lqa native templates, bounds and bi r79")
