#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

base_url="${1:-http://127.0.0.1:18123}"
member_id="mbr_01HX9JORDAN"
database_url="${DATABASE_URL:-postgresql://postgres:postgres@127.0.0.1:55432/coach}"

DATABASE_URL="$database_url" PYTHONPATH=backend backend/.venv/bin/python -c \
  'from app.copilot.persistence import open_postgres_checkpointer; c = open_postgres_checkpointer(); p = c.__enter__(); p.delete_thread("mbr_01HX9JORDAN"); c.__exit__(None, None, None)'

labels=(profile barrier adherence-chart sleep-chart message-pattern-chart four-week-chart profile-repeat)
chart_expected=(false false true true true true false)
questions=(
  "What is Jordan's primary goal and what equipment does she have available?"
  "What adherence Barriers should I know about for Jordan?"
  "Show Jordan's adherence trend as a chart."
  "Show Jordan's sleep this week as a chart."
  "Show Jordan's message pattern for the last 28 days as a chart."
  "Show Jordan's four-week adherence comparison as a chart."
  "What is Jordan's primary goal and what equipment does she have available?"
)

times=()
slow=0
invalid=0

for index in "${!questions[@]}"; do
  message_id="gnt291-$index"
  payload="$(jq -nc \
    --arg member "$member_id" \
    --arg message_id "$message_id" \
    --arg question "${questions[$index]}" \
    '{id: $member, messages: [{id: $message_id, role: "user", parts: [{type: "text", text: $question}]}]}')"
  combined="$(curl --silent --show-error --max-time 30 \
    --header 'Content-Type: application/json' \
    --data "$payload" \
    --write-out $'\n__META__:%{http_code} %{time_total}' \
    "$base_url/api/members/$member_id/copilot")"
  metadata="${combined##*$'\n__META__:'}"
  response="${combined%$'\n__META__:'*}"
  status="${metadata%% *}"
  elapsed="${metadata##* }"
  times+=("$elapsed")

  has_sources=false
  has_chart=false
  if grep -q '"type":"data-sources"' <<<"$response"; then
    has_sources=true
  fi
  if grep -q '"type":"data-chart"' <<<"$response"; then
    has_chart=true
  fi
  if [[ "$status" != 200 || "$has_sources" != true ]]; then
    invalid=$((invalid + 1))
  fi
  if [[ "${chart_expected[$index]}" == true && "$has_chart" != true ]]; then
    invalid=$((invalid + 1))
  fi
  if awk -v elapsed="$elapsed" 'BEGIN { exit !(elapsed > 5.0) }'; then
    slow=$((slow + 1))
  fi

  printf '%-21s total=%ss status=%s sources=%s chart=%s\n' \
    "${labels[$index]}" "$elapsed" "$status" "$has_sources" "$has_chart"
done

median="$(printf '%s\n' "${times[@]}" | sort -n | sed -n '4p')"
maximum="$(printf '%s\n' "${times[@]}" | sort -n | tail -1)"
printf 'summary median=%ss maximum=%ss over_5s=%s/7 invalid=%s\n' \
  "$median" "$maximum" "$slow" "$invalid"

if ((slow > 0 || invalid > 0)); then
  exit 1
fi
