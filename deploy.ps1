# Windows PowerShell 5.1+ / PowerShell 7. Requires Docker Desktop in Linux mode.
param([ValidateSet('ai', 'all', 'portable', 'gateway-portable', 'workstation-bridge')][string]$Role = 'portable')
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Install and start Docker Desktop with Linux containers, then rerun.' }
$engine = docker info --format '{{.OSType}}'
if ($LASTEXITCODE -ne 0 -or $engine -ne 'linux') { throw 'Start Docker Desktop with Linux containers before deploying.' }
$file = switch ($Role) {
    'ai' { 'compose.yaml' }
    'all' { 'compose.yaml' }
    'workstation-bridge' { 'workstation/compose.yaml' }
    default { 'compose.portable.yaml' }
}
$service = if ($Role -eq 'gateway-portable') { @('gateway') } else { @() }
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
function Invoke-Compose {
    & docker compose --env-file .env -f $file @args
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose failed; deployment stopped.' }
}
Invoke-Compose config --quiet
if ($Role -eq 'ai') {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 scripts/ai-install-plan.py $file all
    } else {
        & python scripts/ai-install-plan.py $file all
    }
    if ($LASTEXITCODE -ne 0) { throw 'AI 安装方案未通过，未拉取或创建容器。' }
}
$existing = @(Invoke-Compose ps --all --quiet)
if ($existing.Count -gt 0) { throw 'Existing Compose containers found, including stopped containers. Use start/restart. Export internal data before replacement.' }
Invoke-Compose pull @service
Invoke-Compose up -d --wait --wait-timeout 240 @service
Write-Output "Deployment ready: $file. Use this same Compose file for later operations."
