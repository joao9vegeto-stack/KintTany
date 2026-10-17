#!/usr/bin/env python3
"""PsTJohn1 1.2: control NPUA80918 Vulkan query capacity while preserving correctness.
Physical Ascension 1.1.2: ~8 FPS, 1143 ZCull hard syncs, OOM pressure and RSX freeze.
Existing software 4096/3584 headroom is already active. Change only hardware
query pool 512->768, with low-volume exhaustion telemetry. Device A/B is required.
"""
from pathlib import Path

root = Path("rpcs3-src/rpcs3")
render = root / "Emu/RSX/VK/VKGSRender.cpp"
pool = root / "Emu/RSX/VK/VKQueryPool.cpp"
soft = root / "Emu/RSX/RSXZCULL.cpp"
gates = []

s = soft.read_text()
assert s.count("m63_capacity = 4096;") == 1
assert s.count("m63_queue_threshold = 3584;") == 1
assert s.count('Emu.GetTitleID() == "BCUS98232" || Emu.GetTitleID() == "NPUA80918"') == 2
assert "std::array<occlusion_query_info, occlusion_query_count>" in (root / "Emu/RSX/RSXZCULL.h").read_text()
gates.append("Existing 4096 slots/3584 threshold unchanged for Ascension")

s = render.read_text()
a = s.index("m_occlusion_query_manager = std::make_unique<vk::query_pool_manager>")
b = s.index(";", a)
clause = s[a:b]
old = '(Emu.GetTitleID() == "BCUS98232" || Emu.GetTitleID() == "NPUA80918") ? 512'
new = '(Emu.GetTitleID() == "BCUS98232") ? 512 : (Emu.GetTitleID() == "NPUA80918") ? 768'
assert clause.count(old) == 1, "Vulkan query pool selector changed"
assert 'NPUB31372' in clause and 'NPUB30818' in clause
assert 'std::min<u32>(OCCLUSION_MAX_POOL_SIZE, 512u)' in clause
clause = clause.replace(old, new, 1)
s = s[:a] + clause + s[b:]
old_log = "M6.8.2 NPUA_ASCENSION_QUERY_POOL: Vulkan occlusion pool=512 vs previous default"
new_log = "PsTJohn1.2 NPUA_ASCENSION_VK_QUERY_AB: Vulkan occlusion pool=768 vs 1.1.2 pool=512"
assert s.count(old_log) == 1
s = s.replace(old_log, new_log, 1)
assert "M6.8.6 NPUA_FATAL_SYNC" in s
assert "M6.8.5 RSX_PRESSURE_SUMMARY" in s
assert "M6.8 PIPELINE_BUDGET" in s
render.write_text(s)
gates.append("NPUA 512->768 only; BCUS and DmC/other queries unchanged")

s = pool.read_text()
start = s.index("u32 query_pool_manager::allocate_query(vk::command_buffer& cmd)")
end = s.index("void query_pool_manager::on_query_pool_released", start)
part = s[start:end]
assert part.count("return ~0u;") == 1
assert part.count("if (!m_available_slots.empty())") == 1
guard = r'''#ifdef RPCS3_IOS
		// PsTJohn1.2: log true allocation exhaustion, never fake ZCull results.
		if (Emu.GetTitleID() == "NPUA80918")
		{
			static u64 m12_query_starvations = 0;
			const u64 total = ++m12_query_starvations;
			if ((total & (total - 1)) == 0)
			{
				rsx_log.warning("PsTJohn1.2 NPUA_VK_QUERY_STARVATION: exhausted=%llu capacity=%u sync_policy=unchanged",
					total, ::size32(query_slot_status));
			}
		}
#endif
		return ~0u;'''
part = part.replace("return ~0u;", guard, 1)
s = s[:start] + part + s[end:]
assert s.count("PsTJohn1.2 NPUA_VK_QUERY_STARVATION") == 1
assert "M6.8.7 VULKAN_QUERY_RECLAIM" in s
assert "M6.8.7 VULKAN_QUERY_CREATE" in s
assert "m68_reuse_completed_ios" in s
pool.write_text(s)
gates.append("Powers-of-two diagnostics; unchanged real ZCull values, fences and failure return")

assert (root / "Crypto/unpkg.cpp").read_text().count("PsTJohn1.1.2: Carpeta PKG detected") == 1
assert (root / "ios/GameLibrary.cpp").read_text().count("installed_extracted_game(folder_root + entry.name)") == 1
assert "ios_vram_budget_max = 2048 * vram_budget_mib" in (root / "Emu/RSX/VK/vkutils/VRAMBudgetPolicy.h").read_text()
gates.append("Carpeta, game discovery, VRAM budget retained")
for item in gates:
    print("PsTJohn1 1.2 source verification PASS:", item)
print("PsTJohn1 1.2 speed-up is NOT established until measured on iPhone")
