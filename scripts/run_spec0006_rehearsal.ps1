$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$baseUrl = "http://127.0.0.1:8016"
$stdoutPath = "C:\tmp\spec0006-smoke-stdout.log"
$stderrPath = "C:\tmp\spec0006-smoke-stderr.log"
$smokeCollections = @(
    "spec0006_smoke_conversation_sessions",
    "spec0006_smoke_profile_facts",
    "spec0006_smoke_reminders"
)
$serverProcess = $null

function Clear-SmokeCollections {
    $collectionLiteral = ($smokeCollections | ForEach-Object { "'$_'" }) -join ","
    $code = "from pymongo import MongoClient; from Blue_dream_agents.llm.settings import get_provider_settings; c=MongoClient(get_provider_settings().mongodb_uri); db=c.dementia_assistance; [db[name].delete_many({}) for name in [$collectionLiteral]]; c.close()"
    & conda run -n Project-Memoria python -c $code | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to clear isolated smoke collections."
    }
}

function Start-SmokeServer {
    if (Test-Path $stdoutPath) { Remove-Item -LiteralPath $stdoutPath }
    if (Test-Path $stderrPath) { Remove-Item -LiteralPath $stderrPath }
    $process = Start-Process `
        -FilePath "conda" `
        -ArgumentList @("run", "-n", "Project-Memoria", "python", "scripts/spec0006_smoke_server.py") `
        -WorkingDirectory $repoRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -PassThru

    $deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $deadline) {
        if ($process.HasExited) {
            $detail = if (Test-Path $stderrPath) { Get-Content -Raw $stderrPath } else { "" }
            throw "Smoke server exited during startup. $detail"
        }
        try {
            Invoke-WebRequest -Uri $baseUrl -UseBasicParsing -TimeoutSec 2 | Out-Null
            return $process
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    throw "Smoke server did not become ready within 45 seconds."
}

function Stop-SmokeServer {
    param($Process)
    if ($null -ne $Process -and -not $Process.HasExited) {
        Stop-Process -Id $Process.Id
        $Process.WaitForExit()
    }
}

function Invoke-JsonPost {
    param([string]$Path, [hashtable]$Body)
    return Invoke-RestMethod `
        -Method Post `
        -Uri "$baseUrl$Path" `
        -ContentType "application/json" `
        -Body ($Body | ConvertTo-Json -Depth 8) `
        -TimeoutSec 180
}

function Wait-ForProfileFacts {
    param([int]$MinimumCount)
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        $result = Invoke-RestMethod -Uri "$baseUrl/memory/profile" -TimeoutSec 10
        if ($result.facts.Count -ge $MinimumCount) { return $result.facts }
        Start-Sleep -Seconds 1
    }
    throw "Profile extraction did not finish within 60 seconds."
}

function Wait-ForStableProfileFacts {
    param([int]$MinimumCount)
    $deadline = (Get-Date).AddSeconds(90)
    $lastCount = -1
    $stablePolls = 0
    while ((Get-Date) -lt $deadline) {
        $facts = @((Invoke-RestMethod -Uri "$baseUrl/memory/profile" -TimeoutSec 10).facts)
        if ($facts.Count -ge $MinimumCount -and $facts.Count -eq $lastCount) {
            $stablePolls += 1
        } else {
            $stablePolls = 0
        }
        if ($stablePolls -ge 5) { return $facts }
        $lastCount = $facts.Count
        Start-Sleep -Seconds 1
    }
    throw "Profile fact count did not stabilize within 90 seconds."
}

function Wait-ForReminderType {
    param([string]$TriggerType)
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        $result = Invoke-RestMethod -Uri "$baseUrl/reminders" -TimeoutSec 10
        $matching = @($result.reminders | Where-Object { $_.trigger_type -eq $TriggerType })
        if ($matching.Count -gt 0) { return $matching }
        Start-Sleep -Seconds 1
    }
    throw "$TriggerType reminder extraction did not finish within 60 seconds."
}

try {
    Clear-SmokeCollections
    $serverProcess = Start-SmokeServer

    $first = Invoke-JsonPost "/query" @{
        query = "My daughter Sarah visits me on Sundays."
        session_id = "spec0006-restart-session"
    }
    $factsAfterFirst = @(Wait-ForStableProfileFacts 1)

    $duplicate = Invoke-JsonPost "/query" @{
        query = "My daughter Sarah visits me on Sundays."
        session_id = "spec0006-duplicate-session"
    }
    $factsAfterDuplicate = @(Wait-ForStableProfileFacts 1)
    if ($factsAfterDuplicate.Count -ne $factsAfterFirst.Count) {
        throw "Duplicate statement changed active fact count from $($factsAfterFirst.Count) to $($factsAfterDuplicate.Count)."
    }

    $timeTurn = Invoke-JsonPost "/query" @{
        query = "Remind me to take my pill tomorrow at 8:00 AM."
        session_id = "spec0006-time-reminder-session"
    }
    $timeReminders = @(Wait-ForReminderType "time")
    if (-not $timeReminders[0].due_at) { throw "Time reminder did not include due_at." }

    $eventTurn = Invoke-JsonPost "/query" @{
        query = "When I leave for my morning walk tomorrow, remind me to take my water bottle."
        session_id = "spec0006-event-reminder-session"
    }
    $eventReminders = @(Wait-ForReminderType "event")
    $eventTrigger = $eventReminders[0].event_trigger
    if (-not $eventTrigger.valid_date -or -not $eventTrigger.window_start -or -not $eventTrigger.condition) {
        throw "Event reminder did not include the resolved date, window, and condition."
    }

    Stop-SmokeServer $serverProcess
    $serverProcess = $null
    $serverProcess = Start-SmokeServer

    $restartFollowUp = Invoke-JsonPost "/query" @{
        query = "What should we do when she visits?"
        session_id = "spec0006-restart-session"
    }
    $resolvedQuery = $restartFollowUp.data.resolved_query
    $usedContext = $restartFollowUp.data.conversation_resolution.used_context
    if (-not $usedContext -or $resolvedQuery -notmatch "Sarah|Sunday") {
        throw "Restart follow-up did not resolve the stored conversation: $($restartFollowUp.text)"
    }

    $freshProfileAnswer = Invoke-JsonPost "/query" @{
        query = "What is my daughter's name?"
        session_id = "spec0006-fresh-session"
    }
    if ($freshProfileAnswer.text -notmatch "Sarah") {
        throw "Fresh-session answer did not use the profile fact: $($freshProfileAnswer.text)"
    }

    $legacy = Invoke-JsonPost "/query" @{ query = "Hello, Jeeves." }
    if (-not $legacy.text) { throw "Legacy query-only request returned no text." }

    [ordered]@{
        restart_survival = $true
        cross_session_profile = $true
        duplicate_fact_suppressed = $true
        time_reminder_due_at = $timeReminders[0].due_at
        event_reminder_valid_date = $eventTrigger.valid_date
        event_reminder_window = "$($eventTrigger.window_start)-$($eventTrigger.window_end)"
        event_reminder_condition_present = [bool]$eventTrigger.condition
        legacy_query_only = $true
        active_fact_count = $factsAfterDuplicate.Count
        reminder_count = $timeReminders.Count + $eventReminders.Count
    } | ConvertTo-Json
} finally {
    Stop-SmokeServer $serverProcess
    Clear-SmokeCollections
}
