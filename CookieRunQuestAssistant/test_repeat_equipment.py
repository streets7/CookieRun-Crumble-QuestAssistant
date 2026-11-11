import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import quest_assistant as e
D=Path(__file__).parent/'tests/fixtures/sep20'
class RepeatEquipmentTests(unittest.TestCase):
    def test_repeat_cards_distinct_from_bag(self):
        for name,expected in [('022005_227000',True),('022545_041000',True),('022635_044000',False)]:
            with self.subTest(name=name):self.assertEqual(e.repeat_equipment_reward_visible(Image.open(D/(name+'.png'))),expected)
    def test_second_tap_only_if_repeat_is_still_visible(self):
        first,second,bag=object(),object(),object()
        with patch.object(e,'repeat_equipment_reward_visible',side_effect=lambda im:im is not bag),patch.object(e,'screenshot',side_effect=[first,second]),patch.object(e,'wait_for_state',side_effect=[second,bag]),patch.object(e,'check_stop'),patch.object(e,'tap') as tap,patch.object(e.time,'sleep'):
            self.assertIs(e.claim_repeat_equipment_rewards(first),bag)
        self.assertEqual(tap.call_count,2)
    def test_no_second_tap_on_another_quest(self):
        first,bag=object(),object()
        with patch.object(e,'repeat_equipment_reward_visible',side_effect=lambda im:im is first),patch.object(e,'screenshot',return_value=first),patch.object(e,'wait_for_state',return_value=bag),patch.object(e,'check_stop'),patch.object(e,'tap') as tap,patch.object(e.time,'sleep'):
            self.assertIs(e.claim_repeat_equipment_rewards(first),bag)
        self.assertEqual(tap.call_count,1)
    def test_never_taps_more_than_twice_per_pass(self):
        im=object()
        with patch.object(e,'repeat_equipment_reward_visible',return_value=True),patch.object(e,'screenshot',return_value=im),patch.object(e,'wait_for_state',return_value=im),patch.object(e,'check_stop'),patch.object(e,'tap') as tap,patch.object(e.time,'sleep'):
            e.claim_repeat_equipment_rewards(im)
        self.assertEqual(tap.call_count,2)

    def test_repeat_card_preempts_normal_classifier(self):
        im = object()
        with patch.object(e, 'screen_state', return_value='battle'), patch.object(e, 'repeat_equipment_reward_visible', return_value=True), patch.object(e, 'detect_quest') as detect, patch.object(e, 'check_stop'):
            self.assertEqual(e.wait_detect_quest(initial_image=im)[1], 'equipment_repeat')
        detect.assert_not_called()

    def test_repeat_claim_limit_cannot_restart_recovery_loop(self):
        self.assertFalse(e.recoverable_in_infinite_mode(e.SafeStop('누적 장비 보상 수령 한도')))
