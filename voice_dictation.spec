# voice_dictation.spec
block_cipher = None

a = Analysis(
    ['src/voice_dictation/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/icons', 'assets/icons'),
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
        'objc',
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
            'CFBundleName': 'Voice Dictation',
            'CFBundleShortVersionString': '0.1.0',
            'CFBundleVersion': '1',
        },
    )
