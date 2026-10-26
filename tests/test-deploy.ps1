$ErrorActionPreference = 'Stop'
$fixture = Join-Path ([IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString())
New-Item -ItemType Directory $fixture | Out-Null
Copy-Item (Join-Path $PSScriptRoot '../deploy.ps1') $fixture
Set-Content (Join-Path $fixture '.env.example') 'WEB_PASSWORD=root'
$global:DockerCalls = @()
$global:ExistingFixture = $false
function global:docker {
    $global:DockerCalls += ($args -join ' ')
    $global:LASTEXITCODE = 0
    if ($args[0] -eq 'info') { 'linux'; return }
    if (($args -join ' ') -like '*ps --all --quiet' -and $global:ExistingFixture) { 'stopped-container-id' }
}
try {
    & (Join-Path $fixture deploy.ps1)
    if (-not ($global:DockerCalls -match 'compose.portable.yaml up -d --wait')) { throw 'Fresh deployment did not start portable mode' }
    $global:DockerCalls = @()
    $global:ExistingFixture = $true
    $blocked = $false
    try { & (Join-Path $fixture deploy.ps1) } catch { $blocked = $_.Exception.Message -like '*Existing Compose*' }
    if (-not $blocked) { throw 'Stopped containers were not protected' }
    if ($global:DockerCalls -match ' pull| up ') { throw 'Guard allowed mutation' }
    Write-Output 'PASS: PowerShell portable deployment and stopped-container preservation.'
} finally {
    Remove-Item Function:/docker
    Set-Location $PSScriptRoot
    Remove-Item -Recurse -Force $fixture
}
