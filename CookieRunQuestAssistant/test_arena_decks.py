import unittest
from unittest.mock import patch
import quest_assistant as e
class DeckTests(unittest.TestCase):
    def test_thresholds(self):
        for n,enemy,expected in [(1,99,True),(1,100,True),(1,105,True),(1,110,True),(1,111,False),(2,110,True),(3,110,False),(2,111,False),(3,111,False),(2,None,False)]:
            with self.subTest(n=n,enemy=enemy):self.assertEqual(e.arena_deck_can_challenge(n,(enemy,100,100,100)),expected)
    def test_main_deck_wins_without_comparing_alternatives(self):
        with patch.object(e, 'select_regular_arena_deck', return_value=(110,999,100,1)) as select:
            self.assertEqual(e.compare_regular_arena_decks(), 1)
        select.assert_called_once_with(1)
    def test_only_stronger_opponent_triggers_alternatives(self):
        for opponent in (None, 0):
            with patch.object(e, 'select_regular_arena_deck', return_value=(opponent,999,100,1)) as select:
                self.assertIsNone(e.compare_regular_arena_decks())
            select.assert_called_once_with(1)
    def test_stops_at_first_eligible_deck(self):
        with patch.object(e, 'select_regular_arena_deck', side_effect=[(120,1,100,1),(120,1,100,1),(99,1,100,1)]) as select:
            self.assertEqual(e.compare_regular_arena_decks(), 3)
        self.assertEqual([c.args[0] for c in select.call_args_list], [1,2,3])
    def test_no_eligible_deck(self):
        reports = []
        with patch.object(e, 'select_regular_arena_deck', return_value=(200,1,100,1)) as select, patch.object(e, 'ARENA_DECISION_REPORTER', side_effect=reports.append):
            self.assertIsNone(e.compare_regular_arena_decks())
        self.assertEqual([c.args[0] for c in select.call_args_list], [1,2,3,4,5,1])
        self.assertEqual([item['deck'] for item in reports], [1,2,3,4,5,1])
        self.assertEqual(reports[-1]['result'], '주덱 복원')
    def test_four_and_five_require_higher_power(self):
        for n in (3,4,5):
            for power, expected in ((99,True),(100,False),(110,False)):
                self.assertEqual(e.arena_deck_can_challenge(n,(power,1,100,1)),expected)
    def test_wagle_never_gets_deck_tap(self):
        with patch.object(e,'arena_decision_capture',return_value=object()),patch.object(e,'check_stop'),patch.object(e,'arena_opponents_visible',return_value=True),patch.object(e,'wagle_arena_opponents_visible',return_value=True),patch.object(e,'tap') as tap:
            with self.assertRaises(e.SafeStop):e.compare_regular_arena_decks()
        tap.assert_not_called()

class DeckReadRecoveryTests(unittest.TestCase):
    def test_invalid_repeated_readings_are_retried_for_every_deck(self):
        from contextlib import ExitStack
        for number in range(1, 6):
            with self.subTest(deck=number), ExitStack() as stack:
                for name, value in [('check_stop',None),('arena_decision_capture',object()),('arena_opponents_visible',True),('wagle_arena_opponents_visible',False),('_orange_button_fraction',.7),('tap',None)]:
                    stack.enter_context(patch.object(e,name,return_value=value))
                stack.enter_context(patch.object(e.time,'sleep'))
                stack.enter_context(patch.object(e,'arena_match_values',side_effect=[(None,1,100,1)]*2+[(120,1,100,1)]*2))
                self.assertEqual(e.select_regular_arena_deck(number),(120,1,100,1))
    def test_persistent_invalid_readings_stop_instead_of_skipping(self):
        with patch.object(e,'check_stop'), patch.object(e,'arena_decision_capture',return_value=object()), patch.object(e,'arena_opponents_visible',return_value=True), patch.object(e,'wagle_arena_opponents_visible',return_value=False), patch.object(e,'_orange_button_fraction',return_value=.7), patch.object(e,'tap'), patch.object(e,'arena_match_values',return_value=(None,1,100,1)), patch.object(e.time,'sleep'), patch.object(e.time,'monotonic',side_effect=[0,1,2,9]):
            with self.assertRaises(e.SafeStop):e.select_regular_arena_deck(1)

class RecordedDeckSelectionTests(unittest.TestCase):
    def test_recorded_fifth_deck_is_selected_and_others_are_not(self):
        from pathlib import Path
        from PIL import Image
        with Image.open(Path(__file__).parent/'tests/fixtures/sep27/free_refresh.png') as image:
            selected = [e._orange_button_fraction(image,(x-25,1260,x+25,1300)) > .35 for x in e.ARENA_DECK_X]
        self.assertEqual(selected,[False,False,False,False,True])
