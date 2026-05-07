#!/usr/bin/env bash
# Atlas host-mode smoke test.
#
# - Sources `.env` for ATLAS_BEARER_TOKEN
# - Hits /system/health on local API
# - Verifies /agents reports 5 agents in state=running
# - Pings Alpaca public clock endpoint
# - Prints PASS/FAIL summary; exits 0 on full pass, 1 otherwise.

set -u

ATLAS_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ATLAS_ROOT}/.env"
API_BASE="${ATLAS_API_BASE:-http://localhost:8000}"

green() { printf '\033[32m%s\033[0m' "$1"; }
red()   { printf '\033[31m%s\033[0m' "$1"; }
yellow(){ printf '\033[33m%s\033[0m' "$1"; }

PASS=0
FAIL=0
RESULTS=()

record() {
    local label="$1"
    local outcome="$2"
    local detail="${3:-}"
    if [[ "$outcome" == "PASS" ]]; then
        PASS=$((PASS+1))
        RESULTS+=("$(green PASS) ${label} ${detail}")
    else
        FAIL=$((FAIL+1))
        RESULTS+=("$(red FAIL) ${label} ${detail}")
    fi
}

# 1) Source .env without leaking values into the shell history
if [[ ! -f "$ENV_FILE" ]]; then
    echo "$(red FAIL) .env not found at $ENV_FILE — run scripts/gen_secrets.py"
    exit 1
fi
# shellcheck disable=SC1090
set -a
. "$ENV_FILE"
set +a

if [[ -z "${ATLAS_BEARER_TOKEN:-}" ]]; then
    echo "$(red FAIL) ATLAS_BEARER_TOKEN missing from .env"
    exit 1
fi

AUTH_HEADER="Authorization: Bearer ${ATLAS_BEARER_TOKEN}"

# 2) /system/health
health_body="$(curl -fsS -m 5 -H "$AUTH_HEADER" "${API_BASE}/system/health" 2>/dev/null || true)"
if [[ -n "$health_body" ]]; then
    record "api /system/health" "PASS" "(${API_BASE})"
else
    record "api /system/health" "FAIL" "(${API_BASE} unreachable or non-2xx)"
fi

# 3) /agents — expect 5 running
agents_body="$(curl -fsS -m 5 -H "$AUTH_HEADER" "${API_BASE}/agents" 2>/dev/null || true)"
if [[ -n "$agents_body" ]]; then
    running_count="$(printf '%s' "$agents_body" \
        | python -c 'import json,sys
try:
    data=json.load(sys.stdin)
    if isinstance(data, dict):
        data=data.get("agents", data.get("data", []))
    print(sum(1 for a in data if (a.get("state") or a.get("status")) == "running"))
except Exception:
    print(0)
' 2>/dev/null)"
    if [[ "$running_count" -ge 5 ]]; then
        record "/agents running count" "PASS" "(${running_count}/5)"
    else
        record "/agents running count" "FAIL" "(only ${running_count}/5 running)"
    fi
else
    record "/agents endpoint" "FAIL" "(no response)"
fi

# 4) Alpaca public clock — no auth needed for clock endpoint via paper API
alpaca_body="$(curl -fsS -m 5 https://paper-api.alpaca.markets/v2/clock \
    -H "APCA-API-KEY-ID: ${ALPACA_API_KEY:-}" \
    -H "APCA-API-SECRET-KEY: ${ALPACA_SECRET_KEY:-}" 2>/dev/null || true)"
if [[ -n "$alpaca_body" ]] && printf '%s' "$alpaca_body" | grep -q '"is_open"'; then
    alpaca_open="$(printf '%s' "$alpaca_body" \
        | python -c 'import json,sys
try:
    print(json.load(sys.stdin).get("is_open"))
except Exception:
    print("parse_error")
' 2>/dev/null)"
    record "alpaca clock" "PASS" "(is_open=${alpaca_open})"
else
    record "alpaca clock" "FAIL" "(no response or auth failed)"
fi

# Summary
echo ""
echo "Atlas smoke results:"
for line in "${RESULTS[@]}"; do
    echo "  $line"
done
echo ""
total=$((PASS + FAIL))
if [[ "$FAIL" -eq 0 ]]; then
    echo "$(green ALL_PASS) ${PASS}/${total}"
    exit 0
else
    echo "$(red FAIL) ${FAIL}/${total} failed"
    exit 1
fi
