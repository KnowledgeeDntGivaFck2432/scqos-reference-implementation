#!/usr/bin/env bash
# Derived from aws-samples/sample-playwright-cli-browser-agent-on-bedrock-agentcore
# commit 0c04fb491cd981db464618108bfb770d0f41a0ad (MIT-0).
set -euo pipefail
region="${1:-us-east-1}"
config_path=".playwright/cli.config.json"
playwright-cli close >/dev/null 2>&1 || true
if [ -f "$config_path" ]; then
  session_id="$(python3 -c "import json; print(json.load(open('$config_path')).get('sessionId',''))")"
  if [ -n "$session_id" ]; then
    browser_id="$(python3 -c "import json; print(json.load(open('$config_path')).get('browserId','aws.browser.v1'))")"
    python3 - "$region" "$browser_id" "$session_id" <<'PY'
import boto3, sys
boto3.client("bedrock-agentcore", region_name=sys.argv[1]).stop_browser_session(
    browserIdentifier=sys.argv[2], sessionId=sys.argv[3]
)
PY
  fi
  rm -f "$config_path"
fi
