# 관리자 오늘의 총정리 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 관리자에게 오늘의 실행·완료·오류·복구·아레나 판단을 재시작 후에도 유지되는 한 개의 팝업으로 제공한다.

**Architecture:** 날짜별 구조화 기록은 새 `daily_summary.py`가 읽기·정리·원자적 저장을 담당한다. `web_ui.py`는 기존 실행 이벤트를 기록하고 인증된 상태 응답으로 오늘 자료를 제공하며, 기존 관리자 팝업 틀로 렌더링한다. 아레나 엔진은 덱 판단을 구조화해 전달하고 실패 시 1번 주덱을 복원한다.

**Tech Stack:** Python 3 표준 라이브러리, 기존 HTTP 서버, HTML/CSS/JavaScript, `unittest`, Node VM UI 검사

**Spec:** `docs/superpowers/specs/2026-11-11-daily-admin-summary-design.md`

## Global Constraints

- 기록은 사용자 데이터 폴더의 `daily_summary.json`에 저장하고 최근 31일만 유지한다.
- 관리자 인증 응답에만 총정리를 포함한다.
- 비밀번호, 계좌 정보, 전체 오류 로그 및 스크린샷 내용은 기록하지 않는다.
- 베타를 만들지 않고 정식 버전을 올린다.
- 현재 저장소에 커밋 이력이 없으므로 이 계획에서는 Git 커밋을 만들지 않는다.

## Review Focus

- 손상되거나 비어 있는 JSON 파일은 실행을 막지 않고 오늘의 빈 기록으로 복구돼야 한다.
- 날짜 변경 직전 실행이 다음 날짜 기록과 섞이지 않아야 한다.
- 완료 진행 값이 새 실행에서 0으로 돌아갈 때 음수 또는 중복 누적이 없어야 한다.
- 관리자 토큰이 없거나 만료된 응답에는 `daily_summary`가 없어야 한다.
- 총정리 팝업이 열린 상태에서 상태 갱신과 로그 특수문자가 화면 구조를 깨뜨리지 않아야 한다.

---

### Task 1: 날짜별 기록 저장소

**Files:**
- Create: `CookieRunQuestAssistant/daily_summary.py`
- Create: `CookieRunQuestAssistant/test_daily_summary.py`

**Interfaces:**
- Produces: `DailySummaryStore(path: Path, keep_days: int = 31, now: Callable = datetime.now)`
- Produces: `record_start(task_labels: list[str])`, `record_completed(total: int)`, `record_error()`, `record_recovery(text: str)`, `record_activity(text: str)`, `record_arena_decision(data: dict)`, `today() -> dict`

- [ ] Write failing tests for defaults, persistence, 31-day cleanup, corrupt-file recovery, completion deltas and bounded recent lists.
- [ ] Run `python3 -m unittest test_daily_summary -q` and verify the missing module/API failures.
- [ ] Implement locking, schema normalization and temp-file replacement in `daily_summary.py`.
- [ ] Run `python3 -m unittest test_daily_summary -q` and verify PASS.

### Task 2: 실행 이벤트와 아레나 판단 연결

**Files:**
- Modify: `CookieRunQuestAssistant/web_ui.py`
- Modify: `CookieRunQuestAssistant/quest_assistant.py`
- Modify: `CookieRunQuestAssistant/test_arena_decks.py`
- Create: `CookieRunQuestAssistant/test_daily_summary_integration.py`

**Interfaces:**
- Consumes: Task 1 `DailySummaryStore`
- Produces: `engine.ARENA_DECISION_REPORTER: Callable[[dict], None] | None`

- [ ] Write failing tests that start requests record task labels, completion/error/recovery events accumulate, and no eligible arena deck restores deck 1.
- [ ] Run the focused tests and verify failures describe the missing event wiring and restoration.
- [ ] Instantiate the store under `DATA_DIR`, connect start/completion/error/recovery events and expose an arena reporter callback.
- [ ] Update `compare_regular_arena_decks()` to report each deck decision and reselect deck 1 before returning `None`.
- [ ] Run the focused tests and verify PASS.

### Task 3: 관리자 총정리 팝업

**Files:**
- Modify: `CookieRunQuestAssistant/web_ui.py`
- Create: `CookieRunQuestAssistant/test_daily_summary_ui.cjs`

**Interfaces:**
- Consumes: Task 1 `today()` data returned as authenticated `/status.daily_summary`
- Produces: `renderDailySummary(summary)`, `copyDailySummary()`, existing `openAdminPopup('dailySummaryCard')`

- [ ] Write a failing Node UI test for admin-only visibility, summary cards, escaped recent activity, arena rows and copy text.
- [ ] Run `node test_daily_summary_ui.cjs` and verify failure.
- [ ] Add the hidden admin card, submenu entry, responsive styles, rendering and copy/refresh controls.
- [ ] Add `daily_summary` only when `/status` validates the admin token.
- [ ] Run the Node test and existing three UI tests; verify PASS.

### Task 4: 정식 버전과 배포 검증

**Files:**
- Modify: `CookieRunQuestAssistant/web_ui.py`
- Modify: `CookieRunQuestAssistant/RELEASE_NOTES.md`
- Modify: `CookieRunQuestAssistant/packaging/build_macos.command`
- Modify: `CookieRunQuestAssistant/packaging/build_windows.bat`
- Modify: `CookieRunQuestAssistant/packaging/windows_version.txt`
- Modify: `CookieRunQuestAssistant.app/Contents/Info.plist`

**Interfaces:**
- Produces: v15.18 stable source and Mac DMG; Windows build source at the same version.

- [ ] Update every displayed and packaged version to v15.18 and document the feature and arena restoration.
- [ ] Run `python3 -m unittest discover -q` plus all four Node UI tests and verify zero failures.
- [ ] Build the Mac app, run bundled `--self-test`, verify its signature and DMG checksum.
- [ ] Confirm the Windows script packages `daily_summary.py`, uses v15.18, and retains the existing note that real Windows execution remains unverified.

