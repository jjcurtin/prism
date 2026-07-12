<#
.SYNOPSIS
    Windows convenience wrapper for tasks.py, mirroring the Makefile's own
    targets so `make <target>` on Linux/macOS and `.\prism.ps1 <target>` on
    Windows use the same vocabulary. See Makefile for the Linux/macOS
    equivalent and tasks.py for the underlying commands/options.

    Self-locates the repo root via $PSScriptRoot (this script's own
    location), not the caller's cwd -- mirrors tasks.py's own
    REPO_ROOT = Path(__file__).resolve().parent, so this works no matter
    where the repo is cloned or which directory it's invoked from.

.EXAMPLE
    .\prism.ps1 setup
    .\prism.ps1 run-silent
    .\prism.ps1 interface
    .\prism.ps1 test-all
#>

param(
    # Named $RestArgs rather than $Args -- $args is a PowerShell automatic
    # variable name; giving a declared parameter that exact name works but
    # is needless ambiguity in a script nobody here can dry-run before it
    # touches a machine with live research-drive access.
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RestArgs
)

if ($null -eq $RestArgs) { $RestArgs = @() }

$repo = $PSScriptRoot
$venvPy = Join-Path $repo ".venv\Scripts\python.exe"
$tasksPy = Join-Path $repo "tasks.py"

# Same target names as the Makefile -- kept in lockstep with it by hand
# (mirrors the two-implementation split tasks.py itself already has for
# Linux/macOS `make` vs this).
$targets = @{
    'run-silent'       = @('run', '--mode', 'silent')
    'run-live'         = @('run', '--mode', 'live')
    'interface'        = @('interface')
    'test-server'      = @('test', 'server')
    'test-client'      = @('test', 'client')
    'test-all'         = @('test', 'all')
    'test-integration' = @('test', 'integration')
    'typecheck'        = @('typecheck')
}

$target = $null
if ($RestArgs.Count -gt 0) { $target = $RestArgs[0] }

$passthroughArgs = @()
if ($RestArgs.Count -gt 1) { $passthroughArgs = $RestArgs[1..($RestArgs.Count - 1)] }

if ($null -eq $target -or $target -eq 'help') {
    # Bare (no target) or 'help': same as `make help` -- tasks.py's own
    # no-args help. Must run with the system python (setup may not have
    # happened yet, so the venv might not exist).
    python $tasksPy
    exit $LASTEXITCODE
}

if ($target -eq 'setup') {
    # setup must be invoked with the SYSTEM python -- no venv exists yet.
    python $tasksPy setup
    exit $LASTEXITCODE
}

if (-not (Test-Path $venvPy)) {
    Write-Host "No venv found at $venvPy -- run '.\prism.ps1 setup' first." -ForegroundColor Yellow
    exit 1
}

if ($targets.ContainsKey($target)) {
    $targetArgs = $targets[$target]
    & $venvPy $tasksPy @targetArgs @passthroughArgs
} else {
    # Not a Makefile-style target -- pass everything straight through to
    # tasks.py, so its own raw subcommands still work (e.g.
    # `.\prism.ps1 run --mode silent`).
    & $venvPy $tasksPy @RestArgs
}
exit $LASTEXITCODE
