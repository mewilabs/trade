#!/usr/bin/env python3
"""Optional Claude Code PreToolUse hook. Reads {"tool_input": {"rows": [...]}} on stdin; exit 2 blocks."""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agent.validate import validate_pick

rows = json.load(sys.stdin).get("tool_input", {}).get("rows", [])
errors = [e for r in rows for e in validate_pick(r, float(os.getenv("MIN_RR", 1.5)))]
counts = {}
for r in rows:
    counts[r.get("type")] = counts.get(r.get("type"), 0) + 1
errors += [f"{k}: {v} picks, max 2" for k, v in counts.items() if v > 2]
if errors:
    print("BLOCKED:\n" + "\n".join(errors), file=sys.stderr)
    sys.exit(2)
