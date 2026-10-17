#!/usr/bin/env python3
"""PsTJohn1.1.2: safely import Carpeta PS3 PKGs on iOS."""
from pathlib import Path
root = Path("rpcs3-src/rpcs3")
def replace_once(source, needle, replacement):
    n = source.count(needle)
    if n != 1:
        raise RuntimeError(f"Carpeta source anchor count {n}: {needle[:130]!r}")
    return source.replace(needle, replacement, 1)

def acceptable(raw, folder=False):
    prefix = "../../dev_hdd0"
    if raw == prefix:
        return folder
    if not raw.startswith(prefix + "/"):
        return False
    rel = raw[len(prefix)+1:]
    if not rel or "\\" in rel or "//" in rel or "\0" in rel:
        return False
    parts = rel.split("/")
    return parts[0] in ("game", "GAMES", "GAMEZ", "exdata") and all(x not in (".", "..", "") for x in parts)
for name, folder in [
    ("../../dev_hdd0", True),
    ("../../dev_hdd0/GAMES", True),
    ("../../dev_hdd0/GAMES/A/PS3_GAME/USRDIR/EBOOT.BIN", False),
    ("../../dev_hdd0/game/NPUB12345/USRDIR/EBOOT.BIN", False),
    ("../../dev_hdd0/GAMEZ/A/PS3_GAME/PARAM.SFO", False),
    ("../../dev_hdd0/exdata", True),
    ("../../dev_hdd0/exdata/ABCD12345.rap", False),
]:
    assert acceptable(name, folder)
for name, folder in [
    ("../../dev_hdd0", False), ("../../dev_hdd0/../dev_flash/x", False),
    ("../../dev_hdd0/GAMES/../../home/x", False),
    ("../../dev_hdd0/GAMES/.//x", False),
    ("../../dev_hdd0//GAMES/x", False),
    ("../../dev_hdd0/GAMES\\evil", False),
    ("../../dev_hdd0/home/00000001/savedata/x", False),
    ("../../dev_hdd0evil/GAMES/x", False),
    ("/dev_hdd0/GAMES/x", False), ("PS3_GAME/PARAM.SFO", False),
]:
    assert not acceptable(name, folder)
print("PsTJohn1.1.2: 17 Carpeta path acceptance/security fixtures PASS")

