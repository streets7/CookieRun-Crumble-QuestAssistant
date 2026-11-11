import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import quest_assistant as e

class RewardPopupTests(unittest.TestCase):
    def test_offer_during_claim_returns_to_battle_without_reward_retry(self):
        battle, popup = object(), object()
        with patch.object(e,'wait_until'), patch.object(e,'wait_for_state',return_value=battle) as wait, patch.object(e,'quest_complete',return_value=True), patch.object(e,'screenshot',return_value=popup), patch.object(e,'screen_state',return_value='unknown'), patch.object(e,'bottom_x_visible',return_value=True), patch.object(e,'wait_detect_quest',return_value=(battle,'equipment_repeat',0)), patch.object(e,'claim_repeat_equipment_rewards'), patch.object(e,'check_stop'), patch.object(e,'tap') as tap, patch.object(e.time,'sleep'):
            e.claim_reward_verified('bag')
        self.assertEqual(tap.call_count,1)
        self.assertGreaterEqual(wait.call_count,1)

    def test_no_card_tap_when_battle_cannot_be_confirmed(self):
        with patch.object(e,'wait_until'), patch.object(e,'wait_for_state',side_effect=e.SafeStop('예상 화면을 확인하지 못했습니다: battle')), patch.object(e,'tap') as tap:
            with self.assertRaises(e.SafeStop):
                e.claim_reward_verified('bag')
        tap.assert_not_called()

    def test_no_card_tap_when_completion_has_disappeared(self):
        with patch.object(e,'wait_until'), patch.object(e,'wait_for_state',return_value=object()), patch.object(e,'quest_complete',return_value=False), patch.object(e,'tap') as tap:
            e.claim_reward_verified('bag')
        tap.assert_not_called()
