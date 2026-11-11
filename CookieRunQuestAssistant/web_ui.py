#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import contextlib
import hashlib
import os
import platform
import sys
import io
import json
import re
import secrets
import subprocess
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import quest_assistant as engine
import release_update
from daily_summary import DailySummaryStore
from ui_live import LiveHTML


HOST = "127.0.0.1"
PORT = int(os.environ.get("CQA_PORT", "8765"))
APP_VERSION = "v16.0"
STABLE_VERSION = "v16.0"
GITHUB_REPOSITORY = os.environ.get("CQA_GITHUB_REPOSITORY", "").strip()
ADMIN_TOKENS = set()
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
SOURCE_DIR = Path(__file__).resolve().parent


def load_private_config(path=None):
    values = {
        "admin_password": "",
        "support_account": "",
        "support_holder": "",
        "contact_email": "",
    }
    target = Path(path) if path is not None else RESOURCE_DIR / "private_config.json"
    try:
        loaded = json.loads(target.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            for key in values:
                values[key] = str(loaded.get(key, "")).strip()
    except (OSError, ValueError, TypeError):
        pass
    return values


PRIVATE_CONFIG = load_private_config()


def application_data_dir() -> Path:
    configured = os.environ.get("CQA_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    if not getattr(sys, "frozen", False):
        return SOURCE_DIR
    if engine.IS_WINDOWS:
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "CookieRunCrumbleQuestAssistant"
    return Path.home() / "Library" / "Application Support" / "CookieRunCrumbleQuestAssistant"


DATA_DIR = application_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)
ROOT_DIR = RESOURCE_DIR
SETTINGS_FILE = DATA_DIR / "settings.json"
UI_LAYOUT_FILE = DATA_DIR / "ui_layout.json"
DAILY_SUMMARY_FILE = DATA_DIR / "daily_summary.json"
CHANNEL_FILE = DATA_DIR / "channel.json"
RELEASES_DIR = DATA_DIR / "releases"
ERROR_SCREENSHOT_DIR = DATA_DIR / "error_screenshots"
SCREENSHOT_MAX_BYTES = 200 * 1024 * 1024
SCREENSHOT_TARGET_BYTES = 150 * 1024 * 1024
LOCK = threading.Lock()
STATE = {"running": False, "paused": False, "maintenance": False, "pause_requested": False, "can_skip": False, "last_data": None, "status": "대기 중", "logs": [], "errors": [], "execution_count": 0, "worker": None}
DAILY_SUMMARY = DailySummaryStore(DAILY_SUMMARY_FILE)


def source_build_id():
    digest = hashlib.sha256()
    for path in (Path(__file__).resolve(), Path(engine.__file__).resolve()):
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(str(path).encode("utf-8"))
            digest.update(APP_VERSION.encode("utf-8"))
    return digest.hexdigest()[:16]


BUILD_ID = source_build_id()

DEFAULTS = {
    "cycles": 1, "infinite": False, "automatic_check": False, "dry_run": False,
    "adjust_screen_size": True, "screen_width": 1080, "screen_height": 1920,
    "task_quest": True, "restart_game_on_exit": True,
    "task_auto_hunt_reward": False, "task_attendance": False,
    "task_missions": False, "task_event_rewards": False,
    "task_pass_free": False, "task_mailbox": False,
    "task_crumble_dungeon": False, "task_crumble_dungeon_runs": 1,
    "task_arena": False, "task_arena_runs": 1,
    "task_arena_decision": False, "arena_decision_mode": "compare", "arena_kind": "regular",
    "task_implant_tower": False, "task_implant_tower_runs": 1,
    "task_exp_dungeon": False, "task_exp_dungeon_runs": 1, "task_exp_dungeon_continuous": False,
    "task_coin_dungeon": False, "task_coin_dungeon_runs": 1, "task_coin_dungeon_continuous": False,
    "task_dough_dungeon": False, "task_dough_dungeon_runs": 1, "task_dough_dungeon_continuous": False,
    "task_research_stone_dungeon": False, "task_research_stone_dungeon_runs": 1, "task_research_stone_dungeon_continuous": False,
    "task_rune_crystal_dungeon": False, "task_rune_crystal_dungeon_runs": 1, "task_rune_crystal_dungeon_continuous": False,
    "task_guild_attendance": False,
    "task_cookie_upgrade": False, "task_pet_upgrade": False,
    "task_breakthrough": False,
    "draw_timeout": 25, "equipment_timeout": 90, "monster_timeout": 180,
    "bag_timeout": 30, "stage_timeout": 300,
    "boss_move_seconds": 4.0, "boss_corner_move_seconds": 6.0,
    "boss_preset_1": False, "boss_preset_2": True, "boss_preset_3": True,
    "boss_preset_4": False, "boss_preset_5": True, "boss_preset_order": "5,2,3",
    "boss_keyboard_move": False,
    "boss_keyboard_move_normal": False, "boss_keyboard_move_corner": False,
    "quest_panel": "900,1060", "ten_draw": "575,1565",
    "bottom_x": "540,1845", "auto_button": "415,1725",
    "auto_start": "540,1690", "bag_item": "160,1160",
    "item_minus": "225,708", "item_use": "540,850",
    "equipment_action": "723,1300", "boss_summon": "540,305",
}

TASK_LABELS = {
    "task_quest": "현재 퀘스트 자동 완료",
    "task_auto_hunt_reward": "자동 사냥 무료 보상",
    "task_attendance": "오늘의 출석 보상",
    "task_missions": "일일·주간 미션 모두 받기",
    "task_event_rewards": "이벤트 무료 보상",
    "task_pass_free": "크럼블 패스 무료 보상",
    "task_mailbox": "우편함 보상",
    "task_crumble_dungeon": "크럼블 던전",
    "task_arena": "아레나",
    "task_arena_decision": "아레나 모드",
    "task_implant_tower": "임플란트 타워",
    "task_exp_dungeon": "경험치 던전",
    "task_coin_dungeon": "코인 던전",
    "task_dough_dungeon": "반죽 던전",
    "task_research_stone_dungeon": "연구석 던전",
    "task_rune_crystal_dungeon": "룬결정 던전",
    "task_guild_attendance": "길드 출석 보상",
    "task_cookie_upgrade": "쿠키 일괄 업데이트",
    "task_pet_upgrade": "펫 일괄 업데이트",
    "task_breakthrough": "돌파력 업그레이드",
}
IMPLEMENTED_TASKS = {
    "task_arena_decision",
    "task_quest", "task_crumble_dungeon", "task_arena", "task_implant_tower",
    "task_exp_dungeon", "task_coin_dungeon", "task_dough_dungeon",
    "task_research_stone_dungeon", "task_rune_crystal_dungeon",
}
TASK_COUNT_LIMITS = {
    "task_crumble_dungeon": ("task_crumble_dungeon_runs", 5),
    "task_arena": ("task_arena_runs", 5),
    "task_implant_tower": ("task_implant_tower_runs", 5),
    "task_exp_dungeon": ("task_exp_dungeon_runs", 3),
    "task_coin_dungeon": ("task_coin_dungeon_runs", 3),
    "task_dough_dungeon": ("task_dough_dungeon_runs", 3),
    "task_research_stone_dungeon": ("task_research_stone_dungeon_runs", 3),
    "task_rune_crystal_dungeon": ("task_rune_crystal_dungeon_runs", 3),
}
TASK_GROUPS = {
    "arena_decision": ("task_arena_decision",),
    "daily_rewards": (
        "task_auto_hunt_reward", "task_attendance", "task_missions",
        "task_event_rewards", "task_pass_free", "task_mailbox",
        "task_guild_attendance",
    ),
    "challenge": ("task_crumble_dungeon", "task_arena", "task_implant_tower"),
    "daily_dungeon": (
        "task_exp_dungeon", "task_coin_dungeon", "task_dough_dungeon",
        "task_research_stone_dungeon", "task_rune_crystal_dungeon",
    ),
    "growth": ("task_cookie_upgrade", "task_pet_upgrade", "task_breakthrough"),
}


def summary_call(method, *args):
    try:
        return getattr(DAILY_SUMMARY, method)(*args)
    except (OSError, ValueError, TypeError):
        return None


def record_run_start(data):
    labels = [label for key, label in TASK_LABELS.items() if data.get(key)]
    return summary_call("record_start", labels)


def configure_daily_summary_callbacks():
    engine.ARENA_DECISION_REPORTER = lambda item: summary_call("record_arena_decision", item)


def release_catalog():
    return {"stable": {"version": APP_VERSION, "file": ""}}


def active_channel():
    # Old saved beta selections are treated as the unified stable release.
    return "stable"


def channel_status():
    return {"active": "stable", "active_version": APP_VERSION,
            "stable": release_catalog()["stable"]}


def apply_channel_policy(data):
    # v15.0 promotes the complete beta checklist and dungeon controls to the
    # stable channel, so stable runs no longer suppress non-quest tasks.
    return dict(data)


def apply_run_scope(data, scope):
    """Apply the exclusive checklist rules for infinite and group starts."""
    if not scope:
        result = dict(data)
        if result.get("infinite"):
            for key in TASK_LABELS:
                result[key] = key == "task_quest"
        return result
    if scope not in TASK_GROUPS:
        raise ValueError("알 수 없는 독립 실행 묶음입니다.")
    allowed = set(TASK_GROUPS[scope])
    result = dict(data)
    for key in TASK_LABELS:
        result[key] = key in allowed and bool(data.get(key))
    result["infinite"] = False
    return result


def prepare_group_run(request):
    """Build an independent run without relying on the main quest controls."""
    scope = request.get("scope")
    if not isinstance(scope, str) or scope not in TASK_GROUPS:
        raise ValueError("알 수 없는 독립 실행 묶음입니다.")
    selected = request.get("selected_tasks", [])
    allowed = TASK_GROUPS[scope]
    if not isinstance(selected, list) or not all(
        isinstance(key, str) and key in allowed for key in selected
    ):
        raise ValueError("이 묶음에 속한 작업만 선택해 주세요.")
    if not selected:
        raise ValueError("실행할 항목을 하나 이상 체크해 주세요.")
    if not any(key in IMPLEMENTED_TASKS for key in selected):
        raise ValueError("선택한 작업은 아직 제작 중이라 실행할 수 없습니다. 현재 도전 던전과 일일 던전만 실행 가능합니다.")
    overrides = request.get("settings", {})
    if not isinstance(overrides, dict):
        raise ValueError("실행 설정 형식이 올바르지 않습니다.")
    raw = settings()
    raw.update({key: value for key, value in overrides.items() if key in DEFAULTS})
    for key in TASK_LABELS:
        raw[key] = key in selected
    raw.update(infinite=False, cycles=1, task_quest=False)
    return validate(raw)


HTML = r'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>쿠키런: 크럼블 퀘스트 도우미</title>
<style>
:root{color-scheme:dark;--bg:#10172a;--card:#19233b;--line:#31405f;--accent:#60a5fa;--danger:#fb7185;--text:#eef4ff;--muted:#9fb0cd}
*{box-sizing:border-box}body{margin:0;background:linear-gradient(145deg,#0b1020,#17213a);font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo",sans-serif;color:var(--text)}
.wrap{max-width:1240px;margin:8px auto;padding:0 10px}.title{font-size:23px;font-weight:800;margin:0}.version{display:inline-block;vertical-align:middle;margin-left:8px;padding:3px 8px;border-radius:999px;background:#263b63;color:#93c5fd;font-size:12px}.sub{color:var(--muted);margin:0 0 2px;font-size:12px}
#layoutCanvas{position:relative;display:grid;grid-template-columns:minmax(0,1.08fr) minmax(360px,.92fr);gap:8px;grid-auto-flow:dense}.layout-toolbar{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:7px 0}.layout-toolbar button{flex:0 0 auto;padding:6px 10px;font-size:10px}.layout-help{color:var(--muted);font-size:10px}.snap-toggle{display:flex;align-items:center;gap:5px;margin:0;padding:5px 8px;border:1px solid #315277;border-radius:8px;background:#132640;color:#bfdbfe;font-size:10px;font-weight:800}.snap-toggle input{width:auto;margin:0}.layout-drag-handle{display:none;position:absolute;z-index:10;right:25px;top:5px;padding:4px 8px;border-radius:7px;background:#2563eb;color:white;font-size:10px;font-weight:800;cursor:grab;touch-action:none}.layout-drag-handle:active{cursor:grabbing}.snap-guide{display:none;position:absolute;z-index:100;pointer-events:none;background:#4ade80;box-shadow:0 0 8px #4ade80}.snap-guide.vertical{top:0;bottom:0;width:1px}.snap-guide.horizontal{left:0;right:0;height:1px}#layoutCanvas.layout-editing .snap-guide.visible{display:block}#layoutCanvas.custom-layout{display:block;min-height:600px}#layoutCanvas.custom-layout>.card{position:absolute;max-width:none;min-width:240px;min-height:100px;margin:0}#layoutCanvas.layout-editing{outline:2px dashed #60a5fa80;outline-offset:4px;background:#60a5fa08}#layoutCanvas.layout-editing>.card{resize:both;overflow:auto;outline:1px dashed #60a5fa;user-select:none}#layoutCanvas.layout-editing>.card.snap-flash{outline:2px solid #4ade80;box-shadow:0 0 14px #4ade8055}#layoutCanvas.layout-editing .layout-drag-handle{display:block}.layout-toolbar .save-layout{background:#22c55e;color:#052e16}.layout-toolbar .cancel-layout{background:#f59e0b;color:#2d1b00}
.feature-removable{position:relative}.feature-remove-button{display:none;position:absolute;z-index:18;right:4px;top:4px;width:19px!important;height:19px;padding:0!important;border-radius:50%;border:1px solid #fb7185!important;background:#dc2626!important;color:white!important;font-size:11px!important;line-height:17px!important;cursor:pointer!important;opacity:1;box-shadow:none!important;flex:0 0 19px!important}.layout-editing .feature-remove-button{display:block}.feature-removed{display:none!important}.task-row.feature-removable{padding-right:8px}.layout-editing .task-row.feature-removable{padding-right:30px}.task-group-collapsible.feature-removable>summary{padding-right:0}.layout-editing .task-group-collapsible.feature-removable>summary{padding-right:25px}.task-group-collapsible:not([open]) .task-row>.feature-remove-button{display:none!important}.settings-section.feature-removable,.channel-box.feature-removable,.inline-dashboard.feature-removable,.combined-error-report.feature-removable,#screenshotStorage.feature-removable{padding-right:11px}.layout-editing .settings-section.feature-removable,.layout-editing .channel-box.feature-removable,.layout-editing .inline-dashboard.feature-removable,.layout-editing .combined-error-report.feature-removable,.layout-editing #screenshotStorage.feature-removable{padding-right:30px}.layout-toolbar .restore-features{background:#475569;color:#e2e8f0}.layout-toolbar .restore-features:disabled{opacity:.45}
.card{background:rgba(25,35,59,.94);border:1px solid var(--line);border-radius:12px;padding:12px;margin:0;box-shadow:0 8px 20px #0004}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.wide{grid-column:1/-1}label{display:block;color:var(--muted);font-size:11px;margin-bottom:3px}
input{width:100%;background:#0d1528;color:var(--text);border:1px solid var(--line);border-radius:8px;padding:7px;font-size:13px}
select{width:100%;background:#0d1528;color:var(--text);border:1px solid var(--line);border-radius:8px;padding:7px;font-size:12px}.screen-config{margin-top:10px;padding:9px;background:#0d1528;border:1px solid var(--line);border-radius:9px}.screen-config-grid{display:grid;grid-template-columns:minmax(180px,1fr) 90px 90px;gap:7px;align-items:end}.screen-config .check{margin-bottom:7px}.screen-size-note{color:var(--muted);font-size:9px;margin-top:5px}
.check{display:flex;gap:7px;align-items:center}.check input{width:auto}.buttons{display:flex;gap:6px;margin-top:9px}
button{border:0;border-radius:8px;padding:8px 10px;font-weight:750;font-size:12px;cursor:pointer;background:var(--accent);color:#07101f;flex:1}
button.stop{background:var(--danger);color:white}button.next{background:#8b5cf6;color:white}button.quit{background:#7f1d1d;color:white}button.secondary{background:#354461;color:white}#start{background:linear-gradient(135deg,#f8df86,#e8c85b);color:#3d3105;box-shadow:0 5px 14px #e8c85b35}#infiniteStart{background:linear-gradient(135deg,#60a5fa,#2563eb);color:white;box-shadow:0 5px 14px #2563eb45}button:disabled{opacity:.45;cursor:not-allowed}
.status{font-size:17px;font-weight:800}.dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#94a3b8;margin-right:7px}.running .dot{background:#4ade80;box-shadow:0 0 12px #4ade80}
pre{height:190px;overflow:auto;white-space:pre-wrap;background:#080d19;border-radius:8px;padding:9px;color:#cfe2ff;border:1px solid #26324a}
details summary{cursor:pointer;font-weight:750;margin-bottom:7px}.warning{color:#fbbf24;font-size:11px;margin:6px 0}.footer{grid-column:1/-1;color:#7f91af;text-align:center;font-size:10px;margin:2px}
.errors{display:grid;gap:8px;margin-top:14px;max-height:298px;overflow-y:auto;padding-right:5px}.error-item{height:94px;overflow:hidden;background:#281724;border:1px solid #713348;border-radius:12px;padding:10px 13px}.error-head{display:flex;justify-content:space-between;gap:12px;color:#fda4af}.error-reason{margin:6px 0;color:#ffe4e6;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.error-meta{color:#c7a9b3;font-size:12px;line-height:1.35}.empty{color:var(--muted);padding:8px 0}
.admin-row{display:flex;align-items:end;gap:10px}.admin-row>div{flex:1}.admin-row button{flex:0 0 auto}.admin-ok{color:#86efac;font-size:13px;margin-top:10px}.hidden{display:none!important}
.admin-popup-launch,.admin-popup-close,.admin-submenu{display:none}.admin-popup-panel.admin-popup-ready:not(.admin-popup-active){height:44px!important;min-height:44px!important;padding:7px 10px!important;overflow:hidden!important;resize:none!important}.admin-popup-panel.admin-popup-ready:not(.admin-popup-active)>.admin-popup-launch{display:flex;width:100%;height:28px;align-items:center;justify-content:space-between;gap:10px;padding:4px 8px;background:#233654;color:#dbeafe;text-align:left}.admin-popup-panel.admin-popup-ready:not(.admin-popup-active)>.admin-popup-content{display:none}.admin-popup-launch .popup-arrow{color:#93c5fd}.admin-popup-storage:not(.admin-popup-active){display:none!important}#adminCard.admin-authenticated>.admin-submenu{display:grid;grid-template-columns:1fr;gap:4px;margin-top:8px;padding-top:8px;border-top:1px solid var(--line)}#adminCard .admin-submenu button{display:flex;align-items:center;justify-content:space-between;width:100%;height:28px;padding:4px 8px;background:#172a46;color:#dbeafe;text-align:left;font-size:10px}#adminCard .admin-submenu button span:last-child{color:#93c5fd}.admin-popup-backdrop{display:none;position:fixed;inset:0;z-index:9998;background:#030712b8;backdrop-filter:blur(3px)}body.admin-popup-open .admin-popup-backdrop{display:block}.admin-popup-panel.admin-popup-active{display:block!important;position:fixed!important;z-index:9999!important;left:50%!important;top:50%!important;transform:translate(-50%,-50%)!important;width:min(920px,calc(100vw - 30px))!important;height:min(760px,calc(100vh - 30px))!important;min-width:0!important;min-height:0!important;max-width:none!important;margin:0!important;padding:16px!important;overflow:auto!important;resize:none!important;outline:1px solid #60a5fa!important;box-shadow:0 24px 80px #000c!important}.admin-popup-panel.admin-popup-active>.admin-popup-launch{display:none}.admin-popup-panel.admin-popup-active>.admin-popup-content{display:block}.admin-popup-panel.admin-popup-active>.admin-popup-close{display:block;position:sticky;z-index:4;top:0;margin:0 0 8px auto;width:auto;min-width:70px;padding:6px 10px;background:#7f1d1d;color:white}.admin-popup-panel.admin-popup-active details>summary{display:none}.admin-popup-panel.admin-popup-active details{display:block}.admin-popup-panel.admin-popup-active details>.grid{margin-top:4px}
.channel-box{margin-top:10px;padding:9px;background:#0d1528;border:1px solid var(--line);border-radius:9px}.channel-current{font-size:12px;font-weight:800;color:#93c5fd}.channel-versions{font-size:10px;color:var(--muted);margin-top:4px;line-height:1.5}.channel-buttons{display:flex;align-items:center;gap:6px;margin-top:7px}.channel-buttons>.help-dot{flex:0 0 17px;margin-left:0}.channel-buttons button.active{outline:2px solid #86efac;box-shadow:0 0 10px #4ade8040}.channel-notice{margin-top:7px;color:#fbbf24;font-size:10px}
.boss-preset-row{margin-top:8px;padding:9px 10px;border:1px solid #315277;border-radius:9px;background:#101c32}.boss-preset-title{font-size:11px;font-weight:850;color:#dbeafe}.boss-preset-help{margin:2px 0 7px;color:var(--muted);font-size:9px}.boss-preset-options{display:flex;gap:6px;flex-wrap:wrap}.boss-preset-option{display:flex;align-items:center;justify-content:center;gap:4px;min-width:52px;margin:0;padding:6px 8px;border:1px solid #3b4d70;border-radius:8px;background:#172640;color:#dbeafe;font-weight:850;cursor:pointer}.boss-preset-option:has(input:checked){border-color:#60a5fa;background:#1d4f91;color:white}.boss-preset-option input{width:auto;margin:0;padding:0}.boss-preset-rank{display:inline-flex;align-items:center;justify-content:center;min-width:15px;height:15px;padding:0 3px;border-radius:999px;background:#f8df86;color:#3d3105;font-size:8px}.boss-preset-rank:empty{display:none}
.boss-keyboard-options{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px;margin-top:8px;padding-top:7px;border-top:1px solid #315277}.boss-keyboard-option{display:flex;align-items:center;gap:7px;margin:0;padding:7px 8px;border:1px solid #314968;border-radius:8px;background:#111f36;color:#dbeafe;font-size:10px;font-weight:800}.boss-keyboard-option:has(input:checked){border-color:#4a72a0;background:#142d4c}.boss-keyboard-option input{width:auto;margin:0}.boss-keyboard-option small{color:var(--muted);font-weight:500}
.boss-movement-public{margin-top:8px;padding:10px;border:1px solid #3b5479;border-radius:10px;background:linear-gradient(145deg,#101e35,#0d1729)}.boss-movement-public .settings-section-head{margin-bottom:8px}.boss-movement-actions{display:flex;justify-content:flex-end;margin-top:8px}.boss-movement-actions button{flex:0 0 auto;width:auto;padding:7px 12px;background:#2563eb;color:white}
.task-checklist-panel{min-width:0;margin-top:10px;padding:10px;border:1px solid #3b5479;border-radius:11px;background:linear-gradient(145deg,#101e35,#0d1729)}.boss-config-header{display:flex;align-items:center;gap:9px;margin-bottom:9px;padding-bottom:9px;border-bottom:1px solid #3b5479}.boss-config-icon{display:grid;place-items:center;width:34px;height:34px;flex:0 0 34px;border-radius:10px;background:linear-gradient(145deg,#2563eb,#4f46e5);font-size:18px;box-shadow:0 5px 14px #2563eb45}.boss-config-title{font-size:14px;font-weight:900;color:#eaf4ff}.boss-config-sub{margin-top:2px;color:var(--muted);font-size:9px}#summaryCard{display:block}#bossPopupContent>.boss-preset-row{margin:0;padding:10px;border-color:#4b6690;background:linear-gradient(145deg,#142844,#101d33)}#bossPopup .boss-preset-title{font-size:12px;color:#f8df86}#bossPopup .boss-preset-options{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:5px}#bossPopup .boss-preset-option{min-width:0;padding:8px 4px;flex-direction:column;gap:3px;text-align:center;font-size:9px}#bossPopupContent>.boss-movement-public{margin-top:9px;padding:10px;border-color:#4a5f85;background:linear-gradient(145deg,#111f37,#171a35)}#bossPopupContent>.boss-movement-public .movement-guide{grid-template-columns:repeat(2,minmax(0,1fr))}#bossPopupContent>.boss-movement-public .boss-keyboard-options{grid-template-columns:repeat(2,minmax(0,1fr))}#controlCard>.task-checklist-panel .boss-preset-row{display:none}
.dashboard-warning{margin:8px 0 0;white-space:nowrap;font-size:10px;letter-spacing:-.15px}.compact-check{margin:0}.compact-check>div{display:flex;align-items:center;gap:5px}.compact-check .help-dot{margin-left:2px}#runSetupFeature{display:block;margin-top:10px!important;padding:9px 10px!important}
.task-popup-launch{margin-top:10px}.task-popup-launch button{display:flex;align-items:center;justify-content:space-between;gap:10px;width:100%;padding:11px 13px;border:1px solid #43658f;background:linear-gradient(135deg,#173359,#1d4779);color:#eaf4ff;text-align:left}.task-popup-launch strong{display:block;font-size:12px}.task-popup-launch small{color:#a9d4ff;font-size:9px}.task-popup-launch .popup-arrow{font-size:18px;color:#93c5fd}.task-popup-backdrop{display:none;position:fixed;inset:0;z-index:8998;background:#020617b8;backdrop-filter:blur(3px)}.task-popup{display:none;position:fixed;z-index:8999;left:50%;top:50%;transform:translate(-50%,-50%);width:min(820px,calc(100vw - 28px));max-height:min(760px,calc(100vh - 28px));padding:14px;border:1px solid #5275a3;border-radius:15px;background:linear-gradient(155deg,#1a2945,#111b30);box-shadow:0 26px 90px #000d;overflow:auto}.task-popup.open,.task-popup-backdrop.open{display:block}body.task-popup-open{overflow:hidden}.task-popup-head{position:sticky;z-index:4;top:-14px;display:flex;align-items:center;justify-content:space-between;gap:10px;margin:-14px -14px 10px;padding:12px 14px;border-bottom:1px solid #3c5272;background:#172540f5;backdrop-filter:blur(8px)}.task-popup-title{font-size:15px;font-weight:900}.task-popup-sub{margin-top:2px;color:var(--muted);font-size:9px}.task-popup-close{flex:0 0 auto;width:auto;padding:7px 11px;background:#7f1d1d;color:white}.task-popup-content{display:grid;gap:8px}.task-popup-content>.task-group{margin:0}.task-popup-content .task-group-collapsible{background:#0d182b}.task-popup-content .no-shop{margin-top:0}
.dashboard-title{font-size:17px;font-weight:850;color:#dbeafe;margin:0 0 8px}.inline-dashboard{margin-top:9px;padding-top:9px;border-top:1px solid var(--line)}.summary-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}.summary-item{background:#0d1528;border:1px solid var(--line);border-radius:8px;padding:8px}.summary-label{color:var(--muted);font-size:10px}.summary-value{font-size:14px;font-weight:800;margin-top:2px}.dashboard-error-link{display:block;width:100%;min-width:0;color:var(--text);text-align:left;font:inherit;box-shadow:none;flex:initial}.dashboard-error-link:hover{border-color:#fb7185!important;background:#281724!important}.dashboard-error-link:focus-visible{outline:2px solid #fda4af;outline-offset:2px}.dashboard-error-link .summary-value{color:#fda4af}
.task-title{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:11px;padding-top:10px;border-top:1px solid var(--line)}.task-help{color:var(--muted);font-size:10px}.task-group{margin-top:8px}.task-group-head{display:flex;align-items:center;justify-content:space-between;gap:7px;margin-bottom:5px}.task-group-name{color:#cfe2ff;font-size:11px;font-weight:800}.task-group-collapsible{border:1px solid #2b3955;border-radius:8px;padding:6px 7px}.task-group-collapsible>summary{list-style:none;cursor:pointer;margin:0}.task-group-collapsible>summary::-webkit-details-marker{display:none}.task-group-collapsible>summary .task-group-name:before{content:'▶ ';color:#7f91af}.task-group-collapsible[open]>summary .task-group-name:before{content:'▼ '}.task-group-collapsible[open]>summary{margin-bottom:6px}.task-mini-buttons{display:flex;gap:4px;flex-wrap:wrap;justify-content:flex-end}.task-mini-buttons button{flex:0 0 auto;padding:4px 7px;border-radius:6px;font-size:9px}.task-mini-buttons button.group-start{background:#2563eb;color:white}.task-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px}.task-row{display:flex;align-items:center;gap:7px;background:#0d1528;border:1px solid var(--line);border-radius:8px;padding:7px 8px;min-height:39px}.task-row>input[type=checkbox]{width:auto;flex:0 0 auto}.task-text{display:block;min-width:0;flex:1}.task-name,.task-state{display:block}.task-name{font-size:11px;font-weight:750}.task-state{font-size:9px;color:var(--muted);margin-top:1px}.task-state.ready{color:#86efac}.task-state.preparing{color:#fbbf24}.task-count{display:flex;align-items:center;gap:4px;flex:0 0 auto;color:var(--muted);font-size:9px}.task-count input[type=number]{width:42px;padding:5px;text-align:center}.task-count select{width:156px;max-width:38vw;padding:5px}.continuous-option{display:flex;align-items:center;gap:2px;color:#93c5fd;white-space:nowrap}.continuous-option input{width:auto!important}.continuous-option.disabled{opacity:.45}.daily-task-grid{gap:3px}.daily-task-row{min-height:31px;padding:4px 6px;gap:5px}.daily-task-row .task-name{font-size:10px;white-space:nowrap}.daily-task-row .task-count{gap:3px}.daily-task-row .task-count input[type=number]{width:36px;padding:3px 2px;font-size:11px}.daily-task-row .continuous-option{font-size:8px;margin:0}.daily-task-row>input[type=checkbox],.daily-task-row .continuous-option input{transform:scale(.88)}.no-shop{margin-top:8px;padding:6px 8px;border-radius:7px;background:#201b12;color:#fde68a;font-size:10px}
.settings-intro{display:flex;gap:10px;align-items:center;padding:10px 12px;margin:4px 0 10px;border-radius:10px;background:#132640;border:1px solid #315277;color:#dbeafe}.settings-intro-icon{font-size:25px}.settings-intro b{display:block;font-size:13px}.settings-intro small{display:block;color:#9fb0cd;margin-top:2px}.settings-section{margin-top:10px;padding:11px;background:#0d1528;border:1px solid var(--line);border-radius:10px}.settings-section-head{display:flex;align-items:center;gap:8px;margin-bottom:8px}.settings-section-icon{font-size:20px}.settings-section-title{font-weight:850;color:#dbeafe}.settings-section-help{color:var(--muted);font-size:10px;margin-top:2px}.field-help{display:block;color:#7f91af;font-size:9px;line-height:1.35;margin-top:3px}.movement-guide{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.movement-card{padding:10px;border-radius:10px;background:#14213a;border:1px solid #315277}.movement-card.corner{border-color:#7652a8;background:#211938}.movement-visual{display:flex;align-items:center;justify-content:center;gap:8px;min-height:48px;margin-bottom:7px;font-size:22px;background:#081121;border-radius:8px}.movement-arrow{font-size:24px;color:#60a5fa}.movement-arrow.corner{color:#c084fc}.keycap{display:inline-block;padding:3px 7px;border-radius:6px;border:1px solid #64748b;border-bottom-width:3px;background:#e2e8f0;color:#111827;font-size:11px;font-weight:900}.movement-name{font-size:11px;font-weight:850;margin-bottom:5px}.coordinate-layout{display:grid;grid-template-columns:150px 1fr;gap:12px;align-items:start}.phone-map{position:relative;width:132px;height:220px;margin:auto;border:5px solid #53627d;border-radius:22px;background:linear-gradient(#75c7f3 0 55%,#42332f 55%);box-shadow:inset 0 0 0 2px #0b1020}.phone-map:before{content:'';position:absolute;top:5px;left:43px;width:38px;height:5px;border-radius:5px;background:#1f2937}.map-dot{position:absolute;padding:2px 5px;border-radius:6px;background:#f8df86;color:#3d3105;font-size:8px;font-weight:900;white-space:nowrap}.map-boss{top:28px;left:36px}.map-quest{top:105px;right:3px}.map-auto{bottom:35px;left:8px}.map-x{bottom:8px;left:49px;background:#fb7185;color:white}.coordinate-note{text-align:center;color:var(--muted);font-size:9px;margin-top:5px}
.coordinate-preview-toolbar{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:9px;padding-top:8px;border-top:1px solid var(--line)}.coordinate-preview-toolbar b{display:block;font-size:10px}.coordinate-preview-toolbar button{flex:0 0 auto;width:auto;padding:5px 8px;font-size:9px}.coordinate-field{display:grid!important;grid-template-columns:minmax(0,1fr) 76px;gap:6px;align-items:center}.coordinate-field-content{min-width:0}.coordinate-preview-card{padding:3px;background:#14213a;border:1px solid #315277;border-radius:6px;min-width:0}.coordinate-preview-card canvas{display:block;width:68px;height:43px;background:#050914;border-radius:4px}.coordinate-preview-value{display:block;color:#f8df86;font-size:7px;line-height:1;text-align:center;white-space:nowrap;margin-top:3px}
.error-preview{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;margin-top:7px}.error-preview img{width:100%;max-height:170px;object-fit:contain;background:#080d19;border:1px solid var(--line);border-radius:8px}.direction{background:#2b2412;border:1px solid #705b20;border-radius:8px;padding:7px;color:#fde68a;margin-top:6px;font-size:11px}
.shot-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;margin-top:7px}.shot-item{background:#0d1528;border:1px solid var(--line);border-radius:8px;padding:5px}.shot-item img{display:block;width:100%;height:112px;object-fit:contain;background:#080d19;border-radius:5px;cursor:pointer}.shot-name{margin-top:4px;color:var(--muted);font-size:9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.pager{display:flex;justify-content:center;align-items:center;gap:4px;flex-wrap:wrap;margin-top:6px}.pager button{flex:0 0 auto;min-width:28px;padding:5px 7px}.pager button.current{background:#f8df86;color:#3d3105}.page-status{text-align:center;color:var(--muted);font-size:9px;margin-top:4px}.combined-error-report{margin-top:14px;padding-top:12px;border-top:1px solid var(--line)}.combined-error-head{display:flex;align-items:center;gap:10px}.combined-error-head b{flex:1}.combined-error-head button{flex:0 0 auto;padding:8px 12px;font-size:12px}
.combined-error-head>div{flex:1}.unified-errors{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;max-height:none;overflow:visible;margin-top:12px;padding:0}.unified-error-item{min-width:0;padding:11px;border:1px solid #713348;border-radius:12px;background:linear-gradient(145deg,#281724,#1b1624)}.unified-error-item .error-reason{white-space:normal;line-height:1.4}.unified-error-item .error-preview img{height:190px;max-height:190px;cursor:zoom-in}.missing-shot{display:grid;place-items:center;height:190px;border:1px dashed #49556b;border-radius:8px;background:#080d19;color:var(--muted);font-size:10px}.error-log-context{margin-top:8px}.error-log-context>summary{margin:0;color:#a9d4ff;font-size:10px}.error-log-context pre{height:120px;min-height:120px;margin:6px 0 0;font-size:9px}.error-actions{flex-wrap:wrap}.error-actions button{min-width:130px;font-size:10px}.unified-storage{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:12px;padding:10px;border-top:1px solid var(--line);background:#0d1528;border-radius:9px}.unified-storage>div:first-child{flex:1}.unified-storage p{margin:3px 0;font-size:9px}.unified-storage .buttons{flex:0 0 auto;margin:0}.unified-storage button{white-space:nowrap;font-size:10px}
@media(max-width:720px){.unified-errors{grid-template-columns:1fr}.unified-error-item .error-preview img,.missing-shot{height:210px;max-height:210px}.unified-storage{display:block}.unified-storage .buttons{margin-top:8px}}
#layoutCanvas:not(.custom-layout){width:100%;min-width:0;grid-template-columns:repeat(2,minmax(0,1fr))!important;grid-template-areas:"main admin" "main logs"!important;align-items:start}#controlCard{grid-area:main;min-width:0;width:100%}#summaryCard{display:none!important}#adminCard{grid-area:admin;align-self:start;min-width:0;width:100%}#adminLogs{grid-area:logs;align-self:start;min-width:0;width:100%;padding:12px}#adminLogs pre{height:180px;margin:8px 0 0;font-size:10px;line-height:1.35}#adminLogs button{padding:6px 9px!important;font-size:10px}#settingsCard{grid-column:1/-1}#adminScreenshots{grid-column:1/-1}.recent-error{border-bottom:1px solid var(--line);padding-bottom:9px;margin-bottom:9px}#screenshotStorage>p{margin:6px 0}.admin-shot-details>summary{font-size:13px;font-weight:800;margin:0;cursor:pointer}.admin-shot-details[open]>summary{margin-bottom:10px}
/* Polished user dashboard */
:root{--card:#17233b;--line:#334565;--accent:#6eb4ff;--muted:#aab9d2}body{min-height:100vh;background:radial-gradient(circle at 12% 0,#23426b80,transparent 34%),radial-gradient(circle at 88% 8%,#31265f70,transparent 30%),linear-gradient(150deg,#080d1a 0%,#111a2d 52%,#0b1221 100%);background-attachment:fixed}.wrap{max-width:1280px;padding:10px 14px 18px}.app-header{display:flex;align-items:center;gap:12px;padding:12px 15px;border:1px solid #3a5278;border-radius:16px;background:linear-gradient(135deg,#1d3152e8,#17213ae8);box-shadow:0 12px 32px #02061770,inset 0 1px #ffffff0c}.brand-mark{display:grid;place-items:center;width:44px;height:44px;border-radius:13px;background:linear-gradient(145deg,#f8df86,#e8a93a);box-shadow:0 7px 18px #e8a93a36;font-size:24px}.brand-copy{min-width:0;flex:1}.title{font-size:22px;letter-spacing:-.35px}.sub{margin-top:3px}.header-actions{display:flex;align-items:center;gap:7px;flex:0 0 auto}.header-badge{flex:0 0 auto;padding:6px 10px;border:1px solid #41628f;border-radius:999px;background:#0e1a2f;color:#a9d4ff;font-size:10px;font-weight:800}.header-quit{flex:0 0 auto!important;width:auto;padding:8px 12px!important;border:1px solid #9f3344!important;background:linear-gradient(145deg,#8f2637,#641c29)!important;box-shadow:0 5px 14px #7f1d1d55}.layout-toolbar{padding:6px 3px;margin:4px 0}.layout-help{flex:1;min-width:230px;text-align:right}.card{border-color:#344766;border-radius:15px;background:linear-gradient(155deg,#1a2741f2,#131e34f2);box-shadow:0 12px 28px #02061755,inset 0 1px #ffffff08}#layoutCanvas{gap:10px}#controlCard{border-color:#43638d}#summaryCard{border-color:#3a4d70}#statusBox{position:relative;padding:11px 13px 11px 40px;border:1px solid #3e5b80;border-radius:11px;background:linear-gradient(105deg,#10233e,#162b49)}#statusBox:before{content:'●';position:absolute;left:15px;top:11px;color:#94a3b8;text-shadow:0 0 10px currentColor}#statusBox.running:before{color:#4ade80}.status .dot{display:none}.status{font-size:15px}.status:before{content:'현재 상태';display:block;margin-bottom:2px;color:#8fa6c6;font-size:9px;font-weight:700;letter-spacing:.6px}#runSetupFeature{margin-top:10px!important;padding:10px;border:1px solid #2d4263;border-radius:11px;background:#0c1629a8}#runSetupFeature #start{width:100%}#runActionsFeature{gap:7px;margin-top:10px}#runActionsFeature button{min-height:39px}button{border-radius:9px;transition:transform .12s ease,filter .12s ease,box-shadow .12s ease}button:hover:not(:disabled){filter:brightness(1.08);transform:translateY(-1px)}button:active:not(:disabled){transform:translateY(0)}#start,#infiniteStart{font-size:13px}.inline-dashboard{margin-top:11px;padding:11px;border:1px solid #334d72;border-radius:12px;background:linear-gradient(135deg,#101d33,#0d1729)}.dashboard-title{font-size:13px;color:#93c5fd}.summary-grid{gap:8px}.summary-item{position:relative;overflow:hidden;padding:9px 10px;border-color:#304664;background:#111f36}.summary-item:after{content:'';position:absolute;left:0;bottom:0;width:100%;height:2px;background:#60a5fa}.summary-item:nth-child(2):after{background:#fb7185}.summary-item:nth-child(3):after{background:#4ade80}.summary-value{font-size:15px}.warning{line-height:1.45}#summaryCard .task-title{margin:0;padding:0 0 9px;border:0;border-bottom:1px solid #334565}#summaryCard .task-title b{font-size:14px}.task-group{margin-top:10px}.task-group-name{font-size:11px;color:#dbeafe}.task-row{border-color:#31445f;background:#0d182b}.task-row:has(input:checked){border-color:#3f6592;background:#10233e}.task-group-collapsible{margin-top:7px;padding:8px 9px;border-color:#344966;background:#101a2da8}.task-group-collapsible>summary{min-height:27px}.boss-preset-row{border-color:#3b5479;background:linear-gradient(145deg,#101e35,#0d1729)}.boss-preset-option{transition:border-color .12s ease,background .12s ease,transform .12s ease}.boss-preset-option:hover{transform:translateY(-1px)}.no-shop{text-align:center;border:1px solid #5f4a22}#adminCard{opacity:.92}#adminLogs{min-height:430px}#layoutCanvas.custom-layout>#adminLogs{min-height:430px}#adminLogs pre,#logs{height:360px;min-height:360px;margin:9px 0 0;padding:12px;font-size:11px;line-height:1.52;border-color:#304563;background:#050a13;box-shadow:inset 0 0 20px #0005;scrollbar-color:#46658d #0b1424}#adminLogs button{padding:7px 10px!important}#adminLogs>div:first-child{padding-bottom:7px;border-bottom:1px solid #304563}.hover-help-source{display:none!important}.help-dot{display:inline-grid;place-items:center;width:17px;height:17px;margin-left:5px;border:1px solid #51729e;border-radius:50%;background:#142641;color:#a9d4ff;font-size:10px;font-weight:900;line-height:1;cursor:help;vertical-align:middle}.help-dot:hover,.help-dot:focus{border-color:#93c5fd;background:#1e3a5f;outline:none}#hoverTooltip{display:none;position:fixed;z-index:12000;max-width:320px;padding:8px 10px;border:1px solid #5577a5;border-radius:8px;background:#07101fee;color:#e5f0ff;box-shadow:0 8px 28px #000b;font-size:11px;line-height:1.45;pointer-events:none;white-space:normal}#hoverTooltip.visible{display:block}
.movement-card>.boss-keyboard-option{margin-top:8px}
#summaryCard .boss-popup-launch{margin:0}#bossSettingsSummary{display:block;margin-top:5px;line-height:1.6;white-space:normal}body.boss-popup-open{overflow:hidden}#bossPopupContent>.boss-preset-row{margin-top:0}#bossPopupContent>.boss-movement-public{margin-top:0}
#controlCard #summaryCard{margin:10px 0 0;padding:0;border:0;border-radius:0;background:none;box-shadow:none}
@media(max-width:600px){#bossPopupContent>.boss-movement-public .movement-guide{grid-template-columns:1fr}#bossPopup .boss-preset-options{grid-template-columns:repeat(3,minmax(0,1fr))}}
#adminLogs,#layoutCanvas.custom-layout>#adminLogs{min-height:270px}#adminLogs pre,#logs{height:200px;min-height:200px;padding:11px;line-height:1.5}
@media(max-width:800px){.wrap{margin:5px auto;padding:7px}.app-header{align-items:flex-start;padding:10px}.brand-mark{width:38px;height:38px;font-size:20px}.title{font-size:18px}.header-badge{display:none}.header-quit{padding:7px 9px!important;font-size:10px}.layout-help{display:none}.card{margin:7px 0}#layoutCanvas:not(.custom-layout){display:block}.grid,.task-grid,.movement-guide,.coordinate-layout,#summaryCard>.boss-movement-public .movement-guide,#summaryCard>.boss-movement-public .boss-keyboard-options{grid-template-columns:1fr}.wide{grid-column:auto}.buttons{flex-wrap:wrap}.shot-item img{height:155px}#adminLogs pre,#logs{height:200px;min-height:200px}.dashboard-warning{font-size:9px;letter-spacing:-.35px}}
.app-header{position:sticky;top:8px;z-index:1000;background:linear-gradient(135deg,#1d3152,#17213a)}
.header-actions #runActionsFeature{margin-top:0;flex-wrap:nowrap}.header-actions #runActionsFeature>button:not(.feature-remove-button){flex:0 0 auto;padding:9px 12px;white-space:nowrap}
.layout-toolbar>#quit{margin-left:auto}
@media(max-width:1100px){.app-header{flex-wrap:wrap}.header-actions{margin-left:auto}.app-header .header-badge{display:none}}
@media(max-width:500px){.header-actions{width:100%}.header-actions #runActionsFeature{width:100%;gap:4px}.header-actions #runActionsFeature>button:not(.feature-remove-button){flex:1;padding:8px 5px;font-size:12px}}
.arena-mode-public{margin-top:9px;padding:8px;border:1px solid #416993;border-radius:9px;background:linear-gradient(135deg,#102844,#13213a)}.arena-mode-public .task-group-head{margin-bottom:6px}.arena-mode-public .task-group-name{color:#93c5fd;font-size:12px}.arena-mode-public .task-help{margin:6px 2px 0;line-height:1.4}.arena-mode-public .task-row{background:#0b1729}.arena-mode-public .group-start{background:#2563eb;color:white}
/* Portrait controller layout for the compact app/browser window. */
@media(max-width:720px){
  .wrap{width:100%;max-width:none;margin:0;padding:5px 6px 12px}
  .app-header{top:4px;display:grid;grid-template-columns:38px minmax(0,1fr);align-items:center;gap:6px 9px;padding:8px 9px;border-radius:12px}
  .brand-mark{width:38px;height:38px;border-radius:10px;font-size:20px}
  .brand-copy{align-self:center}.title{font-size:17px;line-height:1.15;letter-spacing:-.4px}.version{display:block;width:max-content;margin:4px 0 0;padding:2px 7px;font-size:10px}.sub{margin-top:4px;font-size:10px;line-height:1.25}
  .header-actions{grid-column:1/-1;width:100%;margin:0}.header-actions #runActionsFeature{width:100%;gap:4px}.header-actions #runActionsFeature>button:not(.feature-remove-button){flex:1 1 0;min-width:0;min-height:36px;padding:7px 3px;font-size:11px}
  .layout-toolbar{gap:4px;margin:3px 0;padding:3px 1px}.layout-toolbar button{padding:6px 7px;font-size:9px}.snap-toggle{padding:5px 7px;font-size:9px}.layout-toolbar>#quit{margin-left:auto;padding:6px 8px!important}
  #layoutCanvas,#layoutCanvas:not(.custom-layout),#layoutCanvas.custom-layout{display:block!important;height:auto!important;min-height:0!important}
  #layoutCanvas.custom-layout>.card{position:relative!important;left:auto!important;top:auto!important;width:auto!important;height:auto!important;min-width:0!important;min-height:0!important;margin:6px 0!important;overflow:visible!important;resize:none!important}
  .card{margin:6px 0;padding:10px;border-radius:12px}
  #statusBox{padding:9px 10px 9px 34px}#statusBox:before{left:12px;top:9px}.status{font-size:14px}
  #runSetupFeature{margin-top:8px!important;padding:8px!important}.inline-dashboard{margin-top:8px;padding:9px}.dashboard-title{margin-bottom:6px}.summary-grid{gap:5px}.summary-item{padding:7px 8px}.summary-value{font-size:14px}
  .task-checklist-panel{margin-top:8px;padding:8px}.task-title{margin-top:8px;padding-top:8px}.task-group{margin-top:7px}.task-row{min-height:38px;padding:7px}.task-popup-launch{margin-top:8px}.task-popup-launch button{padding:9px 11px}
  #adminCard .admin-row{display:grid;grid-template-columns:1fr auto;align-items:end;gap:6px}#adminCard .admin-row button{padding:8px 9px}
  .task-popup,.admin-popup-panel.admin-popup-active{left:6px!important;right:6px!important;top:6px!important;bottom:6px!important;transform:none!important;width:auto!important;height:auto!important;max-height:none!important;padding:11px!important;border-radius:12px!important}
  .task-popup-head{top:-11px;margin:-11px -11px 8px;padding:10px 11px}.error-preview,.shot-grid{grid-template-columns:1fr}.shot-item img{height:190px}
  #adminLogs,#layoutCanvas.custom-layout>#adminLogs{min-height:240px}#adminLogs pre,#logs{height:200px;min-height:200px}
  .footer{padding:5px 8px;line-height:1.35}
}
@media(max-width:420px){
  .wrap{padding-left:4px;padding-right:4px}.app-header{grid-template-columns:34px minmax(0,1fr);padding:7px}.brand-mark{width:34px;height:34px}.title{font-size:15px}.sub{font-size:9px}
  .header-actions #runActionsFeature>button:not(.feature-remove-button){font-size:10px;padding:7px 2px}.card{padding:9px}.summary-label{font-size:9px}.summary-value{font-size:13px}
}
.support-box{box-sizing:border-box;width:100%;min-width:0;height:auto;margin:10px auto 0 0;padding:12px;border:1px solid #776b34;border-radius:10px;background:#302d20;text-align:left}.support-box>b{font-size:13px}.support-box p{margin:7px 0;color:var(--text);font-size:12px;line-height:1.55;overflow-wrap:anywhere}.support-payment{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px 12px;margin-top:9px}.support-bank{min-width:0;max-width:100%;font-size:11px;color:var(--muted)}.support-account{display:block;margin-top:3px;font-size:15px;line-height:1.4;letter-spacing:.2px;overflow-wrap:anywhere;user-select:all;color:var(--text)}.support-box .support-copy{flex:0 1 auto;width:auto;max-width:100%;min-height:36px;margin:0;padding:8px 12px;background:#fee500;color:#191919;font-size:12px;font-weight:800;white-space:normal;overflow-wrap:anywhere}.support-box .support-note{margin-bottom:0;color:var(--muted);font-size:11px}@media(max-width:720px){.support-box{width:100%;margin-top:8px;padding:10px}}
#layoutCanvas.custom-layout:not(.layout-editing)>#adminCard{height:auto!important;min-height:0}
.usage-notice{margin-top:10px;padding:10px 11px;border:1px solid var(--line);border-radius:8px;background:#111c30;color:var(--muted);font-size:11px;line-height:1.6;min-width:0;overflow-wrap:anywhere}.usage-notice>summary{color:var(--text);font-size:12px;font-weight:700;cursor:pointer;margin:0;line-height:1.6}.usage-notice>summary:focus-visible{outline:2px solid var(--accent);outline-offset:3px;border-radius:3px}.usage-notice ul{margin:6px 0 0;padding-left:17px}.usage-notice li+li{margin-top:4px}.dashboard-warning{white-space:normal;overflow-wrap:anywhere}
.combined-error-head{flex-wrap:wrap}.combined-error-head>div{min-width:160px}

.arena-selectors{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:10px 0 8px}.arena-selectors label{display:flex;flex-direction:column;gap:6px;margin:0;min-width:0;color:#cfe2ff;font-size:11px;font-weight:700}.arena-selectors select{box-sizing:border-box;width:100%;min-width:0;margin:0;font-size:12px}.arena-entry-help{margin:0 0 10px;color:#aab9d2;font-size:11px;line-height:1.6;text-align:left}.arena-mode-public .task-group-name{line-height:1.5;word-break:keep-all}@media(max-width:440px){.arena-selectors{grid-template-columns:1fr}}
.daily-summary-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:14px}.daily-summary-heading h2{margin:0;font-size:20px}.daily-summary-heading p{margin:5px 0 0;color:var(--muted);font-size:12px}.daily-summary-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px}.daily-summary-stat{padding:12px;border:1px solid #365276;border-radius:10px;background:#0d1a2e}.daily-summary-stat span{display:block;color:var(--muted);font-size:11px}.daily-summary-stat strong{display:block;margin-top:5px;color:#e8f2ff;font-size:20px}.daily-summary-section{margin-top:13px;padding:12px;border:1px solid var(--line);border-radius:10px;background:#0c1729}.daily-summary-section h3{margin:0 0 9px;font-size:13px}.daily-summary-list{display:grid;gap:7px}.daily-summary-row{display:flex;justify-content:space-between;gap:12px;padding:8px 9px;border-radius:7px;background:#132139;font-size:12px;line-height:1.5}.daily-summary-row span:last-child{text-align:right;color:#b9cbe3}.daily-summary-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}.daily-summary-empty{color:var(--muted);font-size:12px}.deployment-ok{color:#86efac}.deployment-wait{color:#fde68a}@media(max-width:600px){.daily-summary-stats{grid-template-columns:repeat(2,minmax(0,1fr))}.daily-summary-heading{display:block}.daily-summary-heading .buttons{margin-top:9px}.daily-summary-row{display:block}.daily-summary-row span{display:block}.daily-summary-row span:last-child{margin-top:3px;text-align:left}}
</style></head><body><div class="wrap">
<div class="app-header"><div class="brand-mark">🍪</div><div class="brand-copy"><h1 class="title">쿠키런: 크럼블 퀘스트 도우미 <span class="version">v16.0</span></h1><p class="sub">정식 데스크톱 프로그램 · macOS / Windows 11 · 화면 크기 자동 확인</p></div><div class="header-actions"><a id="updateStatus" class="header-badge hidden" target="_blank" rel="noopener">업데이트 확인 중</a><div class="header-badge">STABLE RELEASE</div><div id="runActionsFeature" class="buttons feature-removable" data-feature-id="run_actions" data-feature-label="실행·다음 행동·정지"><button id="infiniteStart" class="secondary" type="button" onclick="startInfinite()">시작</button><button id="nextAction" class="next" type="button" onclick="nextAction()" disabled>다음 행동</button><button id="stop" class="stop" onclick="stopRun()" disabled>정지</button></div></div></div>
<div class="layout-toolbar"><button id="layoutEditButton" class="secondary" type="button" onclick="startLayoutEdit()">화면 배치 편집</button><button id="layoutSaveButton" class="save-layout hidden" type="button" onclick="saveUILayout()">배치 저장</button><button id="layoutCancelButton" class="cancel-layout hidden" type="button" onclick="cancelLayoutEdit()">편집 취소</button><button id="layoutRestoreFeaturesButton" class="restore-features hidden" type="button" onclick="restoreAllFeatures()">숨긴 기능 모두 복원 (0)</button><button id="layoutResetButton" class="secondary" type="button" onclick="resetUILayout()">기본 배치 복원</button><label class="snap-toggle"><input id="layoutSnap" type="checkbox" checked onchange="saveSnapPreference()">자석 맞춤</label><span class="layout-help">X는 화면 배치 편집 중에만 나타나며, 저장하거나 취소하면 사라집니다.</span><button id="memoryCleanup" class="secondary" type="button" onclick="cleanupBluestacksMemory()">메모리 정리</button><button id="quit" class="quit header-quit" type="button" onclick="shutdownApp()">프로그램 종료</button></div>
<div id="layoutCanvas"><div id="snapGuideX" class="snap-guide vertical"></div><div id="snapGuideY" class="snap-guide horizontal"></div>
<section id="controlCard" class="card"><div id="statusBox"><div class="status"><span class="dot"></span><span id="status">대기 중</span></div></div>
<input id="cycles" type="hidden"><input id="infinite" class="hidden" type="checkbox"><span id="start" class="hidden"></span>
<div id="runSetupFeature" class="feature-removable" data-feature-id="run_setup" data-feature-label="자동 점검 설정"><div class="check compact-check"><input id="automatic_check" type="checkbox"><div><b>자동 점검 확인</b><small>체크하면 시작 전 화면과 퀘스트를 확인합니다.</small></div></div></div>
<div class="inline-dashboard feature-removable" data-feature-id="dashboard" data-feature-label="현황판"><div class="dashboard-title">#현황판</div><div class="summary-grid"><div class="summary-item"><div class="summary-label">실행</div><div id="simpleRun" class="summary-value">대기 중</div></div><button id="dashboardErrors" class="summary-item dashboard-error-link" type="button" onclick="openDashboardErrors()" aria-haspopup="dialog" title="전체 오류 화면 열기"><span class="summary-label">전체 오류</span><span id="simpleErrors" class="summary-value">0건</span></button><div class="summary-item"><div class="summary-label">완료</div><div id="simpleCompleted" class="summary-value">0개</div></div></div></div>
<p class="warning dashboard-warning">실행·재시작 전 BlueStacks를 팝업 없는 전투 화면으로 돌려놓으세요.</p></section>
<section id="summaryCard" class="card"><div class="task-popup-launch boss-popup-launch"><button id="bossPopupLaunch" type="button" onclick="openBossPopup()" aria-haspopup="dialog"><span><strong>보스 전투 · 키 입력 설정</strong><small id="bossSettingsSummary" aria-live="polite">설정 확인 중…</small></span><span class="popup-arrow">열기 ↗</span></button></div><div class="task-checklist-panel"><div class="task-title" style="margin-top:0;padding-top:0;border-top:0"><b>실행할 작업 체크리스트</b><span class="task-help">체크한 작업만 실행 대상으로 저장합니다.</span></div>
<div class="task-group"><div class="task-group-name">퀘스트</div><div class="task-grid">
<label class="task-row"><input id="task_quest" type="checkbox"><span class="task-text"><span class="task-name">현재 퀘스트 자동 완료</span><span class="task-state ready">현재 사용 가능</span></span></label>
<label class="task-row"><input id="restart_game_on_exit" type="checkbox"><span class="task-text"><span class="task-name">게임 종료 시 자동 재실행</span><span class="task-state ready">Android 바탕화면 감지 시 게임을 열고 퀘스트를 다시 시작</span></span></label>
</div><div class="boss-preset-row"><div class="boss-preset-title">보스 소환 프리셋 순서</div><div class="boss-preset-help">사용할 번호를 누른 순서대로 변경합니다. 번호 옆 원은 실제 실행 순서입니다.</div><div class="boss-preset-options">
<label class="boss-preset-option"><input id="boss_preset_1" type="checkbox" onchange="updateBossPresetOrder(1)"><span>1 [전투력]</span><span id="boss_preset_rank_1" class="boss-preset-rank"></span></label>
<label class="boss-preset-option"><input id="boss_preset_2" type="checkbox" onchange="updateBossPresetOrder(2)"><span>2 [단일보스]</span><span id="boss_preset_rank_2" class="boss-preset-rank"></span></label>
<label class="boss-preset-option"><input id="boss_preset_3" type="checkbox" onchange="updateBossPresetOrder(3)"><span>3 [아픈단일]</span><span id="boss_preset_rank_3" class="boss-preset-rank"></span></label>
<label class="boss-preset-option"><input id="boss_preset_4" type="checkbox" onchange="updateBossPresetOrder(4)"><span>4 [다수보스]</span><span id="boss_preset_rank_4" class="boss-preset-rank"></span></label>
<label class="boss-preset-option"><input id="boss_preset_5" type="checkbox" onchange="updateBossPresetOrder(5)"><span>5 [아픈다수]</span><span id="boss_preset_rank_5" class="boss-preset-rank"></span></label>
<input id="boss_preset_order" type="hidden">
</div></div></div>
<div class="task-group arena-mode-public"><div class="task-group-head"><div class="task-group-name">아레나 · 와글와글 모드 · 무한</div><div class="task-mini-buttons"><button class="group-start" type="button" onclick="startTaskGroup('arena_decision',['task_arena_decision'],'아레나 · 와글와글 모드 · 무한')">시작</button></div></div><div class="arena-selectors"><label for="arena_kind">아레나 종류<select id="arena_kind" aria-label="아레나 종류"><option value="regular">일반 아레나</option><option value="wagle">와글와글 아레나</option></select></label><label for="arena_decision_mode">진행 방식<select id="arena_decision_mode" aria-label="아레나 실행 방식"><option value="compare">전투력·트로피 비교</option><option value="challenge">도전 우선</option></select></label></div><p class="arena-entry-help">전투 메인 화면에서 시작하면 선택한 아레나로 자동 진입합니다.</p><div class="task-row"><input id="task_arena_decision" type="checkbox"><label for="task_arena_decision" class="task-text"><span class="task-name">일반·와글와글 아레나 사용</span><span class="task-state ready">정지할 때까지 무한 비교</span></label></div><p class="task-help">무료 새로고침만 사용하며 다이아 비용·무료 대기시간은 누르지 않습니다. 승리·패배·승급·강등 결과는 자동으로 넘깁니다.</p></div>
</div>
<div class="boss-movement-public"><div class="settings-section-head"><div class="settings-section-icon">🎮</div><div><div class="settings-section-title">보스 소환 후 이동 조합</div><div class="settings-section-help">두 조합을 모두 선택하면 보스를 다시 소환할 때마다 D → A+S 순서로 번갈아 이동합니다.</div></div></div><div class="movement-guide">
<div class="movement-card"><div class="movement-visual"><span>🦐🦐🦐</span><span class="keycap">D</span><span class="movement-arrow">⟶</span><span>👹</span></div><div class="movement-name">이동 조합 1 · D키</div><label for="boss_move_seconds">D키 유지시간(초)</label><input id="boss_move_seconds" oninput="renderBossSettingsSummary()" type="number" min="0.5" max="15" step="0.5"><span class="field-help">권장 4초 · 오른쪽으로 이동</span><label class="boss-keyboard-option"><input id="boss_keyboard_move_normal" type="checkbox" onchange="syncBossControls()"><span>D키 조합 사용 <small>· 보스 소환 후 D키 이동을 포함합니다.</small></span></label></div>
<div class="movement-card corner"><div class="movement-visual"><span>🦐🦐🦐</span><span><span class="keycap">A</span>+<span class="keycap">S</span></span><span class="movement-arrow corner">↙</span><span>👹</span></div><div class="movement-name">이동 조합 2 · A+S키</div><label for="boss_corner_move_seconds">A+S키 유지시간(초)</label><input id="boss_corner_move_seconds" oninput="renderBossSettingsSummary()" type="number" min="0.5" max="15" step="0.5"><span class="field-help">권장 6초 · 왼쪽 아래로 이동</span><label class="boss-keyboard-option"><input id="boss_keyboard_move_corner" type="checkbox" onchange="syncBossControls()"><span>A+S키 조합 사용 <small>· 두 조합 선택 시 보스 소환마다 교대로 사용합니다.</small></span></label></div>
</div><div class="boss-movement-actions"><button type="button" onclick="saveSettings()">이동 설정 저장</button></div></div>
<div id="bossPopupBackdrop" class="task-popup-backdrop" onclick="closeBossPopup()"></div><div id="bossPopup" class="task-popup" role="dialog" aria-modal="true" aria-labelledby="bossPopupTitle"><div class="task-popup-head"><div><div id="bossPopupTitle" class="task-popup-title">보스 전투 설정</div><div class="task-popup-sub">프리셋 순서 · 이동 조합 · 유지 시간</div></div><button class="task-popup-close" type="button" onclick="closeBossPopup()">닫기</button></div><div id="bossPopupContent" class="task-popup-content"></div></div>
<div id="taskPopupBackdrop" class="task-popup-backdrop" onclick="closeTaskPopup()"></div><div id="taskPopup" class="task-popup" role="dialog" aria-modal="true" aria-labelledby="taskPopupTitle"><div class="task-popup-head"><div><div id="taskPopupTitle" class="task-popup-title">추가 실행 작업</div><div class="task-popup-sub">실행할 묶음을 펼쳐 필요한 항목만 선택하세요.</div></div><button class="task-popup-close" type="button" onclick="closeTaskPopup()">닫기</button></div><div class="task-popup-content">
<details class="task-group task-group-collapsible"><summary class="task-group-head"><div class="task-group-name">일일 무료 보상</div><div class="task-mini-buttons"><button class="group-start" type="button" onclick="event.preventDefault();event.stopPropagation();startTaskGroup('daily_rewards',['task_auto_hunt_reward','task_attendance','task_missions','task_event_rewards','task_pass_free','task_mailbox','task_guild_attendance'],'일일 무료 보상')">시작</button><button type="button" onclick="event.preventDefault();event.stopPropagation();setTaskGroup(['task_auto_hunt_reward','task_attendance','task_missions','task_event_rewards','task_pass_free','task_mailbox','task_guild_attendance'],true)">전체 체크</button><button class="secondary" type="button" onclick="event.preventDefault();event.stopPropagation();setTaskGroup(['task_auto_hunt_reward','task_attendance','task_missions','task_event_rewards','task_pass_free','task_mailbox','task_guild_attendance'],false)">전체 해제</button></div></summary><div class="task-grid">
<label class="task-row"><input id="task_auto_hunt_reward" type="checkbox"><span class="task-text"><span class="task-name">자동 사냥 무료 보상</span><span class="task-state preparing">영상 확인 완료 · 제작 중</span></span></label>
<label class="task-row"><input id="task_attendance" type="checkbox"><span class="task-text"><span class="task-name">오늘의 출석 보상</span><span class="task-state preparing">영상 확인 완료 · 제작 중</span></span></label>
<label class="task-row"><input id="task_missions" type="checkbox"><span class="task-text"><span class="task-name">일일·주간 미션 모두 받기</span><span class="task-state preparing">영상 확인 완료 · 제작 중</span></span></label>
<label class="task-row"><input id="task_event_rewards" type="checkbox"><span class="task-text"><span class="task-name">이벤트 무료 보상</span><span class="task-state preparing">영상 확인 완료 · 제작 중</span></span></label>
<label class="task-row"><input id="task_pass_free" type="checkbox"><span class="task-text"><span class="task-name">크럼블 패스 무료 보상</span><span class="task-state preparing">유료 보상 제외 · 제작 중</span></span></label>
<label class="task-row"><input id="task_mailbox" type="checkbox"><span class="task-text"><span class="task-name">우편함 보상</span><span class="task-state preparing">영상 확인 완료 · 제작 중</span></span></label>
<label class="task-row"><input id="task_guild_attendance" type="checkbox"><span class="task-text"><span class="task-name">길드 출석 보상</span><span class="task-state preparing">연구·도움 제외 · 제작 중</span></span></label>
</div></details>
<details class="task-group task-group-collapsible"><summary class="task-group-head"><div class="task-group-name">도전 던전 · 각각 1–5회</div><div class="task-mini-buttons"><button class="group-start" type="button" onclick="event.preventDefault();event.stopPropagation();startTaskGroup('challenge',['task_crumble_dungeon','task_arena','task_implant_tower'],'도전 던전')">시작</button><button type="button" onclick="event.preventDefault();event.stopPropagation();setTaskGroup(['task_crumble_dungeon','task_arena','task_implant_tower'],true)">전체 체크</button><button class="secondary" type="button" onclick="event.preventDefault();event.stopPropagation();setTaskGroup(['task_crumble_dungeon','task_arena','task_implant_tower'],false)">전체 해제</button></div></summary><div class="task-grid">
<div class="task-row"><input id="task_crumble_dungeon" type="checkbox"><label for="task_crumble_dungeon" class="task-text"><span class="task-name">크럼블 던전</span></label><span class="task-count">횟수 <input id="task_crumble_dungeon_runs" type="number" min="1" max="5"></span></div>
<div class="task-row"><input id="task_arena" type="checkbox"><label for="task_arena" class="task-text"><span class="task-name">아레나</span></label><span class="task-count">횟수 <input id="task_arena_runs" type="number" min="1" max="5"></span></div>
<div class="task-row"><input id="task_implant_tower" type="checkbox"><label for="task_implant_tower" class="task-text"><span class="task-name">임플란트 타워</span></label><span class="task-count">횟수 <input id="task_implant_tower_runs" type="number" min="1" max="5"></span></div>
</div></details>
<details class="task-group task-group-collapsible"><summary class="task-group-head"><div class="task-group-name">일일 던전 · 1–3회(연속)</div><div class="task-mini-buttons"><button class="group-start" type="button" onclick="event.preventDefault();event.stopPropagation();startTaskGroup('daily_dungeon',['task_exp_dungeon','task_coin_dungeon','task_dough_dungeon','task_research_stone_dungeon','task_rune_crystal_dungeon'],'일일 던전')">시작</button><button type="button" onclick="event.preventDefault();event.stopPropagation();setTaskGroup(['task_exp_dungeon','task_coin_dungeon','task_dough_dungeon','task_research_stone_dungeon','task_rune_crystal_dungeon'],true)">전체 체크</button><button class="secondary" type="button" onclick="event.preventDefault();event.stopPropagation();setTaskGroup(['task_exp_dungeon','task_coin_dungeon','task_dough_dungeon','task_research_stone_dungeon','task_rune_crystal_dungeon'],false)">전체 해제</button></div></summary><div class="task-grid daily-task-grid">
<div class="task-row daily-task-row"><input id="task_exp_dungeon" type="checkbox"><label for="task_exp_dungeon" class="task-text"><span class="task-name">경험치</span></label><span class="task-count"><input id="task_exp_dungeon_runs" type="number" min="1" max="3" onchange="syncDailyContinuous()">회 <label class="continuous-option"><input id="task_exp_dungeon_continuous" type="checkbox">연속</label></span></div>
<div class="task-row daily-task-row"><input id="task_coin_dungeon" type="checkbox"><label for="task_coin_dungeon" class="task-text"><span class="task-name">코인</span></label><span class="task-count"><input id="task_coin_dungeon_runs" type="number" min="1" max="3" onchange="syncDailyContinuous()">회 <label class="continuous-option"><input id="task_coin_dungeon_continuous" type="checkbox">연속</label></span></div>
<div class="task-row daily-task-row"><input id="task_dough_dungeon" type="checkbox"><label for="task_dough_dungeon" class="task-text"><span class="task-name">반죽</span></label><span class="task-count"><input id="task_dough_dungeon_runs" type="number" min="1" max="3" onchange="syncDailyContinuous()">회 <label class="continuous-option"><input id="task_dough_dungeon_continuous" type="checkbox">연속</label></span></div>
<div class="task-row daily-task-row"><input id="task_research_stone_dungeon" type="checkbox"><label for="task_research_stone_dungeon" class="task-text"><span class="task-name">연구석</span></label><span class="task-count"><input id="task_research_stone_dungeon_runs" type="number" min="1" max="3" onchange="syncDailyContinuous()">회 <label class="continuous-option"><input id="task_research_stone_dungeon_continuous" type="checkbox">연속</label></span></div>
<div class="task-row daily-task-row"><input id="task_rune_crystal_dungeon" type="checkbox"><label for="task_rune_crystal_dungeon" class="task-text"><span class="task-name">룬결정</span></label><span class="task-count"><input id="task_rune_crystal_dungeon_runs" type="number" min="1" max="3" onchange="syncDailyContinuous()">회 <label class="continuous-option"><input id="task_rune_crystal_dungeon_continuous" type="checkbox">연속</label></span></div>
</div></details>
<details class="task-group task-group-collapsible"><summary class="task-group-head"><div class="task-group-name">성장</div><div class="task-mini-buttons"><button class="group-start" type="button" onclick="event.preventDefault();event.stopPropagation();startTaskGroup('growth',['task_cookie_upgrade','task_pet_upgrade','task_breakthrough'],'성장')">시작</button><button type="button" onclick="event.preventDefault();event.stopPropagation();setTaskGroup(['task_cookie_upgrade','task_pet_upgrade','task_breakthrough'],true)">전체 체크</button><button class="secondary" type="button" onclick="event.preventDefault();event.stopPropagation();setTaskGroup(['task_cookie_upgrade','task_pet_upgrade','task_breakthrough'],false)">전체 해제</button></div></summary><div class="task-grid">
<label class="task-row"><input id="task_cookie_upgrade" type="checkbox"><span class="task-text"><span class="task-name">쿠키 일괄 업데이트</span><span class="task-state preparing">추가 화면 자료 필요</span></span></label>
<label class="task-row"><input id="task_pet_upgrade" type="checkbox"><span class="task-text"><span class="task-name">펫 일괄 업데이트</span><span class="task-state preparing">추가 화면 자료 필요</span></span></label>
<label class="task-row"><input id="task_breakthrough" type="checkbox"><span class="task-text"><span class="task-name">돌파력 업그레이드</span><span class="task-state preparing">추가 화면 자료 필요</span></span></label>
</div></details><div class="no-shop">상점·유료 패키지·결제·상점 안의 무료 상품은 실행 대상에서 완전히 제외됩니다.</div></div></div></section>
<section id="settingsCard" class="card hidden"><details><summary>관리자 세부 설정</summary>
<div class="settings-intro"><div class="settings-intro-icon">⚙️</div><div><b>처음 사용하는 사람도 쉽게 설정할 수 있어요.</b><small>숫자를 바꾼 뒤 아래의 '설정 저장'을 누르면 다음 실행부터 적용됩니다.</small></div></div>

<div class="settings-section"><div class="settings-section-head"><div class="settings-section-icon">📱</div><div><div class="settings-section-title">BlueStacks 화면 크기</div><div class="settings-section-help">게임 화면 크기와 클릭 좌표를 맞추는 설정입니다. 보통은 1080×1920 권장값을 사용하세요.</div></div></div>
<div class="screen-config" style="margin-top:0"><div class="check"><input id="adjust_screen_size" type="checkbox"><div><b>BlueStacks 사이즈 확인</b><span class="field-help">체크하면 시작 전 선택한 크기로 게임 화면을 맞춥니다.</span></div></div><div class="screen-config-grid"><div><label>빠른 크기 선택</label><select id="screenPreset" onchange="applyScreenPreset(this.value)"><option value="1080x1920">1080×1920 권장</option><option value="732x1300">732×1300 영상 크기</option><option value="720x1280">720×1280</option><option value="1440x2560">1440×2560 고해상도</option><option value="custom">직접 입력</option></select></div><div><label>가로</label><input id="screen_width" type="number" min="320" max="2160" onchange="syncScreenPreset()"></div><div><label>세로</label><input id="screen_height" type="number" min="480" max="3840" onchange="syncScreenPreset()"></div></div></div></div>

<div class="settings-section"><div class="settings-section-head"><div class="settings-section-icon">⏱️</div><div><div class="settings-section-title">퀘스트 대기시간</div><div class="settings-section-help">퀘스트가 완료되기를 기다리는 최대 시간입니다. 게임이 느리면 숫자를 늘려주세요.</div></div></div><div class="grid">
<div><label>🎫 뽑기 완료(초)</label><input id="draw_timeout" type="number"><span class="field-help">쿠키·펫 뽑기 결과가 나올 때까지</span></div><div><label>⚒️ 장비 50개(초)</label><input id="equipment_timeout" type="number"><span class="field-help">10개씩 최대 5묶음을 실행하며 50/50을 즉시 확인</span></div>
<div><label>👾 몬스터(초)</label><input id="monster_timeout" type="number"><span class="field-help">몬스터 처치 퀘스트 완료 대기</span></div><div><label>🎒 가방 상자(초)</label><input id="bag_timeout" type="number"><span class="field-help">아이템 사용과 보상 처리 대기</span></div>
<div><label>🏁 스테이지(초)</label><input id="stage_timeout" type="number"><span class="field-help">보스 처치와 1/1 완료 표시 대기</span></div><div></div></div></div>

<div class="settings-section"><div class="settings-section-head"><div class="settings-section-icon">🎯</div><div><div class="settings-section-title">클릭 좌표</div><div class="settings-section-help">1080×1920 기준의 x,y 위치입니다. 화면 구조가 바뀌 때만 수정하세요.</div></div></div><div class="coordinate-layout"><div><div class="phone-map"><span class="map-dot map-boss">보스</span><span class="map-dot map-quest">퀘스트</span><span class="map-dot map-auto">Auto</span><span class="map-dot map-x">X</span></div><div class="coordinate-note">게임 화면 위치 예시</div></div><div class="grid">
<div><label>퀘스트 패널</label><input id="quest_panel"><span class="field-help">오른쪽 퀘스트 카드</span></div><div><label>10회 뽑기</label><input id="ten_draw"><span class="field-help">쿠키·펫 티켓 10회 버튼</span></div>
<div><label>하단 X</label><input id="bottom_x"><span class="field-help">팝업과 보상창 닫기</span></div><div><label>Auto</label><input id="auto_button"><span class="field-help">오븐 자동 열기 메뉴</span></div>
<div><label>Auto 시작</label><input id="auto_start"><span class="field-help">장비 자동 열기 시작</span></div><div><label>가방 한 번 열기</label><input id="bag_item"><span class="field-help">첫 아이템을 한 번만 사용하고 바로 종료</span></div>
<div><label>아이템 사용</label><input id="item_use"><span class="field-help">전부 열기·전부 사용</span></div><div><label>장비 장착/판매</label><input id="equipment_action"><span class="field-help">확대된 공통 버튼 중앙</span></div>
<div><label>보스 소환</label><input id="boss_summon"><span class="field-help">화면 상단 중앙의 빨간 버튼</span></div><div></div>
</div></div><div class="coordinate-preview-toolbar"><div><b>좌표 옆 작은 화면의 빨간 십자가 실제 클릭 위치입니다.</b></div><button id="coordinatePreviewRefresh" class="secondary" type="button" onclick="refreshCoordinatePreviews()">미리보기 갱신</button></div></div>
<div class="buttons"><button class="secondary" onclick="saveSettings()">설정 저장</button><button class="secondary" onclick="loadDefaults()">기본값 복원</button></div></details></section>
<section id="adminCard" class="card"><div id="adminLogin"><b>관리자 모드</b><div class="admin-row" style="margin-top:12px"><div><label>관리자 비밀번호</label><input id="adminPassword" type="password" autocomplete="current-password" onkeydown="if(event.key==='Enter')adminLogin()"></div><button class="secondary" type="button" onclick="adminLogin()">관리자 로그인</button></div><aside id="supportCard" class="support-box" aria-labelledby="supportTitle"><b id="supportTitle">☕ 개발자를 응원해 주세요</b><p>후원은 프로그램 개선과 오류 수정에 도움이 됩니다. 후원 확인 후 관리자 모드 비밀번호를 개별 안내해 드립니다.</p><div class="support-payment"><div class="support-bank"><span>카카오뱅크</span><strong id="supportAccount" class="support-account">후원 정보 확인 중</strong><span id="supportHolder" class="support-holder"></span></div><button class="support-copy" type="button" onclick="copySupportAccount()">계좌번호 복사</button></div><p class="support-note">송금 전 예금주를 확인해 주세요. 후원 확인 시 입금자명과 입금 시각을 알려 주세요.</p><p>후원·오류 문의: <a id="supportEmail" style="color:#93c5fd;overflow-wrap:anywhere"></a></p></aside></div><div id="adminLoggedIn" class="hidden"><div style="display:flex;align-items:center;justify-content:space-between;gap:12px"><div><b>관리자 모드</b><div class="admin-ok">관리자로 로그인했습니다.</div></div><button class="secondary" style="flex:0 0 auto" type="button" onclick="adminLogout()">로그아웃</button></div><div class="channel-box"><div id="channelCurrent" class="channel-current">정식 통합 버전 v16.0</div><div class="channel-notice">모든 기능은 하나의 정식 버전으로 제공됩니다.</div></div></div><details class="usage-notice" onpointerenter="if(event.pointerType==='mouse')this.open=true" onpointerleave="if(event.pointerType==='mouse'&&!this.contains(document.activeElement))this.open=false"><summary>무료 사용 및 이용 규정</summary><ul><li>이 프로그램은 무료로 사용할 수 있으며, 후원은 자율입니다. 관리자 모드 비밀번호는 후원 확인 후 별도로 안내됩니다.</li><li>제작자의 사전 허락 없이 프로그램을 재배포하거나 판매·유료 패키지에 포함할 수 없습니다.</li><li>제작자 표시를 삭제하거나 다른 사람의 제작물로 표시할 수 없습니다. 수정본을 배포하려면 사전 허락을 받아 주세요.</li><li>관리자 비밀번호를 무단으로 공유하거나 판매하지 마세요.</li><li>이용하는 게임 및 플랫폼의 이용약관과 운영정책을 확인하고 준수해 주세요.</li><li>프로그램 사용은 사용자의 자유로운 선택입니다. 사용으로 발생할 수 있는 계정 정지·이용 제한, 게임 내 재화 또는 데이터 손실 등 각종 문제와 불이익에 대한 책임은 사용자 본인에게 있습니다.</li></ul></details></section>
<section id="dailySummaryCard" class="card hidden"><div class="daily-summary-heading"><div><h2 id="dailySummaryTitle">오늘의 총정리</h2><p id="dailySummaryMeta">기록을 불러오는 중입니다.</p></div></div><div class="daily-summary-stats"><div class="daily-summary-stat"><span>실행</span><strong id="dailyRuns">0회</strong></div><div class="daily-summary-stat"><span>완료</span><strong id="dailyCompleted">0개</strong></div><div class="daily-summary-stat"><span>오류</span><strong id="dailyErrors">0건</strong></div><div class="daily-summary-stat"><span>복구</span><strong id="dailyRecoveries">0회</strong></div></div><div class="daily-summary-section"><h3>오늘 선택한 작업</h3><div id="dailySummaryTasks" class="daily-summary-list"><div class="daily-summary-empty">아직 실행한 작업이 없습니다.</div></div></div><div class="daily-summary-section"><h3>아레나 덱 판단</h3><div id="dailySummaryArena" class="daily-summary-list"><div class="daily-summary-empty">오늘의 아레나 판단이 없습니다.</div></div></div><div class="daily-summary-section"><h3>최근 활동</h3><div id="dailySummaryActivities" class="daily-summary-list"><div class="daily-summary-empty">오늘의 활동이 없습니다.</div></div></div><div class="daily-summary-section"><h3>배포 확인 상태</h3><div id="dailySummaryDeploy" class="daily-summary-list"></div></div><div class="daily-summary-actions"><button type="button" onclick="poll(true)">새로고침</button><button class="secondary" type="button" onclick="copyDailySummary()">총정리 복사</button></div></section>
<section id="adminLogs" class="card hidden"><div style="display:flex;align-items:center;justify-content:space-between;gap:12px"><div><b>실행 로그</b> <span id="executionCount" class="warning">(실행횟수:000)</span></div><button class="secondary" style="flex:0 0 auto;padding:9px 14px" onclick="copyLogs()">로그 복사</button></div><pre id="logs">준비 중…</pre></section>
<section id="adminScreenshots" class="card hidden"><details class="admin-shot-details"><summary>통합 오류 확인·보고</summary><div id="unifiedErrorCenter"><div class="combined-error-head"><div><b>통합 오류 확인·보고</b><span class="field-help">오류 기록과 당시 스크린샷을 함께 확인하고 수정 요청을 만듭니다.</span></div><span id="errorCount" class="warning">0건</span><button class="secondary" onclick="copyErrors()">전체 보고 복사</button><button type="button" onclick="emailErrors()">이메일로 오류 보고</button></div><p class="field-help">수신: <a id="reportEmail" style="color:#93c5fd"></a> · 이메일 버튼을 누르면 전체 보고서가 다운로드되고 메일 초안이 열립니다. 보고서와 필요한 스크린샷을 첨부한 뒤 전송해 주세요. 메일 앱이 열리지 않으면 전체 보고를 복사해 직접 보내 주세요.</p><div id="errors" class="errors unified-errors"><div class="empty">이번 실행에서 보고된 오류가 없습니다.</div></div><div id="errorPager" class="pager"></div><div id="errorPageStatus" class="page-status"></div><div id="screenshotStorage" class="unified-storage"><div><b>스크린샷 저장 관리</b><p id="storagePath" style="word-break:break-all;color:var(--muted)"></p><p><span id="storageCount">0개</span> · <span id="storageSize">0MB</span> · 200MB 도달 시 약 150MB까지 자동 정리</p></div><div class="buttons"><button class="secondary" onclick="cleanupScreenshots()">오래된 화면 정리</button><button class="stop" onclick="deleteScreenshots()">스크린샷 전체 삭제</button></div></div></div></details></section>
</div>

<div class="footer">크리스탈 또는 알 수 없는 비용이 감지되면 자동으로 중단합니다.</div>
</div><script>

const loadedUIRevision='__CQA_UI_REVISION__';
async function checkUIRevision(){
    try{
        let response=await fetch('/ui-revision',{cache:'no-store'});
        if(!response.ok)return;
        let state=await response.json(),active=document.activeElement;
        let editing=layoutEditing||(active&&(active.matches('input,textarea,select')||active.isContentEditable));
        if(state.revision&&state.revision!==loadedUIRevision&&!editing){window.location.reload();return}
    }catch(error){}finally{setTimeout(checkUIRevision,1000)}
}
setTimeout(checkUIRevision,1000);

const keys=['cycles','infinite','automatic_check','adjust_screen_size','screen_width','screen_height','task_quest','task_auto_hunt_reward','task_attendance','task_missions','task_event_rewards','task_pass_free','task_mailbox','task_crumble_dungeon','task_crumble_dungeon_runs','task_arena','task_arena_decision','arena_decision_mode','arena_kind','task_arena_runs','task_implant_tower','task_implant_tower_runs','task_exp_dungeon','task_exp_dungeon_runs','task_exp_dungeon_continuous','task_coin_dungeon','task_coin_dungeon_runs','task_coin_dungeon_continuous','task_dough_dungeon','task_dough_dungeon_runs','task_dough_dungeon_continuous','task_research_stone_dungeon','task_research_stone_dungeon_runs','task_research_stone_dungeon_continuous','task_rune_crystal_dungeon','task_rune_crystal_dungeon_runs','task_rune_crystal_dungeon_continuous','task_guild_attendance','task_cookie_upgrade','task_pet_upgrade','task_breakthrough','boss_preset_1','boss_preset_2','boss_preset_3','boss_preset_4','boss_preset_5','boss_preset_order','boss_keyboard_move_normal','boss_keyboard_move_corner','draw_timeout','equipment_timeout','monster_timeout','bag_timeout','stage_timeout','boss_move_seconds','boss_corner_move_seconds','quest_panel','ten_draw','bottom_x','auto_button','auto_start','bag_item','item_use','equipment_action','boss_summon'];
keys.splice(keys.indexOf('task_quest')+1,0,'restart_game_on_exit');
const coordinatePreviewFields=[['quest_panel','퀘스트 패널'],['ten_draw','10회 뽑기'],['bottom_x','하단 X'],['auto_button','Auto'],['auto_start','Auto 시작'],['bag_item','가방 첫 아이템'],['item_use','아이템 사용'],['equipment_action','장비 장착/판매'],['boss_summon','보스 소환']];
let defaults={};
let lastErrorCount=0;
let lastErrors=[];
let lastErrorSignature='';
let isPaused=false;
let groupStartPending=false;
let lastRunBusy=false;
let adminToken=sessionStorage.getItem('cqaAdminToken')||'';
let errorPage=1;
let adminViewState=null;
let layoutEditing=false;
let layoutBeforeEdit={};
let hiddenFeatureIds=new Set();
let dragLayout=null;
let resizeLayoutCard=null;
let layoutResizeObserver=null;
let coordinatePreviewImage=null;
let coordinatePreviewUrl='';
const LAYOUT_SNAP_DISTANCE=12;
function values(){let d={...defaults};keys.forEach(k=>{let e=document.getElementById(k);if(e)d[k]=e.type==='checkbox'?e.checked:e.value});return d}
function arrangePrimaryPanels(){
    let control=document.getElementById('controlCard'),summary=document.getElementById('summaryCard'),dashboard=control?.querySelector('.inline-dashboard'),checklist=summary?.querySelector('.task-checklist-panel'),preset=checklist?.querySelector('.boss-preset-row'),movement=summary?.querySelector('.boss-movement-public'),content=document.getElementById('bossPopupContent');
    if(control&&dashboard&&checklist)dashboard.after(checklist);
    let bossLaunch=summary?.querySelector('.boss-popup-launch');
    if(control&&checklist&&bossLaunch)checklist.after(bossLaunch);
    if(content&&preset)content.appendChild(preset);
    if(content&&movement)content.appendChild(movement);
    ['taskPopupBackdrop','taskPopup','bossPopupBackdrop','bossPopup'].forEach(id=>{let panel=document.getElementById(id);if(panel)document.body.appendChild(panel)});
    if(summary){summary.classList.remove('card');summary.setAttribute('aria-hidden','true')}
}
function placeHelpBesideText(source,dot){let parent=source.parentElement,target=null;if(source.matches('.field-help'))target=parent.querySelector(':scope > label:not(.boss-keyboard-option),:scope > b');else if(source.matches('.settings-section-help'))target=parent.querySelector('.settings-section-title');else if(source.matches('.boss-preset-help'))target=parent.querySelector('.boss-preset-title');else if(source.matches('.task-help'))target=source.closest('.task-group')?.querySelector('.task-group-name');else if(source.matches('.settings-intro small,.check small'))target=parent.querySelector('b,strong');else if(source.matches('.screen-size-note'))target=source.closest('.screen-config')?.querySelector('b,label');else if(source.matches('.channel-notice'))target=source.closest('.channel-box')?.querySelector('.channel-current');else if(source.matches('.coordinate-note'))target=source.parentElement?.querySelector('b,label');else if(source.matches('.layout-help'))target=document.getElementById('layoutEditButton');if(target&&target.tagName!=='BUTTON')target.appendChild(dot);else if(target)target.after(dot);else source.before(dot)}
function setupHoverHelp(){let tooltip=document.getElementById('hoverTooltip');if(!tooltip){tooltip=document.createElement('div');tooltip.id='hoverTooltip';tooltip.setAttribute('role','tooltip');document.body.appendChild(tooltip)}let selectors=['.layout-help','.task-help','.boss-preset-help','.boss-keyboard-option small','.check small','.settings-intro small','.settings-section-help','.field-help','.screen-size-note','.channel-notice','.coordinate-note'];document.querySelectorAll(selectors.join(',')).forEach(source=>{if(source.classList.contains('hover-help-source'))return;let message=(source.textContent||'').trim();if(!message)return;let dot=document.createElement('span');dot.className='help-dot';dot.textContent='ⓘ';dot.tabIndex=0;dot.setAttribute('aria-label',message);dot.dataset.help=message;placeHelpBesideText(source,dot);source.classList.add('hover-help-source')});let show=target=>{tooltip.textContent=target.dataset.help||'';tooltip.style.maxWidth='320px';tooltip.classList.add('visible');let r=target.getBoundingClientRect(),x=r.right+10,room=Math.max(24,window.innerWidth-x-8);tooltip.style.maxWidth=Math.min(320,room)+'px';let h=tooltip.offsetHeight,y=r.top+(r.height-h)/2;tooltip.style.left=x+'px';tooltip.style.top=Math.max(8,Math.min(window.innerHeight-h-8,y))+'px'};document.querySelectorAll('.help-dot').forEach(dot=>{dot.addEventListener('mouseenter',()=>show(dot));dot.addEventListener('mouseleave',()=>tooltip.classList.remove('visible'));dot.addEventListener('focus',()=>show(dot));dot.addEventListener('blur',()=>tooltip.classList.remove('visible'))})}
function bossPresetOrder(){let raw=(document.getElementById('boss_preset_order').value||'').split(',').map(Number).filter(n=>n>=1&&n<=5),checked=[];for(let n=1;n<=5;n++)if(document.getElementById('boss_preset_'+n).checked)checked.push(n);let order=raw.filter((n,i)=>checked.includes(n)&&raw.indexOf(n)===i);checked.forEach(n=>{if(!order.includes(n))order.push(n)});return order}
function renderBossPresetOrder(){let order=bossPresetOrder();document.getElementById('boss_preset_order').value=order.join(',');for(let n=1;n<=5;n++){let rank=document.getElementById('boss_preset_rank_'+n),index=order.indexOf(n);rank.textContent=index>=0?String(index+1):''}}
function updateBossPresetOrder(number){let order=(document.getElementById('boss_preset_order').value||'').split(',').map(Number).filter(n=>n>=1&&n<=5&&n!==number);if(document.getElementById('boss_preset_'+number).checked)order.push(number);document.getElementById('boss_preset_order').value=order.join(',');renderBossPresetOrder();syncBossControls()}
function coordinateValue(id){let raw=(document.getElementById(id)?.value||'').trim(),parts=raw.split(',').map(v=>Number(v.trim()));return parts.length===2&&parts.every(Number.isFinite)?parts:null}
function setupCoordinatePreviews(){coordinatePreviewFields.forEach(([id])=>{let input=document.getElementById(id),field=input?.parentElement;if(!input||!field||field.classList.contains('coordinate-field'))return;let content=document.createElement('div');content.className='coordinate-field-content';while(field.firstChild)content.appendChild(field.firstChild);let preview=document.createElement('div');preview.className='coordinate-preview-card';preview.innerHTML=`<canvas id="coordinateCanvas_${id}" width="160" height="100"></canvas><span id="coordinateValue_${id}" class="coordinate-preview-value">-</span>`;field.append(content,preview);field.classList.add('coordinate-field');input.addEventListener('input',()=>drawCoordinatePreviews())});drawCoordinatePreviews()}
function drawCoordinatePreviews(){coordinatePreviewFields.forEach(([id])=>{let canvas=document.getElementById('coordinateCanvas_'+id),ctx=canvas?.getContext('2d'),point=coordinateValue(id),value=document.getElementById('coordinateValue_'+id);if(!ctx)return;ctx.clearRect(0,0,canvas.width,canvas.height);ctx.fillStyle='#050914';ctx.fillRect(0,0,canvas.width,canvas.height);if(value)value.textContent=point?`${point[0]}, ${point[1]}`:'좌표 확인 필요';if(!coordinatePreviewImage||!point){ctx.fillStyle='#71809c';ctx.font='12px sans-serif';ctx.textAlign='center';ctx.fillText(coordinatePreviewImage?'좌표 형식을 확인하세요':'현재 화면으로 갱신하세요',canvas.width/2,canvas.height/2);return}let img=coordinatePreviewImage,px=point[0]*img.width/1080,py=point[1]*img.height/1920,cropW=Math.min(img.width,Math.max(260,img.width*.30)),cropH=cropW*canvas.height/canvas.width;if(cropH>img.height){cropH=img.height;cropW=cropH*canvas.width/canvas.height}let sx=Math.max(0,Math.min(img.width-cropW,px-cropW/2)),sy=Math.max(0,Math.min(img.height-cropH,py-cropH/2)),cx=(px-sx)/cropW*canvas.width,cy=(py-sy)/cropH*canvas.height;ctx.drawImage(img,sx,sy,cropW,cropH,0,0,canvas.width,canvas.height);ctx.strokeStyle='#ff304f';ctx.fillStyle='#ff304f';ctx.lineWidth=3;ctx.beginPath();ctx.moveTo(cx-13,cy);ctx.lineTo(cx+13,cy);ctx.moveTo(cx,cy-13);ctx.lineTo(cx,cy+13);ctx.stroke();ctx.beginPath();ctx.arc(cx,cy,4,0,Math.PI*2);ctx.fill();ctx.strokeStyle='white';ctx.lineWidth=1;ctx.beginPath();ctx.arc(cx,cy,7,0,Math.PI*2);ctx.stroke()})}
async function refreshCoordinatePreviews(){if(!adminToken){alert('관리자 로그인 후 사용할 수 있습니다.');return}let button=document.getElementById('coordinatePreviewRefresh');button.disabled=true;button.textContent='화면 캡처 중…';try{let response=await fetch('/coordinate-image?admin='+encodeURIComponent(adminToken)+'&t='+Date.now());if(!response.ok)throw new Error('BlueStacks 화면을 가져오지 못했습니다.');let blob=await response.blob(),url=URL.createObjectURL(blob),img=new Image();await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=reject;img.src=url});if(coordinatePreviewUrl)URL.revokeObjectURL(coordinatePreviewUrl);coordinatePreviewUrl=url;coordinatePreviewImage=img;drawCoordinatePreviews()}catch(e){alert(e.message||'좌표 이미지를 갱신하지 못했습니다.')}finally{button.disabled=false;button.textContent='현재 화면으로 갱신'}}
function fill(d){keys.forEach(k=>{let e=document.getElementById(k);if(e.type==='checkbox')e.checked=!!d[k];else e.value=d[k]});renderBossPresetOrder();syncScreenPreset();syncDailyContinuous();renderBossSettingsSummary()}
function layoutCards(){return [...document.querySelectorAll('#layoutCanvas>.card[id]:not(.admin-popup-storage)')]}
function setLayoutButtons(editing){layoutEditing=editing;document.querySelector('.app-header').classList.toggle('layout-editing',editing);document.getElementById('layoutEditButton').classList.toggle('hidden',editing);document.getElementById('layoutSaveButton').classList.toggle('hidden',!editing);document.getElementById('layoutCancelButton').classList.toggle('hidden',!editing);document.getElementById('layoutRestoreFeaturesButton').classList.toggle('hidden',!editing);document.getElementById('layoutResetButton').classList.toggle('hidden',editing);document.querySelectorAll('.feature-remove-button').forEach(button=>button.disabled=!editing);updateHiddenFeatureButton()}
function removableFeatures(){return [...document.querySelectorAll('[data-feature-id]')]}
function removedFeatureIds(){return removableFeatures().filter(item=>item.classList.contains('feature-removed')).map(item=>item.dataset.featureId)}
function updateHiddenFeatureButton(){let button=document.getElementById('layoutRestoreFeaturesButton'),count=removedFeatureIds().length;if(!button)return;button.textContent=`숨긴 기능 모두 복원 (${count})`;button.disabled=!layoutEditing||count===0}
function applyFeatureVisibility(hidden=[]){hiddenFeatureIds=new Set(Array.isArray(hidden)?hidden:[]);removableFeatures().forEach(item=>item.classList.toggle('feature-removed',hiddenFeatureIds.has(item.dataset.featureId)));updateHiddenFeatureButton()}
function removeFeature(event){event.preventDefault();event.stopPropagation();if(!layoutEditing)return;let item=event.currentTarget.closest('[data-feature-id]');if(!item)return;item.classList.add('feature-removed');hiddenFeatureIds.add(item.dataset.featureId);updateHiddenFeatureButton();adjustLayoutCanvas()}
function restoreAllFeatures(){if(!layoutEditing)return;hiddenFeatureIds.clear();removableFeatures().forEach(item=>item.classList.remove('feature-removed'));updateHiddenFeatureButton();requestAnimationFrame(adjustLayoutCanvas)}
function setupRemovableFeatures(){let cards={controlCard:'실행 제어',summaryCard:'실행할 작업 체크리스트',adminCard:'관리자 모드',adminLogs:'실행 로그',settingsCard:'관리자 세부 설정',adminScreenshots:'통합 오류 확인·보고'};Object.entries(cards).forEach(([id,label])=>{let item=document.getElementById(id);if(item){item.dataset.featureId='card_'+id;item.dataset.featureLabel=label;item.classList.add('feature-removable')}});document.querySelectorAll('.task-row').forEach((item,index)=>{let input=item.querySelector('input[type=checkbox][id^="task_"]'),label=item.querySelector('.task-name')?.textContent?.trim()||`작업 ${index+1}`;if(!input)return;item.dataset.featureId='task_'+input.id;item.dataset.featureLabel=label;item.classList.add('feature-removable')});document.querySelectorAll('.task-group-collapsible').forEach((item,index)=>{item.dataset.featureId=`task_group_${index+1}`;item.dataset.featureLabel=item.querySelector(':scope>summary .task-group-name')?.textContent?.trim()||`작업 묶음 ${index+1}`;item.classList.add('feature-removable')});document.querySelectorAll('.settings-section').forEach((item,index)=>{item.dataset.featureId=`settings_section_${index+1}`;item.dataset.featureLabel=item.querySelector('.settings-section-title')?.textContent?.trim()||`세부 설정 ${index+1}`;item.classList.add('feature-removable')});[['.channel-box','admin_channel','버전 전환'],['#unifiedErrorCenter','unified_error_center','통합 오류 확인·보고']].forEach(([selector,id,label])=>{let item=document.querySelector(selector);if(item){item.dataset.featureId=id;item.dataset.featureLabel=label;item.classList.add('feature-removable')}});removableFeatures().forEach(item=>{if(item.querySelector(':scope>.feature-remove-button'))return;let button=document.createElement('button');button.type='button';button.className='feature-remove-button';button.textContent='×';button.title=`${item.dataset.featureLabel||'이 기능'} 숨기기 · 화면 배치 편집 중에만 사용 가능`;button.setAttribute('aria-label',button.title);button.disabled=true;button.addEventListener('click',removeFeature);item.appendChild(button)})}
function addLayoutHandles(){layoutCards().forEach(card=>{if(card.querySelector(':scope>.layout-drag-handle'))return;let handle=document.createElement('div');handle.className='layout-drag-handle';handle.textContent='↕ 이동';handle.addEventListener('pointerdown',beginCardDrag);card.appendChild(handle)})}
function clearUILayout(){let canvas=document.getElementById('layoutCanvas');canvas.classList.remove('custom-layout','layout-editing');canvas.style.removeProperty('height');layoutCards().forEach(card=>{['left','top','width','height'].forEach(name=>card.style.removeProperty(name));delete card.dataset.layoutBaseHeight})}
function applyUILayout(layout){clearUILayout();applyFeatureVisibility(layout&&layout.hiddenFeatures);let cards=layout&&layout.cards;if(!cards||!Object.keys(cards).length)return;let canvas=document.getElementById('layoutCanvas');canvas.classList.add('custom-layout');canvas.style.height=Math.max(300,Number(layout.canvasHeight)||900)+'px';layoutCards().forEach(card=>{let p=cards[card.id];if(!p)return;card.style.left=Number(p.x)+'px';card.style.top=Number(p.y)+'px';card.style.width=Number(p.w)+'px';card.style.height=Number(p.h)+'px';card.dataset.layoutBaseHeight=Number(p.h)})}
function currentUILayout(){let cards={},bottom=300;layoutCards().forEach(card=>{let removed=card.classList.contains('feature-removed'),number=(name,fallback)=>{let value=parseFloat(card.style[name]);return Number.isFinite(value)?value:fallback},x=removed?number('left',0):card.offsetLeft,y=removed?number('top',0):card.offsetTop,w=removed?number('width',400):card.offsetWidth,h=removed?number('height',200):card.offsetHeight;cards[card.id]={x,y,w,h};if(!removed)bottom=Math.max(bottom,y+h+12)});return{canvasHeight:bottom,cards,hiddenFeatures:removedFeatureIds()}}
function adjustLayoutCanvas(){let canvas=document.getElementById('layoutCanvas');if(!canvas.classList.contains('custom-layout'))return;canvas.style.height=currentUILayout().canvasHeight+'px'}
function naturalCardHeight(card){let saved=card.style.height;card.style.height='auto';let height=Math.max(card.offsetHeight,card.scrollHeight)+2;card.style.height=saved;return height}
function handleDetailsToggle(event){let details=event.target,canvas=document.getElementById('layoutCanvas');if(!(details instanceof HTMLDetailsElement)||!canvas.classList.contains('custom-layout'))return;let card=details.closest('#layoutCanvas>.card');if(!card||card.classList.contains('hidden')||card.classList.contains('admin-popup-active'))return;requestAnimationFrame(()=>{let oldHeight=card.offsetHeight,base=Math.max(100,Number(card.dataset.layoutBaseHeight)||oldHeight),target=Math.max(base,naturalCardHeight(card)),delta=target-oldHeight;if(Math.abs(delta)<2){adjustLayoutCanvas();return}let oldBottom=card.offsetTop+oldHeight,newBottom=card.offsetTop+target,left=card.offsetLeft,right=left+card.offsetWidth;visibleOtherCards(card).forEach(other=>{let otherLeft=other.offsetLeft,otherRight=otherLeft+other.offsetWidth,horizontalOverlap=Math.min(right,otherRight)-Math.max(left,otherLeft);if(horizontalOverlap>8&&other.offsetTop>=Math.min(oldBottom,newBottom)-4)other.style.top=Math.max(0,other.offsetTop+delta)+'px'});card.style.height=target+'px';adjustLayoutCanvas()})}
document.addEventListener('toggle',handleDetailsToggle,true);
function snapEnabled(){return document.getElementById('layoutSnap').checked}
function saveSnapPreference(){try{localStorage.setItem('cqaLayoutSnap',snapEnabled()?'on':'off')}catch(e){}}
function nearestLayoutSnap(value,candidates){let best={value,guide:null,distance:LAYOUT_SNAP_DISTANCE+1};candidates.forEach(item=>{let distance=Math.abs(value-item.value);if(distance<best.distance){best={value:item.value,guide:item.guide,distance}}});return best.distance<=LAYOUT_SNAP_DISTANCE?best:{value,guide:null}}
function visibleOtherCards(card){return layoutCards().filter(other=>other!==card&&!other.classList.contains('hidden'))}
function snappedCardPosition(card,x,y){if(!snapEnabled())return{x,y,guideX:null,guideY:null};let canvas=document.getElementById('layoutCanvas'),w=card.offsetWidth,h=card.offsetHeight;let xs=[{value:0,guide:0},{value:canvas.clientWidth-w,guide:canvas.clientWidth}],ys=[{value:0,guide:0}];visibleOtherCards(card).forEach(other=>{let left=other.offsetLeft,top=other.offsetTop,right=left+other.offsetWidth,bottom=top+other.offsetHeight;xs.push({value:left,guide:left},{value:right-w,guide:right},{value:left-w,guide:left},{value:right,guide:right},{value:left+(other.offsetWidth-w)/2,guide:left+other.offsetWidth/2});ys.push({value:top,guide:top},{value:bottom-h,guide:bottom},{value:top-h,guide:top},{value:bottom,guide:bottom},{value:top+(other.offsetHeight-h)/2,guide:top+other.offsetHeight/2})});let sx=nearestLayoutSnap(x,xs),sy=nearestLayoutSnap(y,ys);return{x:sx.value,y:sy.value,guideX:sx.guide,guideY:sy.guide}}
function showSnapGuides(x,y){let gx=document.getElementById('snapGuideX'),gy=document.getElementById('snapGuideY');gx.classList.toggle('visible',x!==null);gy.classList.toggle('visible',y!==null);if(x!==null)gx.style.left=x+'px';if(y!==null)gy.style.top=y+'px'}
function hideSnapGuides(){showSnapGuides(null,null)}
function snapCardSize(card){if(!card)return;let changed=false,sw={guide:null},sh={guide:null};if(snapEnabled()){let widths=[],heights=[];visibleOtherCards(card).forEach(other=>{widths.push({value:other.offsetWidth,guide:card.offsetLeft+other.offsetWidth});heights.push({value:other.offsetHeight,guide:card.offsetTop+other.offsetHeight})});sw=nearestLayoutSnap(card.offsetWidth,widths);sh=nearestLayoutSnap(card.offsetHeight,heights);if(sw.guide!==null){card.style.width=sw.value+'px';changed=true}if(sh.guide!==null){card.style.height=sh.value+'px';changed=true}}card.dataset.layoutBaseHeight=card.offsetHeight;if(changed){showSnapGuides(sw.guide,sh.guide);card.classList.add('snap-flash');setTimeout(()=>{card.classList.remove('snap-flash');hideSnapGuides()},450)}adjustLayoutCanvas()}
function beginCardDrag(event){if(!layoutEditing)return;event.preventDefault();let card=event.currentTarget.parentElement;dragLayout={card,startX:event.clientX,startY:event.clientY,left:card.offsetLeft,top:card.offsetTop};event.currentTarget.setPointerCapture(event.pointerId)}
document.addEventListener('pointerdown',event=>{if(!layoutEditing||event.target.closest('.layout-drag-handle'))return;let card=event.target.closest('#layoutCanvas>.card');if(!card)return;let r=card.getBoundingClientRect();if(r.right-event.clientX<=24&&r.bottom-event.clientY<=24)resizeLayoutCard=card},true);
document.addEventListener('pointermove',event=>{if(!dragLayout)return;let canvas=document.getElementById('layoutCanvas'),card=dragLayout.card;let rawX=Math.max(0,Math.min(dragLayout.left+event.clientX-dragLayout.startX,Math.max(0,canvas.clientWidth-card.offsetWidth))),rawY=Math.max(0,dragLayout.top+event.clientY-dragLayout.startY);let snapped=snappedCardPosition(card,rawX,rawY);card.style.left=Math.max(0,Math.min(snapped.x,Math.max(0,canvas.clientWidth-card.offsetWidth)))+'px';card.style.top=Math.max(0,snapped.y)+'px';showSnapGuides(snapped.guideX,snapped.guideY);adjustLayoutCanvas()});
document.addEventListener('pointerup',()=>{if(resizeLayoutCard)snapCardSize(resizeLayoutCard);resizeLayoutCard=null;dragLayout=null;if(!document.querySelector('.snap-flash'))hideSnapGuides()});
async function loadUILayout(){let r=await fetch('/ui-layout');if(r.ok)applyUILayout(await r.json())}
async function startLayoutEdit(){if(!adminToken){alert('화면 전체를 편집하려면 먼저 관리자 모드로 로그인해 주세요.');return}await poll(true);if(document.getElementById('adminLoggedIn').classList.contains('hidden')){alert('관리자 로그인을 다시 확인해 주세요.');return}addLayoutHandles();layoutBeforeEdit=document.getElementById('layoutCanvas').classList.contains('custom-layout')?currentUILayout():{hiddenFeatures:removedFeatureIds()};let canvas=document.getElementById('layoutCanvas');if(!canvas.classList.contains('custom-layout')){let base=canvas.getBoundingClientRect();let measured=layoutCards().filter(card=>!card.classList.contains('hidden')&&!card.classList.contains('feature-removed')).map(card=>{let r=card.getBoundingClientRect();return{card,x:r.left-base.left,y:r.top-base.top,w:r.width,h:r.height}});canvas.classList.add('custom-layout');let bottom=300;measured.forEach(p=>{p.card.style.left=p.x+'px';p.card.style.top=p.y+'px';p.card.style.width=p.w+'px';p.card.style.height=p.h+'px';p.card.dataset.layoutBaseHeight=p.h;bottom=Math.max(bottom,p.y+p.h+12)});canvas.style.height=bottom+'px'}canvas.classList.add('layout-editing');setLayoutButtons(true);layoutResizeObserver=new ResizeObserver(adjustLayoutCanvas);layoutCards().forEach(card=>layoutResizeObserver.observe(card))}
function finishLayoutEdit(){document.getElementById('layoutCanvas').classList.remove('layout-editing');if(layoutResizeObserver){layoutResizeObserver.disconnect();layoutResizeObserver=null}dragLayout=null;resizeLayoutCard=null;hideSnapGuides();setLayoutButtons(false)}
async function saveUILayout(){let layout=currentUILayout();let r=await fetch('/ui-layout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:adminToken,layout})});let d=await r.json();if(!r.ok){alert(d.message||'배치를 저장하지 못했습니다.');return}layoutCards().forEach(card=>card.dataset.layoutBaseHeight=card.offsetHeight);document.getElementById('layoutCanvas').style.height=layout.canvasHeight+'px';finishLayoutEdit();alert(d.message)}
function cancelLayoutEdit(){applyUILayout(layoutBeforeEdit);finishLayoutEdit()}
async function resetUILayout(){if(!adminToken){alert('기본 배치 복원은 관리자 로그인 후 사용할 수 있습니다.');return}if(!confirm('저장한 화면 위치·크기와 숨긴 기능을 모두 기본 상태로 복원할까요?'))return;let r=await fetch('/reset-ui-layout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:adminToken})});let d=await r.json();if(r.ok){clearUILayout();applyFeatureVisibility([]);finishLayoutEdit()}alert(d.message||'기본 배치 복원을 처리하지 못했습니다.')}
function setupAdminPopups(){let configs=[['settingsCard','세부 설정'],['dailySummaryCard','오늘의 총정리'],['adminScreenshots','통합 오류 확인·보고']];configs.forEach(([id,title])=>{let panel=document.getElementById(id);if(!panel||panel.classList.contains('admin-popup-panel'))return;let content=document.createElement('div');content.className='admin-popup-content';while(panel.firstChild)content.appendChild(panel.firstChild);let launch=document.createElement('button');launch.type='button';launch.className='admin-popup-launch';launch.innerHTML=`<span>${title}</span><span class="popup-arrow">팝업으로 열기 ↗</span>`;launch.onclick=()=>openAdminPopup(id);let close=document.createElement('button');close.type='button';close.className='admin-popup-close';close.textContent='팝업 닫기';close.onclick=closeAdminPopup;panel.append(launch,close,content);panel.classList.add('admin-popup-panel','admin-popup-ready','admin-popup-storage')});let host=document.getElementById('adminCard'),menu=document.createElement('div');menu.className='admin-submenu';configs.forEach(([id,title],index)=>{let button=document.createElement('button');button.type='button';button.innerHTML=`<span>${title}</span><span>열기 ↗</span>`;button.onclick=()=>openAdminPopup(id);menu.appendChild(button);if(index===0){let tasks=document.createElement('button');tasks.type='button';tasks.id='adminExtraTasks';tasks.innerHTML='<span>추가 실행 작업</span><span>열기 ↗</span>';tasks.onclick=openTaskPopup;menu.appendChild(tasks)}});host.appendChild(menu);let backdrop=document.createElement('div');backdrop.id='adminPopupBackdrop';backdrop.className='admin-popup-backdrop';backdrop.onclick=closeAdminPopup;document.body.appendChild(backdrop);document.addEventListener('keydown',event=>{if(event.key==='Escape'){closeAdminPopup();closeTaskPopup();closeBossPopup()}})}
function openAdminPopup(id){if(!adminToken){alert('관리자 로그인 후 사용할 수 있습니다.');return}if(layoutEditing){alert('화면 배치 편집을 먼저 저장하거나 취소해 주세요.');return}closeAdminPopup();let panel=document.getElementById(id);if(!panel)return;panel.classList.add('admin-popup-active');panel.querySelectorAll('.admin-popup-content>details').forEach(details=>details.open=true);document.body.classList.add('admin-popup-open');if(id==='settingsCard'&&!coordinatePreviewImage)refreshCoordinatePreviews()}
function closeAdminPopup(){document.querySelectorAll('.admin-popup-active').forEach(panel=>panel.classList.remove('admin-popup-active'));document.body.classList.remove('admin-popup-open')}

async function loadUpdateStatus(){try{let r=await fetch('/update-status');let d=await r.json(),e=document.getElementById('updateStatus');if(d.update_available){e.textContent='새 버전 '+d.latest_version;e.href=d.download_url;e.classList.remove('hidden')}}catch(error){}}
let publicConfig={support_account:'',support_holder:'',contact_email:''};
async function loadPublicConfig(){try{let r=await fetch('/public-config');publicConfig=await r.json();document.getElementById('supportAccount').textContent=publicConfig.support_account||'후원 정보 없음';document.getElementById('supportHolder').textContent=publicConfig.support_holder||'';['supportEmail','reportEmail'].forEach(id=>{let e=document.getElementById(id);e.textContent=publicConfig.contact_email||'이메일 정보 없음';if(publicConfig.contact_email)e.href='mailto:'+publicConfig.contact_email})}catch(error){}}
function copySupportAccount(){if(!publicConfig.support_account){alert('후원 계좌 정보가 설정되지 않았습니다.');return}copyText(publicConfig.support_account,'카카오뱅크 계좌번호를 복사했습니다. 은행 앱에서 붙여넣어 송금해 주세요.')}
async function init(){arrangePrimaryPanels();let r=await fetch('/settings');defaults=await r.json();fill(defaults);setupCoordinatePreviews();setupHoverHelp();try{document.getElementById('layoutSnap').checked=localStorage.getItem('cqaLayoutSnap')!=='off'}catch(e){}setupAdminPopups();setupRemovableFeatures();addLayoutHandles();await loadUILayout();await loadPublicConfig();loadUpdateStatus();poll()}
let bossControlsPending=Promise.resolve(true);
function syncBossControls(){
    renderBossSettingsSummary();
    let data={};
    ['boss_keyboard_move_normal','boss_keyboard_move_corner',...Array.from({length:5},(_,i)=>'boss_preset_'+(i+1))].forEach(id=>data[id]=document.getElementById(id)?.checked===true);
    data.boss_preset_order=document.getElementById('boss_preset_order')?.value||'';
    bossControlsPending=bossControlsPending.then(async()=>{
        try{
            let response=await fetch('/boss-controls',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data),signal:AbortSignal.timeout(4000)});
            if(!response.ok)throw new Error('설정 반영 실패');
            return true;
        }catch(error){
            try{await fetch('/stop',{method:'POST',signal:AbortSignal.timeout(2000)})}catch(stopError){}
            alert('보스 체크 변경을 반영하지 못해 정지를 요청했습니다. 연결이 끊겼다면 게임에서 직접 키를 떼고 도우미를 다시 열어 주세요.');
            return false;
        }
    });
    return bossControlsPending;
}
async function saveSettings(){await bossControlsPending;let r=await fetch('/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(values())});alert((await r.json()).message)}
function loadDefaults(){fill(defaults);syncBossControls()}
function applyScreenPreset(value){if(value==='custom')return;let [w,h]=value.split('x').map(Number);document.getElementById('screen_width').value=w;document.getElementById('screen_height').value=h}
function syncScreenPreset(){let value=`${document.getElementById('screen_width').value}x${document.getElementById('screen_height').value}`;let select=document.getElementById('screenPreset');select.value=[...select.options].some(o=>o.value===value)?value:'custom'}
function syncDailyContinuous(){['exp','coin','dough','research_stone','rune_crystal'].forEach(kind=>{let runs=document.getElementById(`task_${kind}_dungeon_runs`),box=document.getElementById(`task_${kind}_dungeon_continuous`);if(!runs||!box)return;let allowed=Number(runs.value)>=3;box.disabled=!allowed;if(!allowed)box.checked=false;box.closest('.continuous-option')?.classList.toggle('disabled',!allowed)})}
function setTaskGroup(ids,checked){ids.forEach(id=>{let e=document.getElementById(id);if(e&&!e.disabled)e.checked=checked})}
function renderBossSettingsSummary(){
    let summary=document.getElementById('bossSettingsSummary');if(!summary)return;
    let order=bossPresetOrder(),moves=[];
    if(document.getElementById('boss_keyboard_move_normal')?.checked)moves.push('D '+document.getElementById('boss_move_seconds').value+'초');
    if(document.getElementById('boss_keyboard_move_corner')?.checked)moves.push('A+S '+document.getElementById('boss_corner_move_seconds').value+'초');
    summary.textContent='프리셋 '+(order.length?order.join(' → '):'변경 안 함')+' · '+(moves.length?moves.join(' ↔ '):'키보드 이동 안 함');
}
function openBossPopup(){closeTaskPopup();closeAdminPopup();document.getElementById('bossPopup').classList.add('open');document.getElementById('bossPopupBackdrop').classList.add('open');document.body.classList.add('boss-popup-open');document.querySelector('#bossPopup .task-popup-close').focus()}
function closeBossPopup(){let panel=document.getElementById('bossPopup'),wasOpen=panel?.classList.contains('open');panel?.classList.remove('open');document.getElementById('bossPopupBackdrop')?.classList.remove('open');document.body.classList.remove('boss-popup-open');renderBossSettingsSummary();if(wasOpen)document.getElementById('bossPopupLaunch')?.focus()}
function openTaskPopup(){if(!adminToken){alert('관리자 로그인 후 사용할 수 있습니다.');return}closeBossPopup();document.getElementById('taskPopup').classList.add('open');document.getElementById('taskPopupBackdrop').classList.add('open');document.body.classList.add('task-popup-open')}
function closeTaskPopup(){document.getElementById('taskPopup')?.classList.remove('open');document.getElementById('taskPopupBackdrop')?.classList.remove('open');document.body.classList.remove('task-popup-open')}
async function startInfinite(){document.querySelectorAll('.task-row input[type=checkbox]').forEach(e=>{if(e.id!=='restart_game_on_exit')e.checked=false});document.getElementById('task_quest').checked=true;document.getElementById('infinite').checked=true;await startRun(true)}
async function startRun(skipConfirm=false){if(!await bossControlsPending)return;let d=values();d.dry_run=false;if(d.automatic_check&&!skipConfirm&&!confirm("자동 화면·퀘스트 점검 후 실제 실행을 시작할까요?\n자동화는 계정 제재로 이어질 수 있습니다."))return;await fetch('/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)})}
function updateRunControls(busy){lastRunBusy=!!busy;['start','infiniteStart','memoryCleanup'].forEach(id=>{let button=document.getElementById(id);if(button)button.disabled=lastRunBusy||groupStartPending});document.querySelectorAll('.group-start').forEach(button=>button.disabled=lastRunBusy||groupStartPending)}
async function startTaskGroup(scope,ids,label){
    if(groupStartPending||lastRunBusy)return;
    let selected=ids.filter(id=>document.getElementById(id)?.checked);
    if(!selected.length){alert(label+'에서 실행할 항목을 하나 이상 체크해 주세요.');return}
    groupStartPending=true;updateRunControls(lastRunBusy);
    try{
        if(!await bossControlsPending)return;
        let response;
        try{response=await fetch('/start-group',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scope,selected_tasks:selected,settings:values()})})}
        catch(error){throw new Error('도우미에 연결할 수 없습니다. 도우미 앱을 다시 열고 재시도해 주세요.')}
        let result;
        try{result=await response.json()}catch(error){throw new Error('도우미 응답을 읽지 못했습니다. 앱과 페이지를 다시 열어 주세요.')}
        if(!response.ok)throw new Error(result.message||'독립 실행을 시작하지 못했습니다.');
        defaults={...defaults,task_quest:false,infinite:false,cycles:1};
        document.querySelectorAll('.task-row>input[type=checkbox]').forEach(e=>e.checked=selected.includes(e.id));
        let infinite=document.getElementById('infinite');if(infinite)infinite.checked=false;
        closeTaskPopup();await poll(true);
    }catch(error){alert(error.message||'독립 실행을 시작하지 못했습니다.')}
    finally{groupStartPending=false;updateRunControls(lastRunBusy)}
}
async function nextAction(){let r=await fetch('/next-action',{method:'POST'});let d=await r.json();if(!r.ok)alert(d.message||'다음 행동 요청을 처리하지 못했습니다.')}
async function stopRun(){await fetch('/stop',{method:'POST'})}
async function pauseRun(){if(isPaused){if(!confirm('BlueStacks 게임을 팝업이 없는 첫 전투 화면으로 돌려놓았나요?\n확인을 누르면 퀘스트를 다시 판별하고 실행합니다.'))return;await fetch('/resume',{method:'POST'})}else{await fetch('/pause',{method:'POST'})}}
async function cleanupBluestacksMemory(){if(!confirm('쿠키런을 전면에 둔 상태에서 BlueStacks 메모리를 정리할까요?\n실행 중인 매크로가 없을 때만 사용할 수 있습니다.'))return;let b=document.getElementById('memoryCleanup');b.disabled=true;try{let r=await fetch('/cleanup-memory',{method:'POST'});let d=await r.json();alert(d.message||'메모리 정리를 마쳤습니다.');await poll(true)}catch(e){alert('BlueStacks 메모리 정리 요청에 실패했습니다.')}finally{b.disabled=lastRunBusy||groupStartPending}}
async function shutdownApp(){if(!confirm('실행 중인 작업을 정지하고 프로그램을 완전히 종료할까요?'))return;let b=document.getElementById('quit');b.disabled=true;try{await fetch('/shutdown',{method:'POST'});document.getElementById('status').textContent='프로그램 종료됨';document.getElementById('start').disabled=true;document.getElementById('stop').disabled=true;setTimeout(()=>window.close(),500)}catch(e){b.disabled=false;alert('프로그램 종료 요청에 실패했습니다.')}}
async function copyLogs(){let text=document.getElementById('logs').textContent;try{await navigator.clipboard.writeText(text);alert('실행 로그를 복사했습니다.')}catch(e){let t=document.createElement('textarea');t.value=text;document.body.appendChild(t);t.select();document.execCommand('copy');t.remove();alert('실행 로그를 복사했습니다.')}}
async function copyText(text,message){try{await navigator.clipboard.writeText(text);alert(message)}catch(e){let t=document.createElement('textarea');t.value=text;document.body.appendChild(t);t.select();document.execCommand('copy');t.remove();alert(message)}}
let lastDailySummary=null;
function summaryPower(value){let number=Number(value);if(!Number.isFinite(number)||number<=0)return '판독 실패';if(number>=1000000)return (number/1000000).toFixed(2).replace(/\.00$/,'')+'M';if(number>=1000)return (number/1000).toFixed(2).replace(/\.00$/,'')+'K';return String(Math.round(number))}
function renderDailySummary(summary){
    if(!summary)return;lastDailySummary=summary;
    document.getElementById('dailySummaryTitle').textContent=(summary.date||'-')+' 오늘의 총정리';
    document.getElementById('dailySummaryMeta').textContent=(summary.version||'-')+' · '+(summary.status||'대기 중');
    document.getElementById('dailyRuns').textContent=String(summary.runs||0)+'회';
    document.getElementById('dailyCompleted').textContent=String(summary.completed||0)+'개';
    document.getElementById('dailyErrors').textContent=String(summary.errors||0)+'건';
    document.getElementById('dailyRecoveries').textContent=String(summary.recoveries||0)+'회';
    let tasks=Object.entries(summary.tasks||{}).sort((a,b)=>b[1]-a[1]);
    document.getElementById('dailySummaryTasks').innerHTML=tasks.length?tasks.map(([name,count])=>`<div class="daily-summary-row"><span>${esc(name)}</span><span>${esc(count)}회 실행</span></div>`).join(''):'<div class="daily-summary-empty">아직 실행한 작업이 없습니다.</div>';
    let arena=[...(summary.arena||[])].reverse();
    document.getElementById('dailySummaryArena').innerHTML=arena.length?arena.map(item=>`<div class="daily-summary-row"><span>${esc(item.time||'-')} · ${esc(item.deck||'-')}번 덱</span><span>내 전투력 ${esc(summaryPower(item.mine))} / 상대 ${esc(summaryPower(item.opponent))} · ${esc(item.result||'-')}</span></div>`).join(''):'<div class="daily-summary-empty">오늘의 아레나 판단이 없습니다.</div>';
    let activities=[...(summary.activities||[])].reverse();
    document.getElementById('dailySummaryActivities').innerHTML=activities.length?activities.map(item=>`<div class="daily-summary-row"><span>${esc(item.time||'-')}</span><span>${esc(item.text||'-')}</span></div>`).join(''):'<div class="daily-summary-empty">오늘의 활동이 없습니다.</div>';
    let deploy=summary.deployment||{};
    document.getElementById('dailySummaryDeploy').innerHTML=[['Mac',deploy.mac],['Windows',deploy.windows],['GitHub',deploy.github]].map(([name,value])=>`<div class="daily-summary-row"><span>${name}</span><span class="${value==='검증 완료'?'deployment-ok':'deployment-wait'}">${esc(value||'확인 필요')}</span></div>`).join('');
}
function buildDailySummaryText(summary){let lines=[`${summary.date||'-'} 오늘의 총정리`,`${summary.version||'-'} · ${summary.status||'-'}`,`실행 ${summary.runs||0}회 · 완료 ${summary.completed||0}개 · 오류 ${summary.errors||0}건 · 복구 ${summary.recoveries||0}회`,'','[선택 작업]'];let tasks=Object.entries(summary.tasks||{});lines.push(...(tasks.length?tasks.map(([name,count])=>`${name}: ${count}회`):['없음']),'','[아레나 판단]');let arena=summary.arena||[];lines.push(...(arena.length?arena.map(item=>`${item.time||'-'} · ${item.deck||'-'}번 덱 · 내 ${summaryPower(item.mine)} / 상대 ${summaryPower(item.opponent)} · ${item.result||'-'}`):['없음']),'','[최근 활동]');let activities=summary.activities||[];lines.push(...(activities.length?activities.map(item=>`${item.time||'-'} · ${item.text||'-'}`):['없음']));return lines.join('\n')}
async function copyDailySummary(){if(!lastDailySummary)return;await copyText(buildDailySummaryText(lastDailySummary),'오늘의 총정리를 복사했습니다.')}
async function adminLogin(){let password=document.getElementById('adminPassword').value;let r=await fetch('/admin-login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password})});let d=await r.json();if(!r.ok){alert(d.message||'비밀번호가 올바르지 않습니다.');return}adminToken=d.token;sessionStorage.setItem('cqaAdminToken',adminToken);document.getElementById('adminPassword').value='';await poll(true)}
async function openDashboardErrors(){
    if(layoutEditing){alert('화면 배치 편집을 먼저 저장하거나 취소해 주세요.');return}
    if(adminToken){await poll(true);if(adminViewState){openAdminPopup('adminScreenshots');return}}
    let password=window.prompt('전체 오류 화면을 보려면 관리자 비밀번호를 입력하세요.');
    if(password===null)return;
    let r;
    try{r=await fetch('/admin-login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password})})}
    catch(error){alert('관리자 로그인 요청에 실패했습니다.');return}
    let d=await r.json();
    if(!r.ok){alert(d.message||'비밀번호가 올바르지 않습니다.');return}
    adminToken=d.token;sessionStorage.setItem('cqaAdminToken',adminToken);document.getElementById('adminPassword').value='';
    await poll(true);openAdminPopup('adminScreenshots')
}
async function adminLogout(){if(adminToken)await fetch('/admin-logout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:adminToken})});adminToken='';sessionStorage.removeItem('cqaAdminToken');setAdminView(false)}
function setAdminView(ok){let changed=adminViewState!==ok;adminViewState=ok;document.getElementById('adminLogin').classList.toggle('hidden',ok);document.getElementById('adminLoggedIn').classList.toggle('hidden',!ok);document.getElementById('adminCard').classList.toggle('admin-authenticated',ok);document.getElementById('adminLogs').classList.toggle('hidden',!ok);document.getElementById('dailySummaryCard').classList.toggle('hidden',!ok);document.getElementById('settingsCard').classList.toggle('hidden',!ok);document.getElementById('adminScreenshots').classList.toggle('hidden',!ok);if(!ok){closeAdminPopup();lastErrors=[];lastErrorCount=0;document.getElementById('logs').textContent='관리자 로그인이 필요합니다.'}if(changed&&!document.body.classList.contains('admin-popup-open'))requestAnimationFrame(()=>{let card=document.getElementById('adminCard'),canvas=document.getElementById('layoutCanvas');if(ok&&canvas.classList.contains('custom-layout'))card.style.height=Math.max(card.offsetHeight,naturalCardHeight(card))+'px';adjustLayoutCanvas()})}
function setChannelView(channel){if(channel)document.getElementById('channelCurrent').textContent='정식 통합 버전 '+channel.active_version}
function buildErrorReport(){let base=document.getElementById('storagePath').textContent||'';let lines=[`쿠키런: 크럼블 퀘스트 도우미 v16.0 통합 오류 보고`,`오류 수: ${lastErrors.length}`,''];lastErrors.forEach((e,i)=>{let shot=e.screenshot&&base?base+'/'+e.screenshot:'저장되지 않음';let after=e.after_screenshot&&base?base+'/'+e.after_screenshot:'아직 없음';lines.push(`[오류 ${i+1}]`, `발생 시각: ${e.time||'-'}`,`종류: ${e.kind||'-'}`,`원인: ${e.reason||'-'}`,`현재 퀘스트: ${e.quest||'-'}`,`오류 전/복구 후: ${e.before_state||'-'} / ${e.after_state||'-'}`,`자동 복구: ${e.recovery||'-'}`,`재시작 퀘스트: ${e.resume_quest||'-'}`,`제안된 수정 방향: ${e.direction||'-'}`,`오류 스크린샷: ${shot}`,`수정 후 스크린샷: ${after}`,`직전 실행 기록:\n${e.log_context||'-'}`,'')});return lines.join('\n')}
async function copyErrors(){if(!adminToken){alert('관리자 로그인이 필요합니다.');return}if(!lastErrors.length){alert('복사할 오류 보고가 없습니다.');return}await copyText(buildErrorReport(),'오류 기록과 각 스크린샷 경로를 함께 복사했습니다.')}
function emailErrors(){
    if(!adminToken){alert('관리자 로그인이 필요합니다.');return}
    if(!lastErrors.length){alert('보낼 오류 보고가 없습니다.');return}
    let report=buildErrorReport(),blob=new Blob([report],{type:'text/plain;charset=utf-8'}),url=URL.createObjectURL(blob),link=document.createElement('a');
    link.href=url;link.download='CookieRun-error-report-'+new Date().toISOString().replace(/[:.]/g,'-')+'.txt';document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
    let subject='쿠키런: 크럼블 퀘스트 도우미 오류 확인 및 수정 요청';
    let body='안녕하세요. 프로그램 오류 확인 및 수정을 요청합니다.\n\n오류 수: '+lastErrors.length+'건\n\n[발생 상황을 적어 주세요]\n\n다운로드된 전체 오류 보고서 TXT와 필요한 오류 스크린샷을 이 메일에 첨부해 주세요. 첨부 파일에는 실행 기록과 로컬 파일 경로가 포함되므로 전송 전에 확인해 주세요.';
    if(!publicConfig.contact_email){alert('문의 이메일이 설정되지 않았습니다.');return}
    window.location.href='mailto:'+encodeURIComponent(publicConfig.contact_email)+'?subject='+encodeURIComponent(subject)+'&body='+encodeURIComponent(body);
}
function setErrorPage(page){errorPage=page;lastErrorSignature='';showErrors(lastErrors)}
function imageUrl(url){let result=url;if(url.startsWith('/error-image')&&adminToken)result+=(result.includes('?')?'&':'?')+'admin='+encodeURIComponent(adminToken);return result+(result.includes('?')?'&':'?')+'t='+Date.now()}
function showPublicError(e){}
async function adminPost(path,errorId=''){return fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:adminToken,error_id:errorId})})}
async function captureAfter(errorId){let r=await adminPost('/capture-after',errorId);let d=await r.json();alert(d.message);if(r.ok)await poll(true)}
async function markResolved(errorId){if(!confirm('이 오류 기록과 연결된 스크린샷을 삭제할까요?'))return;let r=await adminPost('/mark-resolved',errorId);let d=await r.json();alert(d.message);if(r.ok)await poll(true)}
async function sendToAdmin(errorId){let r=await adminPost('/prepare-admin-report',errorId);let d=await r.json();if(!r.ok){alert(d.message);return}await copyText(d.text,'오류 보고와 스크린샷 경로를 함께 복사했습니다. Codex 대화에 붙여 넣으면 화면을 확인하여 수정할 수 있습니다.');if(d.screenshot)window.open(imageUrl(d.screenshot),'_blank')}
async function cleanupScreenshots(){let r=await adminPost('/cleanup-screenshots');let d=await r.json();alert(d.message);await poll(true)}
async function deleteScreenshots(){if(!confirm('저장된 스크린샷을 모두 삭제할까요? 삭제한 파일은 복구할 수 없습니다.'))return;let r=await adminPost('/delete-screenshots');let d=await r.json();alert(d.message);await poll(true)}
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function showErrors(items){lastErrors=items;let box=document.getElementById('errors');document.getElementById('errorCount').textContent=items.length+'건';const perPage=2,totalPages=Math.max(1,Math.ceil(items.length/perPage));errorPage=Math.max(1,Math.min(errorPage,totalPages));let signature=errorPage+'|'+items.map(e=>[e.id,e.reason,e.recovery,e.screenshot,e.after_screenshot].join(':')).join('|');if(signature===lastErrorSignature)return;lastErrorSignature=signature;let newest=[...items].reverse(),start=(errorPage-1)*perPage,pageItems=newest.slice(start,start+perPage);if(!items.length){box.innerHTML='<div class="empty">이번 실행에서 보고된 오류가 없습니다.</div>'}else{box.innerHTML=pageItems.map((e,index)=>{let id=esc(e.id||''),before=e.screenshot?imageUrl('/error-image?name='+encodeURIComponent(e.screenshot)):'',after=e.after_screenshot?imageUrl('/error-image?name='+encodeURIComponent(e.after_screenshot)):'';return `<article class="unified-error-item"><div class="error-head"><b>#${items.length-start-index} ${esc(e.kind||'오류')}</b><span>${esc(e.time||'-')}</span></div><div class="error-reason">${esc(e.reason||'-')}</div><div class="error-meta">퀘스트 ${esc(e.quest||'-')} · 오류 전 ${esc(e.before_state||'-')} · 복구 후 ${esc(e.after_state||'-')} · 재시작 ${esc(e.resume_quest||'-')}<br>자동 복구: ${esc(e.recovery||'-')} · 전체 ${esc(e.total||0)}회 · 연속 ${esc(e.consecutive||0)}회 · 완료 ${esc(e.completed||0)}개</div><div class="direction">수정 방향: ${esc(e.direction||'-')}</div><div class="error-preview"><div><label>오류 당시 화면</label>${before?`<img src="${before}" alt="오류 당시 화면" onclick="window.open('${before}','_blank')">`:'<div class="missing-shot">스크린샷 없음</div>'}</div><div><label>수정 후 확인 화면</label>${after?`<img src="${after}" alt="수정 후 화면" onclick="window.open('${after}','_blank')">`:'<div class="missing-shot">아직 저장되지 않음</div>'}</div></div><details class="error-log-context"><summary>직전 실행 기록 보기</summary><pre>${esc(e.log_context||'-')}</pre></details><div class="buttons error-actions"><button onclick="sendToAdmin('${id}')">스크린샷과 함께 수정 요청</button><button class="secondary" onclick="captureAfter('${id}')">수정 후 화면 저장</button><button class="stop" onclick="markResolved('${id}')">해결 완료·삭제</button></div></article>`}).join('')}let first=Math.max(1,Math.min(errorPage-2,totalPages-4)),last=Math.min(totalPages,first+4),buttons=[];for(let p=first;p<=last;p++)buttons.push(`<button class="secondary ${p===errorPage?'current':''}" onclick="setErrorPage(${p})">${p}</button>`);document.getElementById('errorPager').innerHTML=buttons.join('');document.getElementById('errorPageStatus').textContent=items.length?`현재 ${errorPage} / ${totalPages} 페이지 · 오류와 스크린샷을 2개씩 표시`:'현재 1 / 1 페이지';lastErrorCount=items.length}
async function poll(once=false){try{let u='/status'+(adminToken?'?admin='+encodeURIComponent(adminToken):'');let r=await fetch(u);let s=await r.json();isPaused=!!s.paused;setAdminView(!!s.admin);setChannelView(s.channel);if(adminToken&&!s.admin){adminToken='';sessionStorage.removeItem('cqaAdminToken')}document.getElementById('status').textContent=s.status;document.getElementById('statusBox').className=s.running||s.maintenance?'running':'';let dashboardStatus=s.status==='현재 퀘스트 자동 완료 실행 중'?'실행 중':s.status;document.getElementById('simpleRun').textContent=dashboardStatus+(s.public_activity?' · '+s.public_activity:'');document.getElementById('simpleErrors').textContent=String(s.error_count||0)+'건';document.getElementById('simpleCompleted').textContent=String(s.execution_count||0)+'개';updateRunControls(s.running||s.paused||s.maintenance);document.getElementById('nextAction').disabled=!s.can_skip;document.getElementById('stop').disabled=!s.running&&!s.paused;document.getElementById('executionCount').textContent=`(실행횟수:${String(s.execution_count||0).padStart(3,'0')})`;if(s.storage){document.getElementById('storagePath').textContent=s.storage.path;document.getElementById('storageCount').textContent=s.storage.count+'개';document.getElementById('storageSize').textContent=s.storage.mb+'MB 사용 중'}if(s.admin){renderDailySummary(s.daily_summary);showErrors(s.errors||[]);let p=document.getElementById('logs');p.textContent=s.logs||'아직 기록이 없습니다.';p.scrollTop=p.scrollHeight}}catch(e){}if(!once)setTimeout(poll,700)}init();
</script></body></html>'''


class LogWriter(io.TextIOBase):
    def write(self, text):
        if text:
            with LOCK:
                STATE["logs"].append(text)
                STATE["logs"] = STATE["logs"][-600:]
            for raw in text.splitlines():
                line = raw.strip()
                if not line:
                    continue
                if "복구 성공" in line:
                    summary_call("record_recovery", line)
                elif line.startswith(("성공:", "현재 퀘스트:", "판단:", "아레나 판단 처리:")):
                    summary_call("record_activity", line)
        return len(text)

    def flush(self):
        return None


def public_activity(chunks):
    """Return only one short action label for the general dashboard."""
    for raw in reversed("".join(chunks[-160:]).splitlines()):
        line = raw.strip()
        if not line:
            continue
        # Check waiting before generic "완료". Lines such as
        # "대기: monster 완료 표시" describe an active wait, not success.
        if "대기:" in line or "대기 중" in line or "기다리는 중" in line:
            return "대기"
        if "가방" in line:
            return "가방"
        if "장비 비교" in line or "장착/판매" in line:
            return "장비 비교"
        if "비교" in line:
            return "비교"
        if "클릭:" in line:
            return "클릭"
        if "성공:" in line or "완료" in line:
            return "성공"
        if "확인:" in line or "판별" in line:
            return "확인"
    return ""


def coord(value):
    parts = [int(v.strip()) for v in str(value).split(",")]
    if len(parts) != 2 or not (0 <= parts[0] < 1080 and 0 <= parts[1] < 1920):
        raise ValueError("좌표는 1080×1920 범위의 x,y 형식이어야 합니다.")
    return tuple(parts)


def validate(raw):
    data = DEFAULTS.copy(); data.update(raw)
    data["cycles"] = max(1, min(int(data["cycles"]), 100))
    data["infinite"] = bool(data["infinite"])
    data["automatic_check"] = bool(data["automatic_check"])
    data["adjust_screen_size"] = bool(data["adjust_screen_size"])
    data["restart_game_on_exit"] = bool(data.get("restart_game_on_exit", True))
    data["boss_keyboard_move_normal"] = raw.get("boss_keyboard_move_normal") is True
    data["boss_keyboard_move_corner"] = raw.get("boss_keyboard_move_corner") is True
    data["boss_keyboard_move"] = data["boss_keyboard_move_normal"] or data["boss_keyboard_move_corner"]
    data["screen_width"] = max(320, min(int(data["screen_width"]), 2160))
    data["screen_height"] = max(480, min(int(data["screen_height"]), 3840))
    data["dry_run"] = False
    for key in TASK_LABELS:
        data[key] = bool(data[key])
    data["arena_kind"] = str(data.get("arena_kind", "regular"))
    if data["arena_kind"] not in {"regular", "wagle"}:
        raise ValueError("아레나 종류를 확인해 주세요.")
    data["arena_decision_mode"] = str(data.get("arena_decision_mode", "compare"))
    if data["arena_decision_mode"] not in {"compare", "challenge"}:
        raise ValueError("아레나 실행 방식을 다시 선택해 주세요.")
    if data["task_arena_decision"] and any(data[key] for key in TASK_LABELS if key != "task_arena_decision"):
        raise ValueError("아레나 모드는 다른 작업과 함께 실행할 수 없습니다. 아레나 모드 시작 버튼을 사용하세요.")
    for count_key, maximum in TASK_COUNT_LIMITS.values():
        data[count_key] = max(1, min(int(data[count_key]), maximum))
    for kind in ("exp", "coin", "dough", "research_stone", "rune_crystal"):
        continuous_key = f"task_{kind}_dungeon_continuous"
        runs_key = f"task_{kind}_dungeon_runs"
        data[continuous_key] = bool(data.get(continuous_key)) and data[runs_key] >= 3
    for key in ("draw_timeout","equipment_timeout","monster_timeout","bag_timeout","stage_timeout"):
        data[key] = max(5, min(int(data[key]), 900))
    for key in ("boss_move_seconds", "boss_corner_move_seconds"):
        data[key] = max(0.5, min(float(data[key]), 15.0))
    checked_presets = {number for number in range(1, 6) if raw.get(f"boss_preset_{number}") is True}
    order = []
    for value in re.findall(r"[1-5]", str(data.get("boss_preset_order", ""))):
        number = int(value)
        if number in checked_presets and number not in order:
            order.append(number)
    order.extend(number for number in range(1, 6) if number in checked_presets and number not in order)
    for number in range(1, 6):
        data[f"boss_preset_{number}"] = number in checked_presets
    data["boss_preset_order"] = ",".join(map(str, order))
    for key in ("quest_panel","ten_draw","bottom_x","auto_button","auto_start","bag_item","item_use","equipment_action","boss_summon"):
        coord(data[key])
    return data


def settings():
    data = DEFAULTS.copy()
    if SETTINGS_FILE.exists():
        try:
            saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            data.update(saved)
            for key in ("boss_keyboard_move_normal", "boss_keyboard_move_corner"):
                data[key] = saved.get(key) is True
        except Exception: pass
    return data


LAYOUT_CARD_IDS = {
    "controlCard", "summaryCard", "settingsCard", "adminCard",
    "adminLogs", "adminScreenshots",
}


def validate_ui_layout(raw):
    """Keep saved free-form panel positions within reasonable browser limits."""
    source = raw.get("layout", raw) if isinstance(raw, dict) else {}
    cards = source.get("cards", {}) if isinstance(source, dict) else {}
    clean_cards = {}
    for card_id, values in cards.items():
        if card_id not in LAYOUT_CARD_IDS or not isinstance(values, dict):
            continue
        try:
            clean_cards[card_id] = {
                "x": max(0, min(float(values.get("x", 0)), 5000)),
                "y": max(0, min(float(values.get("y", 0)), 10000)),
                "w": max(240, min(float(values.get("w", 400)), 5000)),
                "h": max(100, min(float(values.get("h", 200)), 10000)),
            }
        except (TypeError, ValueError):
            continue
    height = max(300, min(float(source.get("canvasHeight", 900)), 20000))
    hidden = []
    for value in source.get("hiddenFeatures", []):
        value = str(value)
        if re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value) and value not in hidden:
            hidden.append(value)
    return {"canvasHeight": height, "cards": clean_cards, "hiddenFeatures": hidden[:100]}


def ui_layout():
    if UI_LAYOUT_FILE.exists():
        try:
            return validate_ui_layout(json.loads(UI_LAYOUT_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return {}


BOSS_CONTROL_FIELDS = (
    "boss_keyboard_move_normal", "boss_keyboard_move_corner", "boss_keyboard_move",
    "boss_move_seconds", "boss_corner_move_seconds", "boss_preset_order",
    *(f"boss_preset_{number}" for number in range(1, 6)),
)


def configure_boss_controls(data):
    with engine.BOSS_CONTROL_LOCK:
        before = (engine.BOSS_D_MOVE_ENABLED, engine.BOSS_AS_MOVE_ENABLED,
                  engine.BOSS_MOVE_SECONDS, engine.BOSS_CORNER_MOVE_SECONDS)
        engine.BOSS_MOVE_SECONDS = data["boss_move_seconds"]
        engine.BOSS_CORNER_MOVE_SECONDS = data["boss_corner_move_seconds"]
        engine.BOSS_PRESET_SEQUENCE = tuple(int(value) for value in data["boss_preset_order"].split(",") if value)
        engine.BOSS_D_MOVE_ENABLED = data["boss_keyboard_move_normal"] is True
        engine.BOSS_AS_MOVE_ENABLED = data["boss_keyboard_move_corner"] is True
        after = (engine.BOSS_D_MOVE_ENABLED, engine.BOSS_AS_MOVE_ENABLED,
                 engine.BOSS_MOVE_SECONDS, engine.BOSS_CORNER_MOVE_SECONDS)
        if before != after:
            engine.BOSS_MOVEMENT_REVISION += 1
    if STATE.get("last_data") is not None:
        STATE["last_data"].update({key: data[key] for key in BOSS_CONTROL_FIELDS})


def configure(data):
    engine.AUTO_RELAUNCH_GAME = data["restart_game_on_exit"] is True and data["task_quest"] is True
    engine.QUEST_PANEL=coord(data["quest_panel"]); engine.TEN_DRAW=coord(data["ten_draw"])
    engine.BOTTOM_X=coord(data["bottom_x"]); engine.AUTO_BUTTON=coord(data["auto_button"])
    engine.AUTO_START=coord(data["auto_start"]); engine.BAG_FIRST_ITEM=coord(data["bag_item"])
    engine.ITEM_MINUS=coord(data["item_minus"]); engine.ITEM_USE=coord(data["item_use"])
    engine.EQUIPMENT_ACTION=coord(data["equipment_action"])
    engine.BOSS_SUMMON_BUTTON=coord(data["boss_summon"])
    engine.TIMEOUT_DRAW=data["draw_timeout"]; engine.TIMEOUT_EQUIPMENT=data["equipment_timeout"]
    engine.TIMEOUT_MONSTER=data["monster_timeout"]; engine.TIMEOUT_BAG=data["bag_timeout"]
    engine.TIMEOUT_STAGE=data["stage_timeout"]
    configure_boss_controls(data)


def add_error_report(report):
    item = dict(report)
    no_game_actions = item.pop("_no_game_actions", False)
    captured_image = item.pop("_screenshot_image", None)
    item["time"] = time.strftime("%Y-%m-%d %H:%M:%S")
    item["id"] = secrets.token_hex(8)
    item["direction"] = error_direction(item)
    item["resolved"] = False
    try:
        if captured_image is None and no_game_actions:
            captured_image = engine._capture_screenshot()
        item["screenshot"] = capture_game_screenshot("error", captured_image)
    except Exception as error: item["screenshot"]=""; item["screenshot_error"]=str(error)
    with LOCK:
        item["log_context"] = "".join(STATE["logs"][-80:])
        STATE["errors"].append(item)
        STATE["errors"] = STATE["errors"][-100:]
    summary_call("record_error")


def error_index(error_id):
    """Resolve a UI-selected error, falling back to the latest for old clients."""
    if not STATE["errors"]:
        return None
    if error_id:
        for index, item in enumerate(STATE["errors"]):
            if secrets.compare_digest(str(item.get("id", "")), str(error_id)):
                return index
        return None
    return len(STATE["errors"]) - 1


def capture_game_screenshot(prefix, image=None):
    ERROR_SCREENSHOT_DIR.mkdir(exist_ok=True)
    name=f"{prefix}_{time.strftime('%Y%m%d_%H%M%S')}_{time.time_ns()%1000000:06d}.png"
    (image if image is not None else engine.screenshot()).save(ERROR_SCREENSHOT_DIR/name)
    cleanup_screenshots()
    return name


def screenshot_storage():
    files=sorted((p for p in ERROR_SCREENSHOT_DIR.glob("*.png") if p.is_file()),key=lambda p:p.stat().st_mtime,reverse=True) if ERROR_SCREENSHOT_DIR.exists() else []
    total=sum(path.stat().st_size for path in files if path.is_file())
    return {"path":str(ERROR_SCREENSHOT_DIR),"count":len(files),"bytes":total,"mb":round(total/1024/1024,1),"files":[{"name":p.name,"size":p.stat().st_size} for p in files]}


def cleanup_screenshots(delete_all=False):
    if not ERROR_SCREENSHOT_DIR.exists(): return 0
    files=sorted((p for p in ERROR_SCREENSHOT_DIR.glob("*.png") if p.is_file()),key=lambda p:p.stat().st_mtime)
    total=sum(p.stat().st_size for p in files)
    if not delete_all and total < SCREENSHOT_MAX_BYTES: return 0
    target=0 if delete_all else SCREENSHOT_TARGET_BYTES; removed=[]
    for path in files:
        if total <= target: break
        size=path.stat().st_size; path.unlink(); total-=size; removed.append(path.name)
    if removed:
        with LOCK:
            for item in STATE["errors"]:
                for key in ("screenshot","after_screenshot"):
                    if item.get(key) in removed: item[key]=""
    return len(removed)


def error_direction(item):
    state=item.get("before_state") or "unknown"; reason=str(item.get("reason", ""))
    if state=="auto_dialog" or "자동 열기" in reason: return "자동 열기 시작 버튼의 클릭 반응과 화면 전환을 확인하세요."
    if "equipment" in state or "장비" in reason: return "장비 비교 화면과 공통 클릭 좌표를 확인하세요."
    if state in ("gacha","draw_result") or "뽑기" in reason: return "뽑기 결과와 닫기 X 위치를 확인하세요."
    if state=="bag" or "가방" in reason: return "가방 첫 아이템과 보상 닫기 순서를 확인하세요."
    if state in ("battle","unknown") or "퀘스트" in reason: return "퀘스트 카드의 종류와 노란 완료 표시 판별을 확인하세요."
    return "오류 화면과 수정 후 화면을 비교해 화면 종류와 클릭 좌표를 확인하세요."


def update_execution_count(count):
    with LOCK:
        STATE["execution_count"] = count
    summary_call("record_completed", count)


def automatic_preflight():
    print("\n---------- 자동 시작 점검 ----------")
    try:
        image = engine.screenshot()
    except engine.GameRelaunched:
        print("  게임 재실행 후 자동 점검을 다시 시작합니다.")
        image = engine.screenshot()
    state = engine.screen_state(image)
    print(f"  시작 화면: {state}")
    if state != "battle":
        if not engine.recover_to_battle(timeout=40):
            raise engine.SafeStop("자동 점검에서 전투 화면으로 복귀하지 못했습니다.")
    last_error = None
    for attempt in range(1, 4):
        try:
            image, quest, confidence = engine.wait_detect_quest(timeout=15)
            break
        except engine.SafeStop as error:
            last_error = error
            if attempt < 3:
                print(f"  퀘스트 판별 재확인 ({attempt}/3): {error}")
                time.sleep(2)
    else:
        raise engine.SafeStop(f"자동 점검 3회 후에도 퀘스트를 판별하지 못했습니다: {last_error}")
    print(f"  현재 퀘스트: {quest} (신뢰도 {confidence:.2f})")
    print("  자동 점검 완료: 실제 실행으로 넘어갑니다.")
    print("------------------------------------\n")


def prepare_screen_size(data):
    size_output = engine.adb("shell", "wm", "size").stdout
    current_width, current_height = engine.configure_device_size(size_output)
    if not data["adjust_screen_size"]:
        engine.screenshot()
        print(
            f"BlueStacks 현재 화면 크기 유지: "
            f"{engine.DEVICE_WIDTH}x{engine.DEVICE_HEIGHT} · 좌표 자동 변환 사용"
        )
        return

    target_width = data["screen_width"]
    target_height = data["screen_height"]
    print(
        f"BlueStacks 화면 크기 점검: 현재 {current_width}x{current_height} "
        f"→ 선택 {target_width}x{target_height}"
    )
    # 시작할 때마다 강제로 다시 지정한다. 실제 크기가 같더라도 BlueStacks의
    # 이전 화면 설정이 풀려 있거나 게임 창에 늦게 반영되는 경우가 있기 때문이다.
    try:
        engine.adb("shell", "wm", "size", f"{target_width}x{target_height}")
    except Exception as error:
        raise engine.SafeStop(f"BlueStacks 화면 크기 강제 적용 명령이 실패했습니다: {error}") from error
    print("  선택한 화면 크기를 강제로 적용했습니다 · 실제 스크린샷 크기를 확인합니다.")

    deadline = time.monotonic() + 15
    last_size = (current_width, current_height)
    retried = False
    while time.monotonic() < deadline:
        engine.screenshot()
        last_size = (engine.DEVICE_WIDTH, engine.DEVICE_HEIGHT)
        if last_size == (target_width, target_height):
            print(f"  화면 크기 적용 확인: {target_width}x{target_height}")
            fit_bluestacks_window(target_width, target_height)
            return
        if not retried and time.monotonic() + 8 < deadline:
            retried = True
            print(
                f"  아직 실제 크기가 {last_size[0]}x{last_size[1]}입니다. "
                "화면 크기를 한 번 더 강제 적용합니다."
            )
            engine.adb("shell", "wm", "size", f"{target_width}x{target_height}")
        time.sleep(1)
    raise engine.SafeStop(
        f"선택한 화면 크기를 적용하지 못했습니다: "
        f"선택 {target_width}x{target_height}, 실제 {last_size[0]}x{last_size[1]}"
    )


def fit_bluestacks_window(target_width, target_height):
    """Find the visible BlueStacks window and fit it to the selected portrait size."""
    # BlueStacks Air is Retina-aware, so half of the Android pixel size is the
    # closest natural macOS window size. Large presets are capped to the desktop.
    desired_width = max(360, round(target_width / 2) + 23)
    desired_height = max(640, round(target_height / 2) + 17)
    if engine.IS_WINDOWS:
        return fit_bluestacks_window_windows(desired_width, desired_height)
    if not engine.IS_MACOS:
        return
    script = r'''
on run argv
    set requestedWidth to (item 1 of argv) as integer
    set requestedHeight to (item 2 of argv) as integer
    tell application "Finder"
        set desktopBounds to bounds of window of desktop
    end tell
    set availableHeight to (item 4 of desktopBounds) - 80
    if requestedHeight > availableHeight then
        set resizeRatio to availableHeight / requestedHeight
        set requestedWidth to round (requestedWidth * resizeRatio)
        set requestedHeight to availableHeight
    end if
    tell application "System Events"
        if not (exists process "BlueStacks") then return "not-found"
        tell process "BlueStacks"
            if (count of windows) is 0 then return "not-found"
            set gameWindow to front window
            set originalPosition to position of gameWindow
            set size of gameWindow to {requestedWidth, requestedHeight}
            set position of gameWindow to originalPosition
            return (requestedWidth as text) & "x" & (requestedHeight as text)
        end tell
    end tell
end run
'''
    try:
        result = subprocess.run(
            ["/usr/bin/osascript", "-e", script, str(desired_width), str(desired_height)],
            check=True,
            text=True,
            capture_output=True,
            timeout=10,
        ).stdout.strip()
        if result == "not-found":
            print("  BlueStacks 창을 찾지 못해 바깥 창 크기 조정은 건너뜁니다.")
        else:
            print(f"  BlueStacks 게임 창 인식 및 크기 조정 완료: {result}")
    except (subprocess.SubprocessError, OSError) as error:
        # Window fitting is helpful but must not stop an otherwise valid macro run.
        print(f"  BlueStacks 바깥 창 크기 조정은 건너뜁니다: {error}")


def fit_bluestacks_window_windows(desired_width, desired_height):
    """Resize the visible BlueStacks window without extra Windows packages."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        matches = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        @callback_type
        def collect(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title, length + 1)
            if "bluestacks" in title.value.lower():
                matches.append(hwnd)
                return False
            return True

        user32.EnumWindows(collect, 0)
        if not matches:
            print("  BlueStacks window was not found; outer-window resize was skipped.")
            return
        available_height = max(640, user32.GetSystemMetrics(1) - 80)
        if desired_height > available_height:
            ratio = available_height / desired_height
            desired_width, desired_height = round(desired_width * ratio), available_height
        rect = wintypes.RECT()
        user32.GetWindowRect(matches[0], ctypes.byref(rect))
        ok = user32.SetWindowPos(
            matches[0], 0, rect.left, rect.top, desired_width, desired_height,
            0x0004 | 0x0010,
        )
        if ok:
            print(f"  BlueStacks Windows window resize complete: {desired_width}x{desired_height}")
        else:
            print("  BlueStacks Windows outer-window resize was skipped.")
    except (AttributeError, OSError, ValueError) as error:
        print(f"  BlueStacks Windows outer-window resize was skipped: {error}")


def worker(data):
    writer = LogWriter()
    engine.ERROR_REPORTER = add_error_report
    engine.PROGRESS_REPORTER = update_execution_count
    configure_daily_summary_callbacks()
    try:
        with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
            print(f"\n실행 코드: {APP_VERSION} · build {BUILD_ID}")
            serial = engine.ensure_adb_connection()
            print(f"BlueStacks 연결 확인: {serial}")
            if data.get("task_arena_decision"):
                # Enter only the selected arena, then run its battle loop.
                engine.configure_device_size()
                with LOCK:
                    label = "전투력·트로피 비교" if data["arena_decision_mode"] == "compare" else "도전 우선"
                    STATE["status"] = f"아레나 모드 무한 실행 중 · {label}"
                    STATE["can_skip"] = False
                engine.enter_selected_arena(data["arena_kind"])
                engine.run_arena_decision_only(data["arena_decision_mode"], data["arena_kind"])
                return
            with LOCK: STATE["status"]="화면 크기 조정 중" if data["adjust_screen_size"] else "화면 크기 확인 중"
            prepare_screen_size(data)
            selected = [key for key in TASK_LABELS if data.get(key)]
            ready = [key for key in selected if key in IMPLEMENTED_TASKS]
            preparing = [key for key in selected if key not in IMPLEMENTED_TASKS]
            print("\n---------- 선택한 작업 ----------")
            if selected:
                for key in selected:
                    suffix = "실행 가능" if key in IMPLEMENTED_TASKS else "제작 중 - 이번 실행에서 건너뜀"
                    count_key = TASK_COUNT_LIMITS.get(key, (None, None))[0]
                    count_text = f" · 설정 {data[count_key]}회" if count_key else ""
                    print(f"  {'✓' if key in IMPLEMENTED_TASKS else '○'} {TASK_LABELS[key]}: {suffix}{count_text}")
            else:
                print("  선택한 작업이 없습니다.")
            print("  안전 제외: 상점·유료 패키지·결제·상점 내 무료 상품")
            print("---------------------------------\n")
            if not ready:
                with LOCK:
                    STATE["status"] = "선택 작업 없음" if not selected else "선택한 작업은 제작 중"
                return
            if data["automatic_check"]:
                with LOCK:
                    STATE["can_skip"] = True
                try:
                    automatic_preflight()
                except engine.SkipAction:
                    print("\n다음 행동 요청: 자동 점검을 건너뛰고 체크리스트 실행으로 이동합니다.\n")
                finally:
                    with LOCK:
                        STATE["can_skip"] = False
                    engine.SKIP_ACTION = False
            else:
                print("\n자동 점검을 건너뛰고 바로 실행합니다.\n")
            with LOCK: STATE["status"]="무한 반복 실행 중" if data["infinite"] else "실행 중"

            def run_action(task_key, callback, dungeon=False):
                with LOCK:
                    STATE["status"] = f"{TASK_LABELS[task_key]} 실행 중"
                    STATE["can_skip"] = True
                try:
                    relaunch_retries = 0
                    while True:
                        try:
                            callback()
                            break
                        except engine.GameRelaunched:
                            relaunch_retries += 1
                            if relaunch_retries > 3:
                                raise engine.SafeStop("게임 재실행이 3회 반복되어 안전하게 중단합니다.")
                            print("\n---------- 게임 재실행 복구 ----------")
                            print(f"  {TASK_LABELS[task_key]}을(를) 처음부터 다시 시작합니다. ({relaunch_retries}/3)")
                            print("----------------------------------------\n")
                            with LOCK:
                                STATE["status"] = f"{TASK_LABELS[task_key]} 재시작 중"
                            time.sleep(2)
                except engine.SkipAction:
                    print(f"\n---------- 다음 행동 이동 ----------")
                    print(f"  건너뛴 작업: {TASK_LABELS[task_key]}")
                    print("  현재 화면을 정리한 뒤 다음 체크 항목으로 이동합니다.")
                    with LOCK:
                        STATE["status"] = "첫 전투 화면 복귀 중"
                        STATE["can_skip"] = False
                    try:
                        if dungeon:
                            engine.return_to_main_battle()
                        else:
                            engine.recover_to_battle(timeout=50)
                    except engine.SafeStop as recovery_error:
                        if engine.STOP:
                            raise
                        print(f"  화면 자동 복귀 보류: {recovery_error}")
                    print("---------- 다음 체크 항목 준비 ----------\n")
                finally:
                    with LOCK:
                        STATE["can_skip"] = False
                    engine.SKIP_ACTION = False

            challenge_tasks = (
                ("task_crumble_dungeon", "crumble", "task_crumble_dungeon_runs"),
                ("task_arena", "arena", "task_arena_runs"),
                ("task_implant_tower", "implant", "task_implant_tower_runs"),
            )
            for task_key, kind, count_key in challenge_tasks:
                if data.get(task_key):
                    run_action(
                        task_key,
                        lambda kind=kind, count_key=count_key: engine.run_challenge_dungeon(
                            kind, data[count_key], data["dry_run"]
                        ),
                        dungeon=True,
                    )
            daily_tasks = (
                ("task_exp_dungeon", "exp", "task_exp_dungeon_runs", "task_exp_dungeon_continuous"),
                ("task_coin_dungeon", "coin", "task_coin_dungeon_runs", "task_coin_dungeon_continuous"),
                ("task_dough_dungeon", "dough", "task_dough_dungeon_runs", "task_dough_dungeon_continuous"),
                ("task_research_stone_dungeon", "research_stone", "task_research_stone_dungeon_runs", "task_research_stone_dungeon_continuous"),
                ("task_rune_crystal_dungeon", "rune_crystal", "task_rune_crystal_dungeon_runs", "task_rune_crystal_dungeon_continuous"),
            )
            selected_daily = [
                (task_key, kind, data[count_key], data[continuous_key])
                for task_key, kind, count_key, continuous_key in daily_tasks
                if data.get(task_key)
            ]
            if selected_daily:
                first_task_key = selected_daily[0][0]
                sequence = tuple(
                    (kind, runs, continuous)
                    for _, kind, runs, continuous in selected_daily
                )
                run_action(
                    first_task_key,
                    lambda sequence=sequence: engine.run_daily_dungeon_sequence(
                        sequence, data["dry_run"]
                    ),
                    dungeon=True,
                )
            if data.get("task_quest"):
                run_action(
                    "task_quest",
                    lambda: engine.run_dynamic(data["cycles"], data["dry_run"], data["infinite"]),
                )
        with LOCK:
            STATE["status"] = "실행 완료" if not preparing else "실행 완료 · 제작 중 항목 제외"
    except Exception as error:
        safety_report = None
        with LOCK:
            if engine.STOP:
                if STATE["pause_requested"]:
                    STATE["status"]="일시정지"
                    STATE["paused"]=True
                    STATE["logs"].append("\n사용자가 실행을 일시정지했습니다. 첫 전투 화면으로 돌아간 뒤 다시 시작하세요.\n")
                else:
                    STATE["status"]="사용자 정지"
                    STATE["paused"]=False
                    STATE["logs"].append("\n사용자가 실행을 정지했습니다.\n")
            else:
                STATE["status"]="안전 중단"
                STATE["logs"].append(f"\n안전 중단: {error}\n")
                safety_report={"kind":"안전 중단","reason":str(error),"total":1,"same":1,"consecutive":1,"unknown_consecutive":0,"completed":STATE["execution_count"],"quest":"-","before_state":"unknown","recovery":"실행 중단","after_state":"-","resume_quest":"-"}
        if safety_report:
            safety_report["_no_game_actions"] = bool(data.get("task_arena_decision"))
            add_error_report(safety_report)
    finally:
        with LOCK:
            STATE["running"]=False
            STATE["pause_requested"]=False
            STATE["can_skip"]=False


LIVE_HTML = LiveHTML(Path(__file__), HTML)


def status_payload(is_admin):
    with LOCK:
        for item in STATE["errors"]:
            if not item.get("id"):
                item["id"] = secrets.token_hex(8)
        latest = dict(STATE["errors"][-1]) if STATE["errors"] else None
        if latest:
            latest = {key: latest.get(key) for key in (
                "time", "reason", "quest", "before_state", "direction",
                "resolved", "screenshot", "after_screenshot",
            )}
            latest["location"] = latest.get("before_state") or latest.get("quest") or "unknown"
            if is_admin:
                if latest.get("screenshot"):
                    latest["screenshot"] = "/error-image?name=" + latest["screenshot"]
                if latest.get("after_screenshot"):
                    latest["after_screenshot"] = "/error-image?name=" + latest["after_screenshot"]
            else:
                latest["screenshot"] = ""
                latest["after_screenshot"] = ""
        payload = {
            "version": APP_VERSION, "build_id": BUILD_ID, "channel": channel_status(),
            "running": STATE["running"], "paused": STATE["paused"],
            "maintenance": STATE.get("maintenance", False), "can_skip": STATE["can_skip"],
            "status": STATE["status"], "public_activity": public_activity(STATE["logs"]),
            "logs": "".join(STATE["logs"][-300:]) if is_admin else "",
            "admin": is_admin, "errors": list(STATE["errors"]) if is_admin else [],
            "error_count": len(STATE["errors"]), "latest_error": latest,
            "storage": screenshot_storage() if is_admin else None,
            "execution_count": STATE["execution_count"],
        }
    if is_admin:
        summary = DAILY_SUMMARY.today()
        summary.update({
            "version": APP_VERSION,
            "status": payload["status"],
            "deployment": {
                "mac": "검증 완료",
                "windows": "실제 실행 검증 필요",
                "github": "저장소 연결 필요",
            },
        })
        payload["daily_summary"] = summary
    return payload


def update_status_payload():
    if not GITHUB_REPOSITORY:
        return {"status": "unconfigured", "update_available": False}
    api_url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"
    return release_update.check_latest_release(api_url, APP_VERSION, platform.system())


def public_config_payload():
    return {
        "support_account": PRIVATE_CONFIG.get("support_account", ""),
        "support_holder": PRIVATE_CONFIG.get("support_holder", ""),
        "contact_email": PRIVATE_CONFIG.get("contact_email", ""),
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def send_json(self, obj, status=200):
        body=json.dumps(obj,ensure_ascii=False).encode(); self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def read_json(self):
        return json.loads(self.rfile.read(int(self.headers.get("Content-Length","0"))) or b"{}")
    def require_admin(self, data):
        token=str(data.get("token",""))
        with LOCK: allowed=token in ADMIN_TOKENS
        if not allowed: self.send_json({"message":"관리자 로그인이 필요합니다."},403)
        return allowed
    def do_GET(self):
        parsed=urlparse(self.path); path=parsed.path
        if path=="/":
            html,revision=LIVE_HTML.read(); body=html.replace("__CQA_UI_REVISION__",revision).encode(); self.send_response(200); self.send_header("Cache-Control","no-store"); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
        elif path=="/settings": self.send_json(settings())
        elif path=="/ui-layout": self.send_json(ui_layout())
        elif path=="/coordinate-image":
            token=parse_qs(parsed.query).get("admin",[""])[0]
            with LOCK: allowed=token in ADMIN_TOKENS
            if not allowed: self.send_error(403); return
            try:
                image=engine._capture_screenshot()
                output=io.BytesIO(); image.save(output,format="PNG"); body=output.getvalue()
                self.send_response(200); self.send_header("Content-Type","image/png"); self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
            except Exception as exc:
                self.send_error(503,str(exc))
        elif path=="/error-image":
            token=parse_qs(parsed.query).get("admin",[""])[0]
            with LOCK: allowed=token in ADMIN_TOKENS
            if not allowed: self.send_error(403); return
            name=Path(parse_qs(parsed.query).get("name",[""])[0]).name; target=ERROR_SCREENSHOT_DIR/name
            if not name or not target.is_file(): self.send_error(404); return
            body=target.read_bytes(); self.send_response(200); self.send_header("Content-Type","image/png"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
        elif path=="/ui-revision":
            self.send_json({"revision": LIVE_HTML.read()[1]})
        elif path=="/update-status":
            self.send_json(update_status_payload())
        elif path=="/public-config":
            self.send_json(public_config_payload())
        elif path=="/status":
            token=parse_qs(parsed.query).get("admin",[""])[0]
            with LOCK:
                is_admin=token in ADMIN_TOKENS
            self.send_json(status_payload(is_admin))
        else: self.send_error(404)
    def do_POST(self):
        path=urlparse(self.path).path
        try:
            if path=="/admin-login":
                password=str(self.read_json().get("password",""))
                admin_password=PRIVATE_CONFIG.get("admin_password", "")
                if not admin_password or not secrets.compare_digest(password,admin_password):
                    self.send_json({"message":"관리자 비밀번호가 올바르지 않습니다."},403); return
                token=secrets.token_urlsafe(24)
                with LOCK: ADMIN_TOKENS.add(token)
                self.send_json({"message":"관리자 모드로 로그인했습니다.","token":token})
            elif path=="/admin-logout":
                token=str(self.read_json().get("token",""))
                with LOCK: ADMIN_TOKENS.discard(token)
                self.send_json({"message":"관리자 모드에서 로그아웃했습니다."})
            elif path in ("/settings", "/boss-controls"):
                request = self.read_json()
                with LOCK:
                    if path == "/boss-controls":
                        raw = settings()
                        raw.update({key: value for key, value in request.items() if key in BOSS_CONTROL_FIELDS})
                    else:
                        raw = request
                    data = validate(raw)
                    # Apply unchecked actions immediately, even if saving fails.
                    configure_boss_controls(data)
                    SETTINGS_FILE.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
                self.send_json({"message":"설정을 저장했습니다. 보스 체크 변경은 실행 중에도 반영됩니다."})
            elif path=="/ui-layout":
                request=self.read_json()
                if not self.require_admin(request): return
                layout=validate_ui_layout(request)
                UI_LAYOUT_FILE.write_text(json.dumps(layout,ensure_ascii=False,indent=2),encoding="utf-8")
                self.send_json({"message":"화면 위치·크기와 숨긴 기능을 저장했습니다.","layout":layout})
            elif path=="/reset-ui-layout":
                request=self.read_json()
                if not self.require_admin(request): return
                if UI_LAYOUT_FILE.exists(): UI_LAYOUT_FILE.unlink()
                self.send_json({"message":"기본 화면 배치와 모든 기능을 복원했습니다."})
            elif path=="/capture-after":
                request=self.read_json()
                if not self.require_admin(request): return
                with LOCK:
                    index=error_index(str(request.get("error_id", "")))
                    if index is None: self.send_json({"message":"저장할 오류를 찾지 못했습니다."},404); return
                name=capture_game_screenshot("after")
                with LOCK:
                    index=error_index(str(request.get("error_id", "")))
                    if index is None: self.send_json({"message":"스크린샷 저장 중 오류 기록이 사라졌습니다."},409); return
                    STATE["errors"][index]["after_screenshot"]=name
                self.send_json({"message":"수정 후 현재 게임 화면을 저장했습니다."})
            elif path=="/mark-resolved":
                request=self.read_json()
                if not self.require_admin(request): return
                with LOCK:
                    index=error_index(str(request.get("error_id", "")))
                    if index is None: self.send_json({"message":"완료 처리할 오류를 찾지 못했습니다."},404); return
                    item=STATE["errors"].pop(index)
                removed=0
                for key in ("screenshot","after_screenshot"):
                    name=Path(str(item.get(key,""))).name
                    target=ERROR_SCREENSHOT_DIR/name if name else None
                    if target and target.is_file():
                        target.unlink(); removed+=1
                self.send_json({"message":f"해결된 오류 기록과 연결된 스크린샷 {removed}개를 삭제했습니다."})
            elif path=="/prepare-admin-report":
                request=self.read_json()
                if not self.require_admin(request): return
                with LOCK:
                    index=error_index(str(request.get("error_id", "")))
                    if index is None: self.send_json({"message":"전달할 오류를 찾지 못했습니다."},404); return
                    item=dict(STATE["errors"][index])
                screenshot_name=Path(str(item.get("screenshot", ""))).name
                screenshot_path=ERROR_SCREENSHOT_DIR/screenshot_name if screenshot_name else None
                after_name=Path(str(item.get("after_screenshot", ""))).name
                after_path=ERROR_SCREENSHOT_DIR/after_name if after_name else None
                lines=[
                    "쿠키런: 크럼블 퀘스트 도우미 오류 확인 및 수정 요청",
                    f"발생 시각: {item.get('time','-')}",
                    f"오류 종류: {item.get('kind','-')}",
                    f"오류 원인: {item.get('reason','-')}",
                    f"현재 퀘스트: {item.get('quest','-')}",
                    f"오류 화면 판별: {item.get('before_state','-')}",
                    f"자동 복구: {item.get('recovery','-')}",
                    f"복구 후 화면: {item.get('after_state','-')}",
                    f"재시작 퀘스트: {item.get('resume_quest','-')}",
                    f"제안된 방향: {item.get('direction','-')}",
                    f"오류 스크린샷: {screenshot_path if screenshot_path and screenshot_path.is_file() else '저장되지 않음'}",
                    f"수정 후 스크린샷: {after_path if after_path and after_path.is_file() else '아직 없음'}",
                    f"직전 실행 기록:\n{item.get('log_context','-')}",
                    "요청: 위 스크린샷을 직접 확인하고 원인을 판단해 프로그램을 수정해줘. 추가 승인이 필요한 변경은 먼저 질문해줘.",
                ]
                image_url="/error-image?name="+screenshot_name if screenshot_path and screenshot_path.is_file() else ""
                self.send_json({"message":"전달 내용을 준비했습니다.","text":"\n".join(lines),"screenshot":image_url})
            elif path=="/cleanup-screenshots":
                request=self.read_json()
                if not self.require_admin(request): return
                removed=cleanup_screenshots()
                self.send_json({"message":f"오래된 스크린샷 {removed}개를 정리했습니다." if removed else "현재 200MB 미만이어서 정리할 파일이 없습니다."})
            elif path=="/delete-screenshots":
                request=self.read_json()
                if not self.require_admin(request): return
                removed=cleanup_screenshots(delete_all=True)
                self.send_json({"message":f"저장된 스크린샷 {removed}개를 모두 삭제했습니다."})
            elif path=="/cleanup-memory":
                with LOCK:
                    if STATE["running"] or STATE["paused"] or STATE.get("maintenance",False):
                        self.send_json({"message":"매크로 실행 또는 다른 정리 작업 중에는 메모리를 정리할 수 없습니다."},409); return
                    STATE["maintenance"]=True
                    STATE["status"]="BlueStacks 메모리 정리 중"
                try:
                    before,after=engine.trim_bluestacks_memory()
                finally:
                    with LOCK:
                        STATE["maintenance"]=False
                        if not STATE["running"] and not STATE["paused"]:
                            STATE["status"]="대기 중"
                if before is not None and after is not None:
                    released=max(0.0,before-after)
                    message=f"BlueStacks 메모리 정리 완료 · 쿠키런 {before:.0f}MB → {after:.0f}MB"
                    if released >= 1:
                        message+=f" · 약 {released:.0f}MB 감소"
                else:
                    message="BlueStacks 메모리 정리 신호를 보냈습니다."
                self.send_json({"message":message,"before_mb":before,"after_mb":after})
            elif path in ("/start", "/start-group"):
                request=self.read_json()
                if path == "/start-group":
                    saved_data=prepare_group_run(request)
                    run_scope=request["scope"]
                else:
                    run_scope=str(request.pop("_run_scope", "")).strip()
                    saved_data=validate(request)
                data=apply_run_scope(apply_channel_policy(saved_data), run_scope)
                with LOCK:
                    if STATE["running"] or STATE["paused"] or STATE.get("maintenance",False):
                        self.send_json({"message":"기존 작업 또는 메모리 정리가 끝난 뒤 시작해 주세요."},409); return
                    SETTINGS_FILE.write_text(json.dumps(saved_data,ensure_ascii=False,indent=2),encoding="utf-8")
                    configure(data); engine.STOP=False; engine.SKIP_ACTION=False; engine.FAST_SCREENSHOT_AVAILABLE=None; STATE.update(running=True,paused=False,pause_requested=False,can_skip=False,last_data=data,status="화면 크기 조정 준비 중" if data["adjust_screen_size"] else ("자동 점검 중" if data["automatic_check"] else "실행 준비 중"),logs=["--- 새 실행 ---\n"],errors=[],execution_count=0)
                    record_run_start(data)
                    STATE["worker"]=threading.Thread(target=worker,args=(data,),daemon=True); STATE["worker"].start()
                self.send_json({"message":"시작했습니다."})
            elif path=="/next-action":
                with LOCK:
                    if not STATE["running"] or not STATE["can_skip"]:
                        self.send_json({"message":"현재 실행 중인 행동이 없습니다."},409); return
                    engine.SKIP_ACTION=True
                    STATE["status"]="다음 행동 이동 요청 중"
                self.send_json({"message":"현재 행동을 정리한 뒤 다음 체크 항목으로 이동합니다."})
            elif path=="/pause":
                with LOCK:
                    if not STATE["running"]: self.send_json({"message":"실행 중이 아닙니다."},409); return
                    STATE["pause_requested"]=True
                    STATE["can_skip"]=False
                    STATE["status"]="일시정지 요청 중"
                    engine.SKIP_ACTION=False
                    engine.STOP=True
                self.send_json({"message":"안전한 지점에서 일시정지합니다."})
            elif path=="/resume":
                with LOCK:
                    if STATE["running"] or STATE.get("maintenance",False): self.send_json({"message":"아직 정지 또는 메모리 정리 처리 중입니다."},409); return
                    if not STATE["paused"] or not STATE["last_data"]: self.send_json({"message":"다시 시작할 일시정지 작업이 없습니다."},409); return
                    data=dict(STATE["last_data"])
                    configure(data); engine.STOP=False; engine.SKIP_ACTION=False; engine.FAST_SCREENSHOT_AVAILABLE=None
                    STATE.update(running=True,paused=False,pause_requested=False,can_skip=False,status="첫 화면에서 다시 시작 준비 중")
                    STATE["logs"].append("\n---------- 일시정지 해제: 첫 전투 화면부터 재판별 ----------\n")
                    STATE["worker"]=threading.Thread(target=worker,args=(data,),daemon=True); STATE["worker"].start()
                self.send_json({"message":"첫 전투 화면부터 다시 시작합니다."})
            elif path=="/stop":
                engine.SKIP_ACTION=False
                engine.STOP=True
                with LOCK:
                    STATE["pause_requested"]=False
                    STATE["paused"]=False
                    STATE["can_skip"]=False
                    STATE["status"]="정지 요청 중" if STATE["running"] else "사용자 정지"
                    if not STATE["running"]: STATE["logs"].append("\n일시정지된 작업을 종료했습니다.\n")
                self.send_json({"message":"정지를 요청했습니다."})
            elif path=="/shutdown":
                engine.SKIP_ACTION=False
                engine.STOP=True
                with LOCK:
                    STATE["pause_requested"]=False; STATE["paused"]=False; STATE["can_skip"]=False; STATE["status"]="프로그램 종료 중"
                self.send_json({"message":"프로그램을 종료합니다."})
                threading.Timer(0.8, self.server.shutdown).start()
            else: self.send_error(404)
        except Exception as error: self.send_json({"message":str(error)},400)


def create_server(host=HOST, port=PORT):
    return ThreadingHTTPServer((host, port), Handler)


def serve(open_browser=True):
    url=f"http://{HOST}:{PORT}/"
    try:
        server=create_server()
    except OSError as error:
        if open_browser and getattr(error, "errno", None) in (48, 98, 10048):
            webbrowser.open(url)
            return
        raise
    print(f"제어 화면: {url}")
    if open_browser:
        threading.Timer(0.5,lambda:webbrowser.open(url)).start()
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        engine.SKIP_ACTION=False; engine.STOP=True
        server.server_close()


def main():
    serve(open_browser=True)


if __name__ == "__main__":
    main()
