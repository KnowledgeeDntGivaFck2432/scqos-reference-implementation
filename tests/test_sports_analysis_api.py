import hashlib
import json
import os
import unittest
from unittest.mock import patch

from sports_analysis import api
from sports_analysis.contract import CONTRACT_ID


def event(method, path, *, headers=None, body=None):
    return {
        "rawPath": path,
        "headers": headers or {},
        "requestContext": {"http": {"method": method, "path": path}},
        "body": json.dumps(body or {}),
    }


class SportsAnalysisApiTests(unittest.TestCase):
    def test_root_serves_phone_interface(self):
        response = api.lambda_handler(event("GET", "/"), None)
        self.assertEqual(response["statusCode"], 200)
        self.assertIn("Live MLB Analysis", response["body"])
        self.assertIn("Analysis only", response["body"])

    def test_health_names_exact_contract(self):
        response = api.lambda_handler(event("GET", "/api/health"), None)
        self.assertEqual(json.loads(response["body"])["contract"], CONTRACT_ID)

    def test_api_rejects_missing_access_key(self):
        response = api.lambda_handler(event("POST", "/api/analyze"), None)
        self.assertEqual(response["statusCode"], 401)

    def test_invalid_task_id_fails_before_aws_read(self):
        access_key = "test-access-key"
        digest = hashlib.sha256(access_key.encode()).hexdigest()
        with patch.dict(os.environ, {"SCQOS_SPORTS_ACCESS_KEY_SHA256": digest}):
            response = api.lambda_handler(
                event("GET", "/api/analysis/not-a-task", headers={"x-scqos-key": access_key}),
                None,
            )
        self.assertEqual(response["statusCode"], 400)
        self.assertEqual(json.loads(response["body"])["error"], "INVALID_TASK_ID")


if __name__ == "__main__":
    unittest.main()
