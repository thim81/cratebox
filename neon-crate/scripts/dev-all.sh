#!/bin/sh
set -eu

api_dir=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
mcp_dir=$(CDPATH= cd "$api_dir/../rekordbx-mcp" && pwd)
uv --directory "$mcp_dir" run --locked --with fastapi --with uvicorn --with mutagen \
  uvicorn --app-dir "$api_dir" server:app --port 8000 --reload &
api_pid=$!

cleanup() {
  kill "$api_pid" 2>/dev/null || true
  wait "$api_pid" 2>/dev/null || true
}

trap cleanup EXIT INT TERM
npm run dev
