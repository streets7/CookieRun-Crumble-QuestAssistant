# Alert-Driven Integrated Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run safe auxiliary game tasks automatically when the same stage quest has stalled for 180 seconds, using alert-driven entry plus once-daily checks for daily dungeons, Crumble Dungeon, Arena, and Implant Tower.

**Architecture:** Add a small persistent scheduler that owns daily state, cooldowns, candidate ordering, and the 180-second stall gate. Keep screen recognition and game actions in `quest_assistant.py`, and let `web_ui.py` connect the scheduler to the existing infinite quest loop and administrator status. All game taps pass through explicit screen-specific allowlists; unknown or paid states skip the current task and recover to battle.

**Tech Stack:** Python 3.9, Pillow image analysis, existing OCR helper, unittest, existing HTML/JavaScript admin UI

**Spec:** `docs/superpowers/specs/2026-11-12-alert-driven-integrated-automation-design.md`

## Global Constraints

- Stall threshold is exactly 180 seconds for the same stage quest.
- Target reference device is `emulator-5554` at 1080×1920; all taps use existing coordinate scaling.
- Dungeon icon red alerts never create candidates.
- Daily dungeons, Crumble Dungeon, Arena, and Implant Tower are checked at most once per local calendar day even without alerts.
- Cookie, pet, and guild candidates require their own red alert and run at most once per day.
- Cookie current-team upgrade and fame run at most one level; breakthrough runs attack, health, then defense at most one level each.
- Ad entry is allowed only when an ad-pass ownership/applied indicator is positively recognized; actual ad playback is never started.
- Store, draws, Codex, Gnome Lab, Stella Link, guild research donations, and crystal-cost Arena actions are forbidden.
- Unknown or unrecorded screen states never produce taps.
- macOS and Windows use the same JSON schema and automation behavior.

## Review Focus

- A quest changes or completes at 179–180 seconds: reset the stall timer and do not run duplicate maintenance.
- A persistent dungeon red dot caused by Arena: never treat it as a dungeon candidate.
- OCR cannot read currency, cost, free count, or ad-pass state: skip without tapping and record the reason.
- The game closes during a maintenance task: relaunch, recover to battle, and recompute candidates instead of resuming a stale action.
- The local date changes while the app is running: reset daily fields once while retaining permanent Implant 850 completion.

---

### Task 1: Persistent Integrated-Automation State

**Files:**
- Create: `CookieRunQuestAssistant/integrated_automation.py`
- Create: `CookieRunQuestAssistant/test_integrated_automation_state.py`
- Modify: `CookieRunQuestAssistant/web_ui.py`

**Interfaces:**
- Produces: `IntegratedAutomationStore(path: Path, now: Callable[[], datetime])`
- Produces: `today() -> dict`, `mark_checked(task, result, next_check_at=None) -> dict`, `mark_failure(task, reason) -> dict`, `set_implant_850_complete(value=True) -> dict`
- Produces: schema fields `date`, `tasks`, `arena_free_at`, `implant_850_complete`, `stall`

- [ ] **Step 1: Write failing persistence and date-rollover tests**

Test atomic JSON creation, corrupt-file recovery, three-failure daily disable, local-date reset, and retention of `implant_850_complete` across dates.

- [ ] **Step 2: Run the focused test and verify it fails because the module is missing**

Run: `python3 -m unittest CookieRunQuestAssistant/test_integrated_automation_state.py -v`

- [ ] **Step 3: Implement the minimal thread-safe JSON store**

Use temporary-file replacement and bounded strings/lists, following `daily_summary.py` patterns. Add `INTEGRATED_AUTOMATION_FILE = DATA_DIR / "integrated_automation.json"` in `web_ui.py`.

- [ ] **Step 4: Run focused and existing persistence tests**

Run: `python3 -m unittest CookieRunQuestAssistant/test_integrated_automation_state.py CookieRunQuestAssistant/test_daily_summary.py -v`

- [ ] **Step 5: Commit**

Commit message: `feat: persist integrated automation state`

