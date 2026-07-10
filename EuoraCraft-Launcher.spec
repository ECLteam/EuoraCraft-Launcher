from PyInstaller.utils.hooks import copy_metadata
import pytauri_wheel
from pathlib import Path

wheel_lib_dir = Path(pytauri_wheel.__file__).parent / "lib"
binaries_list = []
for dll_file in wheel_lib_dir.glob("*.dll"):
    binaries_list.append((str(dll_file), "pytauri_wheel/lib"))

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries_list,
    datas=[
        ("frontend/dist", "frontend/dist"),
        ("resources", "resources"),
        ("ECL", "ECL"),
        ("capabilities", "capabilities"),
        ("Tauri.toml", "."),
    ] + copy_metadata("pytauri-wheel"),
    hiddenimports=[
        "requests",
        "charset_normalizer",
        "idna",
        "urllib3",
        "certifi",
        "importlib_metadata",
        "pytauri",
        "pytauri.ffi",
        "pytauri.ffi._ext_mod",
        "pytauri_wheel",
        "pytauri_wheel.lib",
        "pytauri_wheel.ext_mod",
        "httpx",
        "psutil"
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["numpy", "bcrypt"],
    noarchive=False,
    optimize=2,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="EuoraCraft Launcher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,          # 开发调试阶段保持True；正式发布改成 false
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
