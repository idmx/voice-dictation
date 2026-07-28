#!/bin/bash
# Build Voice Dictation for macOS
set -euo pipefail

echo "Building Voice Dictation for macOS..."

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Use venv Python (has all project dependencies)
if [ ! -d ".venv" ]; then
    echo "Error: .venv not found. Run: python -m venv .venv && source .venv/bin/activate && pip install -e '.[dev]'"
    exit 1
fi

PYTHON=".venv/bin/python"

# Ensure pip is available in venv
$PYTHON -m ensurepip --default-pip 2>/dev/null || true

# Install PyInstaller into venv
echo "Installing PyInstaller into venv..."
$PYTHON -m pip install --quiet "pyinstaller>=6.0"

# Clean previous builds
rm -rf build dist

# Build with venv Python (includes all dependencies)
echo "Running PyInstaller..."
$PYTHON -m PyInstaller voice_dictation.spec --noconfirm

# Check output
if [ -d "dist/voice-dictation" ]; then
    echo "Build successful!"
    echo "Executable: dist/voice-dictation/voice-dictation"
    echo "App bundle: dist/Voice Dictation.app"
    
    # Create DMG (optional)
    if command -v hdiutil &> /dev/null; then
        echo "Creating DMG..."
        hdiutil create -volname "Voice Dictation" -srcfolder "dist/Voice Dictation.app" -ov -format UDZO "dist/voice-dictation.dmg"
        echo "DMG: dist/voice-dictation.dmg"
    fi
else
    echo "Build failed!"
    exit 1
fi
