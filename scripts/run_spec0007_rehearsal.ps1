param(
    [int]$HoldSeconds = 0
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$baseUrl = "http://127.0.0.1:8017"
$tempRoot = "C:\tmp\spec0007-rehearsal"
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
    if ($resolved -ne "C:\tmp\spec0007-rehearsal") {
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
            & mongosh "mongodb://127.0.0.1:27027/admin" --quiet --eval "db.runCommand({ping:1}).ok" 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { return }
        } catch {
            # MongoDB may still be opening its data files.
        }
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
        -ArgumentList @("--port", "27027", "--bind_ip", "127.0.0.1", "--dbpath", $mongoData, "--logpath", $mongoLog, "--quiet") `
        -WindowStyle Hidden `
        -PassThru
    Wait-ForMongo

    $env:MONGODB_URI = "mongodb://127.0.0.1:27027"
    $env:CHROMA_PERSIST_DIR = $chromaData
    $env:SPEC0007_REHEARSAL_ALLOW_DESTRUCTIVE = "1"
    $env:LLM_PROVIDER = "qwen"
    $env:EMBEDDING_PROVIDER = "qwen"
    $env:CONSOLIDATION_AGE_DAYS = "2"
    $env:CONSOLIDATION_IMPORTANCE_MAX = "0.5"
    $env:CONSOLIDATION_MIN_EVENTS = "3"
    $env:CONSOLIDATE_ON_STARTUP = "false"
    $env:RECALL_HALF_LIFE_DAYS = "14"
    $env:RECALL_TOKEN_BUDGET = "2000"

    $pythonExe = & conda run -n Project-Memoria python -c "import sys; print(sys.executable)" |
        Where-Object { Test-Path -LiteralPath $_ } |
        Select-Object -First 1
    if (-not $pythonExe) { throw "Could not resolve the Project-Memoria Python executable." }

    & $pythonExe scripts/spec0007_rehearsal.py seed
    if ($LASTEXITCODE -ne 0) { throw "Spec 0007 seed failed." }

    $apiProcess = Start-Process `
        -FilePath $pythonExe `
        -ArgumentList @("-m", "uvicorn", "Blue_dream_agents.api:app", "--host", "127.0.0.1", "--port", "8017") `
        -WorkingDirectory $repoRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $apiStdout `
        -RedirectStandardError $apiStderr `
        -PassThru
    Wait-ForApi

    $first = Invoke-RestMethod -Method Post -Uri "$baseUrl/memory/consolidate" -TimeoutSec 300
    if ($first.groups_formed -ne 1 -or $first.events_consolidated -ne 3 -or $first.summaries_created -ne 1 -or $first.failures.Count -ne 0) {
        throw "Unexpected first consolidation report: $($first | ConvertTo-Json -Depth 8)"
    }
    $second = Invoke-RestMethod -Method Post -Uri "$baseUrl/memory/consolidate" -TimeoutSec 300
    if ($second.groups_formed -ne 0 -or $second.events_consolidated -ne 0 -or $second.summaries_created -ne 0) {
        throw "Consolidation rerun was not a no-op: $($second | ConvertTo-Json -Depth 8)"
    }
    $pin = Invoke-RestMethod -Method Post -Uri "$baseUrl/memory/events/spec0007-low-1/pin" -TimeoutSec 180
    if (-not $pin.ok) { throw "Pin endpoint did not return ok." }

    $queryBody = @{
        query = "What do you remember about my quiet reading and tea in the bedroom?"
        session_id = "spec0007-live"
    } | ConvertTo-Json
    $query = Invoke-RestMethod -Method Post -Uri "$baseUrl/query" -ContentType "application/json" -Body $queryBody -TimeoutSec 300
    if ($query.data.route_intent -ne "semantic") { throw "Live query did not use semantic recall." }
    if (-not $query.data.recall_debug -or $query.data.recall_debug.packed_count -lt 1) {
        throw "Live semantic response did not include recall_debug."
    }
    if ($query.text -notmatch "tea|read|newspaper|plant") {
        throw "Live answer was not grounded in the consolidated day: $($query.text)"
    }

    & $pythonExe scripts/spec0007_rehearsal.py verify
    if ($LASTEXITCODE -ne 0) { throw "Spec 0007 verification failed." }

    [ordered]@{
        first_consolidation = $first
        rerun_no_op = $true
        pin_reactivated = $pin.ok
        semantic_route = $query.data.route_intent
        recall_debug_packed = $query.data.recall_debug.packed_count
        summary_grounded_answer = $query.text
        ui_url = $baseUrl
    } | ConvertTo-Json -Depth 8

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
