# Build ASMG TX Dashboard (PyInstaller + Inno Setup)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating .venv ..."
    python -m venv .venv
    & $VenvPython -m pip install -U pip
    & $VenvPython -m pip install -r requirements.txt
}
& $VenvPython -m pip install -q "pyinstaller>=6.0"

# Prefer 8090 in the shipped example (installer also sets this).
$Example = Join-Path $Root "config\transmitters.example.yaml"
if (Test-Path $Example) {
    $text = Get-Content -Raw -Path $Example
    $text = [regex]::Replace($text, '(?m)^http_port:\s*\d+', 'http_port: 8090')
    Set-Content -Path $Example -Value $text -NoNewline
}

Write-Host "=== PyInstaller ==="
& $VenvPython -m PyInstaller --noconfirm --clean (Join-Path $Root "asmg_tx_dashboard.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed ($LASTEXITCODE)" }

$DistExe = Join-Path $Root "dist\AsmgTxDashboard\AsmgTxDashboard.exe"
if (-not (Test-Path $DistExe)) { throw "Missing $DistExe" }

$Iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $Iscc)) {
    $Iscc = "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
}
if (-not (Test-Path $Iscc)) {
    throw "Inno Setup 6 not found (ISCC.exe). Install from https://jrsoftware.org/isinfo.php"
}

Write-Host "=== Inno Setup ==="
New-Item -ItemType Directory -Force -Path (Join-Path $Root "dist\installer") | Out-Null
& $Iscc (Join-Path $Root "installer\asmg_tx_dashboard.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed ($LASTEXITCODE)" }

$Setup = Get-ChildItem (Join-Path $Root "dist\installer\ASMG-TX-Dashboard-Setup*.exe") | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Host ""
Write-Host "Build OK:"
Write-Host "  App:     $DistExe"
Write-Host "  Setup:   $($Setup.FullName)"
Write-Host "  Port is chosen in the installer wizard (default 8090)."
