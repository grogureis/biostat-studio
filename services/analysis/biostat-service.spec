# -*- mode: python ; coding: utf-8 -*-
from os.path import join

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs


block_cipher = None
spec_root = SPECPATH
datas = []
binaries = []
hiddenimports = [
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
]
for package in (
    "docx",
    "fastapi",
    "matplotlib",
    "numpy",
    "openpyxl",
    "pandas",
    "pydantic",
    "pypdf",
    "scipy",
    "statsmodels",
    "uvicorn",
):
    datas += collect_data_files(package, include_py_files=False)
    binaries += collect_dynamic_libs(package)

a = Analysis(
    [join(spec_root, "biostat_service", "__main__.py")],
    pathex=[spec_root],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    name="biostat-service",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    target_arch="arm64",
    exclude_binaries=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="biostat-service",
)
