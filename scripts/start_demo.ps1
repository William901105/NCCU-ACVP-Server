param()

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$FrontendRoot = Join-Path $RepoRoot "frontend"
$RunnerDll = Join-Path $RepoRoot ".nist-bin\genval-runner\NIST.CVP.ACVTS.Generation.GenValApp.dll"
$OrleansDll = Join-Path $RepoRoot ".nist-bin\orleans-server\NIST.CVP.ACVTS.Orleans.ServerHost.dll"
$ArtifactRoot = Join-Path $RepoRoot "backend\data\acvp-sessions"

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

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    while ((Get-Date) -lt $deadline) {
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

$SecurePassword = Read-Host "請輸入 acvp_app 的 PostgreSQL 密碼" -AsSecureString
$Pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePassword)

try {
    $PlainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Pointer)
    $EncodedPassword = [Uri]::EscapeDataString($PlainPassword)

    $env:DATABASE_URL = "postgresql://acvp_app:$EncodedPassword@127.0.0.1:5432/acvp"
    $env:ACVP_DATABASE_URL = $env:DATABASE_URL
    $env:ACVP_STORAGE_BACKEND = "postgresql"
    $env:ACVP_GENVAL_RUNNER_DLL = $RunnerDll
    $env:ACVP_GENVAL_ARTIFACT_ROOT = $ArtifactRoot

    New-Item -ItemType Directory -Force $ArtifactRoot | Out-Null

    if (-not (Test-LocalPort -Port 8000)) {
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

    $OrleansCommand = @"
Set-Location '$RepoRoot'
dotnet '$OrleansDll' --console
"@

    Start-Process powershell `
        -ArgumentList "-NoExit", "-Command", $OrleansCommand

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
    Write-Host "ACVP Demo 已啟動："
    Write-Host "前端：http://127.0.0.1:5173/"
    Write-Host "後端：http://127.0.0.1:8000/"
}
finally {
    if ($Pointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Pointer)
    }

    Remove-Variable PlainPassword, EncodedPassword -ErrorAction SilentlyContinue
}
