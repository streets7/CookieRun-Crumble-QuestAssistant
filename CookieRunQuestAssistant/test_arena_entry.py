import unittest
from unittest.mock import patch
import quest_assistant as e
import web_ui as ui
class EntryTests(unittest.TestCase):
    def test_kind_validation(self):
        self.assertEqual(ui.validate(dict(ui.DEFAULTS,arena_kind='wagle'))['arena_kind'],'wagle')
        with self.assertRaises(ValueError):ui.validate(dict(ui.DEFAULTS,arena_kind='bad'))
    def test_wagle_entry_from_battle(self):
        battle,home,opponents=object(),object(),object()
        with patch.object(e,'screenshot',return_value=battle), patch.object(e,'arena_opponents_visible',return_value=False), patch.object(e,'arena_home_visible',side_effect=lambda im:im is home), patch.object(e,'wagle_arena_home_visible',side_effect=lambda im:im is home), patch.object(e,'_main_battle_visible',return_value=True), patch.object(e,'_wait_dungeon_screen',side_effect=[home,opponents]), patch.object(e,'tap') as tap:
            self.assertIs(e.enter_selected_arena('wagle'),opponents)
        self.assertEqual([c.args[0] for c in tap.call_args_list],[(1000,815),(820,1550)])
    def test_regular_uses_dungeon_route(self):
        home,opponents=object(),object()
        with patch.object(e,'screenshot',return_value=object()), patch.object(e,'arena_opponents_visible',return_value=False), patch.object(e,'arena_home_visible',side_effect=lambda im:im is home), patch.object(e,'wagle_arena_home_visible',return_value=False), patch.object(e,'open_challenge_dungeon',return_value=home) as route, patch.object(e,'_wait_dungeon_screen',return_value=opponents), patch.object(e,'tap') as tap:
            self.assertIs(e.enter_selected_arena('regular'),opponents)
        route.assert_called_once_with('arena')
        self.assertEqual(tap.call_args.args[0],e.ARENA_ENTER)
    def test_wrong_home_never_starts_challenge(self):
        with patch.object(e,'screenshot',return_value=object()), patch.object(e,'arena_opponents_visible',return_value=False), patch.object(e,'arena_home_visible',return_value=False), patch.object(e,'open_challenge_dungeon',return_value=object()), patch.object(e,'tap') as tap:
            with self.assertRaises(e.SafeStop):e.enter_selected_arena('regular')
        tap.assert_not_called()
