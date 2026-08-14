#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -d node_modules ]]; then
  pnpm install --frozen-lockfile
fi

if [[ ! -d frontend/node_modules ]]; then
  pnpm --dir frontend install --frozen-lockfile
fi

docker compose up -d --wait neo4j postgres

neo4j_address="$(docker compose port neo4j 7687)"
postgres_address="$(docker compose port postgres 5432)"

export NEO4J_URI="bolt://localhost:${neo4j_address##*:}"
export DATABASE_URL="postgresql://postgres:postgres@localhost:${postgres_address##*:}/coach"

exec pnpm exec concurrently -k -n api,web -c blue,green "pnpm dev:api" "pnpm dev:web"
