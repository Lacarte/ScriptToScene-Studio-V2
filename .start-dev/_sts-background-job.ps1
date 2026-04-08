# _sts-background-job.ps1
# Wraps start-dev.bat inside a Windows Job Object so that every descendant
# process (Flask, Vite, Chromium, esbuild, etc.) is terminated by the kernel
# when this PowerShell process exits — by any cause: clean exit, Ctrl+C,
# closing the console window, crash, or Task Manager kill.
#
# This is invoked automatically by start-dev.bat when STS_IN_JOB is not set.

$ErrorActionPreference = 'Stop'

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public static class JobMgr {
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    public static extern IntPtr CreateJobObject(IntPtr a, string lpName);

    [DllImport("kernel32.dll")]
    public static extern bool SetInformationJobObject(IntPtr hJob, int infoClass, IntPtr lpJobObjectInfo, uint cbJobObjectInfoLength);

    [DllImport("kernel32.dll")]
    public static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);

    [DllImport("kernel32.dll")]
    public static extern bool TerminateJobObject(IntPtr hJob, uint uExitCode);

    [DllImport("kernel32.dll")]
    public static extern bool CloseHandle(IntPtr hObject);

    [StructLayout(LayoutKind.Sequential)]
    public struct JOBOBJECT_BASIC_LIMIT_INFORMATION {
        public Int64  PerProcessUserTimeLimit;
        public Int64  PerJobUserTimeLimit;
        public UInt32 LimitFlags;
        public UIntPtr MinimumWorkingSetSize;
        public UIntPtr MaximumWorkingSetSize;
        public UInt32 ActiveProcessLimit;
        public Int64  Affinity;
        public UInt32 PriorityClass;
        public UInt32 SchedulingClass;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct IO_COUNTERS {
        public UInt64 ReadOperationCount;
        public UInt64 WriteOperationCount;
        public UInt64 OtherOperationCount;
        public UInt64 ReadTransferCount;
        public UInt64 WriteTransferCount;
        public UInt64 OtherTransferCount;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION {
        public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation;
        public IO_COUNTERS IoInfo;
        public UIntPtr ProcessMemoryLimit;
        public UIntPtr JobMemoryLimit;
        public UIntPtr PeakProcessMemoryUsed;
        public UIntPtr PeakJobMemoryUsed;
    }
}
"@

# 1. Create the job
$job = [JobMgr]::CreateJobObject([IntPtr]::Zero, $null)
if ($job -eq [IntPtr]::Zero) {
    throw "CreateJobObject failed"
}

# 2. Configure: KILL_ON_JOB_CLOSE = 0x2000
$info = New-Object JobMgr+JOBOBJECT_EXTENDED_LIMIT_INFORMATION
$info.BasicLimitInformation.LimitFlags = 0x2000

$size = [System.Runtime.InteropServices.Marshal]::SizeOf($info)
$ptr  = [System.Runtime.InteropServices.Marshal]::AllocHGlobal($size)
try {
    [System.Runtime.InteropServices.Marshal]::StructureToPtr($info, $ptr, $false)
    # 9 = JobObjectExtendedLimitInformation
    [void][JobMgr]::SetInformationJobObject($job, 9, $ptr, [uint32]$size)
} finally {
    [System.Runtime.InteropServices.Marshal]::FreeHGlobal($ptr)
}

# 3. Spawn start-dev.bat as a child cmd, assign to the job
$helperDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $helperDir
$bat         = Join-Path $projectRoot 'start-dev.bat'
$guard       = Join-Path $helperDir '_sts-background-guard.ps1'

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName         = $env:ComSpec
$psi.Arguments        = "/c `"$bat`""
$psi.WorkingDirectory = $projectRoot
$psi.UseShellExecute  = $false
# Mark the child so the bat skips the bootstrap and runs the real logic
$psi.EnvironmentVariables["STS_IN_JOB"] = "1"

$proc = [System.Diagnostics.Process]::Start($psi)
[void][JobMgr]::AssignProcessToJobObject($job, $proc.Handle)

# Detached watchdog that survives console-window X closes and cleans up
# any terminals / Chromium still left behind after the wrapper process dies.
try {
    Start-Process -FilePath 'powershell.exe' `
        -ArgumentList @(
            '-NoProfile',
            '-ExecutionPolicy', 'Bypass',
            '-File', $guard,
            '-ParentPid', $PID,
            '-ScriptDir', $projectRoot
        ) `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden | Out-Null
} catch {}

# Path used to identify *our* Chromium so we don't kill the user's other Chrome
$chromiumExe = Join-Path $projectRoot 'bin\chromium\ungoogled-chromium\chrome.exe'
$chromiumProfile = Join-Path $projectRoot 'data\chromium-profile'

function Stop-StsWindowTree {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WindowTitle
    )

    try {
        $taskkill = Join-Path $env:SystemRoot 'System32\taskkill.exe'
        $killProc = Start-Process -FilePath $taskkill `
            -ArgumentList '/F', '/T', '/FI', "WINDOWTITLE eq $WindowTitle" `
            -NoNewWindow -PassThru -Wait -ErrorAction SilentlyContinue
        if ($killProc) {
            $null = $killProc.ExitCode
        }
    } catch {}
}

function Stop-ListenersOnPort {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    $pids = @()
    try {
        $pids = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
    } catch {
        try {
            $pids = netstat -aon |
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

    foreach ($listenerPid in @($pids | Where-Object { $_ -and $_ -gt 0 })) {
        try {
            Stop-Process -Id $listenerPid -Force -ErrorAction SilentlyContinue
        } catch {}
    }
}

# 4. Wait. On any exit path — clean exit, Ctrl+C, crash, console X-button —
#    PowerShell runs the finally block, which terminates the entire job
#    atomically: every Flask/Vite process dies at once. Chromium is launched
#    detached so we kill it separately, filtered by executable path.
$code = 0
try {
    $proc.WaitForExit()
    $code = $proc.ExitCode
} finally {
    Write-Host ""
    Write-Host "  Stopping ScriptToScene Studio..." -ForegroundColor Yellow

    # Close detached Flask/Vite consoles and their listener processes.
    Stop-StsWindowTree -WindowTitle 'STS - Flask Server (:5050)'
    Stop-StsWindowTree -WindowTitle 'STS - Vite Dev Server (:5174)'
    Stop-StsWindowTree -WindowTitle 'STS - AI Web-Auto Server (ws://8765)'
    Stop-ListenersOnPort -Port 5050
    Stop-ListenersOnPort -Port 5174
    Stop-ListenersOnPort -Port 8765

    # Kill our Chromium (and only ours) by matching the executable path
    try {
        Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" -ErrorAction SilentlyContinue |
            Where-Object {
                $_.ExecutablePath -and
                ($_.ExecutablePath -ieq $chromiumExe) -and
                (
                    -not $_.CommandLine -or
                    ($_.CommandLine -like "*$chromiumProfile*")
                )
            } |
            ForEach-Object {
                Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
            }
    } catch {}

    # Kill the Job Object — atomically terminates Flask, Vite, and any
    # grandchild processes spawned via the launcher.
    [void][JobMgr]::TerminateJobObject($job, 0)
    [void][JobMgr]::CloseHandle($job)
}
exit $code
