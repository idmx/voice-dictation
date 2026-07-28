# Build Voice Dictation for Windows
Write-Host "Building Voice Dictation for Windows..."

$ErrorActionPreference = "Stop"

# Use venv Python (has all project dependencies)
if (-not (Test-Path ".venv")) {
    Write-Host "Error: .venv not found. Run: python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -e '.[dev]'"
    exit 1
}

$python = ".\.venv\Scripts\python.exe"

# Install PyInstaller into venv
Write-Host "Installing PyInstaller into venv..."
& $python -m pip install --quiet "pyinstaller>=6.0"

# Clean previous builds
if (Test-Path build) { Remove-Item -Recurse -Force build }
if (Test-Path dist) { Remove-Item -Recurse -Force dist }

# Build with venv Python (includes all dependencies)
Write-Host "Running PyInstaller..."
& $python -m PyInstaller voice_dictation.spec --noconfirm

# Check output
if (Test-Path "dist\voice-dictation") {
    Write-Host "Build successful!"
    Write-Host "Executable: dist\voice-dictation\voice-dictation.exe"
} else {
    Write-Host "Build failed!"
    exit 1
}
