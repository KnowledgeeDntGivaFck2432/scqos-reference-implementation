#!/usr/bin/env python3
"""Deploy and live-qualify Shadow Clone against Supreme Mind v1.

This is intentionally one idempotent command.  It verifies the already-deployed
59-faculty universe before changing anything, builds an immutable browser body,
creates the AgentCore Harness, attaches the Shadow Clone executor to the existing
SQS action plane, executes one live-source qualification task, writes a receipt
bundle, and optionally publishes the exact code and evidence from a clean
worktree.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    import boto3
    import botocore
except ImportError:
    raise SystemExit(
        "boto3 is required. Run this exact command again through the documented "
        "Shadow Clone virtual-environment launcher."
    )


ROOT = Path(__file__).resolve().parents[1]
SHADOW = ROOT / "shadow_clone"
SUPREME_MANIFEST_PATH = ROOT / "supreme_mind/v1/supreme_mind_manifest.json"
SHADOW_MANIFEST_PATH = SHADOW / "shadow_clone_manifest.json"
ARCHITECTURE_ID = "SUPREME-MIND-59-FACULTY-UNIVERSE-V1"
SHADOW_PROTOCOL = "SHADOW-CLONE-RECURSIVE-EXECUTION-V1"
EXPECTED_SOURCE_MANIFEST_RAW_SHA256 = "a70a130772ca13cf55bf4887e1862eebbf27bd1fc62d1de1db2f2dc366a0f9ac"
DEFAULT_REGION = "us-east-1"
DEFAULT_MODEL = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
GOVERNOR_FUNCTION = "supreme-mind-v1-governor"
EXECUTOR_FUNCTION = "shadow-clone-v1-executor"
HARNESS_NAME = "shadow_clone_v1"
BROWSER_NAME = "shadow_clone_v1_recorded_browser"
ECR_REPOSITORY = "shadow-clone-browser"
HARNESS_ROLE = "shadow-clone-v1-harness-role"
EXECUTOR_ROLE = "shadow-clone-v1-executor-role"
CODEBUILD_ROLE = "shadow-clone-v1-codebuild-role"
CODEBUILD_PROJECT = "shadow-clone-v1-browser-build"


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def digest(value: bytes | Any) -> str:
    raw = value if isinstance(value, bytes) else canonical_bytes(value)
    return hashlib.sha256(raw).hexdigest()


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest(paths: Iterable[Path]) -> str:
    records = []
    for path in sorted(paths, key=lambda item: str(item)):
        records.append({"path": str(path.relative_to(ROOT)), "sha256": file_digest(path)})
    return digest(records)


def run(args: list[str], *, cwd: Path | None = None, stdin: str | None = None) -> str:
    result = subprocess.run(
        args,
        cwd=str(cwd or ROOT),
        input=stdin,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"COMMAND_FAILED ({result.returncode}): {' '.join(args)}\n{result.stdout}")
    return result.stdout.strip()


def wait_until(label: str, fetch, ready, failed, timeout: int = 900) -> Any:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = fetch()
        if failed(last):
            raise RuntimeError(f"{label}_FAILED:{last}")
        if ready(last):
            return last
        print(f"  {label}: {last}")
        time.sleep(10)
    raise RuntimeError(f"{label}_TIMEOUT:{last}")


class Deployment:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.region = args.region
        self.session = boto3.Session(region_name=self.region)
        self.sts = self.session.client("sts")
        self.iam = self.session.client("iam")
        self.ecr = self.session.client("ecr")
        self.codebuild = self.session.client("codebuild")
        self.lambda_client = self.session.client("lambda")
        self.s3 = self.session.client("s3")
        self.sqs = self.session.client("sqs")
        self.ddb = self.session.client("dynamodb")
        self.agent_control = self.session.client("bedrock-agentcore-control")
        self.agent_data = self.session.client("bedrock-agentcore")
        self.identity: dict[str, Any] = {}
        self.account = ""
        self.governor_config: dict[str, Any] = {}
        self.env: dict[str, str] = {}
        self.queue_arn = ""
        self.queue_previous_visibility_timeout = 0
        self.harness: dict[str, Any] = {}
        self.browser: dict[str, Any] = {}
        self.image_uri = ""
        self.image_digest = ""
        self.lambda_zip_sha256 = ""
        self.disabled_mappings: list[dict[str, Any]] = []
        self.qualification: dict[str, Any] = {}
        self.browser_recordings: list[dict[str, Any]] = []
        self.evidence_dir: Path | None = None

    def verify_local_source(self) -> None:
        print("[1/8] Verifying local Supreme Mind and Shadow Clone source")
        if file_digest(SUPREME_MANIFEST_PATH) != EXPECTED_SOURCE_MANIFEST_RAW_SHA256:
            raise RuntimeError("LOCAL_SUPREME_MIND_MANIFEST_SHA256_MISMATCH")
        manifest = json.loads(SUPREME_MANIFEST_PATH.read_text())
        if manifest.get("architecture_id") != ARCHITECTURE_ID:
            raise RuntimeError("LOCAL_ARCHITECTURE_ID_MISMATCH")
        if len(manifest.get("roles", [])) != 59:
            raise RuntimeError("LOCAL_ROLE_COUNT_NOT_59")
        shadow_manifest = json.loads(SHADOW_MANIFEST_PATH.read_text())
        if shadow_manifest.get("architecture_id") != ARCHITECTURE_ID:
            raise RuntimeError("SHADOW_SOURCE_ARCHITECTURE_MISMATCH")
        run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_shadow_clone_protocol.py", "-v"])
        print("  PERMIT: source manifest, 59 roles, and invariant tests agree")

    def verify_aws_and_live_architecture(self) -> None:
        print("[2/8] Verifying live AWS identity and existing 59-faculty universe")
        self.identity = self.sts.get_caller_identity()
        self.account = str(self.identity["Account"])
        self.governor_config = self.lambda_client.get_function_configuration(
            FunctionName=GOVERNOR_FUNCTION
        )
        if self.governor_config.get("State") not in (None, "Active"):
            raise RuntimeError("LIVE_GOVERNOR_NOT_ACTIVE")
        self.env = self.governor_config.get("Environment", {}).get("Variables", {})
        required = {
            "SUPREME_MIND_TABLE",
            "SUPREME_MIND_RECEIPT_TABLE",
            "SUPREME_MIND_QUEUE_URL",
            "SUPREME_MIND_MANIFEST_BUCKET",
            "SUPREME_MIND_MANIFEST_KEY",
        }
        missing = sorted(required - self.env.keys())
        if missing:
            raise RuntimeError("LIVE_GOVERNOR_ENV_MISSING:" + ",".join(missing))
        raw = self.s3.get_object(
            Bucket=self.env["SUPREME_MIND_MANIFEST_BUCKET"],
            Key=self.env["SUPREME_MIND_MANIFEST_KEY"],
        )["Body"].read()
        if digest(raw) != EXPECTED_SOURCE_MANIFEST_RAW_SHA256:
            raise RuntimeError("LIVE_MANIFEST_RAW_SHA256_MISMATCH")
        live_manifest = json.loads(raw)
        if live_manifest.get("architecture_id") != ARCHITECTURE_ID:
            raise RuntimeError("LIVE_ARCHITECTURE_ID_MISMATCH")
        if len(live_manifest.get("roles", [])) != 59:
            raise RuntimeError("LIVE_ROLE_COUNT_NOT_59")
        for table in (self.env["SUPREME_MIND_TABLE"], self.env["SUPREME_MIND_RECEIPT_TABLE"]):
            if self.ddb.describe_table(TableName=table)["Table"]["TableStatus"] != "ACTIVE":
                raise RuntimeError("LIVE_TABLE_NOT_ACTIVE:" + table)
        attributes = self.sqs.get_queue_attributes(
            QueueUrl=self.env["SUPREME_MIND_QUEUE_URL"],
            AttributeNames=["QueueArn", "VisibilityTimeout"],
        )["Attributes"]
        self.queue_arn = attributes["QueueArn"]
        self.queue_previous_visibility_timeout = int(attributes.get("VisibilityTimeout", "30"))
        health = self.lambda_client.invoke(
            FunctionName=GOVERNOR_FUNCTION,
            InvocationType="RequestResponse",
            Payload=json.dumps({"operation": "health"}).encode(),
        )
        health_payload = json.loads(health["Payload"].read())
        health_body = json.loads(health_payload.get("body", "{}"))
        if health_body.get("state") != "PERMIT" or health_body.get("role_count") != 59:
            raise RuntimeError("LIVE_GOVERNOR_HEALTH_NOT_PERMIT")
        print(f"  PERMIT: account {self.account}, {self.region}, 59 live faculties")

    def ensure_role(self, name: str, trust: dict[str, Any], policy: dict[str, Any]) -> str:
        try:
            response = self.iam.get_role(RoleName=name)
            arn = response["Role"]["Arn"]
            self.iam.update_assume_role_policy(
                RoleName=name,
                PolicyDocument=json.dumps(trust),
            )
        except self.iam.exceptions.NoSuchEntityException:
            response = self.iam.create_role(
                RoleName=name,
                AssumeRolePolicyDocument=json.dumps(trust),
                Description="Supreme Computation Shadow Clone v1",
                Tags=[{"Key": "Architecture", "Value": ARCHITECTURE_ID}],
            )
            arn = response["Role"]["Arn"]
        self.iam.put_role_policy(
            RoleName=name,
            PolicyName="shadow-clone-v1",
            PolicyDocument=json.dumps(policy),
        )
        return arn

    def remote_build_browser_image(self, repository_uri: str, tag: str, source_hash: str) -> None:
        """Build in AWS when the laptop has no usable Docker/buildx installation."""

        source_key = f"build-inputs/shadow-clone/browser-{source_hash}.zip"
        temp_root = Path(tempfile.mkdtemp(prefix="shadow-clone-codebuild-"))
        source_zip = temp_root / "browser.zip"
        try:
            with zipfile.ZipFile(source_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in sorted((SHADOW / "browser").rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(SHADOW / "browser"))
            self.s3.put_object(
                Bucket=self.env["SUPREME_MIND_MANIFEST_BUCKET"],
                Key=source_key,
                Body=source_zip.read_bytes(),
                Metadata={"sha256": file_digest(source_zip), "source-tree-sha256": source_hash},
            )
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

        trust = {
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow", "Principal": {"Service": "codebuild.amazonaws.com"}, "Action": "sts:AssumeRole"}],
        }
        repository_arn = f"arn:aws:ecr:{self.region}:{self.account}:repository/{ECR_REPOSITORY}"
        source_arn = f"arn:aws:s3:::{self.env['SUPREME_MIND_MANIFEST_BUCKET']}/{source_key}"
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {"Effect": "Allow", "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"], "Resource": "*"},
                {"Effect": "Allow", "Action": ["s3:GetObject", "s3:GetObjectVersion"], "Resource": source_arn},
                {"Effect": "Allow", "Action": ["ecr:GetAuthorizationToken"], "Resource": "*"},
                {"Effect": "Allow", "Action": [
                    "ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage", "ecr:InitiateLayerUpload",
                    "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage"
                ], "Resource": repository_arn},
            ],
        }
        role_arn = self.ensure_role(CODEBUILD_ROLE, trust, policy)
        time.sleep(8)
        buildspec = """version: 0.2
