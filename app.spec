# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = []
binaries = []
hiddenimports = []

# Bundle built web UI
datas.append(("web/dist", "web/dist"))

# Bundle .env example if present (optional)
try:
    datas.append((".env.example", "."))
except Exception:
    pass

# Collect common packages with native deps
for pkg in [
    "numpy",
    "pydantic",
    "pydantic_core",
    "pydantic_settings",
    "sqlalchemy",
    "docx",
    "fitz",
    "PIL",
    "Pillow",
    "cryptography",
    "uvicorn",
    "anyio",
    "httpx",
    "email_validator",
    "itsdangerous",
    "multipart",
    "psycopg",
    "starlette",
    "fastapi",
]:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# Ensure app modules are included
hiddenimports += collect_submodules("app")
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("starlette")

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "paddle",
        "paddleocr",
        "paddlepaddle",
        "matplotlib",
        "scipy",
        "tkinter",
        "tests",
        "pytest",
        "IPython",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="BankingLegalAssistant",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
