import unittest
from pathlib import Path
from unittest.mock import call, patch

from PIL import Image

import quest_assistant as engine


FIXTURES = Path(__file__).resolve().parent / "tests" / "fixtures" / "integrated"


def fixture(name):
    return Image.open(FIXTURES / name).convert("RGB")


class IntegratedAlertActionTests(unittest.TestCase):
    def test_cookie_pet_and_guild_do_not_enter_without_alert(self):
        no_alerts = {"cookie": False, "pet": False, "guild": False, "dungeon": False}
        with patch.object(engine, "screenshot", return_value=fixture("battle_alerts.png")), \
                patch.object(engine, "integrated_alerts", return_value=no_alerts), \
                patch.object(engine, "tap") as tap:
            self.assertEqual(engine.run_cookie_maintenance(), "no_alert")
            self.assertEqual(engine.run_pet_shelter_collection(), "no_alert")
            self.assertEqual(engine.run_guild_maintenance(), {"status": "no_alert"})
        tap.assert_not_called()

    def test_cookie_inactive_actions_are_skipped(self):
        with patch.object(engine, "screenshot", return_value=fixture("battle_alerts.png")), \
                patch.object(engine, "integrated_alerts", return_value={"cookie": True}), \
                patch.object(engine, "_open_cookie_maintenance", return_value=fixture("cookie_menu.png")), \
                patch.object(engine, "return_to_main_battle"), \
                patch.object(engine, "tap") as tap:
            self.assertEqual(engine.run_cookie_maintenance(), "skipped")
        tap.assert_not_called()

    def test_pet_collects_only_the_confirmed_collect_all_button(self):
        pet = fixture("pet_menu.png")
        with patch.object(engine, "screenshot", side_effect=[fixture("battle_alerts.png"), pet]), \
                patch.object(engine, "integrated_alerts", return_value={"pet": True}), \
                patch.object(engine, "_open_pet_shelter", return_value=pet), \
                patch.object(engine, "return_to_main_battle"), \
                patch.object(engine, "tap") as tap:
            self.assertEqual(engine.run_pet_shelter_collection(), "collected")
        self.assertEqual(tap.call_args_list, [call(engine.PET_COLLECT_ALL, "펫 쉼터 모두 받기", dry_run=False)])

    def test_guild_donation_is_never_allowlisted(self):
        self.assertFalse(engine.allowed_integrated_action(
            "guild_lab", "research_donation", fixture("guild_lab.png")
        ))


class IntegratedGrowthActionTests(unittest.TestCase):
    def test_resource_guard_requires_readable_owned_value_at_least_cost(self):
        image = fixture("growth_menu.png")
        with patch.object(engine, "integrated_resource_values", return_value=(None, 10)):
            self.assertFalse(engine.integrated_cost_action_allowed(
                "breakthrough", "attack_level", image
            ))
        with patch.object(engine, "integrated_resource_values", return_value=(9, 10)):
            self.assertFalse(engine.integrated_cost_action_allowed(
                "breakthrough", "attack_level", image
            ))
        with patch.object(engine, "integrated_resource_values", return_value=(10, 10)):
            self.assertTrue(engine.integrated_cost_action_allowed(
                "breakthrough", "attack_level", image
            ))

    def test_breakthrough_runs_attack_health_defense_once_each(self):
        growth = fixture("growth_menu.png")
        with patch.object(engine, "_open_growth_screen", return_value=growth), \
                patch.object(engine, "screenshot", return_value=growth), \
                patch.object(engine, "integrated_resource_values", return_value=(4_300, 700)), \
                patch.object(engine, "return_to_main_battle"), \
                patch.object(engine, "tap") as tap:
            result = engine.run_breakthrough_once()

        self.assertEqual(result, {"attack": True, "health": True, "defense": True})
        self.assertEqual(
            [item.args[0] for item in tap.call_args_list],
            [engine.BREAKTHROUGH_ATTACK, engine.BREAKTHROUGH_HEALTH, engine.BREAKTHROUGH_DEFENSE],
        )

    def test_fame_with_insufficient_visible_currency_never_taps(self):
        fame = fixture("fame_menu.png")
        with patch.object(engine, "_open_fame_screen", return_value=fame), \
                patch.object(engine, "return_to_main_battle"), \
                patch.object(engine, "tap") as tap:
            self.assertFalse(engine.run_fame_once())
        tap.assert_not_called()


if __name__ == "__main__":
    unittest.main()
