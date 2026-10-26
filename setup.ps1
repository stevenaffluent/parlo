# Parlo setup: installs a private Python 3.11, the libraries and the Bark 3.0 model
# into this folder, then adds Desktop and Start Menu shortcuts. Safe to run again.
param([switch]$NoShortcuts)
# "Continue", not "Stop": Python writes progress bars to stderr, which Windows PowerShell 5.1 would
# otherwise treat as a failure. Each step checks its exit code instead.
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Step($msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Check($what) { if ($LASTEXITCODE -ne 0) { throw "$what failed (exit code $LASTEXITCODE)" } }

function Has-Py311 { try { & py -3.11 -c "pass" 2>$null; return ($LASTEXITCODE -eq 0) } catch { return $false } }

Step "Finding Python 3.11 (the model's supported version)"
if (-not (Has-Py311)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        Write-Host "Installing Python 3.11 with the official Python install manager ..."
        & py install 3.11
    }
    if (-not (Has-Py311) -and (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Host "Installing Python 3.11 with winget ..."
        & winget install -e --id Python.Python.3.11 --scope user
    }
    if (-not (Has-Py311)) {
        throw "Python 3.11 is not installed. Install it from https://www.python.org/downloads/ (tick 'py launcher'), then run Setup.bat again."
    }
}

Step "Creating a private Python environment in .venv"
if (-not (Test-Path "$Root\.venv\Scripts\python.exe")) {
    & py -3.11 -m venv "$Root\.venv"
    Check "Creating the Python environment"
}
$py = "$Root\.venv\Scripts\python.exe"
& $py -m pip install --upgrade pip --quiet
Check "Updating pip"

Step "Installing PyTorch"
$cuda = [bool](Get-Command nvidia-smi -ErrorAction SilentlyContinue)
if ($cuda) { $index = "https://download.pytorch.org/whl/cu128"; Write-Host "NVIDIA GPU found: installing the CUDA build" }
else { $index = "https://download.pytorch.org/whl/cpu"; Write-Host "No NVIDIA GPU: installing the CPU build" }
& $py -m pip install "torch==2.8.0" --index-url $index
Check "Installing PyTorch"

Step "Installing the other libraries"
& $py -m pip install -r "$Root\requirements.txt"
Check "Installing libraries"

Step "Downloading the Underdog Bark 3.0 model (about 170 MB, once)"
& $py "$Root\app\prefetch.py"
Check "Downloading the model"

if (-not $NoShortcuts) {
    Step "Adding shortcuts"
    $ws = New-Object -ComObject WScript.Shell
    $dirs = @([Environment]::GetFolderPath("Desktop"), "$env:APPDATA\Microsoft\Windows\Start Menu\Programs")
    foreach ($dir in $dirs) {
        Remove-Item "$dir\Bark Dictate.lnk" -ErrorAction SilentlyContinue  # the app's earlier name
        $lnk = $ws.CreateShortcut("$dir\Parlo.lnk")
        $lnk.TargetPath = "$Root\.venv\Scripts\pythonw.exe"
        $lnk.Arguments = "`"$Root\app\main.py`""
        $lnk.WorkingDirectory = $Root
        $lnk.IconLocation = "$Root\data\icon.ico"
        $lnk.Save()
        Write-Host "Shortcut: $dir\Parlo.lnk"
    }
}

Step "Done. Start Parlo from the Desktop shortcut or 'Start Parlo.bat'."
