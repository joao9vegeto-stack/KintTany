"""M7.51 source integration gates; runtime evidence still requires iPhone."""
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[1]
class M751(unittest.TestCase):
 def test_guest_io_connected_to_execution_not_detection(self):
  bridge=(R/"ios/ARLivePPUBridge.c").read_text()
  ui=(R/"ios/ARProbeApp.m").read_text()
  service=(R/"runtime/ppu_guest_fs.c").read_text()
  folder=(R/"ios/ARGameFolderStore.m").read_text()
  for x in ("ar_fs_bind_syscalls()","ar_fs_set_host_io(ARGameFolderGuestIO)",
            "ar_fs_snapshot(&last_fs_trace)","ar_m751_register_vsubfp(d,len)"):
   self.assertIn(x,bridge)
  self.assertLess(bridge.index("ar_m750_register_owner(d,len)"),
                  bridge.index("ar_m751_register_vsubfp(d,len)"))
  for x in ("801u","802u","804u","ar_fs_guest_open",
            "ar_fs_guest_read","ar_fs_guest_close","ar_vm_load",
            "/app_home/","NPUA80918","EACCES_CELL"):
   self.assertIn(x,service)
  self.assertIn("openat(current",folder)
  self.assertIn("O_NOFOLLOW",folder)
  self.assertIn("fsMeasured.bytes_read",ui)
  self.assertIn("cellFsRead com bytes positivos",ui)
 def test_vmxfp_genuine_pc(self):
  text=(R/"runtime/ppu_m751_vsubfp.c").read_text()
  vmx=(R/"runtime/ppu_vmx_cell.h").read_text()
  fallback=(R/"runtime/ppu_m720_fallback.c").read_text()
  for x in ("0x003b0604","0x1062184a","ar_vmx_vsubfp",
            "ar_m712_exec_window","ar_read32","ar_register"):
   self.assertIn(x,text)
  self.assertIn("fegetround()!=FE_TONEAREST",vmx)
  self.assertIn("if(xo==74u)",fallback)
 def test_packaged_not_link_only(self):
  build=(R/"tools/build_ios_probe_ipa.sh").read_text()
  workflow=(R/".github/workflows/ascension-recomp-m0.yml").read_text()
  for x in ("ppu_guest_fs.o","ppu_m751_vsubfp.o","_ar_m751_register_vsubfp",
            "_ar_fs_guest_open"):
   self.assertIn(x,build)
  for x in ("host_m751_guest_fs.c","host_m751_vsubfp.c",
            "m751-guest-fs-host.log","m751-vsubfp-host.log"):
   self.assertIn(x,workflow)
if __name__=="__main__":unittest.main()
