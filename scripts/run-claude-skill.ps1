# run-claude-skill.ps1 — invoked by Windows Task Scheduler to trigger a Claude Code skill headlessly.
# Usage: powershell -ExecutionPolicy Bypass -File run-claude-skill.ps1 -Skill "update-dashboard"
param(
    [Parameter(Mandatory=$true)][string]$Skill,
    [string]$LogDir = "C:\Users\Chris Gaor\recruitment-dashboard\scripts\logs"
)

# Ensure log dir exists
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

$timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$logFile = Join-Path $LogDir ("$Skill-$timestamp.log")

# Prepend node.exe path so `claude` resolves
$env:PATH = "C:\Users\Chris Gaor\AppData\Local\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe\node-v24.19.0-win-x64;$env:PATH"

# Work from the project so relative paths in skill instructions resolve
Set-Location "C:\Users\Chris Gaor\recruitment-dashboard"

"[$(Get-Date -Format 'u')] START: /$Skill" | Out-File $logFile -Append -Encoding utf8

try {
    # -p enters print mode: run one turn, print, exit
    # --dangerously-skip-permissions: needed for fully non-interactive runs since
    # no human can approve MCP tool prompts. Project settings.json also allowlists
    # the specific tools we need as a belt-and-braces measure.
    & claude -p --dangerously-skip-permissions "/$Skill" *>&1 | Tee-Object -FilePath $logFile -Append
    $exit = $LASTEXITCODE
    "[$(Get-Date -Format 'u')] DONE  exit=$exit" | Out-File $logFile -Append -Encoding utf8
} catch {
    "[$(Get-Date -Format 'u')] ERROR $_" | Out-File $logFile -Append -Encoding utf8
    exit 1
}

# Keep the last 30 log files per skill; delete older ones
Get-ChildItem $LogDir -Filter "$Skill-*.log" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 30 |
    Remove-Item -Force -ErrorAction SilentlyContinue

exit $exit
