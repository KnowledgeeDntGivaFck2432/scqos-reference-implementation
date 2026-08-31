#!/usr/bin/env python3
# Derived from aws-samples/sample-playwright-cli-browser-agent-on-bedrock-agentcore
# commit 0c04fb491cd981db464618108bfb770d0f41a0ad (MIT-0).

import argparse
import json
import os

from bedrock_agentcore.tools.browser_client import BrowserClient


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument(
        "--browser-id",
        default=os.getenv("SHADOW_CLONE_BROWSER_ID", "aws.browser.v1"),
    )
    args = parser.parse_args()
    client = BrowserClient(region=args.region)
    client.start(identifier=args.browser_id)
    ws_url, headers = client.generate_ws_headers()
    config = {
        "browser": {
            "cdpEndpoint": ws_url,
            "cdpHeaders": dict(headers),
            "cdpTimeout": 30000,
        },
        "sessionId": client.session_id,
        "browserId": client.identifier,
    }
    os.makedirs(".playwright", exist_ok=True)
    with open(".playwright/cli.config.json", "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
    print(json.dumps({"session_id": client.session_id, "state": "PERMIT"}))


if __name__ == "__main__":
    main()
