# watchdog-streamlit.ps1 — ensures Streamlit + Cloudflare tunnel + localtunnel are always running
$ErrorActionPreference = "SilentlyContinue"
$env:PATH = "C:\Users\Chris Gaor\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\LocalCache\local-packages\Python312\Scripts;C:\Users\Chris Gaor\AppData\Local\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe\node-v24.19.0-win-x64;$env:PATH"
$logDir = "C:\Users\Chris Gaor\recruitment-dashboard\scripts\logs"
function Log($msg) { "[$(Get-Date -Format u)] $msg" | Out-File "$logDir\watchdog.log" -Append }

# 1. Streamlit on port 8501
if (-not (Get-Process -Name "streamlit" -ErrorAction SilentlyContinue)) {
    Set-Location "C:\Users\Chris Gaor\recruitment-dashboard"
    Start-Process -FilePath "streamlit" -ArgumentList "run","app.py","--server.headless=true" -WindowStyle Hidden
    Start-Sleep -Seconds 8
    Log "restarted streamlit"
}

# 2. Cloudflare Tunnel
if (-not (Get-Process -Name "cloudflared" -ErrorAction SilentlyContinue)) {
    $cfExe = "C:\Users\Chris Gaor\recruitment-dashboard\scripts\cloudflared.exe"
    Start-Process -FilePath $cfExe `
        -ArgumentList "tunnel","--no-autoupdate","--url","http://localhost:8501" `
        -RedirectStandardOutput "$logDir\cloudflared-tunnel.log" `
        -RedirectStandardError "$logDir\cloudflared-tunnel.log.err" `
        -WindowStyle Hidden
    Log "restarted cloudflared"
}

# 3. Localtunnel with fixed subdomain "recruitmentdashboard"
$ltRunning = Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "localtunnel|lt\.js" -or $_.CommandLine -match "recruitmentdashboard" }
if (-not $ltRunning) {
    $ltCmd = "C:\Users\Chris Gaor\AppData\Local\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe\node-v24.19.0-win-x64\lt.cmd"
    Start-Process -FilePath $ltCmd `
        -ArgumentList "--port","8501","--subdomain","recruitmentdashboard" `
        -RedirectStandardOutput "$logDir\localtunnel.log" `
        -RedirectStandardError "$logDir\localtunnel.log.err" `
        -WindowStyle Hidden
    Log "restarted localtunnel"
}
