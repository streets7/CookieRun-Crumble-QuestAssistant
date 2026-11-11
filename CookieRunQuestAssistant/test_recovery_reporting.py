import unittest
from contextlib import ExitStack
from unittest.mock import patch
import quest_assistant as engine


class RecoveryReportingTests(unittest.TestCase):
    def test_score_changes_share_count_and_recovery_continues(self):
        reasons = [f'현재 퀘스트를 여러 화면에서 판별하지 못했습니다(최고 {score}).' for score in ('0.68', '0.67')]
        reports = []
        with ExitStack() as stack:
            for name, value in [('STOP', False), ('ERROR_REPORTER', reports.append)]:
                stack.enter_context(patch.object(engine, name, value))
            stack.enter_context(patch.object(engine, 'repeat_equipment_reward_visible', return_value=False))
            stack.enter_context(patch.object(engine, 'screenshot', return_value=object()))
            stack.enter_context(patch.object(engine, 'screen_state', return_value='battle'))
            stack.enter_context(patch.object(engine, 'wait_for_state', return_value=object()))
            stack.enter_context(patch.object(engine, 'wait_detect_quest', side_effect=[engine.SafeStop(r) for r in reasons]))
            stack.enter_context(patch.object(engine, 'check_stop', side_effect=[None, None, RuntimeError('test loop finished')]))
            stack.enter_context(patch.object(engine, 'recover_and_find_resume_point', return_value=(True, 'pet', 0.67)))
            stack.enter_context(patch.object(engine.time, 'sleep'))
            with self.assertRaisesRegex(RuntimeError, 'test loop finished'):
                engine.run_dynamic(1, False, infinite=True)
        self.assertEqual([r['same'] for r in reports], [1, 2])
        self.assertEqual([r['reason'] for r in reports], reasons)
        self.assertTrue(all(r['resume_quest'] == 'pet' for r in reports))
