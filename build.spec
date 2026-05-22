# PyInstaller spec — Nations at War
# Build: pyinstaller build.spec --noconfirm

import sys
from pathlib import Path

root = Path(SPECPATH)

datas = [
    (str(root / "world_map_data.npz"), "."),
]

block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "pygame",
        "numpy",
        "nation_ai",
        "real_capitals",
        "map_io",
        "paths",
        "bitmap_font",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NationsAtWar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=sys.platform == "darwin",
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="NationsAtWar",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="NationsAtWar.app",
        icon=None,
        bundle_identifier="dev.dcx.nationsatwar",
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleName": "Nations at War",
        },
    )
