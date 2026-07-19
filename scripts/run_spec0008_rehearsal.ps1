param(
    [int]$HoldSeconds = 0,
    [switch]$UiOnly
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$baseUrl = "http://127.0.0.1:8018"
$tempRoot = "C:\tmp\spec0008-rehearsal"
$mongoData = Join-Path $tempRoot "mongo"
$chromaData = Join-Path $tempRoot "chroma"
$mongoLog = Join-Path $tempRoot "mongod.log"
$apiStdout = Join-Path $tempRoot "api-stdout.log"
$apiStderr = Join-Path $tempRoot "api-stderr.log"
$mongoProcess = $null
$apiProcess = $null

function Remove-RehearsalData {
    if (-not (Test-Path -LiteralPath $tempRoot)) { return }
    $resolved = (Resolve-Path -LiteralPath $tempRoot).Path
    if ($resolved -ne "C:\tmp\spec0008-rehearsal") {
        throw "Refusing to remove unexpected rehearsal path: $resolved"
    }
    for ($attempt = 1; $attempt -le 10; $attempt++) {
        try {
            Remove-Item -LiteralPath $resolved -Recurse -Force
            return
        } catch {
            if ($attempt -eq 10) { throw }
            Start-Sleep -Seconds 1
        }
    }
}

function Stop-RehearsalProcess {
    param($Process)
    if ($null -ne $Process -and -not $Process.HasExited) {
        Stop-Process -Id $Process.Id
        $Process.WaitForExit()
    }
}

function Wait-ForMongo {
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        try {
            & mongosh "mongodb://127.0.0.1:27028/admin" --quiet --eval "db.runCommand({ping:1}).ok" 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { return }
        } catch {}
        Start-Sleep -Milliseconds 500
    }
    throw "Isolated MongoDB did not become ready within 30 seconds."
}

function Wait-ForApi {
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        if ($apiProcess.HasExited) {
            $detail = if (Test-Path $apiStderr) { Get-Content -Raw $apiStderr } else { "" }
            throw "Rehearsal API exited during startup. $detail"
        }
        try {
            Invoke-WebRequest -Uri $baseUrl -UseBasicParsing -TimeoutSec 2 | Out-Null
            return
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    throw "Rehearsal API did not become ready within 60 seconds."
}

try {
    Remove-RehearsalData
    New-Item -ItemType Directory -Path $mongoData -Force | Out-Null
    New-Item -ItemType Directory -Path $chromaData -Force | Out-Null

    $mongoProcess = Start-Process `
        -FilePath "C:\Program Files\MongoDB\Server\8.2\bin\mongod.exe" `
        -ArgumentList @("--port", "27028", "--bind_ip", "127.0.0.1", "--dbpath", $mongoData, "--logpath", $mongoLog, "--quiet") `
        -WindowStyle Hidden `
        -PassThru
    Wait-ForMongo

    $env:MONGODB_URI = "mongodb://127.0.0.1:27028"
    $env:CHROMA_PERSIST_DIR = $chromaData
    $env:SPEC0008_REHEARSAL_ALLOW_DESTRUCTIVE = "1"
    $env:LLM_PROVIDER = "qwen"
    $env:EMBEDDING_PROVIDER = "qwen"
    $env:EVENT_REMINDER_LLM_MATCH = "true"
    $env:PROACTIVE_EXPIRY_MINUTES = "60"
    $env:CONSOLIDATE_ON_STARTUP = "false"

    $pythonExe = & conda run -n Project-Memoria python -c "import sys; print(sys.executable)" |
        Where-Object { Test-Path -LiteralPath $_ } |
        Select-Object -First 1
    if (-not $pythonExe) { throw "Could not resolve the Project-Memoria Python executable." }

    if (-not $UiOnly) {
        & $pythonExe scripts/spec0008_rehearsal.py seed
        if ($LASTEXITCODE -ne 0) { throw "Spec 0008 seed failed." }
    }

    $apiProcess = Start-Process `
        -FilePath $pythonExe `
        -ArgumentList @("-m", "uvicorn", "Blue_dream_agents.api:app", "--host", "127.0.0.1", "--port", "8018") `
        -WorkingDirectory $repoRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $apiStdout `
        -RedirectStandardError $apiStderr `
        -PassThru
    Wait-ForApi

    if (-not $UiOnly) {
        $first = Invoke-RestMethod -Method Get -Uri "$baseUrl/proactive/pending?session_id=spec0008-browser-a" -TimeoutSec 60
        if ($first.messages.Count -ne 4) {
            throw "Expected four delivered trigger messages: $($first | ConvertTo-Json -Depth 8)"
        }
        $second = Invoke-RestMethod -Method Get -Uri "$baseUrl/proactive/pending?session_id=spec0008-browser-b" -TimeoutSec 60
        if ($second.messages.Count -ne 0) { throw "Global delivery allowed a second session to claim messages." }
        foreach ($message in $first.messages) {
            $ack = Invoke-RestMethod -Method Post -Uri "$baseUrl/proactive/$($message.message_id)/ack" -TimeoutSec 30
            if (-not $ack.ok) { throw "Message acknowledgement failed." }
        }
        $empty = Invoke-RestMethod -Method Get -Uri "$baseUrl/proactive/pending?session_id=spec0008-browser-a" -TimeoutSec 60
        if ($empty.messages.Count -ne 0) { throw "Acknowledged messages reappeared." }

        & $pythonExe scripts/spec0008_rehearsal.py verify
        if ($LASTEXITCODE -ne 0) { throw "Spec 0008 verification failed." }
    }
    & $pythonExe scripts/spec0008_rehearsal.py ui
    if ($LASTEXITCODE -ne 0) { throw "Spec 0008 UI message seed failed." }

    if ($UiOnly) {
        [ordered]@{ ui_only = $true; ui_url = $baseUrl } | ConvertTo-Json
    } else {
        [ordered]@{
            delivered_trigger_types = @($first.messages | ForEach-Object { $_.trigger_type })
            delivered_message_count = $first.messages.Count
            second_session_message_count = $second.messages.Count
            acknowledged_reload_count = $empty.messages.Count
            ui_url = $baseUrl
        } | ConvertTo-Json -Depth 8
    }

    if ($HoldSeconds -gt 0) {
        Start-Sleep -Seconds ([Math]::Min($HoldSeconds, 60))
    }
} catch {
    Write-Error $_
    if (Test-Path -LiteralPath $apiStderr) {
        Write-Host "--- API stderr ---"
        Get-Content -Raw -LiteralPath $apiStderr
    }
    if (Test-Path -LiteralPath $apiStdout) {
        Write-Host "--- API stdout ---"
        Get-Content -Raw -LiteralPath $apiStdout
    }
    if (Test-Path -LiteralPath $mongoLog) {
        Write-Host "--- Mongo tail ---"
        Get-Content -LiteralPath $mongoLog -Tail 40
    }
    throw
} finally {
    Stop-RehearsalProcess $apiProcess
    Stop-RehearsalProcess $mongoProcess
    Remove-RehearsalData
}
