import unittest
from pathlib import Path
from PIL import Image
from unittest.mock import patch
import quest_assistant as e
D=Path(__file__).parent/'tests/fixtures/wagle'
class WagleTests(unittest.TestCase):
    def setUp(self):
        self.home=Image.open(D/'home.png').convert('RGB')
        self.opponents=Image.open(D/'opponents.png').convert('RGB')
    def test_screen_types_and_coordinates(self):
        self.assertTrue(e.wagle_arena_home_visible(self.home))
        self.assertFalse(e.wagle_arena_opponents_visible(self.home))
        self.assertTrue(e.arena_opponents_visible(self.opponents))
        self.assertFalse(e.arena_home_visible(self.opponents))
        self.assertEqual(e.arena_action_point(self.opponents,'challenge'),(540,1537))
        self.assertEqual(e.arena_action_point(self.opponents,'refresh'),(920,1537))
        self.assertEqual(e.arena_action_point(self.home,'enter'),(820,1550))
    def test_regular_layout_unchanged(self):
        im=Image.open(Path(__file__).parent/'tests/fixtures/sep27/free_refresh.png').convert('RGB')
        self.assertFalse(e.wagle_arena_opponents_visible(im))
        self.assertEqual(e.arena_action_point(im,'refresh'),e.ARENA_REFRESH)
    def test_wagle_ocr_regions_and_free_button(self):
        with patch.object(e,'_ocr_arena_power',return_value='13.54M') as power, patch.object(e,'_ocr_region',side_effect=['1902','12.23M','1668']) as ocr:
            self.assertEqual(e.arena_match_values(self.opponents),(13540000,1902,12230000,1668))
        self.assertEqual(power.call_args.args[1],(520,225,760,325))
        self.assertEqual(ocr.call_args_list[-1].args[1],(410,900,650,985))
        with patch.object(e,'_ocr_region',side_effect=['515','새로고침']):
            self.assertTrue(e.arena_selector_status(self.opponents)[1])
