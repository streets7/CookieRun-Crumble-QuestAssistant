import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import quest_assistant as engine
import web_ui
from daily_summary import DailySummaryStore


class DailySummaryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = DailySummaryStore(
            Path(self.temp.name) / "summary.json",
            now=lambda: datetime(2026, 11, 11, 12, 34, 56),
        )
        self.old_store = web_ui.DAILY_SUMMARY
        web_ui.DAILY_SUMMARY = self.store
        self.addCleanup(setattr, web_ui, "DAILY_SUMMARY", self.old_store)

    def test_run_progress_error_and_recovery_are_accumulated(self):
        data = dict(web_ui.DEFAULTS)
        data.update(task_quest=True, task_arena_decision=True)
        web_ui.record_run_start(data)
        web_ui.update_execution_count(4)
        with patch.object(web_ui, "capture_game_screenshot", return_value=""):
            web_ui.add_error_report({"reason": "테스트", "before_state": "battle"})
        web_ui.LogWriter().write("  복구 성공: 전투 화면 확인\n")

        today = self.store.today()
        self.assertEqual(today["runs"], 1)
        self.assertEqual(today["completed"], 4)
        self.assertEqual(today["errors"], 1)
        self.assertEqual(today["recoveries"], 1)
        self.assertEqual(today["tasks"], {"현재 퀘스트 자동 완료": 1, "아레나 모드": 1})

    def test_normal_screen_return_is_not_counted_as_recovery(self):
        web_ui.LogWriter().write("  복귀 성공: 전투 메인 화면 확인\n")
        self.assertEqual(self.store.today()["recoveries"], 0)

    def test_arena_reporter_writes_structured_decision(self):
        web_ui.configure_daily_summary_callbacks()
        engine.ARENA_DECISION_REPORTER({"deck": 2, "mine": 100, "opponent": 105, "result": "10% 허용 도전"})
        self.assertEqual(self.store.today()["arena"][0]["result"], "10% 허용 도전")

    def test_status_payload_exposes_summary_only_to_admin(self):
        self.store.record_start(["아레나 모드"])
        self.assertNotIn("daily_summary", web_ui.status_payload(False))
        private = web_ui.status_payload(True)
        self.assertEqual(private["daily_summary"]["runs"], 1)
        self.assertEqual(private["daily_summary"]["version"], web_ui.APP_VERSION)
        self.assertEqual(private["daily_summary"]["deployment"]["windows"], "실제 실행 검증 필요")


if __name__ == "__main__":
    unittest.main()
