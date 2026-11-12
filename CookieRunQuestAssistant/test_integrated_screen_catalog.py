import unittest
from pathlib import Path

from PIL import Image

import quest_assistant as engine


FIXTURES = Path(__file__).resolve().parent / "tests" / "fixtures" / "integrated"


def fixture(name):
    return Image.open(FIXTURES / name).convert("RGB")


class IntegratedScreenCatalogTests(unittest.TestCase):
    def test_battle_alerts_exclude_persistent_dungeon_red_dot(self):
        alerts = engine.integrated_alerts(fixture("battle_alerts.png"))

        self.assertTrue(alerts["cookie"])
        self.assertTrue(alerts["pet"])
        self.assertTrue(alerts["guild"])
        self.assertFalse(alerts["dungeon"])

    def test_confirmed_screens_are_recognized(self):
        cases = {
            "cookie_menu.png": engine.cookie_maintenance_visible,
            "pet_menu.png": engine.pet_shelter_visible,
            "growth_menu.png": engine.breakthrough_visible,
            "fame_menu.png": engine.fame_visible,
            "guild_entry.png": engine.guild_home_visible,
            "guild_help.png": engine.guild_help_visible,
            "guild_lab.png": engine.guild_lab_visible,
            "daily_menu.png": engine.integrated_ad_pass_visible,
        }
        for name, predicate in cases.items():
            with self.subTest(name=name):
                self.assertTrue(predicate(fixture(name)))

    def test_only_observed_safe_actions_are_allowed(self):
        self.assertFalse(engine.allowed_integrated_action(
            "cookie", "batch_upgrade", fixture("cookie_menu.png")
        ))
        self.assertFalse(engine.allowed_integrated_action(
            "cookie", "team_level", fixture("cookie_menu.png")
        ))
        self.assertTrue(engine.allowed_integrated_action(
            "pet", "collect_all", fixture("pet_menu.png")
        ))
        for action in ("attack_level", "health_level", "defense_level"):
            self.assertTrue(engine.allowed_integrated_action(
                "breakthrough", action, fixture("growth_menu.png")
            ))
        self.assertFalse(engine.allowed_integrated_action(
            "fame", "level", fixture("fame_menu.png")
        ))
        self.assertTrue(engine.allowed_integrated_action(
            "guild_help", "help_all", fixture("guild_help.png")
        ))
        self.assertFalse(engine.allowed_integrated_action(
            "guild_lab", "research_support", fixture("guild_lab.png")
        ))
        self.assertFalse(engine.allowed_integrated_action(
            "guild_lab", "research_donation", fixture("guild_lab.png")
        ))

    def test_unknown_or_mismatched_screens_never_allow_actions(self):
        battle = fixture("battle_alerts.png")
        self.assertFalse(engine.allowed_integrated_action("unknown", "tap", battle))
        self.assertFalse(engine.allowed_integrated_action("pet", "collect_all", battle))
        self.assertFalse(engine.allowed_integrated_action(
            "guild_lab", "research_donation", fixture("guild_help.png")
        ))


if __name__ == "__main__":
    unittest.main()
