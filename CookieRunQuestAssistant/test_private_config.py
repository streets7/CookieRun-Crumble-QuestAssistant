import json
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import web_ui


class PrivateConfigTests(unittest.TestCase):
    def test_private_config_loads_without_exposing_defaults(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "private_config.json"
            path.write_text(json.dumps({
                "admin_password": "secret-value",
                "support_account": "account-value",
                "support_holder": "holder-value",
                "contact_email": "owner@example.com",
            }), encoding="utf-8")
            config = web_ui.load_private_config(path)
        self.assertEqual(config["admin_password"], "secret-value")
        self.assertEqual(config["support_account"], "account-value")

    def test_public_config_omits_admin_password(self):
        with mock.patch.dict(web_ui.PRIVATE_CONFIG, {
            "admin_password": "never-public",
            "support_account": "account",
            "support_holder": "holder",
            "contact_email": "mail@example.com",
        }, clear=True):
            payload = web_ui.public_config_payload()
        self.assertNotIn("admin_password", payload)
        self.assertEqual(payload["support_account"], "account")

    def test_tracked_source_contains_no_real_private_values(self):
        source = Path(web_ui.__file__).read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"\d{4}-\d{2}-\d{7}", source))
        self.assertNotIn("ADMIN_PASSWORD =", source)


if __name__ == "__main__":
    unittest.main()
