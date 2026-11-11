import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import quest_assistant as engine

class PetRecognitionTests(unittest.TestCase):
    def test_live_pet_card_is_distinct_from_cookie(self):
        panel = Image.open(Path(__file__).parent / 'tests/fixtures/pet_20430.png')
        image = Image.new('RGB', (1080,1920))
        image.paste(panel, (704,960))
        self.assertEqual(engine.detect_quest(image, assume_battle=True)[0], 'pet')

    def test_uncertain_preflight_rechecks_without_clicking(self):
        with patch.object(engine,'screenshot',return_value=object()), \
             patch.object(engine,'detect_quest',return_value=('unknown',0.68)), \
             patch.object(engine,'wait_detect_quest',side_effect=engine.SafeStop('still uncertain')) as retry, \
             patch.object(engine,'retry_tap_until_state') as click:
            with self.assertRaisesRegex(engine.SafeStop,'still uncertain'):
                engine.verified_draw('pet')
            retry.assert_called_once()
            click.assert_not_called()
