"""Persistent state and pure scheduling primitives for integrated automation."""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional


MAINTENANCE_ORDER = (
    "daily", "crumble", "arena", "implant", "guild",
    "cookie", "pet", "breakthrough", "fame",
)
DAILY_EXCEPTIONS = ("daily", "crumble", "arena", "implant")
ALERT_TASKS = ("guild", "cookie", "pet")


def _task_pending(tasks: dict, task: str) -> bool:
    """A missing or previously failed task may run; a successful task may not."""
    state = tasks.get(task)
    if not isinstance(state, dict):
        return True
    if bool(state.get("disabled", False)):
        return False
    try:
        failures = int(state.get("failures", 0))
    except (TypeError, ValueError):
        failures = 0
    return 0 < failures < 3


class StallTracker:
    """Fire once when one stage quest and progress key stay unchanged."""

    def __init__(self, threshold: float = 180.0):
        self.threshold = max(1.0, float(threshold))
        self.identity = None
        self.started_at = None
        self.triggered = False

    def reset(self) -> None:
        self.identity = None
        self.started_at = None
        self.triggered = False

    def observe(self, quest: str, screen: str, progress_key: str, at: float) -> bool:
        if quest != "stage" or screen != "battle":
            self.reset()
            return False
        identity = (quest, str(progress_key))
        if identity != self.identity:
            self.identity = identity
            self.started_at = float(at)
            self.triggered = False
            return False
        if self.triggered or self.started_at is None:
            return False
        if float(at) - self.started_at < self.threshold:
            return False
        self.triggered = True
        return True


def build_candidates(day: dict, alerts: dict[str, bool], completed: set[str]) -> list[str]:
    """Return safe maintenance candidates in the fixed user-approved order."""
    tasks = day.get("tasks", {}) if isinstance(day, dict) else {}
    tasks = tasks if isinstance(tasks, dict) else {}
    alerts = alerts if isinstance(alerts, dict) else {}
    completed = {str(item) for item in completed}
    candidates = []

    for task in DAILY_EXCEPTIONS:
        if task == "implant" and bool(day.get("implant_850_complete", False)):
            continue
        if _task_pending(tasks, task):
            candidates.append(task)

    for task in ALERT_TASKS:
        if alerts.get(task, False) and _task_pending(tasks, task):
            candidates.append(task)

    if "coin" in completed and "breakthrough" not in tasks and "breakthrough" not in completed:
        candidates.append("breakthrough")
    if "arena" in completed and "fame" not in tasks and "fame" not in completed:
        candidates.append("fame")

    return [task for task in MAINTENANCE_ORDER if task in candidates]


def _result_text(value) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return str(value)


def run_integrated_maintenance(
    store: "IntegratedAutomationStore",
    alerts_provider: Callable[[], dict[str, bool]],
    runners: dict[str, Callable],
) -> dict:
    """Run one safe maintenance window and persist each isolated outcome.

    Keys beginning with ``_`` are optional lifecycle callbacks supplied by the
    host: ``_recover`` returns to battle and ``_is_stop`` identifies a user
    stop exception. A game relaunch is detected by exception class name so the
    pure scheduler does not need to import the device automation module.
    """
    attempted: list[str] = []
    completed: list[str] = []
    failed: dict[str, str] = {}
    derived: set[str] = set()
    recover = runners.get("_recover")
    is_stop = runners.get("_is_stop", lambda _error: False)

    while True:
        day = store.today()
        alerts = alerts_provider() or {}
        candidates = build_candidates(day, alerts, derived)
        task = next(
            (
                name for name in candidates
                if name not in attempted and callable(runners.get(name))
            ),
            None,
        )
        if task is None:
            break
        attempted.append(task)
        try:
            result = runners[task](day)
            if callable(recover):
                recover()
            next_check_at = "다음 날"
            if isinstance(result, dict):
                next_check_at = result.get("next_check_at") or result.get("free_at") or next_check_at
            store.mark_checked(task, _result_text(result), next_check_at=next_check_at)
            completed.append(task)
            if task == "daily" and isinstance(result, dict) and result.get("coin", 0) > 0:
                derived.add("coin")
            if task == "arena" and isinstance(result, dict) and result.get("completed", 0) > 0:
                derived.add("arena")
            if task == "implant" and result == "complete":
                store.set_implant_850_complete(True)
        except Exception as error:
            if is_stop(error):
                raise
            if error.__class__.__name__ == "GameRelaunched":
                if callable(recover):
                    recover()
                continue
            reason = str(error) or error.__class__.__name__
            store.mark_failure(task, reason)
            failed[task] = reason
            if callable(recover):
                try:
                    recover()
                except Exception as recovery_error:
                    if is_stop(recovery_error):
                        raise

    return {"attempted": attempted, "completed": completed, "failed": failed}


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
