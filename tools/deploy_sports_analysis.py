#!/usr/bin/env python3
"""Idempotently deploy and live-qualify the SCQOS sports-analysis product."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3


ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURE_ID = "SUPREME-MIND-59-FACULTY-UNIVERSE-V1"
CONTRACT_ID = "SCQOS-SPORTS-ANALYSIS-V1"
GOVERNOR_FUNCTION = "supreme-mind-v1-governor"
EXECUTOR_FUNCTION = "shadow-clone-v1-executor"
API_FUNCTION = "scqos-sports-analysis-api"
API_ROLE = "scqos-sports-analysis-api-role"
DEFAULT_REGION = "us-east-1"


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run(args: list[str], *, cwd: Path = ROOT) -> str:
    result = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"COMMAND_FAILED ({result.returncode}): {' '.join(args)}\n{result.stdout}")
    return result.stdout.strip()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wait_until(label: str, fetch, ready, failed, *, timeout: int = 900):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = fetch()
        if failed(last):
            raise RuntimeError(f"{label}_FAILED:{json.dumps(last, default=str)}")
        if ready(last):
            return last
        state = last.get("state") if isinstance(last, dict) else str(last)
        print(f"  {label}: {state}")
        time.sleep(10)
    raise RuntimeError(f"{label}_TIMEOUT:{json.dumps(last, default=str)}")


class Deployment:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.region = args.region
        self.session = boto3.Session(region_name=self.region)
        self.sts = self.session.client("sts")
        self.iam = self.session.client("iam")
        self.lambda_client = self.session.client("lambda")
        self.ddb = self.session.client("dynamodb")
        self.s3 = self.session.client("s3")
        self.account = ""
        self.governor: dict[str, Any] = {}
        self.executor: dict[str, Any] = {}
        self.env: dict[str, str] = {}
        self.access_key = args.access_key or secrets.token_urlsafe(24)
        self.access_key_sha256 = hashlib.sha256(self.access_key.encode()).hexdigest()
        self.function_url = ""
        self.executor_zip_sha256 = ""
        self.api_zip_sha256 = ""
        self.qualification: dict[str, Any] = {}
        self.evidence_dir: Path | None = None

    def verify(self) -> None:
        print("[1/6] Verifying exact source and live SCQOS architecture")
        run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"])
        self.account = str(self.sts.get_caller_identity()["Account"])
        self.governor = self.lambda_client.get_function_configuration(FunctionName=GOVERNOR_FUNCTION)
        self.executor = self.lambda_client.get_function_configuration(FunctionName=EXECUTOR_FUNCTION)
        self.env = self.governor.get("Environment", {}).get("Variables", {})
        required = {
            "SUPREME_MIND_TABLE",
            "SUPREME_MIND_RECEIPT_TABLE",
            "SUPREME_MIND_MANIFEST_BUCKET",
        }
        missing = sorted(required - set(self.env))
        if missing:
            raise RuntimeError("LIVE_GOVERNOR_ENV_MISSING:" + ",".join(missing))
        executor_env = self.executor.get("Environment", {}).get("Variables", {})
        if not executor_env.get("SHADOW_CLONE_HARNESS_ARN"):
            raise RuntimeError("LIVE_SHADOW_CLONE_HARNESS_MISSING")
        if self.governor.get("State") != "Active" or self.executor.get("State") != "Active":
            raise RuntimeError("LIVE_ACTION_PLANE_NOT_ACTIVE")
        for name in (self.env["SUPREME_MIND_TABLE"], self.env["SUPREME_MIND_RECEIPT_TABLE"]):
            if self.ddb.describe_table(TableName=name)["Table"]["TableStatus"] != "ACTIVE":
                raise RuntimeError("LIVE_TABLE_NOT_ACTIVE:" + name)
        print(f"  PERMIT: account {self.account}, {self.region}, governor + executor + live tables")

    @staticmethod
    def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
        root = destination.resolve()
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if root != target and root not in target.parents:
                raise RuntimeError("DEPLOYED_ZIP_PATH_TRAVERSAL")
        archive.extractall(destination)

    def build_executor_zip(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="sports-executor-"))
        existing_zip = temp / "deployed.zip"
        location = self.lambda_client.get_function(FunctionName=EXECUTOR_FUNCTION)["Code"]["Location"]
        urllib.request.urlretrieve(location, existing_zip)
        package = temp / "package"
        package.mkdir()
        with zipfile.ZipFile(existing_zip) as archive:
            self._safe_extract(archive, package)
        shutil.copy2(ROOT / "shadow_clone/executor.py", package / "executor.py")
        shutil.copy2(ROOT / "shadow_clone/protocol.py", package / "protocol.py")
        shutil.rmtree(package / "sports_analysis", ignore_errors=True)
        shutil.copytree(
            ROOT / "sports_analysis",
            package / "sports_analysis",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        output = temp / "executor.zip"
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(package.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(package))
        self.executor_zip_sha256 = file_sha256(output)
        return output

    def deploy_executor(self) -> None:
        print("[2/6] Installing deterministic sports computation in the live executor")
        code = self.build_executor_zip().read_bytes()
        self.lambda_client.update_function_code(
            FunctionName=EXECUTOR_FUNCTION, ZipFile=code, Publish=True
        )
        wait_until(
            "EXECUTOR_UPDATE",
            lambda: self.lambda_client.get_function_configuration(FunctionName=EXECUTOR_FUNCTION),
            lambda item: item.get("LastUpdateStatus") == "Successful",
            lambda item: item.get("LastUpdateStatus") == "Failed",
            timeout=300,
        )
        print("  PERMIT: live executor code updated; configuration and Harness ARN preserved")

    def ensure_role(self) -> str:
        trust = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": "lambda.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }],
        }
        try:
            role = self.iam.get_role(RoleName=API_ROLE)["Role"]
            self.iam.update_assume_role_policy(
                RoleName=API_ROLE, PolicyDocument=json.dumps(trust)
            )
        except self.iam.exceptions.NoSuchEntityException:
            role = self.iam.create_role(
                RoleName=API_ROLE,
                AssumeRolePolicyDocument=json.dumps(trust),
                Description="SCQOS sports-analysis web API",
                Tags=[{"Key": "Architecture", "Value": ARCHITECTURE_ID}],
            )["Role"]
        state_arn = f"arn:aws:dynamodb:{self.region}:{self.account}:table/{self.env['SUPREME_MIND_TABLE']}"
        receipt_arn = f"arn:aws:dynamodb:{self.region}:{self.account}:table/{self.env['SUPREME_MIND_RECEIPT_TABLE']}"
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {"Effect": "Allow", "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"], "Resource": "arn:aws:logs:*:*:*"},
                {"Effect": "Allow", "Action": ["lambda:InvokeFunction"], "Resource": self.governor["FunctionArn"]},
                {"Effect": "Allow", "Action": ["dynamodb:Query"], "Resource": state_arn},
                {"Effect": "Allow", "Action": ["dynamodb:GetItem"], "Resource": receipt_arn},
            ],
        }
        self.iam.put_role_policy(
            RoleName=API_ROLE,
            PolicyName="scqos-sports-analysis-api",
            PolicyDocument=json.dumps(policy),
        )
        return role["Arn"]

    def build_api_zip(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="sports-api-"))
        package = temp / "package"
        package.mkdir()
        shutil.copytree(
            ROOT / "sports_analysis",
            package / "sports_analysis",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        output = temp / "api.zip"
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(package.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(package))
        self.api_zip_sha256 = file_sha256(output)
        return output

    def deploy_api(self) -> None:
        print("[3/6] Deploying the authenticated mobile web application")
        role_arn = self.ensure_role()
        code = self.build_api_zip().read_bytes()
        variables = {
            "SUPREME_MIND_TABLE": self.env["SUPREME_MIND_TABLE"],
            "SUPREME_MIND_RECEIPT_TABLE": self.env["SUPREME_MIND_RECEIPT_TABLE"],
            "SUPREME_MIND_GOVERNOR_FUNCTION": GOVERNOR_FUNCTION,
            "SCQOS_SPORTS_ACCESS_KEY_SHA256": self.access_key_sha256,
        }
        try:
            self.lambda_client.get_function(FunctionName=API_FUNCTION)
            self.lambda_client.update_function_code(
                FunctionName=API_FUNCTION, ZipFile=code, Publish=True
            )
            wait_until(
                "API_CODE",
                lambda: self.lambda_client.get_function_configuration(FunctionName=API_FUNCTION),
                lambda item: item.get("LastUpdateStatus") == "Successful",
                lambda item: item.get("LastUpdateStatus") == "Failed",
                timeout=300,
            )
            self.lambda_client.update_function_configuration(
                FunctionName=API_FUNCTION,
                Role=role_arn,
                Handler="sports_analysis.api.lambda_handler",
                Runtime="python3.13",
                Timeout=30,
                MemorySize=512,
                Environment={"Variables": variables},
            )
        except self.lambda_client.exceptions.ResourceNotFoundException:
            time.sleep(8)
            self.lambda_client.create_function(
                FunctionName=API_FUNCTION,
                Runtime="python3.13",
                Role=role_arn,
                Handler="sports_analysis.api.lambda_handler",
                Code={"ZipFile": code},
                Description="Receipt-verified SCQOS live MLB analysis web application",
                Timeout=30,
                MemorySize=512,
                Publish=True,
                Environment={"Variables": variables},
                Tags={"Architecture": ARCHITECTURE_ID, "Contract": CONTRACT_ID},
            )
        wait_until(
            "SPORTS_API",
            lambda: self.lambda_client.get_function_configuration(FunctionName=API_FUNCTION),
            lambda item: item.get("State") == "Active" and item.get("LastUpdateStatus") == "Successful",
            lambda item: item.get("State") == "Failed" or item.get("LastUpdateStatus") == "Failed",
            timeout=300,
        )
        try:
            config = self.lambda_client.get_function_url_config(FunctionName=API_FUNCTION)
            if config.get("AuthType") != "NONE":
                config = self.lambda_client.update_function_url_config(
                    FunctionName=API_FUNCTION, AuthType="NONE", InvokeMode="BUFFERED"
                )
        except self.lambda_client.exceptions.ResourceNotFoundException:
            config = self.lambda_client.create_function_url_config(
                FunctionName=API_FUNCTION, AuthType="NONE", InvokeMode="BUFFERED"
            )
        self.function_url = config["FunctionUrl"]
        for statement_id, action, extra in (
            ("scqos-sports-function-url", "lambda:InvokeFunctionUrl", {"FunctionUrlAuthType": "NONE"}),
            ("scqos-sports-function-url-invoke", "lambda:InvokeFunction", {"InvokedViaFunctionUrl": True}),
        ):
            try:
                self.lambda_client.add_permission(
                    FunctionName=API_FUNCTION,
                    StatementId=statement_id,
                    Action=action,
                    Principal="*",
                    **extra,
                )
            except self.lambda_client.exceptions.ResourceConflictException:
                pass
        print("  PERMIT: " + self.function_url)

    def request_url(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        raw = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            self.function_url.rstrip("/") + path,
            data=raw,
            method=method,
            headers={
                "content-type": "application/json",
                "x-scqos-key": self.access_key,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = json.loads(response.read())
                return {"statusCode": response.status, **payload}
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read())
            except Exception:
                payload = {"error": "HTTP_" + str(exc.code)}
            return {"statusCode": exc.code, **payload}

    def qualify(self) -> None:
        print("[4/6] Running one live MLB + DraftKings analysis through all eight invariants")
        def live_health():
            try:
                return self.request_url("GET", "/api/health")
            except (OSError, TimeoutError) as exc:
                return {"state": "WAITING", "error": type(exc).__name__}

        wait_until(
            "LIVE_APP_ENDPOINT",
            live_health,
            lambda item: item.get("statusCode") == 200 and item.get("contract") == CONTRACT_ID,
            lambda item: False,
            timeout=180,
        )
        today = datetime.now(timezone.utc).date().isoformat()
        submitted = self.request_url(
            "POST", "/api/analyze", {"analysis_date": today, "max_events": 1, "matchup": ""}
        )
        if submitted.get("statusCode") != 202 or not submitted.get("task_id"):
            raise RuntimeError("LIVE_SPORTS_SUBMISSION_FAILED:" + json.dumps(submitted, default=str))
        task_id = submitted["task_id"]
        table = self.session.resource("dynamodb").Table(self.env["SUPREME_MIND_TABLE"])

        def state():
            rows = table.query(
                KeyConditionExpression="pk = :pk",
                ExpressionAttributeValues={":pk": "TASK#" + task_id},
                ConsistentRead=True,
            ).get("Items", [])
            if not rows:
                return {"state": "QUEUED", "task_id": task_id}
            terminal = [row for row in rows if row.get("state") in ("COMPLETED", "FAILED", "REJECT")]
            return max(terminal or rows, key=lambda row: str(row.get("completed_at") or row.get("started_at") or ""))

        row = wait_until(
            "LIVE_SPORTS_ANALYSIS",
            state,
            lambda item: item.get("state") == "COMPLETED",
            lambda item: item.get("state") in ("FAILED", "REJECT"),
            timeout=self.args.timeout,
        )
        result = self.request_url("GET", "/api/analysis/" + task_id)
        decision = result.get("sports_decision") or {}
        if result.get("statusCode") != 200 or not result.get("receipt_verified"):
            raise RuntimeError("LIVE_RECEIPT_VERIFICATION_FAILED:" + json.dumps(result, default=str))
        if decision.get("contract") != CONTRACT_ID:
            raise RuntimeError("LIVE_SPORTS_CONTRACT_MISSING")
        if decision.get("decision") not in ("EXECUTE", "HOLD", "REJECT"):
            raise RuntimeError("LIVE_SPORTS_DECISION_INVALID")
        if decision.get("action_boundary") != "ANALYSIS_ONLY_NO_WAGER":
            raise RuntimeError("LIVE_ACTION_BOUNDARY_MISSING")
        self.qualification = {
            "task": row,
            "api_result": result,
            "decision": decision.get("decision"),
        }
        print("  PERMIT: live collection completed; verified sports verdict = " + decision["decision"])

    def freeze_evidence(self) -> None:
        print("[5/6] Freezing source, deployment, and live receipt evidence")
        stamp = utc()
        target = ROOT / "evidence" / "sports-analysis" / stamp
        target.mkdir(parents=True)
        receipt = {
            "architecture_id": ARCHITECTURE_ID,
            "contract": CONTRACT_ID,
            "deployed_at_utc": stamp,
            "aws_account": self.account,
            "aws_region": self.region,
            "function_url": self.function_url,
            "access_key_sha256": self.access_key_sha256,
            "executor_function": EXECUTOR_FUNCTION,
            "executor_zip_sha256": self.executor_zip_sha256,
            "api_function": API_FUNCTION,
            "api_zip_sha256": self.api_zip_sha256,
            "qualification": self.qualification,
            "state": "PERMIT",
            "reason": "LIVE_SPORTS_ANALYSIS_COMPLETED_AND_RECEIPTS_VERIFIED",
        }
        from sports_analysis.canonical import sha256

        receipt["receipt_sha256"] = sha256(receipt)
        receipt_path = target / "SPORTS_ANALYSIS_DEPLOYMENT_RECEIPT.json"
        receipt_path.write_text(json.dumps(receipt, indent=2, default=str) + "\n")
        (target / "SHA256SUMS").write_text(file_sha256(receipt_path) + "  " + receipt_path.name + "\n")
        prefix = f"architecture/{ARCHITECTURE_ID}/sports-analysis/{stamp}/"
        for path in target.iterdir():
            self.s3.put_object(
                Bucket=self.env["SUPREME_MIND_MANIFEST_BUCKET"],
                Key=prefix + path.name,
                Body=path.read_bytes(),
                Metadata={"sha256": file_sha256(path), "contract": "scqos-sports-v1"},
            )
        self.evidence_dir = target
        print("  PERMIT: " + str(target))

    def publish(self) -> str | None:
        print("[6/6] Publishing the exact qualified product")
        if not self.args.publish:
            print("  HOLD: --publish not selected; deployment is live but source remains local")
            return None
        run(["git", "fetch", "origin"])
        temp = Path(tempfile.mkdtemp(prefix="sports-publish-"))
        worktree = temp / "repo"
        try:
            run(["git", "worktree", "add", "--detach", str(worktree), "origin/main"])
            relatives = [
                Path("shadow_clone/executor.py"),
                Path("sports_analysis"),
                Path("tools/deploy_shadow_clone.py"),
                Path("tools/deploy_sports_analysis.py"),
                Path("tests/test_sports_analysis_contract.py"),
                Path("tests/test_sports_analysis_prompt.py"),
                Path("tests/test_sports_analysis_api.py"),
                self.evidence_dir.relative_to(ROOT),
            ]
            for relative in relatives:
                source = ROOT / relative
                target = worktree / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if source.is_dir():
                    shutil.copytree(source, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
                else:
                    shutil.copy2(source, target)
            run(["git", "add", *[str(path) for path in relatives]], cwd=worktree)
            if not run(["git", "status", "--porcelain"], cwd=worktree):
                return run(["git", "rev-parse", "HEAD"], cwd=worktree)
            run(["git", "commit", "-m", "Deploy receipt-verified SCQOS sports analysis"], cwd=worktree)
            commit = run(["git", "rev-parse", "HEAD"], cwd=worktree)
            run(["git", "push", "origin", "HEAD:main"], cwd=worktree)
            print("  PERMIT: public main advanced to " + commit)
            return commit
        finally:
            try:
                run(["git", "worktree", "remove", "--force", str(worktree)])
            except Exception:
                pass
            shutil.rmtree(temp, ignore_errors=True)

    def execute(self) -> None:
        self.verify()
        self.deploy_executor()
        self.deploy_api()
        self.qualify()
        self.freeze_evidence()
        commit = self.publish()
        print("\nSPORTS ANALYSIS PRODUCT: PERMIT")
        print("App:", self.function_url)
        print("Access key:", self.access_key)
        print("Contract:", CONTRACT_ID)
        print("Live verdict:", self.qualification["decision"])
        print("Evidence:", self.evidence_dir)
        if commit:
            print("Public commit:", commit)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deploy SCQOS sports-analysis web product")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", DEFAULT_REGION))
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--access-key", default=os.getenv("SCQOS_SPORTS_ACCESS_KEY", ""))
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    if not 300 <= args.timeout <= 1800:
        parser.error("--timeout must be between 300 and 1800 seconds")
    return args


if __name__ == "__main__":
    Deployment(parse_args()).execute()
