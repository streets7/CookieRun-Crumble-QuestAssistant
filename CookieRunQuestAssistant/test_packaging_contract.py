import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class PackagingContractTests(unittest.TestCase):
    def test_mac_build_produces_v16_dmg_and_bundles_desktop_host(self):
        script = (ROOT / "packaging" / "build_macos.command").read_text(encoding="utf-8")
        self.assertIn("CookieRun-Crumble-QuestAssistant-macOS-v16.0.dmg", script)
        self.assertIn("--hidden-import desktop_app", script)
        self.assertIn("--hidden-import release_update", script)

    def test_windows_build_produces_v16_setup_exe(self):
        script = (ROOT / "packaging" / "build_windows.bat").read_text(encoding="utf-8")
        installer = ROOT / "packaging" / "windows_installer.iss"
        self.assertTrue(installer.is_file())
        self.assertIn("CookieRun-Crumble-QuestAssistant-Windows11-v16.0-Setup.exe", script)
        self.assertIn("ISCC.exe", script)

    def test_installer_source_excludes_user_generated_data(self):
        installer = (ROOT / "packaging" / "windows_installer.iss").read_text(encoding="utf-8")
        for private_name in ("settings.json", "daily_summary.json", "error_screenshots"):
            self.assertNotIn(private_name, installer)

    def test_private_config_is_injected_into_both_desktop_builds(self):
        mac = (ROOT / "packaging" / "build_macos.command").read_text(encoding="utf-8")
        windows = (ROOT / "packaging" / "build_windows.bat").read_text(encoding="utf-8")
        self.assertIn("private_config.json", mac)
        self.assertIn("private_config.json", windows)


if __name__ == "__main__":
    unittest.main()
