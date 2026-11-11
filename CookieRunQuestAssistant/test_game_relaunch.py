import unittest
from unittest.mock import call, patch

import quest_assistant as engine
import web_ui as ui


class GameRelaunchModeTests(unittest.TestCase):
    def setUp(self):
        self.original = engine.AUTO_RELAUNCH_GAME

    def tearDown(self):
        engine.AUTO_RELAUNCH_GAME = self.original

    def test_default_is_enabled_and_validation_accepts_checkbox(self):
        self.assertTrue(ui.DEFAULTS["restart_game_on_exit"])
        self.assertFalse(ui.validate(dict(ui.DEFAULTS, restart_game_on_exit=False))["restart_game_on_exit"])

    def test_configure_only_enables_relaunch_for_quest_runs(self):
        ui.configure(ui.validate(dict(ui.DEFAULTS, task_quest=True, restart_game_on_exit=True)))
        self.assertTrue(engine.AUTO_RELAUNCH_GAME)
        ui.configure(ui.validate(dict(ui.DEFAULTS, task_quest=False, restart_game_on_exit=True)))
        self.assertFalse(engine.AUTO_RELAUNCH_GAME)

    def test_screenshot_relaunches_when_enabled(self):
        engine.AUTO_RELAUNCH_GAME = True
        with patch.object(engine, "check_stop"), \
                patch.object(engine, "game_is_foreground", return_value=False), \
                patch.object(engine, "relaunch_game", side_effect=engine.GameRelaunched("restarted")) as relaunch:
            with self.assertRaises(engine.GameRelaunched):
                engine.screenshot()
        relaunch.assert_called_once_with()

    def test_screenshot_stops_without_relaunch_when_disabled(self):
        engine.AUTO_RELAUNCH_GAME = False
        with patch.object(engine, "check_stop"), \
                patch.object(engine, "game_is_foreground", return_value=False), \
                patch.object(engine, "relaunch_game") as relaunch, \
                patch.object(engine, "_capture_screenshot") as capture:
            with self.assertRaisesRegex(engine.SafeStop, "자동 재실행이 꺼져"):
                engine.screenshot()
        relaunch.assert_not_called()
        capture.assert_not_called()

    def test_infinite_recovery_escalates_without_lifetime_error_cap(self):
        self.assertEqual(engine.infinite_recovery_tier(0, 1, 0, True), "screen")
        self.assertEqual(engine.infinite_recovery_tier(3, 1, 0, True), "back")
        self.assertEqual(engine.infinite_recovery_tier(0, 3, 0, True), "back")
        self.assertEqual(engine.infinite_recovery_tier(0, 6, 0, True), "restart")
        self.assertEqual(engine.infinite_recovery_tier(0, 6, 0, False), "back")
        self.assertEqual(engine.infinite_recovery_tier(6, 1, 0, True), "restart")
        self.assertEqual(engine.infinite_recovery_tier(6, 1, 0, False), "back")

    def test_confidence_changes_are_grouped_as_the_same_recognition_error(self):
        first = "현재 퀘스트를 여러 화면에서 판별하지 못했습니다(최고 0.49)."
        second = "현재 퀘스트를 여러 화면에서 판별하지 못했습니다(최고 0.44)."
        self.assertEqual(engine.recovery_reason_key(first), engine.recovery_reason_key(second))

    def test_brighter_level_up_overlay_is_detected(self):
        # Metrics measured from error_20260908_165538_892000.png.
        with patch.object(
            engine, "pixel_fraction", side_effect=[0.7003, 0.3072, 0.1633, 0.0384]
        ):
            self.assertTrue(engine.level_up_visible(object()))

    def test_repeated_error_restart_force_stops_and_recovers(self):
        with patch.object(engine, "adb") as adb, \
                patch.object(engine.time, "sleep"), \
                patch.object(engine, "relaunch_game", side_effect=engine.GameRelaunched("ok")), \
                patch.object(engine, "recover_to_battle", return_value=True) as recover:
            self.assertTrue(engine.restart_game_for_infinite_recovery())
        adb.assert_called_once_with("shell", "am", "force-stop", engine.GAME_PACKAGE)
        recover.assert_called_once_with(timeout=90)


