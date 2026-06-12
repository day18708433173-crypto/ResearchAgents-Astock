$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Frontend = Join-Path $Root "frontend"
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) {
  Write-Host "Creating Python virtual environment..."
  $BundledPython = "C:\Users\Dai\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
  if (Test-Path $BundledPython) {
    & $BundledPython -m venv (Join-Path $Root ".venv")
  } else {
    py -3.12 -m venv (Join-Path $Root ".venv")
  }
}

if (!(Test-Path (Join-Path $Root "data"))) {
  New-Item -ItemType Directory -Force (Join-Path $Root "data") | Out-Null
}

Write-Host "Starting Jingheng dev servers..."
Write-Host "Frontend: http://localhost:5000"
Write-Host "Backend:  http://localhost:8000/api/health"
Write-Host ""

$backend = Start-Job -Name "jingheng-backend" -ScriptBlock {
  param($Root, $Python)
  Set-Location $Root
  & $Python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
} -ArgumentList $Root, $Python

$frontend = Start-Job -Name "jingheng-frontend" -ScriptBlock {
  param($Frontend)
  Set-Location $Frontend
  & npm.cmd run dev -- -p 5000
} -ArgumentList $Frontend

try {
  while ($true) {
    Receive-Job $backend, $frontend
    Start-Sleep -Seconds 1
  }
} finally {
  Stop-Job $backend, $frontend -ErrorAction SilentlyContinue
  Remove-Job $backend, $frontend -Force -ErrorAction SilentlyContinue
}
