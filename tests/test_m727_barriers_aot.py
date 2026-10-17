"""M7.27 Power ISA memory barriers: actual native C code generation tests.

Synthetic words only; verifies that EIEIO/SYNC/LWSYNC/ISYNC emit host
memory fences rather than NOPs, and rejects all nonarchitectural encodings.
"""
from __future__ import annotations
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_m23_cfg_lifter import BLR, run_c, li
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from ppu_cfg_lifter import Unsupported, lift

EIEIO=0x7c0006ac
SYNC=0x7c0004ac
LWSYNC=0x7c2004ac
ISYNC=0x4c00012c

class M727Barriers(unittest.TestCase):
    def test_eieio_exact_native_fence(self):
        src,h=lift([EIEIO,BLR],0x10000)
        self.assertEqual(h.get('eieio'),1)
        self.assertEqual(src.count('__atomic_thread_fence(__ATOMIC_SEQ_CST);'),1)
        self.assertNotIn('ar_ppc_fallback_step',src)

    def test_eieio_retains_correct_native_register_flow(self):
        run_c([li(3,0x1234),EIEIO,li(4,7),BLR],
              checks=['rc==0','ctx.gpr[3]==0x1234ULL',
                      'ctx.gpr[4]==7ULL','ctx.cia==0x1234ULL'])

    def test_repeated_eieio_is_not_collapsed(self):
        src,h=lift([EIEIO,EIEIO,EIEIO,BLR],0x10000)
        self.assertEqual(h.get('eieio'),3)
        self.assertEqual(src.count('__atomic_thread_fence(__ATOMIC_SEQ_CST);'),3)
        run_c([EIEIO,EIEIO,EIEIO,BLR],
              checks=['rc==0','ctx.cr==0U','ctx.xer==0U'])

    def test_sync_lwsync_isync_have_host_fences(self):
        src,h=lift([SYNC,LWSYNC,ISYNC,BLR],0x10000)
        for item in ('sync','lwsync','isync'):
            self.assertEqual(h.get(item),1)
        self.assertEqual(src.count('__atomic_thread_fence(__ATOMIC_SEQ_CST);'),3)
        run_c([SYNC,LWSYNC,ISYNC,BLR],
              checks=['rc==0','ctx.cr==0U','ctx.xer==0U',
                      'ctx.cia==0x1234ULL'])

    def test_nonstandard_forms_never_become_nops(self):
        for word in (0x7c2006ac,0x7c0006ad,0x7c4004ac,
                     0x7c6004ac,0x4c20012c,0x4c00012d):
            with self.subTest(word=f'{word:08X}'):
                with self.assertRaises(Unsupported):
                    lift([word,BLR],0x10000)

    def test_unsupported_opcode_still_halts(self):
        with self.assertRaises(Unsupported):
            lift([EIEIO,0xffffffff,BLR],0x10000)

if __name__=='__main__':unittest.main()
