# 0013 Web UI Rehaul Status

## Status

Not started.

## Verification Evidence

None yet. Record here when work finishes:

- Baseline and final pytest counts (129 at spec authoring; new push/summaries tests added).
- Phone install evidence: adb reverse recipe run, Add to Home Screen, standalone launch (screenshot or notes).
- Closed-app push evidence: +2 min reminder → OS notification with app closed → tap → highlighted bubble in the ongoing thread, rendered once.
- Foreground suppression evidence: push with app visible → no OS toast, in-app bubble/chime path.
- Hazard, morning-report, and grounded-recall (pinned row in "Memory used") demo beats.
- `Mobile/` deletion commit, docs-update commit hashes.
- Cut lines exercised, if any, and why.
- Demo-morning runbook results (before the spec 0011 video).
