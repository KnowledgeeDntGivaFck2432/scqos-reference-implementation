#!/usr/bin/env python3

import json
import sys

from integration.universal_gateway import (
    TransitionRequest,
    govern_transition,
)

if len(sys.argv) != 2:
    raise SystemExit(
        "usage: python -m integration.scqos_transition request.json"
    )

with open(sys.argv[1], "r", encoding="utf-8") as f:
    request = TransitionRequest.model_validate(json.load(f))

result = govern_transition(request)

print(
    json.dumps(
        result.model_dump(mode="python"),
        indent=2,
        ensure_ascii=False,
    )
)

raise SystemExit(
    0 if result.decision == "PERMIT" else
    2 if result.decision == "HOLD" else
    3
)
