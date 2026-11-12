import unittest

from integrated_automation import MAINTENANCE_ORDER, StallTracker, build_candidates


class StallTrackerTests(unittest.TestCase):
    def test_same_stage_triggers_on_fifth_actual_attempt(self):
        tracker = StallTracker(threshold=5)

        for attempt in range(1, 5):
            self.assertFalse(
                tracker.observe("stage_attempt", "battle", "297-1", attempt)
            )
        self.assertTrue(tracker.observe("stage_attempt", "battle", "297-1", 5))
        self.assertFalse(tracker.observe("stage_attempt", "battle", "297-1", 6))

    def test_regular_battle_polling_does_not_count_as_attempts(self):
        tracker = StallTracker(threshold=5)

        for poll in range(20):
            self.assertFalse(tracker.observe("stage", "battle", "297-1", poll))
        for attempt in range(1, 5):
            self.assertFalse(
                tracker.observe("stage_attempt", "battle", "297-1", 20 + attempt)
            )
        self.assertTrue(tracker.observe("stage_attempt", "battle", "297-1", 25))

    def test_stage_progress_change_resets_attempt_count(self):
        tracker = StallTracker(threshold=5)
        for attempt in range(4):
            tracker.observe("stage_attempt", "battle", "297-1", attempt)

        for attempt in range(4):
            self.assertFalse(
                tracker.observe("stage_attempt", "battle", "297-2", 10 + attempt)
            )
        self.assertTrue(tracker.observe("stage_attempt", "battle", "297-2", 14))

    def test_non_battle_screen_resets_stall(self):
        tracker = StallTracker(threshold=5)
        for attempt in range(4):
            tracker.observe("stage_attempt", "battle", "297-1", attempt)
        tracker.observe("stage", "reward", "297-1", 10)

        self.assertFalse(tracker.observe("stage_attempt", "battle", "297-1", 11))


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

    def test_failed_task_is_retryable_until_three_failures_disable_it(self):
        for failures in (1, 2):
            day = {
                "tasks": {"daily": {"failures": failures, "disabled": False}},
                "implant_850_complete": False,
            }
            self.assertIn("daily", build_candidates(day, {}, completed=set()))

        day["tasks"]["daily"] = {"failures": 3, "disabled": True}
        self.assertNotIn("daily", build_candidates(day, {}, completed=set()))


if __name__ == "__main__":
    unittest.main()
