import unittest
from copy import deepcopy
from unittest.mock import patch
from io import BytesIO

from relaybench.engine import FAULTS, action, dispatch, execute, fixture, replay
from relaybench.model import local_policy


class EngineTests(unittest.TestCase):
    def test_controlled_matrix(self):
        for seed in range(31):
            for policy in ("reconcile", "blind_retry"):
                for fault in FAULTS:
                    with self.subTest(seed=seed, policy=policy, fault=fault):
                        trace = execute(seed, policy, fault)
                        duplicate = policy == "blind_retry" and fault == "lost_ack"
                        self.assertEqual(trace["metrics"]["passed"], not duplicate)
                        self.assertEqual(trace["metrics"]["writes"], 1 + duplicate)
                        self.assertTrue(replay(trace)["verified"])
                        self.assertEqual(trace, execute(seed, policy, fault))

    def test_indistinguishable_timeout_different_worlds(self):
        a, b = (execute(42, "reconcile", f)["events"][1] for f in FAULTS[1:])
        self.assertEqual(a["observation"], b["observation"])
        self.assertEqual(a["before"], a["after"])
        self.assertNotEqual(b["before"], b["after"])

    def test_divergence_localization(self):
        trace = execute(42, "reconcile", "lost_ack")
        trace["events"][1]["after"] = "edited"
        self.assertEqual(replay(trace)["divergence"], "step 2")

    def test_incomplete_trace_and_altered_metadata(self):
        trace = execute(7, "blind_retry", "none")
        trace["model"] = "changed"
        self.assertEqual(replay(trace)["divergence"], "checksum")
        trace["events"].pop()
        self.assertEqual(replay(trace)["divergence"], "early_stop")

    def test_boundary(self):
        world = fixture(8)
        initial = deepcopy(world)
        for call in (None, action("shell"), action("inspect", path="/"),
                     action("reserve", pool="delta", units=True),
                     action("reserve", pool="unknown", units=1),
                     action("reserve", pool="atlas", units=-1)):
            result, hit = dispatch(world, call, "lost_ack", False)
            self.assertIn("error", result)
            self.assertFalse(hit)
            self.assertEqual(world, initial)

    def test_policy_has_no_state_aliases(self):
        def meddle(request, history):
            request["units"] = -100
            if history:
                history[0]["observation"].clear()
                return action("finish")
            return action("inspect")
        trace = execute(1, "ollama", "none", meddle)
        self.assertEqual(trace["initial"], fixture(1))
        self.assertTrue(replay(trace)["verified"])

    def test_budget_and_model_free_replay(self):
        trace = execute(1, "ollama", "none", lambda *_: action("inspect"))
        self.assertEqual(trace["metrics"]["steps"], 10)
        self.assertFalse(trace["metrics"]["passed"])
        self.assertTrue(replay(trace)["verified"])

    def test_model_protocol(self):
        with patch("relaybench.model.urlopen", return_value=BytesIO(b'{"message":{"content":"{\\"tool\\":\\"inspect\\",\\"args\\":{}}"}}')):
            self.assertEqual(local_policy("test")({}, []), action("inspect"))
        with patch("relaybench.model.urlopen", return_value=BytesIO(b"broken")):
            with self.assertRaises(RuntimeError):
                local_policy("test")({}, [])
