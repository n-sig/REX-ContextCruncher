# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for contextcruncher — single-file Windows executable."""

import os

block_cipher = None

a = Analysis(
    ["src/contextcruncher/main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("src/contextcruncher/assets/icon.png", "assets"),
    ],
    hiddenimports=[
        # winrt modules required at runtime
        "winrt.windows.media.ocr",
        "winrt.windows.graphics.imaging",
        "winrt.windows.globalization",
        "winrt.windows.storage.streams",
        "winrt.windows.foundation",
        "winrt.windows.foundation.collections",
        # pystray backend
        "pystray._win32",
        # pynput backend
        "pynput.keyboard._win32",
        "pynput.mouse._win32",
        # pyperclip backend
        "pyperclip",
        # mcp_server and new features
        "contextcruncher.mcp_server",
        "contextcruncher.skeletonizer",
        "contextcruncher.security_scanner",
        "contextcruncher.variant_picker",
        "contextcruncher.normalize",
        "contextcruncher.ui.heatmap",
        # AI Context Manager (FR-05) — content routing + hybrid LLM compression
        "contextcruncher.content_router",
        "contextcruncher.prompt_optimizer",
        "contextcruncher.diff_cache",
        "contextcruncher.search_picker",
        # httpx backend (used by prompt_optimizer for all provider calls)
        "httpx",
        "httpcore",
        # tiktoken backend
        "tiktoken",
        "tiktoken_ext.openai_public",
        "tiktoken_ext",
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ContextCruncher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,        # No console window
    windowed=True,        # GUI application
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="src/contextcruncher/assets/icon.png",
)
