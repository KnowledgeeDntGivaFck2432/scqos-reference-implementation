#!/usr/bin/env bash
python3 ./scqos_supreme_stack.py | grep -q "SCQOS ONLINE"
if [ $? -eq 0 ]; then
  echo "SCQOS ENFORCEMENT: ALLOW -> $*"
  exec "$@"
else
  echo "SCQOS ENFORCEMENT: DENY -> $*"
  exit 126
fi
