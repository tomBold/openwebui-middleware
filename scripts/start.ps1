#Requires -Version 5.1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
Get-Content scripts/banner.txt

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env from .env.example"
}

if ((Get-Content .env -Raw) -match "OPENAI_API_KEY=sk-replace-me") {
    $key = $env:OPENAI_API_KEY
    if (-not $key) {
        $secure = Read-Host "OpenAI API key" -AsSecureString
        $key = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
    }
    (Get-Content .env) -replace "^OPENAI_API_KEY=.*", "OPENAI_API_KEY=$key" | Set-Content .env
}

docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw "docker compose failed" }

function Get-EnvValue($name, $fallback) {
    $line = Select-String -Path .env -Pattern "^$name=(.*)$" | Select-Object -First 1
    if ($line) { $line.Matches[0].Groups[1].Value } else { $fallback }
}

$middlewareUrl = "http://localhost:$(Get-EnvValue 'MIDDLEWARE_PORT' '8000')"
$webuiUrl = "http://localhost:$(Get-EnvValue 'OPEN_WEBUI_PORT' '3000')"

function Wait-ForService($name, $url, $service) {
    Write-Host "Waiting for $name" -NoNewline
    foreach ($attempt in 1..90) {
        try {
            Invoke-RestMethod $url -TimeoutSec 5 | Out-Null
            Write-Host " up"
            return
        }
        catch {
            Write-Host "." -NoNewline
            Start-Sleep -Seconds 2
        }
    }
    Write-Host " failed"
    Write-Host "$name did not come up. Check: docker compose logs $service"
    exit 1
}

Wait-ForService "middleware" "$middlewareUrl/ready" "middleware"
Wait-ForService "Open WebUI" "$webuiUrl/health" "open-webui"

Write-Host ""
Write-Host "Middleware is up at $middlewareUrl"
Write-Host "Open WebUI is up at $webuiUrl"
Write-Host "Stop with: docker compose down"
