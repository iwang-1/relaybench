import json
import unittest
from pathlib import Path
from examples.model_study import verify


class StudyTests(unittest.TestCase):
    def test_reexecute_every_recorded_action_offline(self):
        root = Path(__file__).resolve().parents[1] / "docs"
        for name in ("initial-model-study", "local-model-study", "completion-model-study"):
            with self.subTest(name=name):
                report = json.loads((root / (name + ".json")).read_text())
                self.assertEqual(len(report["runs"]), 10)
                verify(report)
                report["runs"][0]["writes"] += 1
                with self.assertRaises(ValueError):
                    verify(report)
