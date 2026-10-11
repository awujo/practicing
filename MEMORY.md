
## RULE (owner-mandated, 2026-10-11): Feedback loop — never report an action as done without independent verification.
After ANY push/workflow/API action, re-query the remote (git ls-remote, REST GET) and paste the actual returned state. If verification fails or is impossible, say so explicitly. Do not infer success from a command's exit code alone.

## RULE (owner-mandated, 2026-10-11): Feedback loop
After ANY push/workflow/API action, independently re-query the remote (git ls-remote, REST GET) and report the actual returned state. Never infer success from an exit code or a single API response. If verification is impossible, say so explicitly.
