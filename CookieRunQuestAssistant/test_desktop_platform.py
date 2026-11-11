import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import quest_assistant as engine


class DesktopPlatformTests(unittest.TestCase):
    def tearDown(self):
        engine.ADB_SERIAL = None

    def test_configured_adb_path_has_priority(self):
        with tempfile.TemporaryDirectory() as folder:
            executable = Path(folder) / ("HD-Adb.exe" if engine.IS_WINDOWS else "hd-adb")
            executable.touch()
            with mock.patch.dict(os.environ, {"CQA_ADB_PATH": str(executable)}):
                self.assertEqual(engine.find_bluestacks_adb(), executable)

    def test_windows_bluestacks_config_port_is_discovered(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "BlueStacks_nxt" / "bluestacks.conf"
            config.parent.mkdir()
            config.write_text('bst.instance.Pie64.status.adb_port="5565"\n', encoding="utf-8")
            with mock.patch.object(engine, "IS_WINDOWS", True), mock.patch.dict(
                os.environ, {"PROGRAMDATA": folder, "APPDATA": ""}, clear=False
            ):
                self.assertEqual(engine._windows_bluestacks_adb_ports(), [5565])

    def test_windows_adb_connects_when_device_list_starts_empty(self):
        calls = []

        def fake_adb(*args, **_kwargs):
            calls.append(args)
            if args == ("devices",) and calls.count(("devices",)) > 1:
                output = "List of devices attached\n127.0.0.1:5555\tdevice\n"
            else:
                output = "List of devices attached\n\n" if args == ("devices",) else "connected"
            return subprocess.CompletedProcess(args, 0, output, "")

        with mock.patch.object(engine, "IS_WINDOWS", True), mock.patch.object(
            engine, "adb_available", return_value=True
        ), mock.patch.object(engine, "_windows_bluestacks_adb_ports", return_value=[5555]), mock.patch.object(
            engine, "adb", side_effect=fake_adb
        ):
            self.assertEqual(engine.ensure_adb_connection(), "127.0.0.1:5555")
        self.assertIn(("connect", "127.0.0.1:5555"), calls)

    def test_platform_ocr_helpers_are_packaged(self):
        project = Path(__file__).resolve().parent
        self.assertTrue((project / "vision_ocr").is_file())
        self.assertTrue((project / "vision_ocr_windows.ps1").is_file())
        self.assertTrue((project / "packaging" / "build_macos.command").is_file())
        self.assertTrue((project / "packaging" / "build_windows.bat").is_file())


if __name__ == "__main__":
    unittest.main()
