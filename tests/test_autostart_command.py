"""
Tests for config._get_autostart_command() and set_autostart() — BUG-08.

Goal: the registry Run value must always be a launchable shell command:
  - Frozen (.exe) → "path/to/app.exe"
  - Dev mode      → "path/to/python.exe" "path/to/main.py"

All Windows APIs (winreg, sys.frozen, sys.executable, sys.argv) are
replaced with mocks so the tests run on Linux CI without side-effects.
"""

from __future__ import annotations

import os
import sys
import types
import unittest.mock as mock
from pathlib import Path

import pytest

# ── Stub winreg for Linux CI ─────────────────────────────────────────────────
if "winreg" not in sys.modules:
    _fake_winreg = types.ModuleType("winreg")
    for _attr in (
        "OpenKey", "CloseKey", "SetValueEx", "DeleteValue",
        "QueryValueEx", "HKEY_CURRENT_USER", "KEY_SET_VALUE",
        "KEY_READ", "REG_SZ",
    ):
        setattr(_fake_winreg, _attr, mock.MagicMock())
    sys.modules["winreg"] = _fake_winreg

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from contextcruncher.config import _get_autostart_command  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_frozen(exe_path: str) -> str:
    """Simulate a PyInstaller-frozen process and return the command string."""
    with (
        mock.patch.object(sys, "frozen", True, create=True),
        mock.patch.object(sys, "executable", exe_path),
    ):
        return _get_autostart_command()


def _run_dev(python_exe: str, script_path: str) -> str:
    """Simulate a dev-mode process and return the command string."""
    abs_script = os.path.abspath(script_path)
    with (
        mock.patch.object(sys, "executable", python_exe),
        mock.patch("sys.argv", [script_path]),
        mock.patch("contextcruncher.config.getattr", side_effect=lambda obj, attr, *d: (
            False if (obj is sys and attr == "frozen") else getattr(obj, attr, *d)
        ), create=False),
    ):
        # Unset frozen to simulate dev mode (default: attribute absent)
        if hasattr(sys, "frozen"):
            with mock.patch.object(sys, "frozen", False):
                return _get_autostart_command()
        return _get_autostart_command()


# ---------------------------------------------------------------------------
# Tests — frozen mode
# ---------------------------------------------------------------------------

def test_frozen_returns_quoted_exe():
    """Frozen mode must return the exe path wrapped in double quotes."""
    result = _run_frozen(r"C:\Program Files\ContextCruncher\contextcruncher.exe")
    assert result == r'"C:\Program Files\ContextCruncher\contextcruncher.exe"'


def test_frozen_no_python_in_command():
    """Frozen mode must NOT reference python.exe."""
    result = _run_frozen(r"C:\App\app.exe")
    assert "python" not in result.lower()


def test_frozen_single_quoted_token():
    """Frozen mode command is a single quoted token (exe only, no script arg)."""
    result = _run_frozen(r"C:\App\app.exe")
    # Should start and end with a quote; no space outside quotes means 1 token
    assert result.startswith('"') and result.endswith('"')
    # Strip the surrounding quotes — remaining string should have no unquoted space
    inner = result[1:-1]
    assert '"' not in inner, "Frozen command must not contain nested quotes"


# ---------------------------------------------------------------------------
# Tests — dev mode
# ---------------------------------------------------------------------------

def test_dev_mode_contains_python_exe():
    """Dev mode command must reference the Python interpreter."""
    with (
        mock.patch.object(sys, "executable", r"C:\Python311\python.exe"),
        mock.patch("sys.argv", [r"C:\projects\src\contextcruncher\main.py"]),
    ):
        # Ensure sys.frozen is absent (dev mode)
        frozen_attr = getattr(sys, "frozen", None)
        try:
            if hasattr(sys, "frozen"):
                del sys.frozen  # type: ignore[attr-defined]
            result = _get_autostart_command()
        finally:
            if frozen_attr is not None:
                sys.frozen = frozen_attr  # type: ignore[attr-defined]

    assert r"C:\Python311\python.exe" in result


def test_dev_mode_contains_script_path():
    """Dev mode command must include the absolute path to the script."""
    script = r"C:\projects\src\contextcruncher\main.py"
    with (
        mock.patch.object(sys, "executable", r"C:\Python311\python.exe"),
        mock.patch("sys.argv", [script]),
        mock.patch("os.path.abspath", side_effect=lambda p: p),
    ):
        frozen_attr = getattr(sys, "frozen", None)
        try:
            if hasattr(sys, "frozen"):
                del sys.frozen  # type: ignore[attr-defined]
            result = _get_autostart_command()
        finally:
            if frozen_attr is not None:
                sys.frozen = frozen_attr  # type: ignore[attr-defined]

    assert script in result


