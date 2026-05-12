# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ICON = ROOT / "packaging" / "build" / "windows" / "telegram-control-center.ico"

datas = [
    (str(ROOT / "tools" / "telegram"), "tools/telegram"),
    (str(ROOT / "docs"), "docs"),
    (str(ROOT / "scripts" / "telegram_portable.py"), "scripts"),
    (str(ROOT / "scripts" / "telegram_invite_manager.py"), "scripts"),
    (str(ROOT / "scripts" / "telegram_invite_executor.py"), "scripts"),
    (str(ROOT / "packaging" / "assets" / "telegram-control-center.svg"), "packaging/assets"),
]

a = Analysis(
    [str(ROOT / "tool_platform" / "control_center.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "tkinter",
        "tool_platform.gui",
        "telegram_portable_session_tool.cli",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["runtime", "TG_APP", "telegram_ak"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="TelegramControlCenter",
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
    icon=str(ICON) if ICON.exists() else None,
)
