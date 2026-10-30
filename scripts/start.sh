#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

if grep -q '^OPENAI_API_KEY=sk-replace-me$' .env; then
  read -rsp "OpenAI API key: " key
  echo
  tmp=$(mktemp)
  sed "s|^OPENAI_API_KEY=.*|OPENAI_API_KEY=${key}|" .env >"$tmp" && mv "$tmp" .env
fi

docker compose up -d --build

middleware_port=$(grep -E '^MIDDLEWARE_PORT=' .env | cut -d= -f2 || echo 8000)
webui_port=$(grep -E '^OPEN_WEBUI_PORT=' .env | cut -d= -f2 || echo 3000)

printf 'Waiting for middleware readiness'
for _ in $(seq 1 60); do
  if curl -fsS "http://localhost:${middleware_port}/ready" >/dev/null 2>&1; then
    echo " ready"
    echo "Open WebUI: http://localhost:${webui_port}"
    echo "Middleware status: http://localhost:${middleware_port}"
    exit 0
  fi
  printf '.'
  sleep 2
done

echo " failed"
echo "Middleware did not become ready. Check: docker compose logs middleware"
exit 1
