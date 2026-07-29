# voice_dictation.spec
import os
import sys

import faster_whisper

block_cipher = None

# Find silero_vad_v6.onnx dynamically — it's bundled with faster_whisper
_silero_vad_path = os.path.join(
    os.path.dirname(faster_whisper.__file__),
    "assets",
    "silero_vad_v6.onnx",
)

a = Analysis(
    ['src/voice_dictation/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/icons', 'assets/icons'),
        (_silero_vad_path, 'faster_whisper/assets'),
    ],
    hiddenimports=[
        'sounddevice',
        'numpy',
        'pynput',
        'pynput.keyboard',
        'pynput.keyboard._darwin',
        'pynput.keyboard._win32',
        'pynput.mouse',
        'pynput.mouse._darwin',
        'pynput.mouse._win32',
        'pystray',
        'pystray._darwin',
        'pystray._win32',
        'PIL',
        'PIL.Image',
        'loguru',
        'pydantic',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'pytest_cov', 'pytest_mock', 'pytest_timeout', 'ruff', 'mypy', 'tests'],
    cipher=block_cipher,
    noarchive=False,
)

# Platform-specific hidden imports
import sys
if sys.platform == 'darwin':
    a.hiddenimports += [
        'Quartz',
        'AppKit',
        'ApplicationServices',
        'CoreFoundation',
        'Foundation',
        'objc',
        'Carbon',
    ]
    a.binaries += [
        # Ensure libdispatch is bundled for dispatch_async in carbon_listener
    ]
elif sys.platform == 'win32':
    a.hiddenimports += [
        'win32clipboard',
        'win32con',
        'ctypes.wintypes',
    ]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='voice-dictation',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    # icon='assets/icons/app_icon.icns',  # Uncomment when icon is available
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='voice-dictation',
)

# macOS .app bundle
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='Voice Dictation.app',
        # icon='assets/icons/app_icon.icns',
        bundle_identifier='com.alfagen.voice-dictation',
        info_plist={
            'LSUIElement': True,  # No Dock icon, tray only
            'NSMicrophoneUsageDescription': 'Voice Dictation needs microphone access to transcribe your speech.',
            'NSAppleEventsUsageDescription': 'Voice Dictation uses AppleScript to simulate Cmd+V paste into the active text field.',
            'LSEnvironment': {
                'LANG': 'en_US.UTF-8',
                'LC_ALL': 'en_US.UTF-8',
            },
            'CFBundleName': 'Voice Dictation',
            'CFBundleShortVersionString': '0.1.0',
            'CFBundleVersion': '1',
        },
    )
