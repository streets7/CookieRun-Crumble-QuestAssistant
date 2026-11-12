# Five Stage Repeats and Log Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run integrated maintenance after five actual same-stage boss attempts and keep admin execution logs visible across login/restart races.

**Architecture:** Convert the pure scheduler tracker from elapsed-time observation to explicit attempt events. Emit those events at the boss summon boundary, and guard UI polling so only a response for the current admin token may update authentication and logs.

**Tech Stack:** Python 3, unittest, vanilla JavaScript, Node assertions

**Spec:** `docs/superpowers/specs/2026-11-13-five-stage-repeats-and-log-visibility-design.md`

## Global Constraints

- Count only actual boss summon attempts.
- Trigger on attempt 5, reset on completion, screen change, or stage change.
- Ignore stale admin poll responses.
- Release as stable v16.2.

## Review Focus

- Frequent battle polling must not count as attempts.
- A fifth attempt on a new stage must not inherit the previous stage count.
- Completion must reset before reward handling.
- A stale unauthenticated response must not clear a fresh login.
- Existing settings must load without the removed 180-second field affecting behavior.

---

### Task 1: Five-attempt scheduler

**Files:**
- Modify: `CookieRunQuestAssistant/integrated_automation.py`
- Modify: `CookieRunQuestAssistant/quest_assistant.py`
- Modify: `CookieRunQuestAssistant/web_ui.py`
- Test: `CookieRunQuestAssistant/test_integrated_scheduler.py`
- Test: `CookieRunQuestAssistant/test_integrated_orchestrator.py`

- [ ] Write failing tests for the fifth actual attempt and reset boundaries.
- [ ] Run focused tests and confirm expected failures.
- [ ] Implement attempt event tracking and update user-facing text/settings.
- [ ] Run focused tests and confirm they pass.

### Task 2: Stable admin log polling

**Files:**
- Modify: `CookieRunQuestAssistant/web_ui.py`
- Test: `CookieRunQuestAssistant/test_integrated_automation_ui.cjs`

- [ ] Write a failing behavior test for stale versus current admin poll responses.
- [ ] Run the UI test and confirm the expected failure.
- [ ] Add the poll generation guard and keep logs visible for current admin sessions.
- [ ] Run the UI test and confirm it passes.

### Task 3: Stable v16.2 release verification

**Files:**
- Modify: release and packaging version files
- Test: existing full test suites

- [ ] Update stable version references and release notes.
- [ ] Run all UI and Python tests plus self-test.
- [ ] Build and verify the macOS package, then replace and reopen the installed app without starting the macro.
- [ ] Commit the verified release.
