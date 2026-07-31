param()

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$FrontendRoot = Join-Path $RepoRoot "frontend"
$RunnerDll = Join-Path $RepoRoot ".nist-bin\genval-runner\NIST.CVP.ACVTS.Generation.GenValApp.dll"
$OrleansDll = Join-Path $RepoRoot ".nist-bin\orleans-server\NIST.CVP.ACVTS.Orleans.ServerHost.dll"
$ArtifactRoot = Join-Path $RepoRoot "backend\data\acvp-sessions"
$SecretPath = Join-Path $env:APPDATA "NCCU-ACVP-Server\neon-secrets.xml"

function Test-LocalPort {
    param([int]$Port)

    return $null -ne (
        Get-NetTCPConnection `
            -LocalPort $Port `
            -State Listen `
            -ErrorAction SilentlyContinue |
        Select-Object -First 1
    )
}

function Wait-LocalPort {
    param(
        [int]$Port,
        [int]$TimeoutSeconds = 30
    )

    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    while ((Get-Date) -lt $Deadline) {
        if (Test-LocalPort -Port $Port) {
            return $true
        }

        Start-Sleep -Milliseconds 500
    }

    return $false
}

if (-not (Test-Path $RunnerDll)) {
    throw "找不到 NIST GenVal Runner：$RunnerDll"
}

if (-not (Test-Path $OrleansDll)) {
    throw "找不到 Orleans Server：$OrleansDll"
}

if (-not (Test-Path (Join-Path $FrontendRoot "node_modules"))) {
    throw "前端套件尚未安裝，請先在 frontend 執行 npm.cmd install。"
}

if (-not (Test-Path $SecretPath)) {
    throw "找不到 Neon 加密連線設定：$SecretPath"
}

$Secrets = Import-Clixml -Path $SecretPath

if (
    $null -eq $Secrets.OwnerUrl -or
    $null -eq $Secrets.AppDsn
) {
    throw "Neon 加密連線設定內容不完整。"
}

$OwnerUrl = [System.Net.NetworkCredential]::new(
    "",
    $Secrets.OwnerUrl
).Password

$AppDsn = [System.Net.NetworkCredential]::new(
    "",
    $Secrets.AppDsn
).Password

if (
    [string]::IsNullOrWhiteSpace($OwnerUrl) -or
    [string]::IsNullOrWhiteSpace($AppDsn)
) {
    throw "無法解密 Neon 連線資訊。請使用建立此設定檔的 Windows 帳號執行。"
}

New-Item -ItemType Directory -Force $ArtifactRoot | Out-Null

try {
    if (-not (Test-LocalPort -Port 8000)) {
        $env:DATABASE_URL = $AppDsn
        $env:ACVP_DATABASE_URL = $AppDsn
        $env:ACVP_SCHEMA_DATABASE_URL = $OwnerUrl
        $env:ACVP_GENVAL_RUNNER_DLL = $RunnerDll
        $env:ACVP_GENVAL_ARTIFACT_ROOT = $ArtifactRoot

        $BackendCommand = @"
Set-Location '$RepoRoot'
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
"@

        Start-Process powershell `
            -ArgumentList "-NoExit", "-Command", $BackendCommand
    }
    else {
        Write-Host "後端 8000 已在執行。"
    }
}
finally {
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:ACVP_DATABASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:ACVP_SCHEMA_DATABASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:ACVP_GENVAL_RUNNER_DLL -ErrorAction SilentlyContinue
    Remove-Item Env:ACVP_GENVAL_ARTIFACT_ROOT -ErrorAction SilentlyContinue

    Remove-Variable OwnerUrl, AppDsn, Secrets -ErrorAction SilentlyContinue
}

if (-not (Test-LocalPort -Port 11111)) {
    $OrleansCommand = @"
Set-Location '$RepoRoot'
dotnet '$OrleansDll' --console
"@

    Start-Process powershell `
        -ArgumentList "-NoExit", "-Command", $OrleansCommand
}
else {
    Write-Host "Orleans 已在執行。"
}

if (-not (Test-LocalPort -Port 5173)) {
    Start-Process cmd.exe `
        -ArgumentList "/k", "cd /d `"$FrontendRoot`" && npm.cmd run dev"
}
else {
    Write-Host "前端 5173 已在執行。"
}

$BackendReady = Wait-LocalPort -Port 8000
$FrontendReady = Wait-LocalPort -Port 5173

if (-not $BackendReady) {
    throw "後端未在預期時間內啟動，請查看 Uvicorn 視窗。"
}

if (-not $FrontendReady) {
    throw "前端未在預期時間內啟動，請查看 Vite 視窗。"
}

Start-Process "http://127.0.0.1:5173/"

Write-Host ""
Write-Host "ACVP Neon Demo 已啟動："
Write-Host "前端：http://127.0.0.1:5173/"
Write-Host "後端：http://127.0.0.1:8000/"
Write-Host "資料庫：Neon PostgreSQL（低權限 acvp_app）"
