import unittest
from unittest.mock import Mock, patch

import quest_assistant as engine
import web_ui as ui


class ArenaDecisionTests(unittest.TestCase):
    def test_challenge_priority_policy_uses_only_free_refresh(self):
        for values, available, nxt, free, terminal, expected in (
            ((500, 3000, 1000, 2000), True, True, False, False, 'challenge'),
            ((1500, 1500, 1000, 2000), True, True, False, False, 'challenge'),
            ((1500, 2500, 1000, 2000), True, True, False, False, 'next'),
            ((1500, 2500, 1000, 2000), True, False, True, True, 'refresh'),
            ((1500, 2500, 1000, 2000), True, False, False, True, 'challenge'),
            ((1500, 2500, 1000, 2000), True, False, False, False, 'wait'),
            ((1000, 2500, 1000, 2000), True, True, False, False, 'challenge'),
            ((1500, 2000, 1000, 2000), True, True, False, False, 'challenge'),
            ((1500, 2500, 1000, 2000), False, False, True, True, 'refresh'),
            ((1500, 2500, 1000, 2000), False, False, False, True, 'wait'),
            ((None, 2500, 1000, 2000), True, False, False, True, 'challenge'),
            ((500, None, 1000, 2000), True, True, False, False, 'challenge'),
            ((1500, None, 1000, 2000), True, True, False, False, 'next'),
            ((None, None, None, None), True, False, True, True, 'refresh'),
            ((None, None, None, None), True, False, False, True, 'challenge'),
            ((None, None, None, None), True, False, False, False, 'wait'),
        ):
            with self.subTest(values=values, expected=expected):
                self.assertEqual(
                    engine.arena_mode_action('challenge', values, available, nxt, free, terminal), expected
                )

    def test_partial_ocr_can_skip_but_never_force_challenge_or_paid_refresh(self):
        values = (None, 1873, 5300000, 1862)
        self.assertEqual(engine.arena_decision_action(values, True, True, False), 'next')
        self.assertEqual(engine.arena_decision_action(values, True, False, True), 'refresh')
        self.assertEqual(engine.arena_decision_action(values, True, False, False), 'wait')

    def test_comparison_policy(self):
        for values, challenge, nxt, free, expected in (
            ((500, 3000, 1000, 2000), True, True, True, 'challenge'),
            ((500, 1000, 1000, 2000), True, True, False, 'challenge'),
            ((1000, 3000, 500, 2000), True, True, True, 'next'),
            ((1000, 1000, 500, 2000), True, True, False, 'next'),
            ((1000, 3000, 500, 2000), True, False, True, 'refresh'),
            ((1000, 1000, 500, 2000), True, False, True, 'refresh'),
            ((1000, 3000, 500, 2000), True, False, False, 'wait'),
            ((500, 3000, 1000, 2000), False, True, False, 'wait'),
            ((None, 3000, 1000, 2000), True, True, True, 'next'),
            ((0, 3000, 1000, 2000), True, True, True, 'next'),
            ((1000, 2000, 1000, 2000), True, True, True, 'next'),
        ):
            with self.subTest(values=values, expected=expected):
                self.assertEqual(engine.arena_decision_action(values, challenge, nxt, free), expected)

    def test_refresh_requires_positive_free_text_not_missing_price(self):
        for counter, text, expected in (
            ((5, 5), '무료 새로고침', (False, True)),
            ((5, 5), '', (False, False)),
            ((5, 5), '새로고침', (False, False)),
            ((5, 5), '28분 11초 후 무료 새로고침 300', (False, False)),
            ((5, 5), '무료 새로고침 크리스탈', (False, False)),
            ((3, 5), '다음 상대', (True, False)),
            ((3, 5), '', (True, False)),
            ((4, 5), '판독 실패', (True, False)),
            (None, '무료 새로고침', (False, False)),
        ):
            with self.subTest(text=text), patch.object(engine, 'arena_opponent_counter', return_value=counter), \
                    patch.object(engine, '_ocr_region', return_value=text):
                self.assertEqual(engine.arena_selector_options(object()), expected)

    def test_selector_distinguishes_last_opponent_from_unknown_counter(self):
        for counter, text, expected in (
            ((5, 5), '새로고침 300', (False, False, True)),
            ((5, 5), '무료 새로고침', (False, True, True)),
            ((3, 5), '다음 상대', (True, False, False)),
            ((4, 5), '', (True, False, False)),
            (None, '', (False, False, False)),
        ):
            with self.subTest(counter=counter), patch.object(engine, 'arena_opponent_counter', return_value=counter), \
                    patch.object(engine, '_ocr_region', return_value=text):
                self.assertEqual(engine.arena_selector_details(object()), expected)

    def test_selector_uses_button_text_when_small_counter_is_unreadable(self):
        for text, expected in (
            ('다음 상대', (True, False, False)),
            ('새로고침 300', (False, False, True)),
            ('28분 후 무료 새로고침', (False, False, True)),
            ('', (False, False, False)),
        ):
            with self.subTest(text=text), patch.object(engine, 'arena_opponent_counter', return_value=None), \
                    patch.object(engine, '_ocr_region', return_value=text):
                self.assertEqual(engine.arena_selector_details(object()), expected)

    def test_refresh_kind_separates_free_from_diamond_and_cooldown(self):
        for counter, text, expected in (
            ((5, 5), '무료 새로고침', 'free'),
            ((5, 5), '새로고침 300', 'paid_or_wait'),
            ((5, 5), '28분 11초 후 무료 새로고침', 'paid_or_wait'),
            ((3, 5), '다음 상대', 'next'),
            ((5, 5), '', 'unknown'),
        ):
            with self.subTest(text=text):
                self.assertEqual(engine.arena_refresh_kind(counter, text), expected)

    def test_selector_status_exposes_paid_refresh_without_enabling_it(self):
        with patch.object(engine, 'arena_opponent_counter', return_value=(5, 5)), \
                patch.object(engine, '_ocr_region', return_value='새로고침 300'):
            self.assertEqual(
                engine.arena_selector_status(object()),
                (False, False, True, 'paid_or_wait'),
            )

    def test_scope_excludes_every_other_task(self):
        with patch.object(ui, 'settings', return_value=dict(ui.DEFAULTS, task_arena=True, task_quest=True)):
            data = ui.prepare_group_run({'scope': 'arena_decision', 'selected_tasks': ['task_arena_decision']})
        self.assertEqual([k for k in ui.TASK_LABELS if data[k]], ['task_arena_decision'])
        self.assertFalse(data['infinite'])
        selected = ui.prepare_group_run({
            'scope': 'arena_decision', 'selected_tasks': ['task_arena_decision'],
            'settings': {'arena_decision_mode': 'challenge'},
        })
        self.assertEqual(selected['arena_decision_mode'], 'challenge')
        with self.assertRaises(ValueError):
            ui.validate(dict(ui.DEFAULTS, task_arena_decision=True, task_quest=True))
        with self.assertRaises(ValueError):
            ui.validate(dict(ui.DEFAULTS, arena_decision_mode='invalid'))

    def test_challenge_priority_run_uses_next_then_last_opponent_challenge(self):
        values = (1500, 2500, 1000, 2000)
        with patch.object(engine, 'check_stop'), \
                patch.object(engine, 'arena_decision_capture', side_effect=[object(), object(), engine.SafeStop('end')]), \
                patch.object(engine, 'arena_opponents_visible', return_value=True), \
                patch.object(engine, 'arena_match_values', return_value=values), \
                patch.object(engine, 'arena_selector_details', return_value=(True, False, False)), \
                patch.object(engine, 'dungeon_action_available', return_value=True), \
                patch.object(engine, 'game_is_foreground', return_value=True), \
                patch.object(engine, 'tap') as tap, patch.object(engine, 'wait_arena_decision_change'), \
                patch.object(engine.time, 'sleep'):
            with self.assertRaises(engine.SafeStop):
                engine.run_arena_decision_only('challenge')
            tap.assert_called_once_with(engine.ARENA_REFRESH, '아레나 모드 - 다음 상대', dry_run=False)

        with patch.object(engine, 'check_stop'), \
                patch.object(engine, 'arena_decision_capture', side_effect=[object(), object(), engine.SafeStop('end')]), \
                patch.object(engine, 'arena_opponents_visible', return_value=True), \
                patch.object(engine, 'arena_match_values', return_value=values), \
                patch.object(engine, 'arena_selector_details', return_value=(False, False, True)), \
                patch.object(engine, 'dungeon_action_available', return_value=True), \
                patch.object(engine, 'game_is_foreground', return_value=True), \
                patch.object(engine, 'tap') as tap, patch.object(engine, 'wait_arena_decision_change'), \
                patch.object(engine.time, 'sleep'):
            with self.assertRaises(engine.SafeStop):
                engine.run_arena_decision_only('challenge')
            tap.assert_called_once_with(engine.ARENA_CHALLENGE, '아레나 모드 - 도전하기', dry_run=False)

    def test_raw_capture_never_auto_recovers_or_wakes_game(self):
        with patch.object(engine, 'check_stop'), patch.object(engine, 'game_is_foreground', return_value=False), \
                patch.object(engine, 'relaunch_game') as launch, patch.object(engine, 'wake_sleep_mode') as wake:
            with self.assertRaises(engine.SafeStop):
                engine.arena_decision_capture()
            launch.assert_not_called()
            wake.assert_not_called()

    def test_only_three_allowed_buttons_after_two_consistent_frames(self):
        for values, options, expected in (
            ((500, 1000, 1000, 2000), (True, False), engine.ARENA_CHALLENGE),
            ((1000, 1000, 500, 2000), (True, False), engine.ARENA_REFRESH),
            ((1000, 3000, 500, 2000), (False, True), engine.ARENA_REFRESH),
        ):
            with self.subTest(values=values), patch.object(engine, 'check_stop'), \
                    patch.object(engine, 'arena_decision_capture', side_effect=[object(), object(), engine.SafeStop('test end')]), \
                    patch.object(engine, 'arena_opponents_visible', return_value=True), \
                    patch.object(engine, 'arena_match_values', return_value=values), \
                    patch.object(engine, 'arena_selector_details', return_value=(*options, not options[0])), \
                    patch.object(engine, 'dungeon_action_available', return_value=True), \
                    patch.object(engine, 'game_is_foreground', return_value=True), \
                    patch.object(engine, 'tap') as tap, patch.object(engine, 'wait_arena_decision_change'), \
                    patch.object(engine.time, 'sleep'), patch.object(engine, 'return_to_main_battle') as back:
                with self.assertRaises(engine.SafeStop):
                    engine.run_arena_decision_only()
                self.assertEqual(tap.call_count, 1)
                self.assertEqual(tap.call_args.args[0], expected)
                back.assert_not_called()

    def test_result_screens_never_clicked(self):
        with patch.object(engine, 'arena_decision_capture', side_effect=[object(), engine.SafeStop('test end')]), \
                patch.object(engine, 'arena_opponents_visible', return_value=False), \
                patch.object(engine, 'tap') as tap, patch.object(engine.time, 'sleep'):
            with self.assertRaises(engine.SafeStop):
                engine.run_arena_decision_only()
            tap.assert_not_called()

    def test_unchanged_screen_stops_without_reclick(self):
        with patch.object(engine.time, 'monotonic', side_effect=[0, 0, 16]), \
                patch.object(engine, 'arena_decision_capture', return_value=object()), \
                patch.object(engine, 'arena_opponents_visible', return_value=True), \
                patch.object(engine.time, 'sleep'), patch.object(engine, 'tap') as tap:
            with self.assertRaises(engine.SafeStop):
                engine.wait_arena_decision_change('challenge', (1, 2, 3, 4))
            tap.assert_not_called()

    def test_next_opponent_accepts_visual_change_when_ocr_is_partial(self):
        before, after = object(), object()
        with patch.object(engine.time, 'monotonic', side_effect=[0, 0]), \
                patch.object(engine, 'arena_decision_capture', return_value=after), \
                patch.object(engine, 'arena_opponents_visible', return_value=True), \
                patch.object(engine, 'arena_match_values', return_value=(None, 2100, 1000, 2000)), \
                patch.object(engine, 'image_difference', return_value=.08), \
                patch.object(engine.time, 'sleep'):
            engine.wait_arena_decision_change(
                'next', (None, 2200, 1000, 2000), before_image=before
            )

    def test_challenge_mode_requires_stable_action_not_identical_ocr(self):
        first, second = object(), object()
        values = [(500, 1500, 1000, 2000), (510, 1500, 1000, 2000)]
        with patch.object(engine, 'check_stop'), \
                patch.object(engine, 'arena_decision_capture', side_effect=[first, second, engine.SafeStop('end')]), \
                patch.object(engine, 'arena_opponents_visible', return_value=True), \
                patch.object(engine, 'arena_match_values', side_effect=values), \
                patch.object(engine, 'arena_selector_details', return_value=(True, False, False)), \
                patch.object(engine, 'dungeon_action_available', return_value=True), \
                patch.object(engine, 'game_is_foreground', return_value=True), \
                patch.object(engine, 'tap') as tap, \
                patch.object(engine, 'wait_arena_decision_change'), \
                patch.object(engine, 'wait_arena_mode_return'), \
                patch.object(engine.time, 'sleep'):
            with self.assertRaises(engine.SafeStop):
                engine.run_arena_decision_only('challenge')
        tap.assert_called_once_with(
            engine.ARENA_CHALLENGE, '아레나 모드 - 도전하기', dry_run=False
        )

    def test_defeat_page_is_tapped_and_returns_to_opponents(self):
        loss1, loss2, opponents = object(), object(), object()
        with patch.object(engine, 'arena_decision_capture', side_effect=[loss1, loss2, opponents]), \
                patch.object(engine, 'arena_opponents_visible', side_effect=lambda image: image is opponents), \
                patch.object(engine, 'arena_home_visible', return_value=False), \
                patch.object(engine, 'arena_victory_visible', return_value=False), \
                patch.object(engine, 'arena_result_visible', return_value=False), \
                patch.object(engine, 'arena_rank_change_visible', return_value=False), \
                patch.object(engine, 'arena_static_tap_result_visible', side_effect=lambda image, previous: image is loss2), \
                patch.object(engine, 'tap') as tap, patch.object(engine.time, 'sleep'):
            self.assertIs(engine.wait_arena_mode_return(), opponents)
        tap.assert_called_once_with(
            engine.ARENA_RESULT_CONTINUE, '아레나 패배 화면 넘기기 (1/12)', dry_run=False
        )

    def test_regular_arena_and_standalone_mode_share_result_flow(self):
        returned = object()
        with patch.object(engine, 'wait_arena_mode_return', return_value=returned) as wait:
            self.assertIs(engine._wait_arena_completion(timeout=77), returned)
        wait.assert_called_once_with(timeout=77)

    def test_victory_page_advances_on_first_distinctive_frame(self):
        victory, opponents = object(), object()
        with patch.object(engine, 'arena_decision_capture', side_effect=[victory, opponents]), \
                patch.object(engine, 'arena_opponents_visible', side_effect=lambda image: image is opponents), \
                patch.object(engine, 'arena_home_visible', return_value=False), \
                patch.object(engine, 'arena_victory_visible', side_effect=lambda image: image is victory), \
                patch.object(engine, 'arena_result_visible', return_value=False), \
                patch.object(engine, 'arena_rank_change_visible', return_value=False), \
                patch.object(engine, 'arena_static_tap_result_visible', return_value=False), \
                patch.object(engine, 'tap') as tap, patch.object(engine.time, 'sleep'):
            self.assertIs(engine.wait_arena_mode_return(), opponents)
        tap.assert_called_once_with(
            engine.ARENA_RESULT_CONTINUE, '아레나 승리 화면 넘기기 (1/12)', dry_run=False
        )

    def test_live_or_unknown_battle_is_never_tapped(self):
        battle = object()
        with patch.object(engine, 'arena_decision_capture', side_effect=[battle, engine.SafeStop('end')]), \
                patch.object(engine, 'arena_opponents_visible', return_value=False), \
                patch.object(engine, 'arena_home_visible', return_value=False), \
                patch.object(engine, 'arena_victory_visible', return_value=False), \
                patch.object(engine, 'arena_result_visible', return_value=False), \
                patch.object(engine, 'arena_rank_change_visible', return_value=False), \
                patch.object(engine, 'arena_static_tap_result_visible', return_value=False), \
                patch.object(engine, 'tap') as tap, patch.object(engine.time, 'sleep'):
            with self.assertRaises(engine.SafeStop):
                engine.wait_arena_mode_return()
        tap.assert_not_called()

    def test_static_defeat_fallback_requires_prompt_and_stable_image(self):
        image = object()
        with patch.object(engine, 'arena_home_visible', return_value=False), \
                patch.object(engine, 'arena_opponents_visible', return_value=False), \
                patch.object(engine, 'arena_victory_visible', return_value=False), \
                patch.object(engine, 'pixel_fraction', return_value=.05), \
                patch.object(engine, 'image_difference', return_value=.011):
            self.assertTrue(engine.arena_static_tap_result_visible(image, object()))
        with patch.object(engine, 'arena_home_visible', return_value=False), \
                patch.object(engine, 'arena_opponents_visible', return_value=False), \
                patch.object(engine, 'arena_victory_visible', return_value=False), \
                patch.object(engine, 'pixel_fraction', return_value=.05), \
                patch.object(engine, 'image_difference', return_value=.05):
            self.assertFalse(engine.arena_static_tap_result_visible(image, object()))


if __name__ == '__main__':
    unittest.main()
