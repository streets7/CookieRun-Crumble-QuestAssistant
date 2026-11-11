# Desktop Program and GitHub Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace browser launching with a dedicated Mac/Windows desktop window and prepare verified GitHub Releases containing the correct installer for each operating system.

**Architecture:** Keep the existing Python automation engine and localhost HTTP interface, but host that interface inside a `pywebview` desktop window bound only to `127.0.0.1`. Separate server lifecycle, desktop window lifecycle, and GitHub release lookup so each can be tested without BlueStacks or network access. Build platform-specific artifacts from one stable tag: DMG on macOS and installer EXE on Windows.

**Tech Stack:** Python 3.11+, `pywebview`, existing `ThreadingHTTPServer`, PyInstaller, Inno Setup 6, GitHub Actions and Releases.

**Spec:** `docs/superpowers/specs/2026-11-11-github-desktop-download-design.md`

## Global Constraints

- Existing general UI, admin mode, daily summary and error reporting remain available.
- The HTTP server binds to `127.0.0.1` only and does not open a browser in desktop mode.
- Closing the desktop window requests an automation stop and shuts down the internal server.
- Only stable GitHub Releases are considered for update notices; beta builds remain opt-in.
- User settings, administrator secrets, account information, daily summaries and screenshots are never packaged or committed.
- Windows remains marked as unverified until it is exercised on a real Windows 11 machine with BlueStacks 5.

## Review Focus

- Port 8765 already occupied: focus the existing app or show one clear message without starting a duplicate engine.
- Desktop window closes during an active run: request stop, shut down the server and exit without leaving held keys.
- GitHub is offline, rate-limited or returns malformed JSON: the app continues normally and shows no false update.
- A prerelease is newer than the stable version: ignore it unless beta updates are explicitly enabled later.
- A Release lacks the current operating system's asset: show the release page rather than a broken direct-download link.

---

### Task 1: Testable internal server lifecycle

**Files:**
- Modify: `CookieRunQuestAssistant/web_ui.py`
- Create: `CookieRunQuestAssistant/test_web_server_lifecycle.py`

**Interfaces:**
- Produces: `create_server(host: str = HOST, port: int = PORT) -> ThreadingHTTPServer`
- Produces: `serve(open_browser: bool = True) -> None`
- Preserves: `main() -> None` as the source/browser compatibility entry point.

- [ ] Write failing tests asserting `create_server` uses localhost, desktop serving does not call `webbrowser.open`, and shutdown sets `engine.STOP` and `engine.SKIP_ACTION` safely.
- [ ] Run `python3 -m unittest test_web_server_lifecycle -q` and confirm failure because the lifecycle functions do not exist.
- [ ] Extract server creation and serving from `main()` without changing routes or UI content.
- [ ] Run the focused test and the full Python suite; expect all tests to pass.
- [ ] Commit the lifecycle change when a usable Git repository exists.

### Task 2: Dedicated desktop window

**Files:**
- Create: `CookieRunQuestAssistant/desktop_app.py`
- Create: `CookieRunQuestAssistant/test_desktop_app.py`
- Modify: `CookieRunQuestAssistant/app_entry.py`
- Modify: `CookieRunQuestAssistant/requirements-runtime.txt`
- Modify: `CookieRunQuestAssistant/requirements-build.txt`

**Interfaces:**
- Consumes: `web_ui.create_server()` and existing `/shutdown` behavior.
- Produces: `run_desktop() -> int`
- Produces: `shutdown_desktop(server: ThreadingHTTPServer) -> None`

- [ ] Write failing tests with a fake webview asserting one window is created at the local URL, browser launch is never called, duplicate-port startup exits clearly, and window close stops the engine/server.
- [ ] Run `python3 -m unittest test_desktop_app -q`; expect missing-module or missing-function failure.
- [ ] Implement the desktop host using `pywebview`, a background server thread and an idempotent close handler.
- [ ] Change normal `app_entry.py` startup to `run_desktop()` while keeping `--self-test` headless.
- [ ] Add pinned compatible `pywebview` runtime/build dependency and include its PyInstaller hooks.
- [ ] Run focused tests, full Python tests and all four Node UI tests; expect success.
- [ ] Commit when a usable Git repository exists.

### Task 3: Stable GitHub update check

**Files:**
- Create: `CookieRunQuestAssistant/release_update.py`
- Create: `CookieRunQuestAssistant/test_release_update.py`
- Modify: `CookieRunQuestAssistant/web_ui.py`
- Modify: `CookieRunQuestAssistant/web_ui.py` embedded JavaScript/HTML update-status area

