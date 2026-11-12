import unittest

from integrated_automation import MAINTENANCE_ORDER, StallTracker, build_candidates


class StallTrackerTests(unittest.TestCase):
    def test_same_stage_triggers_once_at_180_seconds(self):
        tracker = StallTracker(threshold=180)

        self.assertFalse(tracker.observe("stage", "battle", "297-1", 1000))
        self.assertFalse(tracker.observe("stage", "battle", "297-1", 1179))
        self.assertTrue(tracker.observe("stage", "battle", "297-1", 1180))
        self.assertFalse(tracker.observe("stage", "battle", "297-1", 1300))

    def test_quest_or_stage_progress_change_resets_elapsed_time(self):
        tracker = StallTracker(threshold=180)
        tracker.observe("stage", "battle", "297-1", 1000)

        self.assertFalse(tracker.observe("monster", "battle", "297-1", 1179))
        self.assertFalse(tracker.observe("stage", "battle", "297-2", 1180))
        self.assertFalse(tracker.observe("stage", "battle", "297-2", 1359))
        self.assertTrue(tracker.observe("stage", "battle", "297-2", 1360))

    def test_non_battle_screen_resets_stall(self):
        tracker = StallTracker(threshold=180)
        tracker.observe("stage", "battle", "297-1", 1000)
        tracker.observe("stage", "reward", "297-1", 1179)

        self.assertFalse(tracker.observe("stage", "battle", "297-1", 1180))


class CandidateSchedulerTests(unittest.TestCase):
    def test_daily_exceptions_precede_alert_driven_candidates(self):
        day = {"tasks": {}, "implant_850_complete": False}
        alerts = {"dungeon": True, "guild": True, "cookie": True, "pet": True}

        candidates = build_candidates(day, alerts, completed={"coin", "arena"})

        self.assertEqual(candidates, list(MAINTENANCE_ORDER))

    def test_dungeon_alert_never_adds_or_readds_a_candidate(self):
        day = {
            "tasks": {
                name: {"disabled": False}
                for name in ("daily", "crumble", "arena", "implant")
            },
            "implant_850_complete": False,
        }

        self.assertEqual(build_candidates(day, {"dungeon": True}, completed=set()), [])

    def test_alert_tasks_require_their_own_alert(self):
        day = {
            "tasks": {
                name: {"disabled": False}
                for name in ("daily", "crumble", "arena", "implant")
            },
            "implant_850_complete": False,
        }

        self.assertEqual(
            build_candidates(day, {"cookie": True, "guild": False}, completed=set()),
            ["cookie"],
        )

    def test_checked_disabled_completed_and_permanent_tasks_do_not_reappear(self):
        day = {
            "tasks": {
                "daily": {"disabled": False},
                "crumble": {"disabled": True},
                "guild": {"disabled": True},
                "cookie": {"disabled": False},
            },
            "implant_850_complete": True,
        }

        candidates = build_candidates(
            day,
            {"guild": True, "cookie": True, "pet": True},
            completed={"arena", "coin", "fame"},
        )

        self.assertEqual(candidates, ["arena", "pet", "breakthrough"])


if __name__ == "__main__":
    unittest.main()