phases:
  pre_build:
    commands:
      - aws ecr get-login-password --region "$AWS_DEFAULT_REGION" | docker login --username AWS --password-stdin "$ECR_URI"
      - docker buildx create --use --name shadowclonebuilder || docker buildx use shadowclonebuilder
  build:
    commands:
      - docker buildx build --platform linux/arm64 --tag "$ECR_URI:$IMAGE_TAG" --push .
"""
        project = {
            "name": CODEBUILD_PROJECT,
            "description": "Immutable ARM64 browser body for SCQOS Shadow Clone v1",
            "source": {
                "type": "S3",
                "location": f"{self.env['SUPREME_MIND_MANIFEST_BUCKET']}/{source_key}",
                "buildspec": buildspec,
            },
            "artifacts": {"type": "NO_ARTIFACTS"},
            "environment": {
                "type": "LINUX_CONTAINER",
                "computeType": "BUILD_GENERAL1_SMALL",
                "image": "aws/codebuild/standard:7.0",
                "privilegedMode": True,
                "environmentVariables": [
                    {"name": "ECR_URI", "value": repository_uri, "type": "PLAINTEXT"},
                    {"name": "IMAGE_TAG", "value": tag, "type": "PLAINTEXT"},
                ],
            },
            "serviceRole": role_arn,
            "timeoutInMinutes": 30,
            "queuedTimeoutInMinutes": 30,
            "tags": [{"key": "Architecture", "value": ARCHITECTURE_ID}],
        }
        existing = self.codebuild.batch_get_projects(names=[CODEBUILD_PROJECT]).get("projects", [])
        if existing:
            self.codebuild.update_project(**project)
        else:
            self.codebuild.create_project(**project)
        build_id = self.codebuild.start_build(projectName=CODEBUILD_PROJECT)["build"]["id"]
        build = wait_until(
            "REMOTE_BROWSER_BUILD",
            lambda: self.codebuild.batch_get_builds(ids=[build_id])["builds"][0],
            lambda value: value.get("buildStatus") == "SUCCEEDED",
            lambda value: value.get("buildStatus") in ("FAILED", "FAULT", "STOPPED", "TIMED_OUT"),
            timeout=1800,
        )
        print("  PERMIT: remote build " + build["id"])

    def build_browser_image(self) -> str:
        print("[3/8] Building immutable internet browser body")
        browser_files = [path for path in (SHADOW / "browser").rglob("*") if path.is_file()]
        source_hash = tree_digest(browser_files)
        tag = "sc-" + source_hash[:20]
        try:
            repo = self.ecr.describe_repositories(repositoryNames=[ECR_REPOSITORY])["repositories"][0]
        except self.ecr.exceptions.RepositoryNotFoundException:
            repo = self.ecr.create_repository(
                repositoryName=ECR_REPOSITORY,
                imageTagMutability="IMMUTABLE",
                imageScanningConfiguration={"scanOnPush": True},
                tags=[{"Key": "Architecture", "Value": ARCHITECTURE_ID}],
            )["repository"]
        repository_uri = repo["repositoryUri"]
        try:
            detail = self.ecr.describe_images(
                repositoryName=ECR_REPOSITORY,
                imageIds=[{"imageTag": tag}],
            )["imageDetails"][0]
        except self.ecr.exceptions.ImageNotFoundException:
            local_docker = shutil.which("docker") is not None
            if local_docker:
                try:
                    run(["docker", "buildx", "version"])
                    auth = self.ecr.get_authorization_token()["authorizationData"][0]
                    username, password = base64.b64decode(auth["authorizationToken"]).decode().split(":", 1)
                    run(["docker", "login", "--username", username, "--password-stdin", auth["proxyEndpoint"]], stdin=password)
                    run([
                        "docker", "buildx", "build",
                        "--platform", "linux/arm64",
                        "--tag", f"{repository_uri}:{tag}",
                        "--push",
                        str(SHADOW / "browser"),
                    ])
                except RuntimeError as exc:
                    print("  HOLD: local Docker unavailable; using AWS CodeBuild: " + str(exc).splitlines()[0])
                    self.remote_build_browser_image(repository_uri, tag, source_hash)
            else:
                print("  HOLD: Docker not installed; using AWS CodeBuild")
                self.remote_build_browser_image(repository_uri, tag, source_hash)
            detail = self.ecr.describe_images(
                repositoryName=ECR_REPOSITORY,
                imageIds=[{"imageTag": tag}],
            )["imageDetails"][0]
        self.image_digest = detail["imageDigest"]
        self.image_uri = repository_uri + "@" + self.image_digest
        print("  PERMIT: " + self.image_uri)
        return self.image_uri

    def deploy_harness(self) -> str:
        print("[4/8] Deploying Supreme Mind internet Harness")
        trust = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                "Action": "sts:AssumeRole",
                "Condition": {"StringEquals": {"aws:SourceAccount": self.account}},
            }],
        }
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {"Effect": "Allow", "Action": ["ecr:GetAuthorizationToken"], "Resource": "*"},
                {"Effect": "Allow", "Action": ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"], "Resource": f"arn:aws:ecr:{self.region}:{self.account}:repository/{ECR_REPOSITORY}"},
                {"Effect": "Allow", "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"], "Resource": "*"},
                {"Effect": "Allow", "Action": [
                    "bedrock-agentcore:StartBrowserSession", "bedrock-agentcore:GetBrowserSession",
                    "bedrock-agentcore:StopBrowserSession", "bedrock-agentcore:ListBrowserSessions",
                    "bedrock-agentcore:ConnectBrowserAutomationStream", "bedrock-agentcore:ConnectBrowserLiveViewStream",
                    "bedrock-agentcore:UpdateBrowserStream", "bedrock-agentcore:GetBrowser",
                    "bedrock-agentcore:ListBrowsers"
                ], "Resource": "*"},
                {"Effect": "Allow", "Action": ["s3:PutObject", "s3:GetObject", "s3:ListMultipartUploadParts", "s3:AbortMultipartUpload"], "Resource": f"arn:aws:s3:::{self.env['SUPREME_MIND_MANIFEST_BUCKET']}/*"},
                {"Effect": "Allow", "Action": ["s3:ListBucket"], "Resource": f"arn:aws:s3:::{self.env['SUPREME_MIND_MANIFEST_BUCKET']}"},
                {"Effect": "Allow", "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"], "Resource": "*"},
            ],
        }
        role_arn = self.ensure_role(HARNESS_ROLE, trust, policy)
        time.sleep(8)

        existing_browser = None
        token = None
        while True:
            kwargs = {"nextToken": token} if token else {}
            page = self.agent_control.list_browsers(**kwargs)
            for summary in page.get("browserSummaries", []):
                if summary.get("name") == BROWSER_NAME:
                    existing_browser = summary
                    break
            if existing_browser or not page.get("nextToken"):
                break
            token = page["nextToken"]
        if existing_browser:
            browser_id = existing_browser["browserId"]
        else:
            created_browser = self.agent_control.create_browser(
                name=BROWSER_NAME,
                description="Recorded public-internet body for SCQOS Shadow Clone v1",
                executionRoleArn=role_arn,
                networkConfiguration={"networkMode": "PUBLIC"},
                recording={
                    "enabled": True,
                    "s3Location": {
                        "bucket": self.env["SUPREME_MIND_MANIFEST_BUCKET"],
                        "prefix": "browser-recordings/shadow-clone-v1/",
                    },
                },
                clientToken=str(uuid.uuid4()),
                tags={"Architecture": ARCHITECTURE_ID, "Protocol": SHADOW_PROTOCOL},
            )
            browser_id = created_browser["browserId"]
        self.browser = wait_until(
            "RECORDED_BROWSER",
            lambda: self.agent_control.get_browser(browserId=browser_id),
            lambda item: item.get("status") == "READY",
            lambda item: str(item.get("status", "")).endswith("FAILED"),
        )
        if not self.browser.get("recording", {}).get("enabled"):
            raise RuntimeError("BROWSER_SESSION_RECORDING_NOT_ENABLED")
        expected_prefix = "browser-recordings/shadow-clone-v1/"
        recording = self.browser.get("recording", {}).get("s3Location", {})
        if (
            recording.get("bucket") != self.env["SUPREME_MIND_MANIFEST_BUCKET"]
            or recording.get("prefix") != expected_prefix
        ):
            raise RuntimeError("BROWSER_RECORDING_DESTINATION_MISMATCH")

        system_prompt = (SHADOW / "system_prompt.md").read_text()
        config = {
            "executionRoleArn": role_arn,
            "environmentArtifact": {"containerConfiguration": {"containerUri": self.image_uri}},
            "environmentVariables": {
                "SHADOW_CLONE_BROWSER_ID": self.browser["browserId"],
                "SHADOW_CLONE_BROWSER_ARN": self.browser["browserArn"],
                "SHADOW_CLONE_BROWSER_RECORDING": "true",
            },
            "model": {"bedrockModelConfig": {"modelId": self.args.model_id, "maxTokens": 8192}},
            "systemPrompt": [{"text": system_prompt}],
            "tools": [{"type": "agentcore_browser", "name": "browser", "config": {"agentCoreBrowser": {"browserArn": self.browser["browserArn"]}}}],
            "skills": [{"path": ".agents/skills/playwright-cli"}],
            "maxIterations": 80,
            "maxTokens": 8192,
            "timeoutSeconds": 840,
        }
        existing = None
        token = None
        while True:
            kwargs = {"nextToken": token} if token else {}
            page = self.agent_control.list_harnesses(**kwargs)
            for summary in page.get("harnesses", []):
                if summary.get("harnessName") == HARNESS_NAME:
                    existing = summary
                    break
            if existing or not page.get("nextToken"):
                break
            token = page["nextToken"]
        if existing:
            harness_id = existing["harnessId"]
            current = self.agent_control.get_harness(harnessId=harness_id)["harness"]
            if current.get("status") in ("CREATING", "UPDATING"):
                wait_until(
                    "HARNESS_PREVIOUS_OPERATION",
                    lambda: self.agent_control.get_harness(harnessId=harness_id)["harness"],
                    lambda item: item.get("status") == "READY",
                    lambda item: str(item.get("status", "")).endswith("FAILED"),
                )
            update_config = dict(config)
            update_config["environmentArtifact"] = {
                "optionalValue": config["environmentArtifact"]
            }
            response = self.agent_control.update_harness(
                harnessId=harness_id,
                clientToken=str(uuid.uuid4()),
                **update_config,
            )
        else:
            response = self.agent_control.create_harness(
                harnessName=HARNESS_NAME,
                clientToken=str(uuid.uuid4()),
                tags={"Architecture": ARCHITECTURE_ID, "Protocol": SHADOW_PROTOCOL},
                **config,
            )
        created = response["harness"]
        harness_id = created["harnessId"]
        self.harness = wait_until(
            "HARNESS",
            lambda: self.agent_control.get_harness(harnessId=harness_id)["harness"],
            lambda item: item.get("status") == "READY",
            lambda item: str(item.get("status", "")).endswith("FAILED"),
        )
        print("  PERMIT: " + self.harness["arn"])
        return self.harness["arn"]

    def build_lambda_zip(self) -> Path:
        temp_root = Path(tempfile.mkdtemp(prefix="shadow-clone-lambda-"))
        package = temp_root / "package"
        package.mkdir()
        shutil.copy2(SHADOW / "executor.py", package / "executor.py")
        shutil.copy2(SHADOW / "protocol.py", package / "protocol.py")
        run([
            sys.executable, "-m", "pip", "install",
            "--quiet", "--disable-pip-version-check",
            "--target", str(package),
            "boto3==1.43.82",
        ])
        zip_path = temp_root / "shadow-clone-executor.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(package.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(package))
        self.lambda_zip_sha256 = file_digest(zip_path)
        return zip_path

    def deploy_executor(self) -> str:
        print("[5/8] Attaching Shadow Clone executor to the existing SCQOS action plane")
        if self.queue_previous_visibility_timeout < 5400:
            self.sqs.set_queue_attributes(
                QueueUrl=self.env["SUPREME_MIND_QUEUE_URL"],
                Attributes={"VisibilityTimeout": "5400"},
            )
        trust = {
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}],
        }
        state_arn = f"arn:aws:dynamodb:{self.region}:{self.account}:table/{self.env['SUPREME_MIND_TABLE']}"
        receipt_arn = f"arn:aws:dynamodb:{self.region}:{self.account}:table/{self.env['SUPREME_MIND_RECEIPT_TABLE']}"
        manifest_arn = f"arn:aws:s3:::{self.env['SUPREME_MIND_MANIFEST_BUCKET']}/{self.env['SUPREME_MIND_MANIFEST_KEY']}"
        governor_arn = self.governor_config["FunctionArn"]
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {"Effect": "Allow", "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"], "Resource": "arn:aws:logs:*:*:*"},
                {"Effect": "Allow", "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query"], "Resource": [state_arn, receipt_arn]},
                {"Effect": "Allow", "Action": ["s3:GetObject"], "Resource": manifest_arn},
                {"Effect": "Allow", "Action": ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes", "sqs:ChangeMessageVisibility"], "Resource": self.queue_arn},
                {"Effect": "Allow", "Action": ["lambda:InvokeFunction"], "Resource": governor_arn},
                {"Effect": "Allow", "Action": ["bedrock-agentcore:InvokeAgentRuntime", "bedrock-agentcore:InvokeHarness", "bedrock-agentcore:InvokeHarness", "bedrock-agentcore:InvokeHarness"], "Resource": self.harness["arn"]},
            ],
        }
        role_arn = self.ensure_role(EXECUTOR_ROLE, trust, policy)
        time.sleep(8)
        zip_path = self.build_lambda_zip()
        code = zip_path.read_bytes()
        variables = {
            "SUPREME_MIND_TABLE": self.env["SUPREME_MIND_TABLE"],
            "SUPREME_MIND_RECEIPT_TABLE": self.env["SUPREME_MIND_RECEIPT_TABLE"],
            "SUPREME_MIND_MANIFEST_BUCKET": self.env["SUPREME_MIND_MANIFEST_BUCKET"],
            "SUPREME_MIND_MANIFEST_KEY": self.env["SUPREME_MIND_MANIFEST_KEY"],
            "SUPREME_MIND_MANIFEST_RAW_SHA256": EXPECTED_SOURCE_MANIFEST_RAW_SHA256,
            "SUPREME_MIND_GOVERNOR_FUNCTION": GOVERNOR_FUNCTION,
            "SHADOW_CLONE_HARNESS_ARN": self.harness["arn"],
            "SHADOW_CLONE_MAX_RESULT_CHARS": "60000",
        }
        try:
            self.lambda_client.get_function(FunctionName=EXECUTOR_FUNCTION)
            self.lambda_client.update_function_code(FunctionName=EXECUTOR_FUNCTION, ZipFile=code, Publish=True)
            wait_until(
                "EXECUTOR_CODE",
                lambda: self.lambda_client.get_function_configuration(FunctionName=EXECUTOR_FUNCTION),
                lambda item: item.get("LastUpdateStatus") == "Successful",
                lambda item: item.get("LastUpdateStatus") == "Failed",
            )
            self.lambda_client.update_function_configuration(
                FunctionName=EXECUTOR_FUNCTION,
                Role=role_arn,
                Handler="executor.lambda_handler",
                Runtime="python3.13",
                Timeout=900,
                MemorySize=2048,
                Environment={"Variables": variables},
            )
        except self.lambda_client.exceptions.ResourceNotFoundException:
            self.lambda_client.create_function(
                FunctionName=EXECUTOR_FUNCTION,
                Runtime="python3.13",
                Role=role_arn,
                Handler="executor.lambda_handler",
                Code={"ZipFile": code},
                Description="SCQOS-governed recursive internet executor for the 59-faculty Supreme Mind",
                Timeout=900,
                MemorySize=2048,
                Publish=True,
                Environment={"Variables": variables},
                Tags={"Architecture": ARCHITECTURE_ID, "Protocol": SHADOW_PROTOCOL},
            )
        config = wait_until(
            "EXECUTOR",
            lambda: self.lambda_client.get_function_configuration(FunctionName=EXECUTOR_FUNCTION),
            lambda item: item.get("State") == "Active" and item.get("LastUpdateStatus") == "Successful",
            lambda item: item.get("State") == "Failed" or item.get("LastUpdateStatus") == "Failed",
        )
        mappings = self.lambda_client.list_event_source_mappings(EventSourceArn=self.queue_arn).get("EventSourceMappings", [])
        ours = None
        for mapping in mappings:
            function_arn = mapping.get("FunctionArn", "")
            if function_arn.endswith(":" + EXECUTOR_FUNCTION):
                ours = mapping
            elif mapping.get("State") not in ("Disabled", "Disabling"):
                self.lambda_client.update_event_source_mapping(UUID=mapping["UUID"], Enabled=False)
                self.disabled_mappings.append({"uuid": mapping["UUID"], "function_arn": function_arn})
        if ours:
            self.lambda_client.update_event_source_mapping(
                UUID=ours["UUID"],
                Enabled=True,
                BatchSize=1,
                FunctionResponseTypes=["ReportBatchItemFailures"],
                ScalingConfig={"MaximumConcurrency": self.args.max_concurrency},
            )
            mapping_uuid = ours["UUID"]
        else:
            created = self.lambda_client.create_event_source_mapping(
                EventSourceArn=self.queue_arn,
                FunctionName=EXECUTOR_FUNCTION,
                Enabled=True,
                BatchSize=1,
                FunctionResponseTypes=["ReportBatchItemFailures"],
                ScalingConfig={"MaximumConcurrency": self.args.max_concurrency},
            )
            mapping_uuid = created["UUID"]
        wait_until(
            "ACTION_PLANE_MAPPING",
            lambda: self.lambda_client.get_event_source_mapping(UUID=mapping_uuid),
            lambda item: item.get("State") == "Enabled",
            lambda item: item.get("State") in ("Failed", "Deleting"),
        )
        print("  PERMIT: " + config["FunctionArn"])
        return config["FunctionArn"]

    def submit_live_qualification(self) -> dict[str, Any]:
        print("[6/8] Applying Supreme Computation to live internet data")
        qualification_started_at = datetime.now(timezone.utc)
        task_nonce = str(uuid.uuid4())
        event = {
            "principal_id": "SOVEREIGN_HUMAN",
            "business_id": "supreme-sports-shadow",
            "role_id": "R15",
            "intent": "Prove that an admitted Shadow Clone can independently observe a current official sports source through its internet body.",
            "action": "search",
            "tool": "shadow-clone-internet-body",
            "evidence_refs": ["https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=2026-08-30", "sc:qualification:" + task_nonce],
            "arguments": {
                "objective": "Open the official MLB schedule at https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=2026-08-30, report the page title and one directly observed current schedule fact, and cite only that direct page. Do not create child clones.",
                "expected_output": "A current official-source observation with URL, observation time, invariant assessment, and consequence.",
                "constraints": ["read-only", "official-source-only", "no-child-clones", "no-guesses"],
            },
        }
        response = self.lambda_client.invoke(
            FunctionName=GOVERNOR_FUNCTION,
            InvocationType="RequestResponse",
            Payload=json.dumps(event).encode(),
        )
        envelope = json.loads(response["Payload"].read())
        body = json.loads(envelope.get("body", "{}"))
        if body.get("state") != "PERMIT" or not body.get("queue_message_id"):
            raise RuntimeError("LIVE_QUALIFICATION_NOT_ADMITTED:" + json.dumps(body, default=str))
        task_id = body["receipt_id"]
        table = self.session.resource("dynamodb").Table(self.env["SUPREME_MIND_TABLE"])

        def task_state():
            response = table.query(
                KeyConditionExpression="pk = :pk",
                ExpressionAttributeValues={":pk": "TASK#" + task_id},
            )
            items = response.get("Items", [])
            return items[0] if items else {"state": "QUEUED", "task_id": task_id}

        item = wait_until(
            "LIVE_INTERNET_QUALIFICATION",
            task_state,
            lambda value: value.get("state") == "COMPLETED" and value.get("decision_state") == "PERMIT",
            lambda value: value.get("state") in ("FAILED", "REJECT")
            or (value.get("state") == "COMPLETED" and value.get("decision_state") != "PERMIT"),
            timeout=900,
        )
        if item.get("decision_state") != "PERMIT":
            raise RuntimeError("LIVE_QUALIFICATION_CONSEQUENCE_NOT_PERMIT:" + json.dumps(item, default=str))
        receipt_table = self.session.resource("dynamodb").Table(
            self.env["SUPREME_MIND_RECEIPT_TABLE"]
        )
        consequence_receipt = receipt_table.get_item(
            Key={"receipt_id": item["consequence_receipt_id"]},
            ConsistentRead=True,
        ).get("Item")
        if not consequence_receipt or consequence_receipt.get("state") != "PERMIT":
            raise RuntimeError("LIVE_CONSEQUENCE_RECEIPT_NOT_PERMIT")
        claimed_receipt_hash = consequence_receipt.get("receipt_sha256")
        receipt_for_hash = {
            key: value for key, value in consequence_receipt.items() if key != "receipt_sha256"
        }
        from shadow_clone.executor import receipt_sha256 as _sc_receipt_sha256
        actual_receipt_hash = _sc_receipt_sha256(receipt_for_hash)
        if claimed_receipt_hash != actual_receipt_hash:
            raise RuntimeError("LIVE_CONSEQUENCE_RECEIPT_SHA256_MISMATCH")

        def recording_state():
            page = self.s3.list_objects_v2(
                Bucket=self.env["SUPREME_MIND_MANIFEST_BUCKET"],
                Prefix="browser-recordings/shadow-clone-v1/",
            )
            objects = []
            for value in page.get("Contents", []):
                modified = value.get("LastModified")
                if modified and modified >= qualification_started_at:
                    objects.append({
                        "key": value["Key"],
                        "size": value["Size"],
                        "etag": value.get("ETag", "").strip('"'),
                        "last_modified": modified.isoformat(),
                    })
            return {"state": "PERMIT" if objects else "WAITING", "objects": objects}

        import boto3 as _sc_boto3
        _sc_dp = _sc_boto3.client("bedrock-agentcore", region_name=self.args.region)
        _sc_sessions = _sc_dp.list_browser_sessions(
            browserIdentifier=self.browser["browserId"], status="READY"
        ).get("items", [])
        for _sc_sess in _sc_sessions:
            _sc_dp.stop_browser_session(
                browserIdentifier=self.browser["browserId"],
                sessionId=_sc_sess["sessionId"],
            )
        recording = wait_until(
            "BROWSER_RECORDING",
            recording_state,
            lambda value: value.get("state") == "PERMIT",
            lambda value: False,
            timeout=180,
        )
        self.browser_recordings = recording["objects"]
        self.qualification = {
            "admission": body,
            "task": item,
            "consequence_receipt": consequence_receipt,
            "browser_recordings": self.browser_recordings,
        }
        print("  PERMIT: live official sports source observed by Shadow Clone")
        return self.qualification

    def write_evidence(self) -> Path:
        print("[7/8] Freezing deployment and live qualification receipts")
        timestamp = utc()
        evidence = ROOT / "evidence" / "shadow-clone" / timestamp
        evidence.mkdir(parents=True, exist_ok=False)
        receipt = {
            "architecture_id": ARCHITECTURE_ID,
            "protocol": SHADOW_PROTOCOL,
            "deployed_at_utc": timestamp,
            "aws_account": self.account,
            "aws_region": self.region,
            "source_manifest_raw_sha256": EXPECTED_SOURCE_MANIFEST_RAW_SHA256,
            "shadow_manifest_sha256": file_digest(SHADOW_MANIFEST_PATH),
            "browser_image_uri": self.image_uri,
            "browser_image_digest": self.image_digest,
            "browser_id": self.browser.get("browserId"),
            "browser_arn": self.browser.get("browserArn"),
            "browser_recording": self.browser.get("recording"),
            "harness_id": self.harness.get("harnessId"),
            "harness_arn": self.harness.get("arn"),
            "harness_version": self.harness.get("harnessVersion"),
            "executor_function": EXECUTOR_FUNCTION,
            "executor_zip_sha256": self.lambda_zip_sha256,
            "action_queue_arn": self.queue_arn,
            "action_queue_previous_visibility_timeout": self.queue_previous_visibility_timeout,
            "action_queue_visibility_timeout": 5400,
            "disabled_previous_mappings": self.disabled_mappings,
            "max_concurrency": self.args.max_concurrency,
            "live_qualification": self.qualification,
            "state": "PERMIT",
            "reason": "SHADOW_CLONE_INTERNET_BODY_EXECUTED_LIVE_OFFICIAL_SOURCE_TASK",
        }
        receipt["receipt_sha256"] = digest(receipt)
        (evidence / "SHADOW_CLONE_DEPLOYMENT_RECEIPT.json").write_text(json.dumps(receipt, indent=2, default=str) + "\n")
        (evidence / "VERIFY.py").write_text(
            "#!/usr/bin/env python3\n"
            "import hashlib,json,pathlib\n"
            "p=pathlib.Path(__file__).parent\n"
            "r=json.loads((p/'SHADOW_CLONE_DEPLOYMENT_RECEIPT.json').read_text())\n"
            "claimed=r.pop('receipt_sha256')\n"
            "raw=json.dumps(r,sort_keys=True,separators=(',',':'),default=str).encode()\n"
            "actual=hashlib.sha256(raw).hexdigest()\n"
            "assert actual==claimed,(actual,claimed)\n"
            "print('PERMIT: Shadow Clone deployment receipt identity verified')\n"
        )
        os.chmod(evidence / "VERIFY.py", 0o755)
        sums = []
        for path in sorted(evidence.iterdir()):
            if path.name != "SHA256SUMS":
                sums.append(f"{file_digest(path)}  {path.name}")
        (evidence / "SHA256SUMS").write_text("\n".join(sums) + "\n")
        run([sys.executable, str(evidence / "VERIFY.py")])
        s3_prefix = f"architecture/{ARCHITECTURE_ID}/shadow-clone/{timestamp}"
        for path in evidence.iterdir():
            self.s3.put_object(
                Bucket=self.env["SUPREME_MIND_MANIFEST_BUCKET"],
                Key=s3_prefix + "/" + path.name,
                Body=path.read_bytes(),
                Metadata={"sha256": file_digest(path), "protocol": "shadow-clone-v1"},
            )
        self.evidence_dir = evidence
        print("  PERMIT: " + str(evidence))
        return evidence

    def publish(self) -> str | None:
        print("[8/8] Publishing exact Shadow Clone code and evidence")
        if not self.args.publish:
            print("  HOLD: --publish not selected; cloud deployment remains live and evidence remains local/S3")
            return None
        run(["git", "fetch", "origin"], cwd=ROOT)
        temp = Path(tempfile.mkdtemp(prefix="shadow-clone-publish-"))
        worktree = temp / "repo"
        try:
            run(["git", "worktree", "add", "--detach", str(worktree), "origin/main"], cwd=ROOT)
            for relative in (
                Path(".gitignore"),
                Path("shadow_clone"),
                Path("tools/deploy_shadow_clone.py"),
                Path("tests/test_shadow_clone_protocol.py"),
                self.evidence_dir.relative_to(ROOT),
            ):
                source = ROOT / relative
                target = worktree / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if source.is_dir():
                    shutil.copytree(source, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
                else:
                    shutil.copy2(source, target)
            run(["git", "add", ".gitignore", "shadow_clone", "tools/deploy_shadow_clone.py", "tests/test_shadow_clone_protocol.py", str(self.evidence_dir.relative_to(ROOT))], cwd=worktree)
            if not run(["git", "status", "--porcelain"], cwd=worktree):
                print("  PERMIT: public main already contains the exact deployment")
                return run(["git", "rev-parse", "HEAD"], cwd=worktree)
            run(["git", "commit", "-m", "Deploy SCQOS Shadow Clone v1"], cwd=worktree)
            commit = run(["git", "rev-parse", "HEAD"], cwd=worktree)
            run(["git", "push", "origin", "HEAD:main"], cwd=worktree)
            print("  PERMIT: public main advanced to " + commit)
            return commit
        finally:
            try:
                run(["git", "worktree", "remove", "--force", str(worktree)], cwd=ROOT)
            except Exception:
                pass
            shutil.rmtree(temp, ignore_errors=True)

    def execute(self) -> None:
        self.verify_local_source()
        self.verify_aws_and_live_architecture()
        self.build_browser_image()
        self.deploy_harness()
        self.deploy_executor()
        self.submit_live_qualification()
        evidence = self.write_evidence()
        commit = self.publish()
        print("\nSHADOW CLONE: PERMIT")
        print("Architecture:", ARCHITECTURE_ID)
        print("Prime faculties: 59")
        print("Recursive internet executor:", EXECUTOR_FUNCTION)
        print("Harness:", self.harness.get("arn"))
        print("Evidence:", evidence)
        if commit:
            print("Public commit:", commit)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deploy SCQOS Shadow Clone v1")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", DEFAULT_REGION))
    parser.add_argument("--model-id", default=os.getenv("SHADOW_CLONE_MODEL_ID", DEFAULT_MODEL))
    parser.add_argument("--max-concurrency", type=int, default=10)
    parser.add_argument("--publish", action="store_true", help="Commit and push exact code/evidence through an isolated worktree")
    args = parser.parse_args()
    if not 2 <= args.max_concurrency <= 100:
        parser.error("--max-concurrency must be between 2 and 100")
    return args


if __name__ == "__main__":
    Deployment(parse_args()).execute()