**Interfaces:**
- Produces: `parse_version(value: str) -> tuple[int, ...]`
- Produces: `select_platform_asset(release: dict, platform_name: str) -> dict | None`
- Produces: `check_latest_release(api_url: str, current_version: str, platform_name: str, timeout: float = 3.0) -> dict`
- Adds read-only `/update-status` JSON endpoint.

- [ ] Write failing tests for newer stable versions, equal/older versions, prereleases, offline responses, malformed JSON and missing platform assets.
- [ ] Run `python3 -m unittest test_release_update -q`; expect missing-module failure.
- [ ] Implement the checker with the standard library, a three-second timeout and no startup failure propagation.
- [ ] Add a non-blocking update status in the program header; use the release page as fallback when a direct asset is absent.
- [ ] Run the focused, full Python and UI tests; expect success.
- [ ] Commit when a usable Git repository exists.

### Task 4: Mac DMG and Windows installer EXE

**Files:**
- Modify: `CookieRunQuestAssistant/packaging/build_macos.command`
- Modify: `CookieRunQuestAssistant/packaging/build_windows.bat`
- Create: `CookieRunQuestAssistant/packaging/windows_installer.iss`
- Modify: `CookieRunQuestAssistant/packaging/install-macos.txt`
- Modify: `CookieRunQuestAssistant/packaging/install-windows.txt`
- Create: `CookieRunQuestAssistant/test_packaging_contract.py`

**Interfaces:**
- Produces Mac asset: `CookieRun-Crumble-QuestAssistant-macOS-v<version>.dmg`
- Produces Windows asset: `CookieRun-Crumble-QuestAssistant-Windows11-v<version>-Setup.exe`
- Produces per-platform `SHA256.txt`.

- [ ] Write a failing packaging-contract test asserting both exact asset names, required bundled modules and absence of user data paths.
- [ ] Run `python3 -m unittest test_packaging_contract -q`; expect failure for the missing Windows installer.
- [ ] Update the Mac build to bundle `pywebview` and retain self-test, signing and DMG verification.
- [ ] Add an Inno Setup installer that installs per user, creates Start Menu/Desktop shortcuts and provides a normal uninstaller.
- [ ] Update the Windows build to run tests, build the app, run self-test and compile the installer; fail clearly when Inno Setup is unavailable.
- [ ] Run packaging-contract tests and build/verify the Mac artifact locally.
- [ ] Leave Windows artifact status as `Windows 실기기 검증 필요` until GitHub Windows runner and a real machine pass.
- [ ] Commit when a usable Git repository exists.

### Task 5: Stable tag release workflow and repository handoff

**Files:**
- Modify: `.github/workflows/build-desktop.yml`
- Create: `.github/workflows/release-desktop.yml`
- Modify: `CookieRunQuestAssistant/packaging/BUILDING.md`
- Modify: `CookieRunQuestAssistant/RELEASE_NOTES.md`
- Modify: `.gitignore`
- Create: `CookieRunQuestAssistant/test_release_workflow.py`

**Interfaces:**
- Trigger: stable tags matching `v*` and manual dispatch.
- Produces one GitHub Release containing Mac DMG, Windows Setup EXE and checksums.

- [ ] Write a failing workflow-contract test asserting stable tag trigger, both platform jobs, test gates, exact asset globs and release upload dependencies.
- [ ] Run `python3 -m unittest test_release_workflow -q`; expect failure because the release workflow is absent.
- [ ] Implement build jobs and a release job that downloads both artifacts and publishes them only after both builds pass.
- [ ] Document repository creation, remote connection, first push, tag publication and the Windows verification checklist.
- [ ] Confirm `.gitignore` excludes settings, summaries, screenshots, build work, secrets and generated archives.
- [ ] Run the complete Python/UI suite and validate workflow YAML structure locally.
- [ ] Create/connect the GitHub repository only after the user chooses its name and public/private visibility, then perform the first push and release.

## Self-review result

- The plan covers the desktop window, safe lifecycle, stable updates, both installers and GitHub release flow.
- The GitHub repository mutation is deliberately last because repository name and visibility are owner decisions.
- Windows compilation can be exercised by GitHub Actions, but BlueStacks behavior still requires a real Windows 11 verification pass.
- A fully native UI rewrite and unattended auto-update remain outside this release.

