# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['launcher.py'],
    pathex=['.venv/Lib/site-packages'],
    binaries=[(r'.venv\Lib\site-packages\tkinterdnd2\tkdnd\win64\libtkdnd2.9.2.dll', 'tkinterdnd2/tkdnd/win64')],
    datas=[(r'.venv\Lib\site-packages\tkinterdnd2\tkdnd\win64\*.tcl', 'tkinterdnd2/tkdnd/win64')],
    hiddenimports=['tkinterdnd2'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AutoBaseBot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
)
