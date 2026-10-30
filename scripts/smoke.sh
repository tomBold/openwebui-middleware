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

sample='{"role":"user","content":"Invoice INV-2024-881 from Globex, due 2024-05-01, total 1,250.00 USD"}'

echo "POST ${base}/v1/chat/completions (streaming, model=${model})"
curl -fsS -N "${base}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"${model}\",\"stream\":true,\"messages\":[${sample}]}"
echo

webui="http://localhost:${OPEN_WEBUI_PORT:-3000}"
if ! curl -fsS "${webui}/health" >/dev/null 2>&1; then
  echo "Open WebUI not reachable at ${webui}, skipping the end-to-end step"
  exit 0
fi

echo "POST ${webui}/api/chat/completions (through Open WebUI, no system prompt in the request)"
token="$(curl -fsS -X POST "${webui}/api/v1/auths/signin" -H "Content-Type: application/json" -d '{"email":"","password":""}' | grep -o '"token":"[^"]*"' | cut -d'"' -f4)"
reply="$(curl -fsS "${webui}/api/chat/completions" \
  -H "Authorization: Bearer ${token}" -H "Content-Type: application/json" \
  -d "{\"model\":\"${model}\",\"stream\":false,\"messages\":[${sample}]}")"
printf '%s' "${reply}" | grep -q 'document_type' || { echo "reply is not the extraction envelope: ${reply}"; exit 1; }
echo "Open WebUI -> middleware -> OpenAI: ok, reply is the extraction envelope"
