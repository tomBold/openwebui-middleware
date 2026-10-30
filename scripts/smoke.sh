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
curl -fsS "${base}/v1/models"
echo

echo "POST ${base}/v1/chat/completions (streaming)"
curl -fsS -N "${base}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","stream":true,"messages":[{"role":"user","content":"Invoice INV-2024-881 from Globex, due 2024-05-01, total 1,250.00 USD"}]}'
echo
