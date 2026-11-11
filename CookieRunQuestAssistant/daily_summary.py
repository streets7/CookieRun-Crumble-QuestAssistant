"""Persistent, privacy-limited daily activity summary for the admin UI."""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable


class DailySummaryStore:
    def __init__(self, path: Path, keep_days: int = 31,
                 now: Callable[[], datetime] = datetime.now):
        self.path = Path(path)
        self.keep_days = max(1, int(keep_days))
        self.now = now
        self.lock = threading.RLock()

    @staticmethod
    def _empty(date: str) -> dict:
        return {
            "date": date, "runs": 0, "completed": 0,
            "errors": 0, "recoveries": 0, "tasks": {},
            "activities": [], "arena": [],
        }

    def _read(self) -> dict:
        try:
            source = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(source, dict):
                raise ValueError("root must be an object")
            days = source.get("days", {})
            if not isinstance(days, dict):
                raise ValueError("days must be an object")
            baseline = source.get("last_completed_total")
            if baseline is None and days:
                latest = days.get(max(days), {})
                baseline = latest.get("last_completed_total", 0) if isinstance(latest, dict) else 0
            return {"schema": 2, "days": days, "last_completed_total": max(0, int(baseline or 0))}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {"schema": 2, "days": {}, "last_completed_total": 0}

    def _date(self) -> str:
        return self.now().strftime("%Y-%m-%d")

    def _normalized_day(self, value, date: str) -> dict:
        result = self._empty(date)
        if not isinstance(value, dict):
            return result
        for key in ("runs", "completed", "errors", "recoveries"):
            try:
                result[key] = max(0, int(value.get(key, 0)))
            except (TypeError, ValueError):
                pass
        tasks = value.get("tasks", {})
        if isinstance(tasks, dict):
            for key, count in list(tasks.items())[:100]:
                try:
                    result["tasks"][str(key)[:100]] = max(0, int(count))
                except (TypeError, ValueError):
                    continue
        for key in ("activities", "arena"):
            items = value.get(key, [])
            if isinstance(items, list):
                result[key] = [item for item in items[-50:] if isinstance(item, dict)]
        return result

    def _update(self, change) -> dict:
        with self.lock:
            data = self._read()
            date = self._date()
            day = self._normalized_day(data["days"].get(date), date)
            change(day, data)
            data["days"][date] = day
            cutoff = (self.now().date() - timedelta(days=self.keep_days - 1)).isoformat()
            data["days"] = {
                key: value for key, value in data["days"].items()
                if isinstance(key, str) and key >= cutoff
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(self.path.name + ".tmp")
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.path)
            return self._public(day)

    @staticmethod
    def _public(day: dict) -> dict:
        return deepcopy(day)

    def today(self) -> dict:
        with self.lock:
            date = self._date()
            day = self._normalized_day(self._read()["days"].get(date), date)
            return self._public(day)

    def record_start(self, task_labels: list[str]):
        def change(day, data):
            day["runs"] += 1
            data["last_completed_total"] = 0
            for label in dict.fromkeys(str(item).strip() for item in task_labels if str(item).strip()):
                label = label[:100]
                day["tasks"][label] = day["tasks"].get(label, 0) + 1
        return self._update(change)

    def record_completed(self, total: int):
        total = max(0, int(total))
        def change(day, data):
            previous = data.get("last_completed_total", 0)
            if total >= previous:
                day["completed"] += total - previous
            data["last_completed_total"] = total
        return self._update(change)

    def record_error(self):
        return self._update(lambda day, data: day.__setitem__("errors", day["errors"] + 1))

    def record_recovery(self, text: str):
        text = str(text).strip()[:300]
        def change(day, data):
            day["recoveries"] += 1
            self._append(day["activities"], text)
        return self._update(change)

    def record_activity(self, text: str):
        text = str(text).strip()[:300]
        if not text:
            return self.today()
        return self._update(lambda day, data: self._append(day["activities"], text))

    def record_arena_decision(self, data: dict):
        allowed = ("deck", "mine", "opponent", "result")
        item = {key: data.get(key) for key in allowed if key in data}
        item["time"] = self.now().strftime("%H:%M:%S")
        return self._update(lambda day, data: self._append(day["arena"], item))

    def _append(self, target: list, value):
        if isinstance(value, str):
            value = {"time": self.now().strftime("%H:%M:%S"), "text": value}
        target.append(value)
        del target[:-50]
