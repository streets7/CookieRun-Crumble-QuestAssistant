import unittest
from unittest.mock import patch

import quest_assistant as engine


class IntegratedDungeonRunnerTests(unittest.TestCase):
    def test_crumble_runs_only_remaining_attempts_up_to_four(self):
        with patch.object(engine, "run_crumble_dungeon", return_value=2) as run:
            self.assertEqual(engine.run_integrated_crumble({"crumble_completed": 2}), 2)
        run.assert_called_once_with(2)

        with patch.object(engine, "run_crumble_dungeon") as run:
            self.assertEqual(engine.run_integrated_crumble({"crumble_completed": 4}), 0)
        run.assert_not_called()

    def test_arena_uses_existing_no_paid_runner_and_returns_wait_status(self):
        with patch.object(engine, "run_arena", return_value=3) as run:
            result = engine.run_integrated_arena({"arena_free_at": "14시간 후"})

        run.assert_called_once_with(5)
        self.assertEqual(result, {"completed": 3, "free_at": "14시간 후"})

    def test_implant_skips_permanent_completion_and_stops_after_failure(self):
        with patch.object(engine, "run_implant_tower") as run:
            self.assertEqual(
                engine.run_integrated_implant({"implant_850_complete": True}), "complete"
            )
        run.assert_not_called()

        with patch.object(engine, "run_implant_tower", side_effect=engine.SafeStop("패배")):
            self.assertEqual(
                engine.run_integrated_implant({"implant_850_complete": False}), "failed"
            )

    def test_daily_sequence_contains_all_five_dungeons_and_continues(self):
        result = {"exp": 1, "coin": 2, "dough": 3, "research_stone": 1, "rune_crystal": 2}
        with patch.object(engine, "run_daily_dungeon_sequence", return_value=result) as run:
            actual = engine.run_integrated_daily_dungeons({"ad_pass_confirmed": True})

        self.assertEqual(actual, result)
        run.assert_called_once_with(
            (("exp", 3, True), ("coin", 3, True), ("dough", 3, True),
             ("research_stone", 3, True), ("rune_crystal", 3, True)),
            dry_run=False,
            allow_ad_pass=True,
            continue_on_failure=True,
        )


class IntegratedAdPassPolicyTests(unittest.TestCase):
    def test_key_entry_is_allowed_without_ad_pass(self):
        with patch.object(engine, "daily_start_available", return_value=True), \
                patch.object(engine, "daily_key_count", return_value=1):
            self.assertTrue(engine.integrated_daily_entry_allowed(object(), False))

    def test_ad_entry_requires_positive_pass_confirmation(self):
        with patch.object(engine, "daily_start_available", return_value=True), \
                patch.object(engine, "daily_key_count", return_value=0):
            self.assertFalse(engine.integrated_daily_entry_allowed(object(), False))
            self.assertTrue(engine.integrated_daily_entry_allowed(object(), True))

    def test_ambiguous_key_and_pass_state_never_allows_entry(self):
        with patch.object(engine, "daily_start_available", return_value=True), \
                patch.object(engine, "daily_key_count", return_value=None):
            self.assertFalse(engine.integrated_daily_entry_allowed(object(), False))


if __name__ == "__main__":
    unittest.main()
