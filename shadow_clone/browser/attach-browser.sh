#!/usr/bin/env bash
# Derived from aws-samples/sample-playwright-cli-browser-agent-on-bedrock-agentcore
# commit 0c04fb491cd981db464618108bfb770d0f41a0ad (MIT-0).
set -euo pipefail
region="${1:-us-east-1}"
config_path=".playwright/cli.config.json"
script_dir="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$config_path" ]; then
  bash "$script_dir/close-browser.sh" "$region" >/dev/null 2>&1 || true
fi
python3 "$script_dir/cdp_connect.py" --region "$region"
ws_url="$(python3 -c "import json; print(json.load(open('$config_path'))['browser']['cdpEndpoint'])")"
playwright-cli attach --cdp="$ws_url" --config="$config_path"
