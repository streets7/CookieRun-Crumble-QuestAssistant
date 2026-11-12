import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from integrated_automation import IntegratedAutomationStore


class MutableClock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value


class IntegratedAutomationStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "integrated_automation.json"
        self.clock = MutableClock(datetime(2026, 11, 12, 9, 30, 0))
        self.store = IntegratedAutomationStore(self.path, now=self.clock)

    def test_mark_checked_creates_atomic_normalized_state(self):
        state = self.store.mark_checked("daily", "완료", next_check_at="2026-11-13T00:00:00")

        self.assertEqual(state["date"], "2026-11-12")
        self.assertEqual(state["tasks"]["daily"]["result"], "완료")
        self.assertEqual(state["tasks"]["daily"]["next_check_at"], "2026-11-13T00:00:00")
        self.assertEqual(state["tasks"]["daily"]["failures"], 0)
        self.assertFalse(self.path.with_name(self.path.name + ".tmp").exists())
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["schema"], 1)

    def test_corrupt_file_recovers_to_empty_today(self):
        self.path.write_text("not-json", encoding="utf-8")

        state = self.store.today()

        self.assertEqual(state["date"], "2026-11-12")
        self.assertEqual(state["tasks"], {})
        self.assertIsNone(state["arena_free_at"])
        self.assertFalse(state["implant_850_complete"])
        self.assertEqual(state["stall"], {})

    def test_three_failures_disable_only_that_task_for_today(self):
        self.store.mark_failure("guild", "first")
        self.store.mark_failure("guild", "second")
        state = self.store.mark_failure("guild", "third")

        self.assertEqual(state["tasks"]["guild"]["failures"], 3)
        self.assertTrue(state["tasks"]["guild"]["disabled"])
        self.assertEqual(state["tasks"]["guild"]["result"], "third")

    def test_new_date_resets_daily_tasks_but_retains_implant_completion(self):
        self.store.mark_checked("daily", "완료")
        self.store.set_implant_850_complete()
        self.clock.value = datetime(2026, 11, 13, 0, 1, 0)

        state = self.store.today()

        self.assertEqual(state["date"], "2026-11-13")
        self.assertEqual(state["tasks"], {})
        self.assertTrue(state["implant_850_complete"])

    def test_implant_completion_can_be_cleared_explicitly(self):
        self.store.set_implant_850_complete()

        state = self.store.set_implant_850_complete(False)

        self.assertFalse(state["implant_850_complete"])


if __name__ == "__main__":
    unittest.main()
