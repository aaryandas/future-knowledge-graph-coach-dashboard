#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

base_url="${1:-http://127.0.0.1:18123}"
member_id="mbr_01HX9JORDAN"
database_url="${DATABASE_URL:-postgresql://postgres:postgres@127.0.0.1:55432/coach}"

DATABASE_URL="$database_url" PYTHONPATH=backend backend/.venv/bin/python -c \
  'from app.copilot.persistence import open_postgres_checkpointer; checkpointer_context = open_postgres_checkpointer(); checkpointer = checkpointer_context.__enter__(); checkpointer.delete_thread("mbr_01HX9JORDAN"); checkpointer_context.__exit__(None, None, None)'

labels=(profile barrier adherence-chart sleep-chart message-pattern-chart four-week-chart chart-follow-up)
expected_source_tools=(
  get_member_goals,get_member_profile
  get_morning_brief
  render_chart
  render_chart
  render_chart
  render_chart
  render_chart
)
expected_chart_kinds=(
  none
  none
  adherence_trend
  sleep_week
  message_pattern
  four_week_comparison
  four_week_comparison
)
expected_chart_windows=(none none 28-days 7-days 28-days 28-days 28-days)
brief_expected=(false true false false false false false)
questions=(
  "What is Jordan's primary goal and what equipment does she have available?"
  "What adherence Barriers should I know about for Jordan?"
  "Show Jordan's adherence trend as a chart."
  "Show Jordan's sleep this week as a chart."
  "Show Jordan's message pattern for the last 28 days as a chart."
  "Show Jordan's four-week adherence comparison as a chart."
  "What was the highest bar in that chart? Include its value and week."
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

  if ! events="$(
    sed -n '/^data: {/s/^data: //p' <<<"$response" | jq --slurp '.' 2>/dev/null
  )"; then
    events='[]'
  fi

  sources_valid="$(jq --raw-output \
    --arg expected "${expected_source_tools[$index]}" '
      [.[] | select(.type == "data-sources") | .data.sources] as $payloads
      | ($payloads | length) == 1
        and ($payloads[0] | type) == "array"
        and ($payloads[0] | length) > 0
        and all($payloads[0][];
          (.tool | type) == "string"
          and (.tool | length) > 0
          and (.node_ids | type) == "array"
          and (.node_ids | length) > 0
          and all(.node_ids[]; type == "string" and length > 0)
        )
        and (
          ($expected | split(",")) - [$payloads[0][].tool]
          | length
        ) == 0
    ' <<<"$events")"

  answer_valid="$(jq --raw-output '
    [.[] | select(.type == "text-delta") | (.delta // "")] | join("")
    | length > 0
      and contains("I could not answer that question. Please try again.") == false
      and contains("five retrieval tool rounds") == false
  ' <<<"$events")"

  chart_valid=not-expected
  expected_chart_kind="${expected_chart_kinds[$index]}"
  if [[ "$expected_chart_kind" != none ]]; then
    chart_valid="$(jq --raw-output \
      --arg kind "$expected_chart_kind" \
      --arg window "${expected_chart_windows[$index]}" '
      [.[] | select(.type == "data-chart") | .data] as $payloads
      | ($payloads | length) == 1
        and $payloads[0].kind == $kind
        and $payloads[0].window == $window
        and ($payloads[0].series | type) == "array"
        and ($payloads[0].series | length) > 0
        and ($payloads[0].observation_node_ids | type) == "array"
        and ($payloads[0].observation_node_ids | length) > 0
        and all($payloads[0].observation_node_ids[];
          type == "string" and length > 0
        )
        and ($payloads[0].axes | type) == "object"
        and ($payloads[0].axes.x | type) == "object"
        and ($payloads[0].axes.y | type) == "object"
    ' <<<"$events")"
  fi

  brief_valid=not-expected
  if [[ "${brief_expected[$index]}" == true ]]; then
    brief_valid="$(jq --raw-output '
      [.[] | select(.type == "data-brief") | .data] as $payloads
      | ($payloads | length) == 1
        and ($payloads[0].generated_for | type) == "string"
        and ($payloads[0].generated_for | length) > 0
        and ($payloads[0].barriers | type) == "array"
        and ($payloads[0].barriers | length) > 0
        and (
          ["adherence-decline", "work-fatigue"]
          - [$payloads[0].barriers[].kind]
          | length
        ) == 0
        and all($payloads[0].barriers[];
          (.kind | type) == "string"
          and (.kind | length) > 0
          and (.evidence_node_ids | type) == "array"
          and (.evidence_node_ids | length) > 0
          and all(.evidence_node_ids[]; type == "string" and length > 0)
        )
    ' <<<"$events")"
  fi

  if [[ "$index" == 6 && "$chart_valid" == true ]]; then
    answer_valid="$(jq --raw-output '
      [.[] | select(.type == "data-chart") | .data][0] as $chart
      | ($chart.series | map(.completion_percent) | max | tostring) as $maximum
      | ([.[] | select(.type == "text-delta") | (.delta // "")] | join(""))
        as $answer
      | $answer | contains($maximum)
    ' <<<"$events")"
  fi

  if [[ "$status" != 200 \
    || "$sources_valid" != true \
    || "$answer_valid" != true \
    || "$chart_valid" == false \
    || "$brief_valid" == false ]]; then
    invalid=$((invalid + 1))
  fi
  if awk -v elapsed="$elapsed" 'BEGIN { exit !(elapsed > 5.0) }'; then
    slow=$((slow + 1))
  fi

  printf '%-21s total=%ss status=%s sources=%s chart=%s brief=%s answer=%s\n' \
    "${labels[$index]}" "$elapsed" "$status" "$sources_valid" \
    "$chart_valid" "$brief_valid" "$answer_valid"
done

median="$(printf '%s\n' "${times[@]}" | sort -n | sed -n '4p')"
maximum="$(printf '%s\n' "${times[@]}" | sort -n | tail -1)"
printf 'summary median=%ss maximum=%ss over_5s=%s/7 invalid=%s\n' \
  "$median" "$maximum" "$slow" "$invalid"

if ((slow > 0 || invalid > 0)); then
  exit 1
fi
