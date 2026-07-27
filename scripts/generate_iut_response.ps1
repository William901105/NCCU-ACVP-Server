param(
    [Parameter(Mandatory = $false)]
    [string]$PromptPath
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Runner = Join-Path $RepoRoot "IUT-tests\mldsa-native\run_test.py"
$DefaultOutputRoot = Join-Path $HOME "Downloads\mldsa-response"

function Find-DilithiumSource {
    $Candidates = @(
        (Join-Path $RepoRoot "third_party\dilithium-py\src"),
        (Join-Path $HOME "projects\ACVP-FIPS204\third_party\dilithium-py\src")
    )

    foreach ($Candidate in $Candidates) {
        if (Test-Path (Join-Path $Candidate "dilithium_py\__init__.py")) {
            return $Candidate
        }
    }

    throw "找不到 dilithium-py。請確認其 src 目錄存在。"
}

if (-not (Test-Path $Runner)) {
    throw "找不到 IUT Runner：$Runner"
}

if (-not $PromptPath) {
    Add-Type -AssemblyName System.Windows.Forms

    $Dialog = New-Object System.Windows.Forms.OpenFileDialog
    $Dialog.Title = "選擇 ACVP Prompt JSON"
    $Dialog.InitialDirectory = Join-Path $HOME "Downloads"
    $Dialog.Filter = "JSON files (*.json)|*.json"

    if ($Dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
        Write-Host "已取消。"
        exit 0
    }

    $PromptPath = $Dialog.FileName
}

$PromptPath = (Resolve-Path $PromptPath).Path
$Prompt = Get-Content $PromptPath -Raw | ConvertFrom-Json

$VectorObject = if ($Prompt -is [array]) {
    $Prompt | Where-Object { $_.mode } | Select-Object -First 1
}
else {
    $Prompt
}

$Mode = [string]$VectorObject.mode

if ($Mode -notin @("keyGen", "sigGen", "sigVer")) {
    throw "無法從 Prompt 判斷 mode，取得值：$Mode"
}

$DilithiumSource = Find-DilithiumSource
$OutputDirectory = Join-Path $DefaultOutputRoot (
    "{0}-{1}" -f $Mode, (Get-Date -Format "yyyyMMdd-HHmmss")
)

New-Item -ItemType Directory -Force $OutputDirectory | Out-Null

$env:PYTHONPATH = $DilithiumSource

& python $Runner `
    --prompt $PromptPath `
    --response-dir $OutputDirectory `
    --variant pass `
    --expect-mode $Mode `
    --dilithium-py-src $DilithiumSource

if ($LASTEXITCODE -ne 0) {
    throw "IUT Response 產生失敗，exit code：$LASTEXITCODE"
}

$ResponseFile = Join-Path $OutputDirectory "response_pass_$Mode.json"

if (-not (Test-Path $ResponseFile)) {
    throw "執行完成，但找不到輸出檔：$ResponseFile"
}

Write-Host ""
Write-Host "IUT Response 產生成功："
Write-Host $ResponseFile

Start-Process explorer.exe -ArgumentList "/select,`"$ResponseFile`""
