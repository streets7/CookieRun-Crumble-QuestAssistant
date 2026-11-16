import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class PackagingContractTests(unittest.TestCase):
    def test_mac_build_produces_v16_1_dmg_and_bundles_integrated_automation(self):
        script = (ROOT / "packaging" / "build_macos.command").read_text(encoding="utf-8")
        self.assertIn("CookieRun-Crumble-QuestAssistant-macOS-v16.3.dmg", script)
        self.assertIn("--hidden-import desktop_app", script)
        self.assertIn("--hidden-import release_update", script)
        self.assertIn("--hidden-import integrated_automation", script)

    def test_windows_build_produces_v16_1_setup_exe(self):
        script = (ROOT / "packaging" / "build_windows.bat").read_text(encoding="utf-8")
        installer = ROOT / "packaging" / "windows_installer.iss"
        self.assertTrue(installer.is_file())
        self.assertIn("CookieRun-Crumble-QuestAssistant-Windows11-v16.3-Setup.exe", script)
        self.assertIn("--hidden-import integrated_automation", script)
        self.assertIn("ISCC.exe", script)

    def test_all_release_declarations_use_stable_v16_1(self):
        web = (ROOT / "web_ui.py").read_text(encoding="utf-8")
        mac = (ROOT / "packaging" / "build_macos.command").read_text(encoding="utf-8")
        windows = (ROOT / "packaging" / "build_windows.bat").read_text(encoding="utf-8")
        installer = (ROOT / "packaging" / "windows_installer.iss").read_text(encoding="utf-8")
        version_info = (ROOT / "packaging" / "windows_version.txt").read_text(encoding="utf-8")
        self.assertIn('APP_VERSION = "v16.3"', web)
        self.assertIn("16.3", mac)
        self.assertIn("16.3", windows)
        self.assertIn('#define Version "16.3"', installer)
        self.assertIn("filevers=(16,2,0,0), prodvers=(16,2,0,0)", version_info)

    def test_installer_source_excludes_user_generated_data(self):
        installer = (ROOT / "packaging" / "windows_installer.iss").read_text(encoding="utf-8")
        for private_name in ("settings.json", "daily_summary.json", "error_screenshots"):
            self.assertNotIn(private_name, installer)

    def test_private_config_is_injected_into_both_desktop_builds(self):
        mac = (ROOT / "packaging" / "build_macos.command").read_text(encoding="utf-8")
        windows = (ROOT / "packaging" / "build_windows.bat").read_text(encoding="utf-8")
        self.assertIn("private_config.json", mac)
        self.assertIn("private_config.json", windows)

    def test_desktop_builds_and_windows_installer_use_project_icon(self):
        mac = (ROOT / "packaging" / "build_macos.command").read_text(encoding="utf-8")
        windows = (ROOT / "packaging" / "build_windows.bat").read_text(encoding="utf-8")
        installer = (ROOT / "packaging" / "windows_installer.iss").read_text(encoding="utf-8")

        self.assertTrue((ROOT / "assets" / "app_icon.png").is_file())
        self.assertTrue((ROOT / "packaging" / "app_icon.icns").is_file())
        self.assertTrue((ROOT / "packaging" / "app_icon.ico").is_file())
        self.assertIn('--icon "$PROJECT_DIR/packaging/app_icon.icns"', mac)
        self.assertIn('--icon "%SCRIPT_DIR%app_icon.ico"', windows)
        self.assertIn("SetupIconFile=app_icon.ico", installer)

    def test_integrated_screen_asset_is_packaged_with_assets_directory(self):
        self.assertTrue((ROOT / "assets" / "implant_850_complete.png").is_file())
        for name in ("build_macos.command", "build_windows.bat"):
            script = (ROOT / "packaging" / name).read_text(encoding="utf-8")
            self.assertIn("assets", script)


if __name__ == "__main__":
    unittest.main()
