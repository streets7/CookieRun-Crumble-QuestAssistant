"""Independent popup run regression tests; never connect to BlueStacks."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import web_ui as ui


class GroupStartTests(unittest.TestCase):
    def setUp(self):
        self.saved = dict(ui.DEFAULTS, infinite=True, task_quest=True,
                          task_arena=True, task_arena_runs=5)
        self.settings_mock = patch.object(ui, 'settings', return_value=self.saved)
        self.settings_mock.start()
        self.addCleanup(self.settings_mock.stop)

    def test_every_implemented_group_is_exclusive(self):
        for scope in ('challenge', 'daily_dungeon'):
            for task in ui.TASK_GROUPS[scope]:
                with self.subTest(task=task):
                    data = ui.prepare_group_run({'scope': scope, 'selected_tasks': [task]})
                    self.assertEqual([k for k in ui.TASK_LABELS if data[k]], [task])
                    self.assertFalse(data['infinite'])
                    self.assertEqual(data['cycles'], 1)
                    self.assertEqual(data['task_arena_runs'], 5)

    def test_unrelated_checks_cannot_leak_into_run(self):
        data = ui.prepare_group_run({
            'scope': 'daily_dungeon', 'selected_tasks': ['task_coin_dungeon'],
            'settings': {'infinite': True, 'task_quest': True, 'task_arena': True,
                         'task_coin_dungeon_runs': 3, 'task_coin_dungeon_continuous': True},
        })
        self.assertFalse(data['task_arena'])
        self.assertFalse(data['task_quest'])
        self.assertFalse(data['infinite'])
        self.assertTrue(data['task_coin_dungeon_continuous'])

    def test_empty_invalid_and_unimplemented_rejected(self):
        for request in (
            {'scope': 'challenge', 'selected_tasks': []},
            {'scope': 'challenge', 'selected_tasks': ['task_coin_dungeon']},
            {' ' : 'invalid'},
            {'scope': 'growth', 'selected_tasks': ['task_cookie_upgrade']},
            {'scope': 'daily_rewards', 'selected_tasks': ['task_attendance']},
        ):
            with self.subTest(request=request), self.assertRaises(ValueError):
                ui.prepare_group_run(request)

    def invoke(self, request, running=False, paused=False):
        handler = ui.Handler.__new__(ui.Handler)
        handler.path = '/start-group'
        handler.read_json = lambda: request
        handler.send_json = Mock()
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / 'settings.json'
            with patch.object(ui, 'SETTINGS_FILE', settings_file), \
                 patch.object(ui, 'STATE', {'running': running, 'paused': paused}), \
                 patch.object(ui, 'configure') as configure, \
                 patch.object(ui.threading, 'Thread') as thread, \
                 patch.object(ui.engine, 'STOP'), patch.object(ui.engine, 'SKIP_ACTION'), \
                 patch.object(ui.engine, 'FAST_SCREENSHOT_AVAILABLE'):
                handler.do_POST()
                return handler.send_json.call_args, configure.call_args, thread.return_value.start.call_count, settings_file.exists()

    def test_endpoint_starts_only_selected_group(self):
        response, configured, starts, saved = self.invoke({
            'scope': 'challenge', 'selected_tasks': ['task_arena']})
        self.assertEqual(response.args[0]['message'], '시작했습니다.')
        self.assertEqual(starts, 1)
        self.assertTrue(saved)
        self.assertTrue(configured.args[0]['task_arena'])
        self.assertFalse(configured.args[0]['task_quest'])
        self.assertFalse(configured.args[0]['infinite'])

    def test_busy_or_paused_does_not_replace_existing_run(self):
        for running, paused in ((True, False), (False, True)):
            response, configured, starts, saved = self.invoke(
                {'scope': 'challenge', 'selected_tasks': ['task_arena']}, running, paused)
            self.assertEqual(response.args[1], 409)
            self.assertIsNone(configured)
            self.assertEqual(starts, 0)
            self.assertFalse(saved)

    def test_unimplemented_does_not_start_worker_or_save(self):
        response, configured, starts, saved = self.invoke({
            'scope': 'growth', 'selected_tasks': ['task_cookie_upgrade']})
        self.assertEqual(response.args[1], 400)
        self.assertIn('제작 중', response.args[0]['message'])
        self.assertIsNone(configured)
        self.assertEqual(starts, 0)
        self.assertFalse(saved)


if __name__ == '__main__':
    unittest.main()