### Task 2: Stall Gate and Candidate Scheduler

**Files:**
- Modify: `CookieRunQuestAssistant/integrated_automation.py`
- Create: `CookieRunQuestAssistant/test_integrated_scheduler.py`
- Modify: `CookieRunQuestAssistant/quest_assistant.py`

**Interfaces:**
- Produces: `StallTracker.observe(quest: str, screen: str, progress_key: str, at: float) -> bool`
- Produces: `build_candidates(day: dict, alerts: dict[str, bool], completed: set[str]) -> list[str]`
- Produces: `MAINTENANCE_ORDER = ("daily", "crumble", "arena", "implant", "guild", "cookie", "pet", "breakthrough", "fame")`
- Consumes: daily state from Task 1

- [ ] **Step 1: Write failing tests for 179/180 seconds, quest changes, progress changes, and candidate ordering**

Assert dungeon alert input is ignored, four daily exceptions appear once, cookie/pet/guild require alerts, and completed/disabled items do not reappear.

- [ ] **Step 2: Run the scheduler tests and verify expected failures**

Run: `python3 -m unittest CookieRunQuestAssistant/test_integrated_scheduler.py -v`

- [ ] **Step 3: Implement pure stall and candidate logic**

Use monotonic timestamps for elapsed time and date-store state only for persistence. Add a progress callback hook to `run_dynamic` without performing any maintenance action yet.

- [ ] **Step 4: Run scheduler and quest regression tests**

Run: `python3 -m unittest CookieRunQuestAssistant/test_integrated_scheduler.py CookieRunQuestAssistant/test_quest_speed.py CookieRunQuestAssistant/test_recovery_reporting.py -v`

- [ ] **Step 5: Commit**

Commit message: `feat: detect stalled stage maintenance window`

### Task 3: Safe Live-Screen Survey and Fixture Catalog

**Files:**
- Create: `CookieRunQuestAssistant/tests/fixtures/integrated/README.md`
- Create: `CookieRunQuestAssistant/test_integrated_screen_catalog.py`
- Add: confirmed screenshots under `CookieRunQuestAssistant/tests/fixtures/integrated/`
- Modify: `CookieRunQuestAssistant/quest_assistant.py`

**Interfaces:**
- Produces: `integrated_alerts(image: Image.Image) -> dict[str, bool]`
- Produces: screen predicates for cookie, pet shelter, breakthrough, fame, guild help, guild lab, guild support, ad-pass, and paid-state guards
- Produces: `allowed_integrated_action(screen: str, action: str, image: Image.Image) -> bool`

- [ ] **Step 1: Navigate the live `emulator-5554` UI in observation-only mode**

Capture menu entry, inactive buttons, active buttons if naturally present, cost areas, ad-pass indicator, and return controls. Do not tap reward, upgrade, donation, battle-start, or paid controls. Record missing states in `README.md` as unsupported and therefore no-tap.

- [ ] **Step 2: Write failing fixture tests before adding predicates**

Each fixture must assert its expected screen and allowed/forbidden actions. Add explicit negative tests proving the dungeon red dot does not create a candidate and paid/unknown fixtures have no allowed action.

- [ ] **Step 3: Run the catalog tests and verify recognition failures**

Run: `python3 -m unittest CookieRunQuestAssistant/test_integrated_screen_catalog.py -v`

- [ ] **Step 4: Implement minimal multi-signal predicates**

Require a screen identity signal plus button text/color and cost/pass-region state. Use OCR only when a wrong read results in skipping, never spending.

- [ ] **Step 5: Run fixture tests and inspect every fixture visually**

Run: `python3 -m unittest CookieRunQuestAssistant/test_integrated_screen_catalog.py -v`

- [ ] **Step 6: Commit**

Commit message: `feat: recognize integrated automation screens safely`

### Task 4: Daily and Challenge Exception Runners

**Files:**
- Modify: `CookieRunQuestAssistant/quest_assistant.py`
- Modify: `CookieRunQuestAssistant/integrated_automation.py`
- Create: `CookieRunQuestAssistant/test_integrated_dungeons.py`

