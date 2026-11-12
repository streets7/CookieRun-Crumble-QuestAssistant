"""Persistent state and pure scheduling primitives for integrated automation."""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional


class IntegratedAutomationStore:
    """Keep daily automation state without mixing it with user settings."""

    def __init__(
        self,
        path: Path,
        now: Callable[[], datetime] = datetime.now,
        keep_days: int = 31,
    ):
        self.path = Path(path)
        self.now = now
        self.keep_days = max(1, int(keep_days))
        self.lock = threading.RLock()

    @staticmethod
    def _empty_day(date: str) -> dict:
        return {
            "date": date,
            "tasks": {},
            "arena_free_at": None,
            "stall": {},
        }

    @staticmethod
    def _empty_root() -> dict:
        return {
            "schema": 1,
            "permanent": {"implant_850_complete": False},
            "days": {},
        }

    def _date(self) -> str:
        return self.now().strftime("%Y-%m-%d")

    def _read(self) -> dict:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or not isinstance(value.get("days", {}), dict):
                raise ValueError("invalid integrated automation state")
            permanent = value.get("permanent", {})
            if not isinstance(permanent, dict):
                permanent = {}
            return {
                "schema": 1,
                "permanent": {
                    "implant_850_complete": bool(permanent.get("implant_850_complete", False))
                },
                "days": value.get("days", {}),
            }
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return self._empty_root()

    def _normalize_task(self, value) -> dict:
        value = value if isinstance(value, dict) else {}
        try:
            failures = max(0, min(3, int(value.get("failures", 0))))
        except (TypeError, ValueError):
            failures = 0
        return {
            "result": str(value.get("result", ""))[:300],
            "checked_at": str(value.get("checked_at", ""))[:32],
            "next_check_at": (
                str(value.get("next_check_at"))[:32]
                if value.get("next_check_at") is not None else None
            ),
            "failures": failures,
            "disabled": failures >= 3 or bool(value.get("disabled", False)),
        }

    def _normalize_day(self, value, date: str) -> dict:
        value = value if isinstance(value, dict) else {}
        result = self._empty_day(date)
        tasks = value.get("tasks", {})
        if isinstance(tasks, dict):
            for name, task in list(tasks.items())[:50]:
                result["tasks"][str(name)[:60]] = self._normalize_task(task)
        if value.get("arena_free_at") is not None:
            result["arena_free_at"] = str(value["arena_free_at"])[:32]
        stall = value.get("stall", {})
        if isinstance(stall, dict):
            result["stall"] = {
                str(key)[:60]: str(item)[:100]
                for key, item in list(stall.items())[:10]
            }
        return result

    def _public(self, root: dict, day: dict) -> dict:
        result = deepcopy(day)
        result["implant_850_complete"] = bool(
            root["permanent"].get("implant_850_complete", False)
        )
        return result

    def _update(self, change) -> dict:
        with self.lock:
            root = self._read()
            date = self._date()
            day = self._normalize_day(root["days"].get(date), date)
            change(root, day)
            root["days"][date] = day
            cutoff = (self.now().date() - timedelta(days=self.keep_days - 1)).isoformat()
            root["days"] = {
                key: value for key, value in root["days"].items()
                if isinstance(key, str) and key >= cutoff
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(self.path.name + ".tmp")
            temporary.write_text(
                json.dumps(root, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temporary.replace(self.path)
            return self._public(root, day)

    def today(self) -> dict:
        with self.lock:
            root = self._read()
            day = self._normalize_day(root["days"].get(self._date()), self._date())
            return self._public(root, day)

    def mark_checked(
        self, task: str, result: str, next_check_at: Optional[str] = None
    ) -> dict:
        task = str(task)[:60]
        result = str(result)[:300]

        def change(_root, day):
            day["tasks"][task] = {
                "result": result,
                "checked_at": self.now().isoformat(timespec="seconds"),
                "next_check_at": str(next_check_at)[:32] if next_check_at else None,
                "failures": 0,
                "disabled": False,
            }

        return self._update(change)

    def mark_failure(self, task: str, reason: str) -> dict:
        task = str(task)[:60]
        reason = str(reason)[:300]

        def change(_root, day):
            previous = self._normalize_task(day["tasks"].get(task))
            failures = min(3, previous["failures"] + 1)
            day["tasks"][task] = {
                "result": reason,
                "checked_at": self.now().isoformat(timespec="seconds"),
                "next_check_at": None,
                "failures": failures,
                "disabled": failures >= 3,
            }

        return self._update(change)

    def set_implant_850_complete(self, value: bool = True) -> dict:
        def change(root, _day):
            root["permanent"]["implant_850_complete"] = bool(value)

        return self._update(change)
