#!/bin/bash
# Build Voice Dictation for macOS
set -euo pipefail

echo "Building Voice Dictation for macOS..."

# Clean previous builds
rm -rf build/ dist/

# Install PyInstaller if needed
pip install pyinstaller>=6.0

# Build
pyinstaller voice_dictation.spec --noconfirm

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
