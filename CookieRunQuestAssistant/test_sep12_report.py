import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import quest_assistant as e
D = Path(__file__).parent/'tests/fixtures/sep12'

def panel(i):
    im=Image.new('RGB',(1080,1920));im.paste(Image.open(D/f'panel_{i}.png'),(650,930));return im

class ReportTests(unittest.TestCase):
    def test_incomplete_draws_are_not_completed_by_yellow_background(self):
        for i in [9,10,11,12,13,19]:
            with self.subTest(i=i):self.assertFalse(e.quest_complete(panel(i)))
    def test_completed_stage_cards_remain_complete(self):
        for i in [3,4,8,15,16]:
            with self.subTest(i=i):self.assertTrue(e.quest_complete(panel(i)))
    def test_stage_variants_are_recognized(self):
        for i in [1,3,4,8,15,16]:
            with self.subTest(i=i):self.assertEqual(e.detect_quest(panel(i),assume_battle=True)[0],'stage')
    def test_green_reveals_but_not_popup_screens(self):
        for i in [2,5,6,7,18,21]:
            with self.subTest(i=i):self.assertEqual(e.tssr_reveal_visible(Image.open(D/f'full_{i}.png')),i in [5,6,7])
    def test_unknown_popup_is_closed_only_after_two_frames(self):
        popup=Image.open(D/'full_2.png');battle=object()
        with patch.object(e,'check_stop'),patch.object(e,'screenshot',side_effect=[popup,popup,battle]),patch.object(e,'screen_state',side_effect=['unknown','unknown','battle']),patch.object(e,'tap') as tap,patch.object(e.time,'sleep'):
            self.assertIs(e.wait_for_state('battle'),battle)
        self.assertEqual(tap.call_count,1)
        self.assertEqual(tap.call_args.args[0],e.BOTTOM_X)
    def test_unknown_without_x_is_never_clicked(self):
        with patch.object(e,'check_stop'),patch.object(e,'screenshot',return_value=object()),patch.object(e,'screen_state',side_effect=['unknown','unknown','battle']),patch.object(e,'bottom_x_visible',return_value=False),patch.object(e,'tap') as tap,patch.object(e.time,'sleep'):
            e.wait_for_state('battle')
        tap.assert_not_called()
    def test_bag_close_handles_intervening_popup(self):
        popup=Image.open(D/'full_2.png');battle=object()
        with patch.object(e,'check_stop'),patch.object(e,'screenshot',side_effect=[popup,popup,battle]),patch.object(e,'screen_state',side_effect=['unknown','unknown','battle']),patch.object(e,'tap') as tap,patch.object(e.time,'sleep'):
            self.assertIs(e.retry_tap_until_state(e.BOTTOM_X,'가방 닫기','bag','battle'),battle)
        self.assertEqual(tap.call_count,1)
