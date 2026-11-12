import unittest
from unittest.mock import patch

import quest_assistant as engine


class IntegratedDungeonRunnerTests(unittest.TestCase):
    def test_crumble_uses_game_screen_as_source_of_truth_up_to_four(self):
        with patch.object(engine, "run_crumble_dungeon", return_value=2) as run:
            self.assertEqual(engine.run_integrated_crumble({"crumble_completed": 2}), 2)
        run.assert_called_once_with(4)

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

        with patch.object(engine, "open_challenge_menu", return_value=object()), \
                patch.object(engine, "implant_850_complete_visible", return_value=False), \
                patch.object(engine, "run_implant_tower", side_effect=engine.SafeStop("패배")):
            with self.assertRaises(engine.SafeStop):
                engine.run_integrated_implant({"implant_850_complete": False})

    def test_implant_discovers_850_completion_from_challenge_menu(self):
        menu = object()
        with patch.object(engine, "open_challenge_menu", return_value=menu), \
                patch.object(engine, "implant_850_complete_visible", return_value=True), \
                patch.object(engine, "return_to_main_battle"), \
                patch.object(engine, "run_implant_tower") as run:
            self.assertEqual(engine.run_integrated_implant({}), "complete")
        run.assert_not_called()

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
            service_quests=False,
        )

    def test_integrated_continuous_dungeons_never_service_draw_quests(self):
        with patch.object(engine, "open_daily_menu", return_value=object()), \
                patch.object(engine, "integrated_ad_pass_visible", return_value=False), \
                patch.object(engine, "run_daily_dungeon_sequence", return_value={}) as run:
            engine.run_integrated_daily_dungeons({})
        self.assertFalse(run.call_args.kwargs["service_quests"])


class IntegratedAdPassPolicyTests(unittest.TestCase):
    def test_key_entry_is_allowed_without_ad_pass(self):
        with patch.object(engine, "daily_start_available", return_value=True), \
                patch.object(engine, "daily_key_count", return_value=1):
            self.assertTrue(engine.integrated_daily_entry_allowed(object(), False))

    def test_ad_entry_requires_positive_pass_confirmation(self):
        with patch.object(engine, "daily_start_available", return_value=True), \
                patch.object(engine, "daily_key_count", return_value=0), \
                patch.object(engine, "daily_ad_pass_applied", return_value=False):
            self.assertFalse(engine.integrated_daily_entry_allowed(object(), False))
            self.assertFalse(engine.integrated_daily_entry_allowed(object(), True))
        with patch.object(engine, "daily_start_available", return_value=True), \
                patch.object(engine, "daily_key_count", return_value=0), \
                patch.object(engine, "daily_ad_pass_applied", return_value=True):
            self.assertTrue(engine.integrated_daily_entry_allowed(object(), True))

    def test_ambiguous_key_and_pass_state_never_allows_entry(self):
        with patch.object(engine, "daily_start_available", return_value=True), \
                patch.object(engine, "daily_key_count", return_value=None):
            self.assertFalse(engine.integrated_daily_entry_allowed(object(), False))


if __name__ == "__main__":
    unittest.main()
