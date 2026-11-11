import unittest
from unittest.mock import call, patch

import quest_assistant as engine


class QuestSpeedTests(unittest.TestCase):
    def test_equipment_batches_do_not_use_the_old_six_second_delay(self):
        self.assertLessEqual(engine.EQUIPMENT_BATCH_SETTLE, 1.5)
        self.assertLessEqual(engine.EQUIPMENT_AUTO_RETRY, 1.0)

    def test_completion_poll_is_fast_then_eases_for_long_battles(self):
        with patch.object(engine.time, "monotonic", return_value=100.0):
            self.assertEqual(engine.quest_completion_poll_interval(99.0), 0.45)
            self.assertEqual(engine.quest_completion_poll_interval(79.0), 0.80)

    def test_wait_until_uses_fast_completion_poll_by_default(self):
        waiting, complete = object(), object()
        with patch.object(engine, "check_stop"), \
                patch.object(engine, "screenshot", side_effect=[waiting, complete]), \
                patch.object(engine, "screen_state", return_value="battle"), \
                patch.object(engine.time, "sleep") as sleep:
            result = engine.wait_until(
                "테스트 완료 표시", lambda image: image is complete, timeout=2
            )
        self.assertIs(result, complete)
        sleep.assert_called_once_with(engine.QUEST_COMPLETION_POLL)

    def test_quest_navigation_closes_reward_overlay_then_retries(self):
        reward, battle, gacha = object(), object(), object()
        states = {reward: "reward", battle: "battle", gacha: "gacha"}
        with patch.object(engine, "check_stop"), \
                patch.object(engine, "screenshot", side_effect=[reward, battle, gacha]), \
                patch.object(engine, "screen_state", side_effect=lambda image: states[image]), \
                patch.object(engine, "bottom_x_visible", return_value=True), \
                patch.object(engine, "tap") as tap, \
                patch.object(engine.time, "sleep"):
            result = engine.retry_tap_until_state(
                engine.QUEST_PANEL, "퀘스트 패널 자동 이동", "battle", "gacha"
            )
        self.assertIs(result, gacha)
        self.assertEqual(tap.call_args_list, [
            call(
                engine.BOTTOM_X,
                "퀘스트 패널 자동 이동 도중 보상 획득 팝업 닫기 (1/3)",
                dry_run=False,
            ),
            call(
                engine.QUEST_PANEL,
                "퀘스트 패널 자동 이동 (1/5)",
                dry_run=False,
            ),
        ])

    def test_draw_completion_accepts_only_three_stable_next_quest_frames(self):
        first, second, third = object(), object(), object()
        with patch.object(engine, "check_stop"), \
                patch.object(engine, "screenshot", side_effect=[first, second, third]), \
                patch.object(engine, "screen_state", return_value="battle"), \
                patch.object(engine, "quest_complete", return_value=False), \
                patch.object(engine, "detect_quest", return_value=("equipment", 0.72)), \
                patch.object(engine.time, "monotonic", return_value=0.0), \
                patch.object(engine.time, "sleep") as sleep:
            image, advanced = engine.wait_draw_completion("pet", timeout=2)
        self.assertIs(image, third)
        self.assertTrue(advanced)
        self.assertEqual(sleep.call_count, 2)

    def test_claim_draw_reward_skips_tap_after_confirmed_transition(self):
        image = object()
        with patch.object(
            engine, "wait_draw_completion", return_value=(image, True)
        ) as wait_draw, patch.object(engine, "tap") as tap:
            engine.claim_reward_verified("pet")
        wait_draw.assert_called_once_with("pet", engine.TIMEOUT_DRAW)
        tap.assert_not_called()


if __name__ == "__main__":
    unittest.main()
