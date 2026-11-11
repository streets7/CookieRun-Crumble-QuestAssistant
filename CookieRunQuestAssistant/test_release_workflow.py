import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class ReleaseWorkflowTests(unittest.TestCase):
    def test_stable_tag_builds_both_platforms_before_release(self):
        workflow = ROOT / ".github" / "workflows" / "release-desktop.yml"
        self.assertTrue(workflow.is_file())
        text = workflow.read_text(encoding="utf-8")
        self.assertIn("tags:", text)
        self.assertIn("- 'v*'", text)
        self.assertIn("macos-14", text)
        self.assertIn("windows-2022", text)
        self.assertIn("needs: build", text)
        self.assertIn("softprops/action-gh-release@v2", text)
        self.assertIn("!contains(github.ref_name, '-')", text)
        self.assertLess(text.index("pip install -r requirements-runtime.txt"), text.index("python -m unittest discover -q"))

    def test_release_uploads_exact_v16_installer_types(self):
        text = (ROOT / ".github" / "workflows" / "release-desktop.yml").read_text(encoding="utf-8")
        self.assertIn("CookieRun-Crumble-QuestAssistant-macOS-v16.0.dmg", text)
        self.assertIn("CookieRun-Crumble-QuestAssistant-Windows11-v16.0-Setup.exe", text)
        self.assertIn("SHA256.txt", text)

    def test_manual_windows_artifact_contains_setup_exe(self):
        text = (ROOT / ".github" / "workflows" / "build-desktop.yml").read_text(encoding="utf-8")
        self.assertIn("배포/windows/*-Setup.exe", text)
        self.assertNotIn("배포/windows/*.zip", text)


if __name__ == "__main__":
    unittest.main()
