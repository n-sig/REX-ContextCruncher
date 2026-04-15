"""Hotkeys — register global, system-wide keyboard shortcuts via pynput.

No admin privileges required.  The actual key bindings are loaded from
the user's config file (see ``config.py``).

FR-04: side mouse buttons (X1 / X2) are also supported as standalone
hotkey triggers via ``<mouse_x1>`` and ``<mouse_x2>`` combo strings.
"""

from __future__ import annotations

import logging
from typing import Callable

from pynput import keyboard

log = logging.getLogger(__name__)

# Type alias for a hotkey action callback.
HotkeyAction = Callable[[], None]

# ---------------------------------------------------------------------------
# FR-04 — Mouse button support
# ---------------------------------------------------------------------------

try:
    from pynput import mouse as _mouse

    #: Maps config combo string → pynput Button constant.
    MOUSE_BUTTON_MAP: dict[str, "_mouse.Button"] = {
        "<mouse_x1>": _mouse.Button.x1,
        "<mouse_x2>": _mouse.Button.x2,
    }
    _mouse_available = True
except Exception:          # pragma: no cover
    _mouse_available = False
    MOUSE_BUTTON_MAP = {}


class _MouseHotkeyListener:
    """Listens for side-mouse-button presses and fires registered callbacks.

    Only started when at least one ``<mouse_x*>`` binding is configured.
    """

    def __init__(self, bindings: dict[str, HotkeyAction]) -> None:
        """
        Args:
            bindings: ``{"<mouse_x1>": callback, ...}``
        """
        self._bindings = bindings
        self._listener: "_mouse.Listener | None" = None

    def start(self) -> None:
        if not _mouse_available or not self._bindings:
            return

        button_to_cb: dict["_mouse.Button", HotkeyAction] = {
            MOUSE_BUTTON_MAP[combo]: cb
            for combo, cb in self._bindings.items()
            if combo in MOUSE_BUTTON_MAP
        }

        def _on_click(x, y, button, pressed: bool) -> None:
            if not pressed:
                return
            cb = button_to_cb.get(button)
            if cb:
                try:
                    cb()
                except Exception:
                    log.exception("_MouseHotkeyListener: error in callback")

        self._listener = _mouse.Listener(on_click=_on_click)
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None


class HotkeyManager:
    """Manages global hotkeys for contextcruncher."""

    def __init__(
        self,
        on_scan: HotkeyAction,
        on_navigate_up: HotkeyAction,
        on_navigate_down: HotkeyAction,
        on_search_stack: HotkeyAction | None = None,
        on_ai_compact: HotkeyAction | None = None,
        on_heatmap: HotkeyAction | None = None,
        on_screenshot_full: HotkeyAction | None = None,   # FR-01
        hotkey_bindings: dict[str, str] | None = None,
    ) -> None:
        self._on_scan = on_scan
        self._on_navigate_up = on_navigate_up
        self._on_navigate_down = on_navigate_down
        self._on_search_stack = on_search_stack
        self._on_ai_compact = on_ai_compact
        self._on_heatmap = on_heatmap
        self._on_screenshot_full = on_screenshot_full      # FR-01
        self._bindings = hotkey_bindings or {}
        self._listener: keyboard.GlobalHotKeys | None = None
        self._mouse_listener: _MouseHotkeyListener | None = None  # FR-04

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
            "search_stack": self._on_search_stack,
            "hotkey_heatmap": self._on_heatmap,
        }

        # FR-04: separate mouse bindings from keyboard bindings
        mouse_bindings: dict[str, HotkeyAction] = {}

        for action, combo in self._bindings.items():
            cb = _action_map.get(action)
            if cb is None or not combo:
                continue
            if combo in MOUSE_BUTTON_MAP:          # FR-04 — mouse button
                mouse_bindings[combo] = cb
            else:                                  # regular keyboard combo
                hotkeys[combo] = cb

        self._listener = keyboard.GlobalHotKeys(hotkeys)
        self._listener.daemon = True
        self._listener.start()

        # FR-04 — start mouse listener only when needed
        if mouse_bindings:
            self._mouse_listener = _MouseHotkeyListener(mouse_bindings)
            self._mouse_listener.start()

    def stop(self) -> None:
        """Stop the hotkey listener."""
        if self._listener:
            self._listener.stop()
            self._listener = None
        if self._mouse_listener:          # FR-04
            self._mouse_listener.stop()
            self._mouse_listener = None
