import tempfile
import unittest
from unittest import mock
from datetime import datetime
from pathlib import Path

from integrated_automation import (
    IntegratedAutomationStore,
    StallTracker,
    build_candidates,
    run_integrated_maintenance,
)


class GameRelaunched(Exception):
    pass


class UserStopped(Exception):
    pass


class IntegratedOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = IntegratedAutomationStore(
            Path(self.temporary.name) / "state.json",
            now=lambda: datetime(2026, 11, 12, 12, 0, 0),
        )

    def test_180_second_stall_then_runs_candidates_in_fixed_order(self):
        tracker = StallTracker(180)
        self.assertFalse(tracker.observe("stage", "battle", "250-30", 0))
        self.assertTrue(tracker.observe("stage", "battle", "250-30", 180))
        calls = []
        runners = {
            name: lambda _day, name=name: calls.append(name) or name
            for name in ("daily", "crumble", "arena", "implant", "guild", "cookie", "pet")
        }

        result = run_integrated_maintenance(
            self.store,
            lambda: {"guild": True, "cookie": True, "pet": True},
            runners,
        )

        self.assertEqual(
            calls,
            ["daily", "crumble", "arena", "implant", "guild", "cookie", "pet"],
        )
        self.assertEqual(result["completed"], calls)

    def test_one_task_failure_does_not_block_later_tasks(self):
        calls = []

        def fail(_day):
            calls.append("daily")
            raise RuntimeError("daily failed")

        result = run_integrated_maintenance(
            self.store,
            lambda: {},
            {
                "daily": fail,
                "crumble": lambda _day: calls.append("crumble") or 4,
                "arena": lambda _day: calls.append("arena") or {"completed": 1},
                "implant": lambda _day: calls.append("implant") or "unavailable",
            },
        )

        self.assertEqual(calls, ["daily", "crumble", "arena", "implant"])
        self.assertEqual(result["failed"], {"daily": "daily failed"})

    def test_failed_daily_task_reappears_until_disabled_after_three_failures(self):
        for expected in (1, 2, 3):
            run_integrated_maintenance(
                self.store,
                lambda: {},
                {"daily": lambda _day: (_ for _ in ()).throw(RuntimeError("no entry"))},
            )
            task = self.store.today()["tasks"]["daily"]
            self.assertEqual(task["failures"], expected)
        self.assertTrue(task["disabled"])
        self.assertNotIn("daily", build_candidates(self.store.today(), {}, set()))

    def test_relaunch_recovers_then_recomputes_current_screen_before_retry(self):
        calls = []
        alerts = [{"cookie": True}, {"pet": True}, {"pet": True}]

        def alert_provider():
            return alerts.pop(0) if alerts else {"pet": True}

        def cookie(_day):
            calls.append("cookie")
            raise GameRelaunched("restarted")

        result = run_integrated_maintenance(
            self.store,
            alert_provider,
            {
                "cookie": cookie,
                "pet": lambda _day: calls.append("pet") or "collected",
                "_recover": lambda: calls.append("recover"),
            },
        )

        self.assertEqual(calls, ["cookie", "recover", "pet", "recover"])
        self.assertIn("pet", result["completed"])
        self.assertNotIn("cookie", self.store.today()["tasks"])

    def test_user_stop_propagates_without_recording_failure_or_recovery(self):
        calls = []

        with self.assertRaises(UserStopped):
            run_integrated_maintenance(
                self.store,
                lambda: {},
                {
                    "daily": lambda _day: (_ for _ in ()).throw(UserStopped()),
                    "_is_stop": lambda error: isinstance(error, UserStopped),
                    "_recover": lambda: calls.append("recover"),
                },
            )

        self.assertEqual(calls, [])
        self.assertNotIn("daily", self.store.today()["tasks"])

    def test_recovers_to_battle_after_each_attempt_and_fresh_run_has_no_candidates(self):
        calls = []
        runners = {
            name: lambda _day, name=name: calls.append(name) or "done"
            for name in ("daily", "crumble", "arena", "implant")
        }
        runners["_recover"] = lambda: calls.append("recover")

        run_integrated_maintenance(self.store, lambda: {}, runners)
        first_calls = list(calls)
        second = run_integrated_maintenance(self.store, lambda: {}, runners)

        self.assertEqual(first_calls.count("recover"), 4)
        self.assertEqual(second["attempted"], [])


class WebIntegrationTests(unittest.TestCase):
    def tearDown(self):
        import quest_assistant as engine
        engine.INTEGRATED_MAINTENANCE_REPORTER = None

    def test_hook_is_installed_only_for_enabled_infinite_quest_mode(self):
        import quest_assistant as engine
        import web_ui

        for data in (
            {"task_quest": True, "infinite": True, "integrated_automation": False},
            {"task_quest": True, "infinite": False, "integrated_automation": True},
            {"task_quest": False, "infinite": True, "integrated_automation": True},
        ):
            web_ui.configure_integrated_automation(data)
            self.assertIsNone(engine.INTEGRATED_MAINTENANCE_REPORTER)

        web_ui.configure_integrated_automation(
            {"task_quest": True, "infinite": True, "integrated_automation": True}
        )
        self.assertTrue(callable(engine.INTEGRATED_MAINTENANCE_REPORTER))

    def test_hook_runs_after_180_seconds_and_returns_to_quest_status(self):
        import quest_assistant as engine
        import web_ui

        times = iter((0.0, 180.0))
        with mock.patch.object(engine, "STOP", False), \
                mock.patch.object(web_ui, "run_integrated_maintenance") as run:
            run.return_value = {"attempted": ["daily"], "completed": ["daily"], "failed": {}}
            web_ui.configure_integrated_automation(
                {"task_quest": True, "infinite": True, "integrated_automation": True},
                clock=lambda: next(times),
            )
            engine.INTEGRATED_MAINTENANCE_REPORTER("stage", "battle", "250-30")
            engine.INTEGRATED_MAINTENANCE_REPORTER("stage", "battle", "250-30")

        run.assert_called_once()
        self.assertEqual(web_ui.STATE["status"], "무한 반복 실행 중")


if __name__ == "__main__":
    unittest.main()
