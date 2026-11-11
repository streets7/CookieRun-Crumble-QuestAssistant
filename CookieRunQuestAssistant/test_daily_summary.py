import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from daily_summary import DailySummaryStore


class DailySummaryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "daily_summary.json"
        self.current = datetime(2026, 11, 11, 9, 30)
        self.store = DailySummaryStore(self.path, now=lambda: self.current)

    def test_empty_store_returns_today_defaults(self):
        self.assertEqual(self.store.today(), {
            "date": "2026-11-11", "runs": 0, "completed": 0,
            "errors": 0, "recoveries": 0, "tasks": {},
            "activities": [], "arena": [],
        })

    def test_records_persist_across_store_instances(self):
        self.store.record_start(["현재 퀘스트 자동 완료", "아레나 모드"])
        self.store.record_completed(3)
        self.store.record_error()
        self.store.record_recovery("전투 화면 복구 성공")
        self.store.record_activity("가방 퀘스트 완료")
        self.store.record_arena_decision({"deck": 1, "mine": 100, "opponent": 105, "result": "도전"})

        saved = DailySummaryStore(self.path, now=lambda: self.current).today()
        self.assertEqual((saved["runs"], saved["completed"], saved["errors"], saved["recoveries"]), (1, 3, 1, 1))
        self.assertEqual(saved["tasks"], {"현재 퀘스트 자동 완료": 1, "아레나 모드": 1})
        self.assertEqual(saved["activities"][-1]["text"], "가방 퀘스트 완료")
        self.assertEqual(saved["arena"][0]["deck"], 1)

    def test_completion_uses_positive_delta_and_new_start_resets_baseline(self):
        self.store.record_start(["현재 퀘스트 자동 완료"])
        for total in (1, 3, 3, 2):
            self.store.record_completed(total)
        self.store.record_start(["현재 퀘스트 자동 완료"])
        self.store.record_completed(2)
        self.assertEqual(self.store.today()["completed"], 5)

    def test_date_change_creates_new_day_and_keeps_only_31_days(self):
        for day in range(33):
            self.current = datetime(2026, 10, 10, 8) + timedelta(days=day)
            self.store.record_start(["아레나 모드"])
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(len(data["days"]), 31)
        self.assertNotIn("2026-10-10", data["days"])
        self.assertEqual(self.store.today()["date"], "2026-11-11")

    def test_corrupt_file_recovers_to_empty_today(self):
        self.path.write_text("{broken", encoding="utf-8")
        recovered = DailySummaryStore(self.path, now=lambda: self.current)
        self.assertEqual(recovered.today()["runs"], 0)
        recovered.record_error()
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["days"]["2026-11-11"]["errors"], 1)

    def test_valid_json_with_non_object_root_recovers(self):
        for content in ("null", "[]", '"text"'):
            with self.subTest(content=content):
                self.path.write_text(content, encoding="utf-8")
                recovered = DailySummaryStore(self.path, now=lambda: self.current)
                self.assertEqual(recovered.today()["runs"], 0)
                recovered.record_error()
                self.assertEqual(recovered.today()["errors"], 1)

    def test_continuous_run_crossing_midnight_counts_only_new_progress(self):
        self.store.record_start(["현재 퀘스트 자동 완료"])
        self.store.record_completed(3)
        self.current = datetime(2026, 11, 12, 0, 1)
        self.store.record_completed(4)
        self.assertEqual(self.store.today()["completed"], 1)

    def test_recent_lists_are_bounded_and_text_is_trimmed(self):
        for number in range(55):
            self.store.record_activity(f"  activity {number}  ")
            self.store.record_arena_decision({"deck": number, "result": "확인"})
        today = self.store.today()
        self.assertEqual(len(today["activities"]), 50)
        self.assertEqual(len(today["arena"]), 50)
        self.assertEqual(today["activities"][0]["text"], "activity 5")


if __name__ == "__main__":
    unittest.main()
