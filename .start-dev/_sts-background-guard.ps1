param(
    [Parameter(Mandatory = $true)]
    [int]$ParentPid,

    [Parameter(Mandatory = $true)]
    [string]$ScriptDir
)

# Background watchdog for start-dev shutdown cleanup.
$ErrorActionPreference = 'SilentlyContinue'

$scriptDir = (Resolve-Path $ScriptDir).Path
$chromiumExe = Join-Path $scriptDir 'bin\chromium\ungoogled-chromium\chrome.exe'
$chromiumProfile = Join-Path $scriptDir 'data\chromium-profile'

function Stop-StsWindowTree {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WindowTitle
    )

    try {
        & (Join-Path $env:SystemRoot 'System32\taskkill.exe') /F /T /FI "WINDOWTITLE eq $WindowTitle" | Out-Null
    } catch {}
}

function Stop-ListenersOnPort {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    $listenerPids = @()
    try {
        $listenerPids = Get-NetTCPConnection -State Listen -LocalPort $Port |
            Select-Object -ExpandProperty OwningProcess -Unique
    } catch {
        try {
            $listenerPids = netstat -aon |
                Select-String -Pattern "LISTENING\s+(\d+)$" |
                ForEach-Object {
                    $parts = ($_ -replace '^\s+', '') -split '\s+'
                    if ($parts.Length -ge 5 -and $parts[1] -like "*:$Port") {
                        [int]$parts[4]
                    }
                } |
                Select-Object -Unique
        } catch {}
    }

    foreach ($listenerPid in @($listenerPids | Where-Object { $_ -and $_ -gt 0 })) {
        try {
            Stop-Process -Id $listenerPid -Force
        } catch {}
    }
}

function Stop-StsChromium {
    try {
        Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
            Where-Object {
                $_.ExecutablePath -and
                ($_.ExecutablePath -ieq $chromiumExe) -and
                (
                    -not $_.CommandLine -or
                    ($_.CommandLine -like "*$chromiumProfile*")
                )
            } |
            ForEach-Object {
                try {
                    Stop-Process -Id $_.ProcessId -Force
                } catch {}
            }
    } catch {}
}

while ($true) {
    $parent = Get-Process -Id $ParentPid -ErrorAction SilentlyContinue
    if (-not $parent) {
        break
    }
    Start-Sleep -Milliseconds 750
}

Start-Sleep -Milliseconds 500

Stop-StsWindowTree -WindowTitle 'STS - Flask Server (:5050)'
Stop-StsWindowTree -WindowTitle 'STS - Vite Dev Server (:5174)'
Stop-StsWindowTree -WindowTitle 'STS - AI Web-Auto Server (ws://8765)'

Stop-ListenersOnPort -Port 5050
Stop-ListenersOnPort -Port 5174
Stop-ListenersOnPort -Port 8765

Stop-StsChromium
