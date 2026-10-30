#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
cat scripts/banner.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

if grep -q '^OPENAI_API_KEY=sk-replace-me$' .env; then
  key="${OPENAI_API_KEY:-}"
  if [ -z "$key" ]; then
    read -rsp "OpenAI API key: " key
    echo
  fi
  tmp=$(mktemp)
  sed "s|^OPENAI_API_KEY=.*|OPENAI_API_KEY=${key}|" .env >"$tmp" && mv "$tmp" .env
fi

docker compose up -d --build

middleware_port=$(grep -E '^MIDDLEWARE_PORT=' .env | cut -d= -f2 || echo 8000)
webui_port=$(grep -E '^OPEN_WEBUI_PORT=' .env | cut -d= -f2 || echo 3000)

middleware_url="http://localhost:${middleware_port}"
webui_url="http://localhost:${webui_port}"

wait_for() {
  printf 'Waiting for %s' "$1"
  for _ in $(seq 1 90); do
    if curl -fsS "$2" >/dev/null 2>&1; then
      echo " up"
      return 0
    fi
    printf '.'
    sleep 2
  done
  echo " failed"
  echo "$1 did not come up. Check: docker compose logs $3"
  exit 1
}

wait_for "middleware" "${middleware_url}/ready" middleware
wait_for "Open WebUI" "${webui_url}/health" open-webui

echo
echo "Middleware is up at ${middleware_url}"
echo "Open WebUI is up at ${webui_url}"
echo "Stop with: docker compose down"
