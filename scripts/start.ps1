#Requires -Version 5.1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env from .env.example"
}

if ((Get-Content .env -Raw) -match "OPENAI_API_KEY=sk-replace-me") {
    $secure = Read-Host "OpenAI API key" -AsSecureString
    $key = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
    (Get-Content .env) -replace "^OPENAI_API_KEY=.*", "OPENAI_API_KEY=$key" | Set-Content .env
}

docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw "docker compose failed" }

function Get-EnvValue($name, $fallback) {
    $line = Select-String -Path .env -Pattern "^$name=(.*)$" | Select-Object -First 1
    if ($line) { $line.Matches[0].Groups[1].Value } else { $fallback }
}

$middlewarePort = Get-EnvValue "MIDDLEWARE_PORT" "8000"
$webuiPort = Get-EnvValue "OPEN_WEBUI_PORT" "3000"

Write-Host "Waiting for middleware readiness" -NoNewline
foreach ($attempt in 1..60) {
    try {
        Invoke-RestMethod "http://localhost:$middlewarePort/ready" -TimeoutSec 5 | Out-Null
        Write-Host " ready"
        Write-Host "Open WebUI: http://localhost:$webuiPort"
        Write-Host "Middleware status: http://localhost:$middlewarePort"
        exit 0
    }
    catch {
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 2
    }
}

Write-Host " failed"
Write-Host "Middleware did not become ready. Check: docker compose logs middleware"
exit 1