def test_dev_mode_two_quoted_tokens():
    """Dev mode command must have two quoted tokens: interpreter and script."""
    with (
        mock.patch.object(sys, "executable", r"C:\Python311\python.exe"),
        mock.patch("sys.argv", [r"C:\projects\main.py"]),
        mock.patch("os.path.abspath", side_effect=lambda p: p),
    ):
        frozen_attr = getattr(sys, "frozen", None)
        try:
            if hasattr(sys, "frozen"):
                del sys.frozen  # type: ignore[attr-defined]
            result = _get_autostart_command()
        finally:
            if frozen_attr is not None:
                sys.frozen = frozen_attr  # type: ignore[attr-defined]

    # Expected form: "interpreter" "script"
    assert result.count('"') == 4, (
        f"Expected 4 double-quotes in dev-mode command, got: {result!r}"
    )


def test_dev_mode_interpreter_before_script():
    """The interpreter path must appear before the script path in the command."""
    python = r"C:\Python311\python.exe"
    script = r"C:\projects\main.py"
    with (
        mock.patch.object(sys, "executable", python),
        mock.patch("sys.argv", [script]),
        mock.patch("os.path.abspath", side_effect=lambda p: p),
    ):
        frozen_attr = getattr(sys, "frozen", None)
        try:
            if hasattr(sys, "frozen"):
                del sys.frozen  # type: ignore[attr-defined]
            result = _get_autostart_command()
        finally:
            if frozen_attr is not None:
                sys.frozen = frozen_attr  # type: ignore[attr-defined]

    assert result.index(python) < result.index(script)


def test_dev_mode_path_with_spaces():
    """Paths containing spaces must be quoted so Windows can parse the command."""
    python = r"C:\Program Files\Python311\python.exe"
    script = r"C:\My Projects\contextcruncher\main.py"
    with (
        mock.patch.object(sys, "executable", python),
        mock.patch("sys.argv", [script]),
        mock.patch("os.path.abspath", side_effect=lambda p: p),
    ):
        frozen_attr = getattr(sys, "frozen", None)
        try:
            if hasattr(sys, "frozen"):
                del sys.frozen  # type: ignore[attr-defined]
            result = _get_autostart_command()
        finally:
            if frozen_attr is not None:
                sys.frozen = frozen_attr  # type: ignore[attr-defined]

    # Each path must appear inside quotes
    assert f'"{python}"' in result
    assert f'"{script}"' in result


# ---------------------------------------------------------------------------
# Tests — set_autostart integration (winreg mock)
# ---------------------------------------------------------------------------

def test_set_autostart_enabled_writes_registry():
    """set_autostart(True) must call winreg.SetValueEx with a non-empty value."""
    from contextcruncher.config import set_autostart

    mock_open = mock.MagicMock(return_value=mock.MagicMock())
    mock_set = mock.MagicMock()
    mock_close = mock.MagicMock()

    with (
        mock.patch("contextcruncher.config.winreg.OpenKey", mock_open),
        mock.patch("contextcruncher.config.winreg.SetValueEx", mock_set),
        mock.patch("contextcruncher.config.winreg.CloseKey", mock_close),
    ):
        set_autostart(True)

    assert mock_set.called, "SetValueEx must be called when enabling autostart"
    # 4th positional arg is the registry value
    call_args = mock_set.call_args
    registry_value = call_args[0][4]  # (key, name, reserved, type, value)
    assert registry_value, "Registry value must not be empty"
    assert '"' in registry_value, "Registry value must contain quoted paths"


def test_set_autostart_disabled_deletes_registry():
    """set_autostart(False) must call winreg.DeleteValue."""
    from contextcruncher.config import set_autostart

    mock_open = mock.MagicMock(return_value=mock.MagicMock())
    mock_delete = mock.MagicMock()
    mock_close = mock.MagicMock()

    with (
        mock.patch("contextcruncher.config.winreg.OpenKey", mock_open),
        mock.patch("contextcruncher.config.winreg.DeleteValue", mock_delete),
        mock.patch("contextcruncher.config.winreg.CloseKey", mock_close),
    ):
        set_autostart(False)

    assert mock_delete.called, "DeleteValue must be called when disabling autostart"
