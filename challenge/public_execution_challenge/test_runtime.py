import json, os, sys, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
os.environ["SCQOS_TEST_MODE"] = "1"
sys.path[:0] = [str(HERE), str(ROOT)]
import runtime

class ChallengeTests(unittest.TestCase):
    def test_frozen_matrix(self):
        matrix = runtime.run_matrix()
        self.assertTrue(matrix["all_pass"], matrix)
        self.assertEqual((matrix["passed"], matrix["total"]), (6, 6))

    def test_permit_is_shadow_only_and_nine_gates(self):
        receipt = runtime.evaluate(runtime.case_transition("valid"))
        self.assertEqual(receipt["decision"], "PERMIT")
        self.assertTrue(receipt["release_authorized"])
        self.assertFalse(receipt["external_side_effects"])
        self.assertEqual(len(receipt["gate_proofs"]), 9)

    def test_handler_fails_closed(self):
        event = {"rawPath": "/v1/challenge", "requestContext": {"http": {"method": "POST"}}, "body": "{}"}
        response = runtime.handler(event, None)
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(json.loads(response["body"])["decision"], "HOLD")

if __name__ == "__main__": unittest.main()
