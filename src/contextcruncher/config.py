"""
config.py — Persistent application settings.

Stores settings in ``%APPDATA%/ContextCruncher/config.json``.  On first
launch the file is created with sensible defaults.

pynput key names reference:
  Modifiers : <ctrl>, <alt>, <shift>, <cmd>
  Specials  : <up>, <down>, <left>, <right>, <space>, <tab>, <enter>,
              <f1>–<f12>, <home>, <end>, <delete>, <insert>, <page_up>,
              <page_down>, <print_screen>, <scroll_lock>, <pause>
  Letters   : a–z  (lowercase, no angle brackets)
  Digits    : 0–9  (without angle brackets)

Combine with ``+``:  ``<ctrl>+<alt>+q``
"""

from __future__ import annotations

import json
import os
import sys
import winreg
from typing import Any

# -----------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------
_APP_DIR = os.path.join(os.environ.get("APPDATA", "."), "ContextCruncher")
CONFIG_PATH = os.path.join(_APP_DIR, "config.json")

# -----------------------------------------------------------------------
# Defaults
# -----------------------------------------------------------------------
DEFAULT_HOTKEYS: dict[str, str] = {
    "scan": "<ctrl>+<alt>+s",
    "ai_compact": "<ctrl>+<alt>+c",
    "navigate_up": "<ctrl>+<shift>+<up>",
    "navigate_down": "<ctrl>+<shift>+<down>",
    "toggle_compact": "<ctrl>+<shift>+<right>",
    "hotkey_heatmap": "<alt>+h",
}

_DEFAULT_CONFIG: dict[str, Any] = {
    "hotkeys": DEFAULT_HOTKEYS.copy(),
    "ocr_language": "auto",
    "max_stack_size": 50,
    "ai_compact_level": 1,
    "autostart": False,
    "auto_crunch": False,
    "xml_wrap": False,
    "xml_tag": "context",
    "variant_mode": "cycle",  # "cycle" or "popup"
}


# -----------------------------------------------------------------------
# Load / save
# -----------------------------------------------------------------------

def _ensure_dir() -> None:
    os.makedirs(_APP_DIR, exist_ok=True)


def load_config() -> dict[str, Any]:
    """Load the config file, creating it with defaults if it does not exist."""
    _ensure_dir()

    if not os.path.isfile(CONFIG_PATH):
        save_config(_DEFAULT_CONFIG)
        return _DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        save_config(_DEFAULT_CONFIG)
        return _DEFAULT_CONFIG.copy()

    # Merge missing keys from defaults (forward-compat).
    for key, default in _DEFAULT_CONFIG.items():
        if key not in data:
            data[key] = default
    hotkeys = data.get("hotkeys", {})
    for key, default in DEFAULT_HOTKEYS.items():
        hotkeys.setdefault(key, default)
    data["hotkeys"] = hotkeys
    return data


def save_config(data: dict[str, Any]) -> None:
    """Write *data* to the config file."""
    _ensure_dir()
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def get_hotkeys() -> dict[str, str]:
    """Return a ``{action: hotkey_string}`` mapping."""
    cfg = load_config()
    return cfg.get("hotkeys", DEFAULT_HOTKEYS.copy())


# -----------------------------------------------------------------------
# Display helpers
# -----------------------------------------------------------------------

def hotkey_display_name(hotkey: str) -> str:
    """Turn ``<ctrl>+<alt>+s`` into ``Ctrl+Alt+S`` for display."""
    parts = hotkey.split("+")
    pretty: list[str] = []
    for p in parts:
        p = p.strip()
        if p.startswith("<") and p.endswith(">"):
            inner = p[1:-1]
            pretty.append(inner.replace("_", " ").title())
        else:
            pretty.append(p.upper())
    return "+".join(pretty)


HOTKEY_ACTION_LABELS: dict[str, str] = {
    "scan": "Scan Region",
    "ai_compact": "AI Cruncher",
    "navigate_up": "Newer ↑",
    "navigate_down": "Older ↓",
    "toggle_compact": "Variants ↔",
    "hotkey_heatmap": "Token Heatmap",
}


# -----------------------------------------------------------------------
# Autostart (Windows Registry)
# -----------------------------------------------------------------------
_AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_AUTOSTART_NAME = "ContextCruncher"


def _get_exe_path() -> str:
    """Return the path to the running executable or script."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.abspath(sys.argv[0])


def set_autostart(enabled: bool) -> None:
    """Enable or disable Windows autostart for contextcruncher."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE)
        if enabled:
            winreg.SetValueEx(key, _AUTOSTART_NAME, 0, winreg.REG_SZ, f'"{_get_exe_path()}"')
        else:
            try:
                winreg.DeleteValue(key, _AUTOSTART_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except OSError:
        pass


def get_autostart() -> bool:
    """Check if autostart is currently enabled."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_KEY, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, _AUTOSTART_NAME)
        winreg.CloseKey(key)
        return True
    except (FileNotFoundError, OSError):
        return False
