#!/bin/bash
# usage: run_validator.sh <tag> [validator args...]; runs from /tmp with the pinned interpreter, isolated, no bytecode
O=<FORECAST_ROOT>/d-a39-lane-extract-20261101
V=<FORECAST_ROOT>/newperiod-gate-private-v1/venv/bin/python
tag=$1; shift
cd /tmp || exit 9
date -u +%Y-%m-%dT%H:%M:%SZ > "$O/out/validate-$tag.start"
/usr/bin/time -v "$V" -I -B "$O/scripts/validate_final_data.py" "$@" > "$O/out/validate-$tag.jsonl" 2> "$O/out/validate-$tag.err"
echo $? > "$O/out/validate-$tag.exit"
date -u +%Y-%m-%dT%H:%M:%SZ > "$O/out/validate-$tag.end"
