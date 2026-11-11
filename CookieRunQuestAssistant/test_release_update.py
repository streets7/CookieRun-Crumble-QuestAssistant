import io
import json
import unittest
from unittest import mock

import release_update
import web_ui


class FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class ReleaseUpdateTests(unittest.TestCase):
    def test_default_repository_points_to_public_release_channel(self):
        self.assertEqual(web_ui.GITHUB_REPOSITORY, "streets7/CookieRun-Crumble-QuestAssistant")

    def test_parse_version_ignores_prefix_and_missing_parts(self):
        self.assertEqual(release_update.parse_version("v15.18"), (15, 18))
        self.assertEqual(release_update.parse_version("16.0.1"), (16, 0, 1))

    def test_newer_stable_release_selects_platform_asset(self):
        release = {
            "tag_name": "v16.0",
            "prerelease": False,
            "html_url": "https://github.com/example/app/releases/v16.0",
            "assets": [
                {"name": "CookieRun-macOS-v16.0.dmg", "browser_download_url": "https://download/mac"},
                {"name": "CookieRun-Windows11-v16.0-Setup.exe", "browser_download_url": "https://download/win"},
            ],
        }
        response = FakeResponse(json.dumps(release).encode())
        with mock.patch.object(release_update.urllib.request, "urlopen", return_value=response):
            result = release_update.check_latest_release("https://api/releases/latest", "v15.18", "Windows")

        self.assertTrue(result["update_available"])
        self.assertEqual(result["latest_version"], "v16.0")
        self.assertEqual(result["download_url"], "https://download/win")

    def test_prerelease_and_equal_release_do_not_offer_update(self):
        for tag, prerelease in (("v15.18", False), ("v16.0-beta.1", True)):
            release = {"tag_name": tag, "prerelease": prerelease, "html_url": "https://release", "assets": []}
            with self.subTest(tag=tag), mock.patch.object(
                release_update.urllib.request,
                "urlopen",
                return_value=FakeResponse(json.dumps(release).encode()),
            ):
                result = release_update.check_latest_release("https://api/releases/latest", "v15.18", "Darwin")
                self.assertFalse(result["update_available"])

    def test_missing_platform_asset_falls_back_to_release_page(self):
        release = {
            "tag_name": "v16.0",
            "prerelease": False,
            "html_url": "https://release",
            "assets": [{"name": "SHA256-macOS.txt", "browser_download_url": "https://checksum"}],
        }
        with mock.patch.object(
            release_update.urllib.request,
            "urlopen",
            return_value=FakeResponse(json.dumps(release).encode()),
        ):
            result = release_update.check_latest_release("https://api/releases/latest", "v15.18", "Darwin")
        self.assertEqual(result["download_url"], "https://release")

    def test_network_and_malformed_responses_never_break_startup(self):
        with mock.patch.object(release_update.urllib.request, "urlopen", side_effect=OSError("offline")):
            offline = release_update.check_latest_release("https://api/releases/latest", "v15.18", "Darwin")
        with mock.patch.object(
            release_update.urllib.request, "urlopen", return_value=FakeResponse(b"not-json")
        ):
            malformed = release_update.check_latest_release("https://api/releases/latest", "v15.18", "Darwin")
        self.assertEqual(offline["status"], "unavailable")
        self.assertEqual(malformed["status"], "unavailable")

    def test_web_status_is_unconfigured_without_repository(self):
        with mock.patch.object(web_ui, "GITHUB_REPOSITORY", ""), mock.patch.object(
            web_ui.release_update, "check_latest_release"
        ) as checker:
            result = web_ui.update_status_payload()
        self.assertEqual(result["status"], "unconfigured")
        checker.assert_not_called()

    def test_web_status_builds_official_latest_release_api_url(self):
        expected = {"status": "current", "update_available": False}
        with mock.patch.object(web_ui, "GITHUB_REPOSITORY", "owner/project"), mock.patch.object(
            web_ui.platform, "system", return_value="Darwin"
        ), mock.patch.object(web_ui.release_update, "check_latest_release", return_value=expected) as checker:
            result = web_ui.update_status_payload()
        self.assertEqual(result, expected)
        checker.assert_called_once_with(
            "https://api.github.com/repos/owner/project/releases/latest",
            web_ui.APP_VERSION,
            "Darwin",
        )

    def test_program_header_contains_update_status_control(self):
        self.assertIn('id="updateStatus"', web_ui.HTML)
        self.assertIn("loadUpdateStatus()", web_ui.HTML)


if __name__ == "__main__":
    unittest.main()
