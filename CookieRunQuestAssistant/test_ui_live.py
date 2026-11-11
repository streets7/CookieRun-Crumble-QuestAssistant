import tempfile
import unittest
from pathlib import Path
from ui_live import LiveHTML

class LiveHTMLTests(unittest.TestCase):
    def test_changes_html_without_executing_source(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'ui.py'
            live = LiveHTML(path, '<p>old</p>')
            old = live.read()[1]
            path.write_text("raise RuntimeError('never execute')\nHTML = '<p>new</p>'\n")
            html, revision = live.read()
            self.assertEqual(html, '<p>new</p>')
            self.assertNotEqual(revision, old)
            path.write_text("HTML = '<p>new</p>'\nx = 2\n")
            self.assertEqual(live.read()[1], revision)

    def test_partial_save_keeps_last_valid_html(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'ui.py'
            live = LiveHTML(path, 'initial')
            path.write_text("HTML = 'valid'")
            good = live.read()
            for bad in ["HTML = '", "HTML = make_html()", "x = 1"]:
                path.write_text(bad)
                self.assertEqual(live.read(), good)
            path.unlink()
            self.assertEqual(live.read(), good)
