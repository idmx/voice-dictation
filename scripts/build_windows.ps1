# Build Voice Dictation for Windows
Write-Host "Building Voice Dictation for Windows..."

# Clean previous builds
if (Test-Path build) { Remove-Item -Recurse -Force build }
if (Test-Path dist) { Remove-Item -Recurse -Force dist }

# Install PyInstaller
pip install pyinstaller>=6.0

# Build
pyinstaller voice_dictation.spec --noconfirm

# Check output
if (Test-Path "dist\voice-dictation") {
    Write-Host "Build successful!"
    Write-Host "Executable: dist\voice-dictation\voice-dictation.exe"
    
    # Create installer with NSIS (optional)
    # makensis installer.nsi
} else {
    Write-Host "Build failed!"
    exit 1
}