**Interfaces:**
- Produces: `run_integrated_daily_dungeons(state) -> dict[str, int]`
- Produces: `run_integrated_crumble(state) -> int`
- Produces: `run_integrated_arena(state) -> dict`
- Produces: `run_integrated_implant(state) -> str`
- Consumes: existing dungeon entry, execution, result, and battle-return functions

- [ ] **Step 1: Write failing tests for remaining counts and no-paid behavior**

Cover Crumble capped at four daily clears, Arena free refresh then crystal stop/cooldown record, Implant 850 completion retention and first-failure daily stop, and five daily dungeons advancing after failure/reward collection.

- [ ] **Step 2: Write failing ad-pass tests**

Assert key entries run normally, ad-pass entry runs only on positive pass recognition, and missing/ambiguous pass state never taps `DAILY_START`.

- [ ] **Step 3: Run focused tests and verify failures**

Run: `python3 -m unittest CookieRunQuestAssistant/test_integrated_dungeons.py -v`

- [ ] **Step 4: Implement adapters around existing runners**

Do not change standalone manual behavior. Integrated mode supplies remaining counts, ad-pass policy, failure continuation, daily state updates, and mandatory battle recovery.

- [ ] **Step 5: Run all dungeon and Arena suites**

Run: `python3 -m unittest CookieRunQuestAssistant/test_integrated_dungeons.py CookieRunQuestAssistant/test_wagle_arena.py CookieRunQuestAssistant/test_arena_decision.py CookieRunQuestAssistant/test_daily_summary_integration.py -v`

- [ ] **Step 6: Commit**

Commit message: `feat: run daily dungeon exceptions safely`

### Task 5: Alert-Driven Cookie, Pet, Guild, and Growth Actions

**Files:**
- Modify: `CookieRunQuestAssistant/quest_assistant.py`
- Create: `CookieRunQuestAssistant/test_integrated_alert_actions.py`

**Interfaces:**
- Produces: `run_cookie_maintenance() -> str`
- Produces: `run_pet_shelter_collection() -> str`
- Produces: `run_guild_maintenance() -> dict[str, str]`
- Produces: `run_breakthrough_once() -> dict[str, bool]`
- Produces: `run_fame_once() -> bool`
- Consumes: predicates and allowlist from Task 3

- [ ] **Step 1: Write failing tests for alert gating and once-daily limits**

Assert no menu entry without alert; current team only; pet collect-all only; guild help/research-support/support-claim allowed; research donation always forbidden.

- [ ] **Step 2: Write failing resource safety tests**

Assert attack→health→defense one level each, fame one level, `owned >= cost`, OCR failure skips, and no coordinate outside the per-screen allowlist reaches `tap`.

- [ ] **Step 3: Run focused tests and verify failures**

Run: `python3 -m unittest CookieRunQuestAssistant/test_integrated_alert_actions.py -v`

- [ ] **Step 4: Implement one-action-at-a-time runners**

After every tap, reacquire the screen and reevaluate the allowlist. Recover to battle after each top-level task.

- [ ] **Step 5: Run focused tests plus game relaunch/recovery suites**

Run: `python3 -m unittest CookieRunQuestAssistant/test_integrated_alert_actions.py CookieRunQuestAssistant/test_game_relaunch.py CookieRunQuestAssistant/test_recovery_reporting.py -v`

- [ ] **Step 6: Commit**

Commit message: `feat: automate safe alert-driven maintenance`

### Task 6: Orchestrator Integration With Infinite Quest Mode

**Files:**
- Modify: `CookieRunQuestAssistant/integrated_automation.py`
- Modify: `CookieRunQuestAssistant/quest_assistant.py`
- Modify: `CookieRunQuestAssistant/web_ui.py`
- Create: `CookieRunQuestAssistant/test_integrated_orchestrator.py`

**Interfaces:**
- Produces: `run_integrated_maintenance(store, alerts_provider, runners) -> dict`
- Produces: quest-loop hook `INTEGRATED_MAINTENANCE_REPORTER`
- Consumes: Tasks 1–5 state, scheduler, detectors, and runners

