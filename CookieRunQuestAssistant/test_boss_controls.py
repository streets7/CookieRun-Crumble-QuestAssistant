"""Boss selection/input regression tests. Never send real keys or game clicks."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import quest_assistant as engine
import web_ui as ui


class BossControlTests(unittest.TestCase):
    def setUp(self):
        for name in ('BOSS_D_MOVE_ENABLED', 'BOSS_AS_MOVE_ENABLED', 'BOSS_MOVE_SECONDS',
                     'BOSS_CORNER_MOVE_SECONDS', 'BOSS_MOVEMENT_REVISION',
                     'BOSS_PRESET_SEQUENCE', 'STOP', 'SKIP_ACTION'):
            value = getattr(engine, name)
            self.addCleanup(setattr, engine, name, value)
        engine.STOP = engine.SKIP_ACTION = False
        self.state = patch.object(ui, 'STATE', {'last_data': dict(ui.DEFAULTS)})
        self.state.start()
        self.addCleanup(self.state.stop)

    def configure(self, d=False, corner=False, **extra):
        data = ui.validate(dict(ui.DEFAULTS, boss_keyboard_move_normal=d,
                                boss_keyboard_move_corner=corner, **extra))
        ui.configure_boss_controls(data)
        return data

    def test_four_checkbox_combinations(self):
        for d, corner, expected in ((False, False, []), (True, False, [('d',)]),
                                    (False, True, [('a', 's')]),
                                    (True, True, [('d',), ('a', 's')])):
            with self.subTest(d=d, corner=corner):
                self.configure(d, corner)
                self.assertEqual([row[0] for row in engine.selected_boss_movements()], expected)

    def test_legacy_and_non_boolean_cannot_enable_movement(self):
        for raw in ({}, {'boss_keyboard_move': True},
                    {'boss_keyboard_move_normal': 'false', 'boss_keyboard_move_corner': 1}):
            data = ui.validate(raw)
            self.assertFalse(data['boss_keyboard_move_normal'])
            self.assertFalse(data['boss_keyboard_move_corner'])

    def test_all_unchecked_presets_stay_unchecked(self):
        data = self.configure(**{f'boss_preset_{n}': False for n in range(1, 6)})
        self.assertEqual(data['boss_preset_order'], '')
        self.assertEqual(engine.BOSS_PRESET_SEQUENCE, ())

    def test_disabled_or_unsupported_keys_do_not_launch_any_process(self):
        self.configure(d=True)
        with patch.object(engine.subprocess, 'run') as run, patch.object(engine.subprocess, 'Popen') as launch:
            for keys in (('a', 's'), ('w',), ('d', 'a'), ('d', 'invalid'), ()):
                engine.hold_bluestacks_keys(keys, 4, 'test')
            run.assert_not_called()
            launch.assert_not_called()

    def test_uncheck_during_focus_never_sends_keydown(self):
        self.configure(d=True)
        with patch.object(engine.subprocess, 'run') as run, \
                patch.object(engine.subprocess, 'Popen') as launch, \
                patch.object(engine.time, 'sleep', side_effect=lambda _: self.configure()):
            engine.hold_bluestacks_keys(('d',), 4, 'test')
            launch.assert_not_called()
            self.assertNotIn('key down', run.call_args.args[0][-1])

    def hold_with_change(self, change):
        self.configure(d=True)
        process = Mock(returncode=0)
        process.poll.return_value = None
        sleeps = []
        def sleep(seconds):
            sleeps.append(seconds)
            if seconds == 0.05:
                change()
        with patch.object(engine.subprocess, 'run') as run, \
                patch.object(engine.subprocess, 'Popen', return_value=process) as launch, \
                patch.object(engine.time, 'sleep', side_effect=sleep):
            try:
                engine.hold_bluestacks_keys(('d',), 4, 'test')
            finally:
                process.terminate.assert_called_once()
                self.assertIn('key up "d"', run.call_args.args[0][-1])
                script = launch.call_args.args[0][-1]
                self.assertIn('key down "d"', script)
                self.assertNotIn('key down "a"', script)
                self.assertIn('frontmost', script)

    def test_uncheck_releases_held_keys(self):
        self.hold_with_change(lambda: self.configure())

    def test_stop_releases_held_keys(self):
        with self.assertRaisesRegex(engine.SafeStop, '긴급정지'):
            self.hold_with_change(lambda: setattr(engine, 'STOP', True))

    def test_next_action_releases_held_keys(self):
        with self.assertRaises(engine.SkipAction):
            self.hold_with_change(lambda: setattr(engine, 'SKIP_ACTION', True))

    def test_input_failure_still_releases_keys(self):
        self.configure(corner=True)
        process = Mock(returncode=1)
        process.poll.return_value = 1
        with patch.object(engine.subprocess, 'run') as run, \
                patch.object(engine.subprocess, 'Popen', return_value=process), \
                patch.object(engine.time, 'sleep'), self.assertRaisesRegex(engine.SafeStop, '입력에 실패'):
            try:
                engine.hold_bluestacks_keys(('a', 's'), 6, 'test')
            finally:
                self.assertIn('key up "s"\nkey up "a"', run.call_args.args[0][-1])

    def test_endpoint_updates_running_and_resume_settings_without_other_changes(self):
        self.configure(d=True, corner=True)
        handler = ui.Handler.__new__(ui.Handler)
        handler.path = '/boss-controls'
        handler.read_json = lambda: {'boss_keyboard_move_normal': False,
                                    'boss_keyboard_move_corner': False, 'task_quest': False}
        handler.send_json = Mock()
        with tempfile.TemporaryDirectory() as tmp, patch.object(ui, 'SETTINGS_FILE', Path(tmp) / 'settings.json'):
            handler.do_POST()
            self.assertEqual(engine.selected_boss_movements(), [])
            self.assertFalse(ui.STATE['last_data']['boss_keyboard_move_normal'])
            self.assertFalse(ui.STATE['last_data']['boss_keyboard_move_corner'])
            self.assertTrue(ui.settings()['task_quest'])
            ui.configure(ui.STATE['last_data'])
            self.assertEqual(engine.selected_boss_movements(), [])
            self.assertEqual(len(handler.send_json.call_args.args), 1)


if __name__ == '__main__':
    unittest.main()
