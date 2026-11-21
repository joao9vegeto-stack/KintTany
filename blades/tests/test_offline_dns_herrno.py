"""Validate the precise SDK 9.4 DNS TLS error-pointer fix."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
PATCH="0081-bladestime-offline-dns-host-errno-tls.patch"

class OfflineDNSHostErrnoTest(unittest.TestCase):
    def test_missing_tls_service_produces_valid_thread_local_h_errno(self):
        text=(ROOT/"patches"/PATCH).read_text()
        self.assertIn("Client17InternalHostErrnoEv",text)
        self.assertIn("static __thread int t_sk_herrno = 3",text)
        self.assertIn("return &t_sk_herrno",text)
        self.assertIn("NO_RECOVERY",text)
        self.assertNotIn("return RES_OK",text)
        self.assertNotIn("SK_ENETDOWN = 0",text)
        series=(ROOT/"patches/series").read_text().splitlines()
        self.assertEqual(series.count(PATCH),1)
        self.assertLess(series.index("0080-bladestime-extend-vulkan-capture-through-intro.patch"),series.index(PATCH))

if __name__=="__main__":
    unittest.main()
