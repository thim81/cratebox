#!/bin/sh
set -eu

uv run --with fastapi --with uvicorn --with mutagen uvicorn server:app --port 8000 &
api_pid=$!

cleanup() {
  kill "$api_pid" 2>/dev/null || true
  wait "$api_pid" 2>/dev/null || true
}

trap cleanup EXIT INT TERM
npm run dev