p = root / "Crypto/unpkg.cpp"
s = p.read_text()
preflight = r"""#ifdef RPCS3_IOS
	// A Carpeta PKG is a THEME-type package with no root PARAM.SFO
	// containing a special ../../dev_hdd0 root folder. Fail closed for
	// any other package and for every other target outside game folders.
	bool carpeta_pkg = false;
	if (m_header.pkg_platform == PKG_PLATFORM_TYPE_PS3 &&
		m_metadata.content_type == PKG_CONTENT_TYPE_THEME && m_psf.empty())
	{
		constexpr std::string_view prefix = "../../dev_hdd0";
		std::vector<PKGEntry> candidates;
		if (!read_entries(candidates))
		{
			return false;
		}
		std::vector<std::string> names;
		names.reserve(candidates.size());
		for (const auto& entry : candidates)
		{
			const bool is_psp = (entry.type & PKG_FILE_ENTRY_PSP) != 0u;
			std::string buf(entry.name_size + BUF_PADDING, '\0');
			if (decrypt(entry.name_offset, entry.name_size,
				is_psp ? PKG_AES_KEY2 : m_dec_key.data(),
				std::span<u8>{reinterpret_cast<u8*>(buf.data()), buf.size()}) < entry.name_size)
			{
				pkg_log.error("PsTJohn1.1.2: cannot decrypt PKG path");
				return false;
			}
			const std::string_view name = fmt::trim_back_sv(buf, "\0"sv);
			names.emplace_back(name);
			if (name == prefix || name.starts_with("../../dev_hdd0/"))
			{
				carpeta_pkg = true;
			}
		}
		if (carpeta_pkg)
		{
			// Inventory all encrypted top-level names before rejecting a
			// layout: the device log will show any remaining required roots.
			std::map<std::string, u32> carpeta_roots;
			for (const std::string& raw_name : names)
			{
				const std::string_view n{raw_name};
				if (n == prefix)
					continue;
				std::string_view relative = n.starts_with("../../dev_hdd0/")
					? n.substr(prefix.size() + 1) : std::string_view{"<outside>"};
				const usz slash = relative.find('/');
				std::string root_name{relative.substr(0, slash)};
				if (root_name.size() > 48)
					root_name.resize(48);
				for (char& ch : root_name)
				{
					if (!((ch >= 'a' && ch <= 'z') ||
						(ch >= 'A' && ch <= 'Z') ||
						(ch >= '0' && ch <= '9') ||
						ch == '_' || ch == '-' || ch == '.'))
						ch = '?';
				}
				carpeta_roots[root_name]++;
			}
			for (const auto& [root_name, count] : carpeta_roots)
				pkg_log.notice("PsTJohn1.1.2: Carpeta folder '%s' entries=%u", root_name, count);
			// Preflight ALL entries before touching the filesystem.
			for (usz i = 0; i < names.size(); ++i)
			{
				const std::string_view name{names[i]};
				const u8 type = candidates[i].type & 0xff;
				const bool folder = type == PKG_FILE_ENTRY_FOLDER || type == 0x12;
				if (name == prefix)
				{
					if (!folder)
					{
						pkg_log.error("PsTJohn1.1.2: Carpeta root is not a folder");
						return false;
					}
					continue;
				}
				if (!name.starts_with("../../dev_hdd0/"))
				{
					pkg_log.error("PsTJohn1.1.2: mixed PKG path '%s'", name);
					return false;
				}
				const std::string_view relative = name.substr(prefix.size() + 1);
				const usz slash = relative.find('/');
				const std::string_view top = relative.substr(0, slash);
				if ((top != "game" && top != "GAMES" && top != "GAMEZ" && top != "exdata") ||
					relative.empty() || leaves_directory(relative) ||
					relative.find('\\') != std::string_view::npos ||
					relative.find("//") != std::string_view::npos ||
					relative.find('\0') != std::string_view::npos)
				{
					pkg_log.error("PsTJohn1.1.2: unsafe Carpeta PKG path '%s'", name);
					return false;
				}
			}
			// Limit this importer to the virtual PS3 HDD sandbox.
			// Never delete the shared HDD root after a partial failure.
			m_install_path = rpcs3::utils::get_hdd0_dir();
			m_was_null = false;
			pkg_log.notice("PsTJohn1.1.2: Carpeta PKG detected; %u paths confined to game/GAMES/GAMEZ/exdata",
				static_cast<u32>(names.size()));
		}
	}
#endif
"""
s = replace_once(s, "\tif (!fs::create_path(m_install_path))\n\t{", preflight + "\n\tif (!fs::create_path(m_install_path))\n\t{")
old = '\t\tstd::string_view name = fmt::trim_back_sv(name_buf, "\\0"sv);\n\n\t\tif (leaves_directory(name))'
new = r"""		std::string_view name = fmt::trim_back_sv(name_buf, "\0"sv);

#ifdef RPCS3_IOS
		if (carpeta_pkg)
		{
			constexpr std::string_view prefix = "../../dev_hdd0";
			if (name == prefix)
			{
				continue; // Verified container folder, never overwrite HDD root.
			}
			name.remove_prefix(prefix.size() + 1); // Already preflighted.
		}
#endif

		if (leaves_directory(name))"""
s = replace_once(s, old, new)
assert s.count("PKG entry path escapes installation directory") == 2
assert s.count("m_was_null = false;") == 1
p.write_text(s)

p = root / "ios/GameLibrary.cpp"
s = p.read_text()
scanner = r"""#ifdef RPCS3_IOS
	// Validated Carpeta folder games live outside the ordinary game/ tree.
	for (const std::string& folder_root : {
		rpcs3::utils::get_hdd0_dir() + "GAMES/",
		rpcs3::utils::get_hdd0_dir() + "GAMEZ/"
	})
	{
		for (auto&& entry : fs::dir{folder_root})
		{
			if (!entry.is_directory || entry.name == "." || entry.name == "..")
			{
				continue;
			}
			if (auto game = installed_extracted_game(folder_root + entry.name))
			{
				const bool duplicate = std::any_of(result.begin(), result.end(),
					[&game](const installed_game& other)
					{
						return other.title_id == game->title_id;
					});
				if (!duplicate)
				{
					result.emplace_back(std::move(*game));
				}
			}
		}
	}
#endif
"""
s = replace_once(s, "\tconst std::string iso_root = disc_image_root();\n\tfor (auto&& entry : fs::dir{iso_root})", scanner + "\n\tconst std::string iso_root = disc_image_root();\n\tfor (auto&& entry : fs::dir{iso_root})")
assert s.count("installed_extracted_game(folder_root + entry.name)") == 1
p.write_text(s)
print("PsTJohn1.1.2: Carpeta PKG path preflight and GAMES/GAMEZ game discovery patched")
