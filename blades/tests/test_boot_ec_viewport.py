"""BladesTime offline eShop entitlement and correctly fitted docked/handheld image."""
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]

class BladesTimeBootRegression(unittest.TestCase):
    def test_patch_order_and_scope(self):
        series = (ROOT/"patches/series").read_text().splitlines()
        names = ["0077-vulkan-dagor-log-viewport-scissor-size.patch",
                 "0078-bladestime-offline-eshop-rights-manager.patch",
                 "0079-bladestime-docked-dagor-viewport-720p.patch"]
        for name in names: self.assertEqual(series.count(name), 1)
        self.assertEqual([series.index(name) for name in names],
                         sorted(series.index(name) for name in names))

    def test_rights_offline_without_faking_purchases(self):
        patch = (ROOT/"patches/0078-bladestime-offline-eshop-rights-manager.patch").read_text()
        for required in ("ShopServiceAccessor10Initialize", "ConsumableServiceItemManager10Initialize",
                         "GetProvidableItemIdCount", "h_ec_CsmCount", "ec_blades_time",
                         "GetRequiredBufferSizeToExportSerializedRightData", "return RES_OK"):
            self.assertIn(required, patch)
        self.assertIn("if (!ec_blades_time()) return RES_FAIL;", patch)
        self.assertIn("no-owned-items manager", patch)
        self.assertNotIn("purchased = 1", patch)

    def test_docked_extents_scoped_to_dagor(self):
        patch = (ROOT/"patches/0079-bladestime-docked-dagor-viewport-720p.patch").read_text()
        self.assertIn('strcmp(DM_GAME_ID, "0100CFA00CC74000")', patch)
        self.assertIn('return (VkExtent2D){1280, 720}', patch)
        self.assertIn('return dm_opmode() ? (VkExtent2D){1920, 1080}', patch)

if __name__ == "__main__":
    unittest.main()
