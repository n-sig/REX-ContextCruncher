"""Hotkeys — register global, system-wide keyboard shortcuts via pynput.

No admin privileges required.  The actual key bindings are loaded from
the user's config file (see ``config.py``).
"""

from __future__ import annotations

from typing import Callable

from pynput import keyboard

# Type alias for a hotkey action callback.
HotkeyAction = Callable[[], None]


class HotkeyManager:
    """Manages global hotkeys for contextcruncher."""

    def __init__(
        self,
        on_scan: HotkeyAction,
        on_navigate_up: HotkeyAction,
        on_navigate_down: HotkeyAction,
        on_toggle_compact: HotkeyAction | None = None,
        on_ai_compact: HotkeyAction | None = None,
        on_heatmap: HotkeyAction | None = None,
        on_screenshot_full: HotkeyAction | None = None,   # FR-01
        hotkey_bindings: dict[str, str] | None = None,
    ) -> None:
        self._on_scan = on_scan
        self._on_navigate_up = on_navigate_up
        self._on_navigate_down = on_navigate_down
        self._on_toggle_compact = on_toggle_compact
        self._on_ai_compact = on_ai_compact
        self._on_heatmap = on_heatmap
        self._on_screenshot_full = on_screenshot_full      # FR-01
        self._bindings = hotkey_bindings or {}
        self._listener: keyboard.GlobalHotKeys | None = None

    def start(self) -> None:
        """Start listening for hotkeys (non-blocking, runs in a daemon thread)."""
        hotkeys: dict[str, HotkeyAction] = {}

        # Map config keys to callbacks.
        _action_map: dict[str, HotkeyAction | None] = {
            "scan": self._on_scan,
            "screenshot_full": self._on_screenshot_full,  # FR-01
            "ai_compact": self._on_ai_compact,
            "navigate_up": self._on_navigate_up,
            "navigate_down": self._on_navigate_down,
            "toggle_compact": self._on_toggle_compact,
            "hotkey_heatmap": self._on_heatmap,
        }

        for action, combo in self._bindings.items():
            cb = _action_map.get(action)
            if cb is not None and combo:
                hotkeys[combo] = cb

        self._listener = keyboard.GlobalHotKeys(hotkeys)
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        """Stop the hotkey listener."""
        if self._listener:
            self._listener.stop()
            self._listener = None
