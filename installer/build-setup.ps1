# Builds dist\ParloSetup.exe with the C# compiler that ships with Windows.
#   powershell -ExecutionPolicy Bypass -File installer\build-setup.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path $csc)) { throw "The Windows C# compiler was not found at $csc" }

$version = [regex]::Match((Get-Content (Join-Path $root 'app\version.py') -Raw), '__version__ = "([\d.]+)"').Groups[1].Value
if (-not $version) { throw 'No version number in app\version.py' }

$dist = Join-Path $root 'dist'
New-Item -ItemType Directory -Force $dist | Out-Null
$info = Join-Path $dist 'AssemblyInfo.cs'
@"
using System.Reflection;
[assembly: AssemblyTitle("Parlo Setup")]
[assembly: AssemblyProduct("Parlo")]
[assembly: AssemblyDescription("Installs Parlo, private dictation for Windows")]
[assembly: AssemblyVersion("$version.0")]
[assembly: AssemblyFileVersion("$version.0")]
"@ | Set-Content -Path $info -Encoding UTF8

$out = Join-Path $dist 'ParloSetup.exe'
& $csc /nologo /target:exe /platform:anycpu /optimize+ `
    "/out:$out" `
    "/win32icon:$(Join-Path $PSScriptRoot 'parlo.ico')" `
    "/resource:$(Join-Path $root 'Install Parlo.bat'),InstallParlo.bat" `
    (Join-Path $PSScriptRoot 'ParloSetup.cs') $info
if ($LASTEXITCODE -ne 0) { throw "The build failed (exit code $LASTEXITCODE)" }
Remove-Item $info
$hash = (Get-FileHash $out -Algorithm SHA256).Hash.ToLower()
Write-Host "Built $out (version $version, $([math]::Round((Get-Item $out).Length / 1KB)) KB)"
Write-Host "SHA256 $hash"