- [ ] **Step 1: Write failing end-to-end orchestration tests**

Cover 180-second trigger, ordered candidates, per-task exception isolation, three-failure daily disable, relaunch recomputation, user stop, battle recovery, and return to fresh quest detection.

- [ ] **Step 2: Run focused tests and verify failures**

Run: `python3 -m unittest CookieRunQuestAssistant/test_integrated_orchestrator.py -v`

- [ ] **Step 3: Implement orchestration and wire it into infinite quest mode only**

Manual finite quest runs remain unchanged. The hook executes only when `integrated_automation` is enabled and reports status/activity to the existing UI state and daily summary.

- [ ] **Step 4: Run focused tests and the entire Python suite**

Run: `PYTHONPYCACHEPREFIX=/tmp/cqa-pycache python3 -m unittest discover -s CookieRunQuestAssistant -p 'test_*.py' -q`

- [ ] **Step 5: Commit**

Commit message: `feat: orchestrate maintenance during stalled stages`

### Task 7: User and Administrator Controls

**Files:**
- Modify: `CookieRunQuestAssistant/web_ui.py`
- Create: `CookieRunQuestAssistant/test_integrated_automation_ui.cjs`
- Modify: `CookieRunQuestAssistant/test_ui_live.py`

**Interfaces:**
- Produces settings: `integrated_automation: bool`, `integrated_stall_seconds: 180`
- Produces administrator payload: task status, last checked, next check, skip reason, daily failure count

- [ ] **Step 1: Write failing UI rendering and settings tests**

Assert a simple `통합 자동 순환` control, fixed `스테이지 정체 3분` copy, persisted checkbox, and administrator per-task status without exposing it publicly.

- [ ] **Step 2: Run UI tests and verify failures**

Run: `node CookieRunQuestAssistant/test_integrated_automation_ui.cjs`

- [ ] **Step 3: Implement the minimal controls and administrator status panel**

Keep existing individual task controls. Default the integrated option to off for existing installations until the user enables it.

- [ ] **Step 4: Run all UI and validation tests**

Run: `for test_file in CookieRunQuestAssistant/test_*_ui.cjs; do node "$test_file"; done`

- [ ] **Step 5: Commit**

Commit message: `feat: add integrated automation controls`

### Task 8: Full Verification, Version, Packaging, and Live Dry Run

**Files:**
- Modify: `CookieRunQuestAssistant/RELEASE_NOTES.md`
- Modify: version declarations in `CookieRunQuestAssistant/web_ui.py`, `CookieRunQuestAssistant/packaging/build_macos.command`, `CookieRunQuestAssistant/packaging/build_windows.bat`, and `CookieRunQuestAssistant/packaging/windows_installer.iss`
- Modify: `CookieRunQuestAssistant/test_packaging_contract.py`

**Interfaces:**
- Consumes: all preceding tasks

- [ ] **Step 1: Write failing release-contract tests for the next stable version**

Assert macOS and Windows packaging agree on the same stable version and include the new module and assets.

- [ ] **Step 2: Bump the stable version and add release notes**

Do not create a beta version. Document the 3-minute alert-driven cycle, four daily exceptions, ad-pass gate, and prohibited paid actions.

- [ ] **Step 3: Run every automated test**

Run Python discovery, all Node UI suites, inline JavaScript syntax validation, packaging contracts, and app self-test.

- [ ] **Step 4: Perform a live observation/dry run on `emulator-5554`**

First run with all action taps disabled and verify candidate decisions. Then enable only screen states backed by fixtures. Do not force alerts, spend currency, start ads, donate, or enter the store.

- [ ] **Step 5: Build and verify macOS artifacts**

Run the macOS build, codesign verification, DMG verification, and SHA-256 generation. Leave Windows source ready for GitHub Actions/real Windows verification.

- [ ] **Step 6: Commit and push after review**

Commit message: `release: integrated alert-driven automation`
