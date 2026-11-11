import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw
import quest_assistant as e

class FreeRefreshTests(unittest.TestCase):
    def test_live_button_without_free_word_and_failed_label_ocr(self):
        with Image.open(Path(__file__).parent/'tests/fixtures/sep27/free_refresh.png') as im:
            with patch.object(e,'arena_opponent_counter',return_value=(5,5)), patch.object(e,'_ocr_region',return_value='AHEL'):
                self.assertTrue(e.arena_selector_status(im)[1])

    def test_cost_or_timer_text_overrides_visual_match(self):
        with Image.open(Path(__file__).parent/'tests/fixtures/sep27/free_refresh.png') as im:
            for text in ['새로고침 300', '28분 후 무료 새로고침', '크리스탈']:
                with self.subTest(text=text), patch.object(e,'arena_opponent_counter',return_value=(5,5)), patch.object(e,'_ocr_region',return_value=text):
                    self.assertFalse(e.arena_selector_status(im)[1])

    def test_changed_button_does_not_match_free_reference(self):
        with Image.open(Path(__file__).parent/'tests/fixtures/sep27/free_refresh.png') as original:
            im=original.copy()
        ImageDraw.Draw(im).rectangle((800,1400,1040,1445),fill=(0,130,170))
        with patch.object(e,'arena_opponent_counter',return_value=(5,5)), patch.object(e,'_ocr_region',return_value=''):
            self.assertFalse(e.arena_selector_status(im)[1])
