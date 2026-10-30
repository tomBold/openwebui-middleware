#!/usr/bin/env bash
set -euo pipefail

port="${MIDDLEWARE_PORT:-8000}"
base="http://localhost:${port}"

echo "GET ${base}/health"
curl -fsS "${base}/health"
echo

echo "GET ${base}/ready"
curl -fsS "${base}/ready"
echo

echo "GET ${base}/v1/models"
models="$(curl -fsS "${base}/v1/models")"
echo "${models}"
model="$(printf '%s' "${models}" | grep -o '"id":"[^"]*"' | head -n 1 | cut -d'"' -f4)"

echo "POST ${base}/v1/chat/completions (streaming, model=${model})"
curl -fsS -N "${base}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"${model}\",\"stream\":true,\"messages\":[{\"role\":\"user\",\"content\":\"Invoice INV-2024-881 from Globex, due 2024-05-01, total 1,250.00 USD\"}]}"
echo