class EquipmentAutoRunningTests(unittest.TestCase):
    def test_two_button_auto_running_sheet_is_detected(self):
        with patch.object(engine, "bottom_x_visible", return_value=True), \
                patch.object(engine, "pixel_fraction", side_effect=[0.80, 0.88, 0.60, 0.75]):
            self.assertTrue(engine.equipment_auto_running_visible(object()))

    def test_auto_running_sheet_requires_bottom_x(self):
        with patch.object(engine, "bottom_x_visible", return_value=False), \
                patch.object(engine, "pixel_fraction", side_effect=[0.80, 0.88, 0.60, 0.75]):
            self.assertFalse(engine.equipment_auto_running_visible(object()))

    def test_ten_item_auto_result_sheet_is_detected(self):
        with patch.object(engine, "bottom_x_visible", return_value=True), \
                patch.object(engine, "pixel_fraction", side_effect=[0.59, 0.60, 0.40, 0.26]):
            self.assertTrue(engine.equipment_auto_result_visible(object()))

    def test_santa_auto_tutorial_is_separate_from_running_notice(self):
        with patch.object(engine, "equipment_auto_running_visible", return_value=True), \
                patch.object(engine, "pixel_fraction", side_effect=[0.316, 0.117]):
            self.assertTrue(engine.equipment_auto_tutorial_visible(object()))

    def test_dismiss_auto_tutorial_checks_today_then_closes(self):
        with patch.object(engine, "tap") as tap, patch.object(engine.time, "sleep"):
            engine.dismiss_equipment_auto_tutorial()
        self.assertEqual(tap.call_args_list, [
            call(
                engine.EQUIPMENT_TUTORIAL_DONT_SHOW,
                "장비 Auto 안내 - 오늘 그만보기 체크",
                dry_run=False,
            ),
            call(engine.BOTTOM_X, "장비 Auto 안내창 닫기", dry_run=False),
        ])

    def test_auto_result_continues_after_tutorial_to_battle(self):
        tutorial, result, battle = object(), object(), object()
        with patch.object(engine, "check_stop"), \
                patch.object(
                    engine, "screen_state",
                    side_effect=["equipment_auto_tutorial", "equipment_auto_result", "battle"],
                ), \
                patch.object(engine, "dismiss_equipment_auto_tutorial") as dismiss, \
                patch.object(engine, "screenshot", side_effect=[result, battle]), \
                patch.object(engine, "tap") as tap, \
                patch.object(engine.time, "sleep"):
            image, state = engine.resolve_equipment_auto_result(tutorial)
        self.assertIs(image, battle)
        self.assertEqual(state, "battle")
        dismiss.assert_called_once_with()
        tap.assert_called_once_with(
            engine.AUTO_START,
            "자동 열기 결과 정리하기 (1/3)",
            dry_run=False,
        )


class IntegratedErrorCenterTests(unittest.TestCase):
    def setUp(self):
        self.original_errors = ui.STATE["errors"]

    def tearDown(self):
        ui.STATE["errors"] = self.original_errors

    def test_selected_error_id_resolves_the_exact_record(self):
        ui.STATE["errors"] = [{"id": "first"}, {"id": "second"}]
        self.assertEqual(ui.error_index("first"), 0)
        self.assertEqual(ui.error_index("second"), 1)
        self.assertIsNone(ui.error_index("missing"))
        self.assertEqual(ui.error_index(""), 1)

    def test_ui_combines_report_and_screenshots_per_error(self):
        self.assertIn('통합 오류 확인·보고', ui.HTML)
        self.assertIn('class="errors unified-errors"', ui.HTML)
        self.assertIn("스크린샷과 함께 수정 요청", ui.HTML)
        self.assertIn("sendToAdmin('${id}')", ui.HTML)
        self.assertNotIn('id="screenshotGallery"', ui.HTML)

    def test_extra_tasks_are_in_admin_menu_after_settings(self):
        self.assertIn("tasks.id='adminExtraTasks'", ui.HTML)
        self.assertIn("if(index===0)", ui.HTML)
        self.assertIn("tasks.onclick=openTaskPopup", ui.HTML)
        self.assertNotIn('class="task-popup-launch"><button type="button" onclick="openTaskPopup()"', ui.HTML)
        self.assertIn("function openTaskPopup(){if(!adminToken)", ui.HTML)


class BlueStacksMemoryCleanupTests(unittest.TestCase):
    def test_memory_parser_supports_current_android_output(self):
        completed = type("Result", (), {"stdout": "TOTAL PSS: 524,288 TOTAL RSS: 800000"})()
        with patch.object(engine, "adb", return_value=completed):
            self.assertEqual(engine.game_memory_mb(), 512.0)

    def test_cleanup_requires_cookie_run_in_foreground(self):
        with patch.object(engine, "game_is_foreground", return_value=False), \
                patch.object(engine, "adb") as adb:
            with self.assertRaisesRegex(engine.SafeStop, "전면에 띄워"):
                engine.trim_bluestacks_memory()
        adb.assert_not_called()

    def test_cleanup_sends_trim_then_clears_cached_processes(self):
        with patch.object(engine, "game_is_foreground", return_value=True), \
                patch.object(engine, "game_memory_mb", side_effect=[700.0, 540.0]), \
                patch.object(engine, "adb") as adb, \
                patch.object(engine.time, "sleep"):
            self.assertEqual(engine.trim_bluestacks_memory(), (700.0, 540.0))
        self.assertEqual(adb.call_args_list, [
            call("shell", "am", "send-trim-memory", engine.GAME_PACKAGE, "RUNNING_CRITICAL"),
            call("shell", "am", "kill-all"),
        ])

    def test_ui_exposes_idle_only_memory_button(self):
        self.assertIn('id="memoryCleanup"', ui.HTML)
        self.assertIn("cleanupBluestacksMemory()", ui.HTML)
        self.assertIn("s.running||s.paused||s.maintenance", ui.HTML)

    def test_dashboard_error_total_opens_admin_error_popup(self):
        self.assertIn('id="dashboardErrors"', ui.HTML)
        self.assertIn('onclick="openDashboardErrors()"', ui.HTML)
        self.assertIn("window.prompt('전체 오류 화면을 보려면 관리자 비밀번호를 입력하세요.')", ui.HTML)
        self.assertIn("openAdminPopup('adminScreenshots')", ui.HTML)

    def test_admin_and_logs_use_the_right_column_in_order(self):
        self.assertIn('grid-template-areas:"main admin" "main logs"', ui.HTML)
        self.assertIn("#adminCard{grid-area:admin", ui.HTML)
        self.assertIn("#adminLogs{grid-area:logs", ui.HTML)
        self.assertIn("#summaryCard{display:none!important}", ui.HTML)


if __name__ == "__main__":
    unittest.main()
