# Runbook

Every step is non-interactive and prints something you can check, so it works the same for a person pasting commands or an automation following them. Only Docker is needed. Commands are bash; PowerShell equivalents are noted where they differ.

## 1. Check the prerequisites

```bash
docker --version && docker compose version && docker info --format '{{.ServerVersion}}'
```

Expect three version strings. If the last command fails, Docker Desktop is not running.

## 2. Start the stack

```bash
git clone https://github.com/tomBold/openwebui-middleware.git && cd openwebui-middleware
OPENAI_API_KEY=sk-... ./scripts/start.sh
```

PowerShell: `$env:OPENAI_API_KEY = "sk-..."; powershell -File scripts/start.ps1`

With the key in the environment the script never prompts. Expect, after the build, the lines:

```text
Waiting for middleware readiness ready
Open WebUI: http://localhost:3000
Middleware status: http://localhost:8000
```

If it ends with `failed`, see [Troubleshooting](#troubleshooting). The script waits for the middleware only; Open WebUI needs up to a minute more before it serves its first page.

## 3. Check the middleware

```bash
./scripts/smoke.sh
```

PowerShell: `& "C:\Program Files\Git\bin\bash.exe" scripts/smoke.sh`, or run the four requests from the README by hand.

Expect `{"status":"ok"}`, `{"status":"ready"}`, a model list, then a stream of `data:` lines containing the extraction JSON and ending with `data: [DONE]`.

Open <http://localhost:8000>: all three cards show a green dot and Send returns formatted JSON.

## 4. Check it through Open WebUI

Open <http://localhost:3000>, pick a model, paste:

```text
Fwd: payment - Hi, attached the receipt from Cafe Luna, 14/03 2024, 2x espresso 9.00, 1 croissant 4.50, total 13.5 eur. paid by card ****4421. - Dana
```

Expect a JSON reply with `document_type: "receipt"` and a confidence per field. Then ask `what was the total?` and expect one sentence of prose citing the extracted amount. Confirm the request went through the middleware:

```bash
docker compose logs middleware | grep -c upstream.stream_completed
```

Expect a number of at least 2.

## 5. Run the unit tests, linter and type checker

```bash
make test-docker          # or: docker build --target test --progress=plain middleware
```

No local Python is used. Expect `35 passed, 1 skipped`, a coverage total above 90%, and an exit code of 0. The skipped test compares `SYSTEM_PROMPT.md` with the shipped prompt and needs the repository root, so it runs on the host and in CI. The same checks run on the host with `make check` if `uv` is installed; see the README.

## 6. Stop

```bash
docker compose down -v
```

Expect the three containers and two volumes to be removed. Delete or rotate the OpenAI key when done.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `start.sh` ends with `failed`, `/ready` returns `{"status":"upstream_unavailable"}` | OpenAI rejected the key, or it has no credit | `docker compose logs middleware` shows the upstream status. Fix the key in `.env`, then `docker compose up -d middleware`. |
| `port is already allocated` | 3000 or 8000 is in use | Change `OPEN_WEBUI_PORT` or `MIDDLEWARE_PORT` in `.env` and rerun the script; it prints the final URLs. |
| `401 Missing scopes: model.request` | Restricted key with a single child scope | Set the key to **All** permissions, see the README. |
| Open WebUI shows no models | It started before the middleware was ready | `docker compose restart open-webui`. |
| `smoke.sh: /bin/bash: No such file or directory` on Windows | `bash` resolves to WSL without a distro | Use the Git Bash path above. |
