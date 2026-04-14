"""
settings.py — GUI settings dialog with live hotkey recorder.

FIX (Bug #1): Dialog is now a tk.Toplevel owned by the global TkManager
instead of a standalone tk.Tk() root.  open_settings() blocks the calling
(background) thread via threading.Event instead of mainloop().

FIX (Bug #2): _HotkeyField recorder listener is now always stopped on:
  • Non-modifier key release (finalize combo)
  • All modifier keys released without a trigger key (cancel recording)
  • Dialog destroy / window close (cleanup)
  A "×" button on each row clears the binding entirely.

  All tkinter label updates from the pynput listener thread are dispatched
  via root.after() to avoid cross-thread tkinter access.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable

from PIL import Image, ImageTk
from pynput import keyboard as kb
try:
    from pynput import mouse as _mouse_mod
    _MOUSE_RECORD_MAP = {
        _mouse_mod.Button.x1: "<mouse_x1>",
        _mouse_mod.Button.x2: "<mouse_x2>",
    }
    _mouse_record_available = True
except Exception:
    _mouse_record_available = False
    _MOUSE_RECORD_MAP = {}

from contextcruncher.config import (
    load_config,
    save_config,
    hotkey_display_name,
    HOTKEY_ACTION_LABELS,
    DEFAULT_HOTKEYS,
    set_autostart,
    get_autostart,
    find_hotkey_collision,
)
from contextcruncher.feedback import get_tk_manager
from contextcruncher.ocr import get_available_languages

log = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# Dark theme colors
# -----------------------------------------------------------------------
_BG = "#121212"
_BG_FIELD = "#1e1e1e"
_BG_ACTIVE = "#2d2d2d"
_FG = "#ffffff"
_FG_DIM = "#888888"
_ACCENT = "#D9060D"
_ACCENT_BLUE = "#ff3333"
_BTN_BG = "#2d2d2d"
_BTN_HOVER = "#3d3d3d"


# -----------------------------------------------------------------------
# Resource path helper
# -----------------------------------------------------------------------

def _get_resource_path(relative_path: str) -> str:
    """Resolve *relative_path* for both dev and PyInstaller frozen mode."""
    try:
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    except AttributeError:
        base_path = os.path.dirname(__file__)
    return os.path.join(base_path, relative_path)


# -----------------------------------------------------------------------
# Hotkey recorder widget
# -----------------------------------------------------------------------

class _HotkeyField(tk.Frame):
    """A single-line entry that records a keyboard shortcut when focused.

    FIX: The pynput listener is always stopped on key release (both
    non-modifier finalize and modifier-only cancel).  All tkinter label
    updates are dispatched via root.after() to keep them on TkUIThread.
    """

    def __init__(self, parent: tk.Widget, initial: str = "", **kw) -> None:
        super().__init__(parent, bg=_BG, **kw)
        self._combo = initial
        self._recording = False
        self._pressed_keys: set[str] = set()
        self._listener: kb.Listener | None = None
        self._mouse_listener: "_mouse_mod.Listener | None" = None  # FR-04

        self._label = tk.Label(
            self,
            text=hotkey_display_name(initial) if initial else "Not assigned",
            font=("Segoe UI", 11),
            fg=_FG,
            bg=_BG_FIELD,
            padx=12,
            pady=6,
            width=22,
            anchor="center",
            cursor="hand2",
        )
        self._label.pack(fill=tk.X)
        self._label.bind("<Button-1>", self._start_recording)

    # ── Public API ──────────────────────────────────────────────────────

    @property
    def combo(self) -> str:
        return self._combo

    def clear(self) -> None:
        """Clear the binding to empty (no hotkey)."""
        self._cancel_recording()
        self._combo = ""
        self._label.config(text="Not assigned", bg=_BG_FIELD, fg=_FG_DIM)

    def cleanup(self) -> None:
        """Stop any active listener — call before the parent dialog is destroyed."""
        if self._recording:
            self._cancel_recording()
        elif self._listener:
            self._listener.stop()
            self._listener = None
        # FR-04 — also stop mouse listener if still running
        if self._mouse_listener:
            self._mouse_listener.stop()
            self._mouse_listener = None

    # ── Recording lifecycle ─────────────────────────────────────────────

    def _start_recording(self, _event: tk.Event | None = None) -> None:
        if self._recording:
            return
        self._recording = True
        self._pressed_keys.clear()
        hint = " or 🖱 side btn" if _mouse_record_available else ""
        self._label.config(text=f"⌨ Press keys…{hint}", bg=_ACCENT_BLUE, fg="#1e1e2e")

        self._listener = kb.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self._listener.start()

        # FR-04 — also listen for mouse side buttons during recording
        if _mouse_record_available:
            self._mouse_listener = _mouse_mod.Listener(
                on_click=self._on_mouse_click,
            )
            self._mouse_listener.daemon = True
            self._mouse_listener.start()

    def _on_mouse_click(self, x, y, button, pressed: bool) -> None:
        """FR-04 — called from pynput mouse thread during recording."""
        if not self._recording or not pressed:
            return
        combo = _MOUSE_RECORD_MAP.get(button)
        if combo:
            # Replace pressed_keys with the mouse button token and finalize
            self._pressed_keys = {combo}
            get_tk_manager().schedule(self._finalize_mouse_recording)

    def _finalize_mouse_recording(self) -> None:
        """FR-04 — save mouse button combo and update label (TkUIThread)."""
        self._recording = False
        if self._listener:
            self._listener.stop()
            self._listener = None
        if self._mouse_listener:
            self._mouse_listener.stop()
            self._mouse_listener = None

        if self._pressed_keys:
            self._combo = next(iter(self._pressed_keys))
            self._label.config(
                text=hotkey_display_name(self._combo),
                bg=_BG_FIELD,
                fg=_ACCENT,
            )
        self._pressed_keys.clear()

    def _on_key_press(self, key: kb.Key | kb.KeyCode | None) -> None:
        pynput_key = self._key_to_pynput(key)
        if pynput_key:
            self._pressed_keys.add(pynput_key)

    def _on_key_release(self, key: kb.Key | kb.KeyCode | None) -> None:
        """Called from pynput thread — dispatch any tkinter updates via after()."""
        if not self._recording:
            return

        pynput_key = self._key_to_pynput(key)
        modifiers = {"<ctrl>", "<shift>", "<alt>", "<cmd>"}

        if pynput_key and pynput_key not in modifiers:
            # A real trigger key was released → finalize combo
            get_tk_manager().schedule(self._finalize_recording)
        elif pynput_key in modifiers:
            # A modifier was released — remove it from the tracked set
            self._pressed_keys.discard(pynput_key)
            # If no keys remain at all, user released everything without a
            # trigger key → cancel recording (prevents infinite listener leak)
            if not self._pressed_keys:
                get_tk_manager().schedule(self._cancel_recording)

    def _finalize_recording(self) -> None:
        """Build and save the combo string — runs on TkUIThread."""
        self._recording = False
        if self._listener:
            self._listener.stop()
            self._listener = None

        modifiers = {"<ctrl>", "<shift>", "<alt>", "<cmd>"}
        mod_order = ["<ctrl>", "<alt>", "<shift>", "<cmd>"]
        mods = [m for m in mod_order if m in self._pressed_keys]
        keys = [k for k in self._pressed_keys if k not in modifiers]

        if mods and keys:
            self._combo = "+".join(mods + keys[:1])
            self._label.config(
                text=hotkey_display_name(self._combo),
                bg=_BG_FIELD,
                fg=_ACCENT,
            )
        else:
            # Nothing valid — keep old combo
            self._label.config(
                text=hotkey_display_name(self._combo) if self._combo else "Not assigned",
                bg=_BG_FIELD,
                fg=_FG,
            )
        self._pressed_keys.clear()

    def _cancel_recording(self) -> None:
        """Cancel without changing combo — runs on TkUIThread."""
        self._recording = False
        if self._listener:
            self._listener.stop()
            self._listener = None
        if self._mouse_listener:          # FR-04
            self._mouse_listener.stop()
            self._mouse_listener = None
        self._label.config(
            text=hotkey_display_name(self._combo) if self._combo else "Not assigned",
            bg=_BG_FIELD,
            fg=_FG,
        )
        self._pressed_keys.clear()

    # ── Key mapping ─────────────────────────────────────────────────────

    def _key_to_pynput(self, key: kb.Key | kb.KeyCode | None) -> str:
        """Convert a pynput key object to a hotkey string token."""
        if key is None:
            return ""
        if isinstance(key, kb.Key):
            mapping = {
                kb.Key.ctrl_l: "<ctrl>", kb.Key.ctrl_r: "<ctrl>",
                kb.Key.shift_l: "<shift>", kb.Key.shift_r: "<shift>",
                kb.Key.alt_l: "<alt>", kb.Key.alt_r: "<alt>",
                kb.Key.alt_gr: "<alt>",
                kb.Key.cmd_l: "<cmd>", kb.Key.cmd_r: "<cmd>",
                kb.Key.up: "<up>", kb.Key.down: "<down>",
                kb.Key.left: "<left>", kb.Key.right: "<right>",
                kb.Key.space: "<space>", kb.Key.tab: "<tab>",
                kb.Key.enter: "<enter>", kb.Key.delete: "<delete>",
                kb.Key.home: "<home>", kb.Key.end: "<end>",
                kb.Key.page_up: "<page_up>", kb.Key.page_down: "<page_down>",
                kb.Key.insert: "<insert>",
                kb.Key.print_screen: "<print_screen>",
                kb.Key.f1: "<f1>",  kb.Key.f2: "<f2>",  kb.Key.f3: "<f3>",
                kb.Key.f4: "<f4>",  kb.Key.f5: "<f5>",  kb.Key.f6: "<f6>",
                kb.Key.f7: "<f7>",  kb.Key.f8: "<f8>",  kb.Key.f9: "<f9>",
                kb.Key.f10: "<f10>", kb.Key.f11: "<f11>", kb.Key.f12: "<f12>",
            }
            return mapping.get(key, "")
        if isinstance(key, kb.KeyCode):
            if key.char:
                return key.char.lower()
            if key.vk:
                if 48 <= key.vk <= 57:
                    return str(key.vk - 48)
                if 65 <= key.vk <= 90:
                    return chr(key.vk).lower()
        return ""


# -----------------------------------------------------------------------
# open_settings
# -----------------------------------------------------------------------

def open_settings(on_save: Callable[[], None] | None = None) -> None:
    """Open the settings dialog.  Blocks the calling thread until closed.

    *on_save* is called in the calling thread after the user clicks Save.
    """
    cfg = load_config()
    done_event = threading.Event()
    save_triggered = threading.Event()

    def _build() -> None:
        """Build and show the dialog — runs on TkUIThread."""
        root = get_tk_manager().root
        if root is None:
            log.error("settings: TkManager root unavailable")
            done_event.set()
            return

        win = tk.Toplevel(root)
        win.title("ContextCruncher — Settings")
        win.configure(bg=_BG)
        win.resizable(False, False)
        win.attributes("-topmost", True)

        # Window icon
        try:
            icon_path = _get_resource_path(os.path.join("assets", "icon.png"))
            if os.path.exists(icon_path):
                img = Image.open(icon_path)
                photo = ImageTk.PhotoImage(img)
                win._icon_photo = photo  # type: ignore[attr-defined]  # prevent GC
                win.wm_iconphoto(True, photo)
        except Exception:
            pass  # Non-fatal

        # ── Title ────────────────────────────────────────────────────────
        tk.Label(
            win, text="ContextCruncher", font=("Segoe UI", 20, "bold"),
            fg=_ACCENT, bg=_BG,
        ).pack(pady=(20, 2))
        tk.Label(
            win, text="Settings", font=("Segoe UI", 12),
            fg=_FG_DIM, bg=_BG,
        ).pack(pady=(0, 15))

        # ── Hotkeys section ───────────────────────────────────────────────
        hotkey_frame = tk.LabelFrame(
            win, text="  Hotkeys  ", font=("Segoe UI", 11, "bold"),
            fg=_ACCENT, bg=_BG, bd=1, relief="groove",
            labelanchor="n", padx=15, pady=10,
        )
        hotkey_frame.pack(padx=25, pady=(0, 10), fill=tk.X)

        fields: dict[str, _HotkeyField] = {}
        current_hotkeys = cfg.get("hotkeys", DEFAULT_HOTKEYS.copy())

        for action, label in HOTKEY_ACTION_LABELS.items():
            row = tk.Frame(hotkey_frame, bg=_BG)
            row.pack(fill=tk.X, pady=3)
            tk.Label(
                row, text=label, font=("Segoe UI", 11),
                fg=_FG, bg=_BG, width=18, anchor="w",
            ).pack(side=tk.LEFT)
            field = _HotkeyField(row, initial=current_hotkeys.get(action, ""))
            field.pack(side=tk.RIGHT, padx=(0, 4))

            # "×" clear button
            def _make_clear(f: _HotkeyField):
                return lambda: f.clear()
            clear_btn = tk.Button(
                row, text="×", command=_make_clear(field),
                font=("Segoe UI", 10, "bold"), fg=_FG_DIM, bg=_BTN_BG,
                activebackground=_BTN_HOVER, activeforeground=_FG,
                bd=0, padx=6, pady=4, cursor="hand2",
            )
            clear_btn.pack(side=tk.RIGHT)
            fields[action] = field

        tk.Label(
            hotkey_frame,
            text="Click a field and press the desired key combination.  ×  = Clear.",
            font=("Segoe UI", 9), fg=_FG_DIM, bg=_BG,
        ).pack(pady=(8, 0))

        # ── General settings ──────────────────────────────────────────────
        general_frame = tk.LabelFrame(
            win, text="  General  ", font=("Segoe UI", 11, "bold"),
            fg=_ACCENT, bg=_BG, bd=1, relief="groove",
            labelanchor="n", padx=15, pady=10,
        )
        general_frame.pack(padx=25, pady=(0, 10), fill=tk.X)

        # Stack size
        size_row = tk.Frame(general_frame, bg=_BG)
        size_row.pack(fill=tk.X, pady=3)
        tk.Label(
            size_row, text="Max. Stack Size", font=("Segoe UI", 11),
            fg=_FG, bg=_BG, width=18, anchor="w",
        ).pack(side=tk.LEFT)
        stack_var = tk.IntVar(value=cfg.get("max_stack_size", 50))
        tk.Spinbox(
            size_row, from_=5, to=200, textvariable=stack_var, width=6,
            font=("Segoe UI", 11), bg=_BG_FIELD, fg=_FG,
            buttonbackground=_BTN_BG, relief="flat",
        ).pack(side=tk.RIGHT)

        # Autostart
        autostart_var = tk.BooleanVar(value=get_autostart())
        autostart_row = tk.Frame(general_frame, bg=_BG)
        autostart_row.pack(fill=tk.X, pady=3)
        tk.Checkbutton(
            autostart_row, text="  Start with Windows",
            variable=autostart_var, font=("Segoe UI", 11),
            fg=_FG, bg=_BG, selectcolor=_BG_FIELD,
            activebackground=_BG, activeforeground=_FG,
        ).pack(side=tk.LEFT)

        # AI Compression level
        level_row = tk.Frame(general_frame, bg=_BG)
        level_row.pack(fill=tk.X, pady=(10, 3))
        tk.Label(
            level_row, text="AI Compression", font=("Segoe UI", 11),
            fg=_FG, bg=_BG, width=18, anchor="w",
        ).pack(side=tk.LEFT)
        level_options = {
            "Level 1 (Light / Code)": 1,
            "Level 2 (Token-Cruncher)": 2,
            "Level 3 (Annihilator)": 3,
            "Level 4 (Experimental: Not AI-compatible!)": 4,
        }
        level_var = tk.StringVar()
        current_lvl = cfg.get("ai_compact_level", 1)
        for k, v in level_options.items():
            if v == current_lvl:
                level_var.set(k)
                break
        if not level_var.get():
            level_var.set("Level 1 (Light / Code)")
        level_menu = tk.OptionMenu(level_row, level_var, *level_options.keys())
        level_menu.config(
            font=("Segoe UI", 10), bg=_BG_FIELD, fg=_FG,
            activebackground=_BTN_HOVER, activeforeground=_FG,
            highlightthickness=0, bd=0,
        )
        level_menu["menu"].config(font=("Segoe UI", 10), bg=_BG_FIELD, fg=_FG)
        level_menu.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))

        # OCR Language
        ocr_lang_row = tk.Frame(general_frame, bg=_BG)
        ocr_lang_row.pack(fill=tk.X, pady=(10, 3))
        tk.Label(
            ocr_lang_row, text="OCR Language", font=("Segoe UI", 11),
            fg=_FG, bg=_BG, width=18, anchor="w",
        ).pack(side=tk.LEFT)

        # Build options: "Auto" first, then installed language packs
        _lang_options: list[tuple[str, str]] = (
            [("Auto (EU Priority)", "auto")] + get_available_languages()
        )
        _lang_display_to_tag: dict[str, str] = {name: tag for name, tag in _lang_options}
        _lang_tag_to_display: dict[str, str] = {tag: name for name, tag in _lang_options}

        ocr_lang_var = tk.StringVar()
        _current_lang = cfg.get("ocr_language", "auto")
        ocr_lang_var.set(_lang_tag_to_display.get(_current_lang, "Auto (EU Priority)"))

        ocr_lang_menu = tk.OptionMenu(ocr_lang_row, ocr_lang_var, *[n for n, _ in _lang_options])
        ocr_lang_menu.config(
            font=("Segoe UI", 10), bg=_BG_FIELD, fg=_FG,
            activebackground=_BTN_HOVER, activeforeground=_FG,
            highlightthickness=0, bd=0,
        )
        ocr_lang_menu["menu"].config(font=("Segoe UI", 10), bg=_BG_FIELD, fg=_FG)
        ocr_lang_menu.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))

        # XML Wrap
        xml_wrap_var = tk.BooleanVar(value=cfg.get("xml_wrap", False))
        xml_wrap_row = tk.Frame(general_frame, bg=_BG)
        xml_wrap_row.pack(fill=tk.X, pady=(10, 3))
        tk.Checkbutton(
            xml_wrap_row, text="  XML Tag Formatting (e.g. <context>)",
            variable=xml_wrap_var, font=("Segoe UI", 11),
            fg=_FG, bg=_BG, selectcolor=_BG_FIELD,
            activebackground=_BG, activeforeground=_FG,
        ).pack(side=tk.LEFT)

        # XML Tag name
        xml_tag_row = tk.Frame(general_frame, bg=_BG)
        xml_tag_row.pack(fill=tk.X, pady=3)
        tk.Label(
            xml_tag_row, text="XML Tag Name", font=("Segoe UI", 11),
            fg=_FG, bg=_BG, width=18, anchor="w",
        ).pack(side=tk.LEFT)
        xml_tag_var = tk.StringVar(value=cfg.get("xml_tag", "context"))
        tk.Entry(
            xml_tag_row, textvariable=xml_tag_var, font=("Segoe UI", 11),
            bg=_BG_FIELD, fg=_FG, insertbackground=_FG, relief="flat",
        ).pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))

        # Variant mode
        variant_row = tk.Frame(general_frame, bg=_BG)
        variant_row.pack(fill=tk.X, pady=(10, 3))
        tk.Label(
            variant_row, text="Variant Mode", font=("Segoe UI", 11),
            fg=_FG, bg=_BG, width=18, anchor="w",
        ).pack(side=tk.LEFT)
        variant_mode_options = {
            "Cycle Key": "cycle",
            "Popup Picker (Win+V Style)": "popup",
        }
        variant_mode_var = tk.StringVar()
        current_vm = cfg.get("variant_mode", "cycle")
        for k, v in variant_mode_options.items():
            if v == current_vm:
                variant_mode_var.set(k)
                break
        if not variant_mode_var.get():
            variant_mode_var.set("Cycle Key")
        variant_mode_menu = tk.OptionMenu(variant_row, variant_mode_var, *variant_mode_options.keys())
        variant_mode_menu.config(
            font=("Segoe UI", 10), bg=_BG_FIELD, fg=_FG,
            activebackground=_BTN_HOVER, activeforeground=_FG,
            highlightthickness=0, bd=0,
        )
        variant_mode_menu["menu"].config(font=("Segoe UI", 10), bg=_BG_FIELD, fg=_FG)
        variant_mode_menu.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))

        # ── Error label (hidden until a validation error occurs) ─────────
        error_label = tk.Label(
            win, text="", font=("Segoe UI", 10),
            fg="#ff6b6b", bg=_BG, wraplength=360,
        )
        error_label.pack(padx=25, pady=(4, 0))

        # ── Buttons ───────────────────────────────────────────────────────
        btn_frame = tk.Frame(win, bg=_BG)
        btn_frame.pack(pady=(5, 20))

        def _cleanup_fields() -> None:
            for f in fields.values():
                f.cleanup()

        def _save() -> None:
            new_hotkeys = {action: field.combo for action, field in fields.items()}

            # BUG-05 — reject duplicate bindings before touching the config
            collision = find_hotkey_collision(new_hotkeys)
            if collision:
                combo, action_a, action_b = collision
                label_a = HOTKEY_ACTION_LABELS.get(action_a, action_a)
                label_b = HOTKEY_ACTION_LABELS.get(action_b, action_b)
                error_label.config(
                    text=(
                        f"⚠ Conflict: '{hotkey_display_name(combo)}' is assigned to "
                        f"both '{label_a}' and '{label_b}'. Please choose a different key."
                    )
                )
                return  # abort — do NOT save or close the dialog

            # No collision → clear any previous error and proceed
            error_label.config(text="")
            _cleanup_fields()
            cfg["hotkeys"] = new_hotkeys
            cfg["max_stack_size"] = stack_var.get()
            cfg["autostart"] = autostart_var.get()
            cfg["ai_compact_level"] = level_options.get(level_var.get(), 1)
            cfg["ocr_language"] = _lang_display_to_tag.get(ocr_lang_var.get(), "auto")
            cfg["xml_wrap"] = xml_wrap_var.get()
            cfg["xml_tag"] = xml_tag_var.get()
            cfg["variant_mode"] = variant_mode_options.get(variant_mode_var.get(), "cycle")
            save_config(cfg)
            set_autostart(autostart_var.get())
            win.destroy()
            save_triggered.set()
            done_event.set()

        def _cancel() -> None:
            _cleanup_fields()
            win.destroy()
            done_event.set()

        win.protocol("WM_DELETE_WINDOW", _cancel)

        tk.Button(
            btn_frame, text="  ✓ Save  ", command=_save,
            font=("Segoe UI", 11, "bold"), fg="#1e1e2e", bg=_ACCENT,
            activebackground="#94e2d5", activeforeground="#1e1e2e",
            bd=0, padx=20, pady=8, cursor="hand2",
        ).pack(side=tk.LEFT, padx=8)

        tk.Button(
            btn_frame, text="  ✕ Cancel  ", command=_cancel,
            font=("Segoe UI", 11), fg=_FG, bg=_BTN_BG,
            activebackground=_BTN_HOVER, activeforeground=_FG,
            bd=0, padx=20, pady=8, cursor="hand2",
        ).pack(side=tk.LEFT, padx=8)

        # Center on screen
        win.update_idletasks()
        w = win.winfo_reqwidth()
        h = win.winfo_reqheight()
        x = (win.winfo_screenwidth() - w) // 2
        y = (win.winfo_screenheight() - h) // 2
        win.geometry(f"+{x}+{y}")

    get_tk_manager().schedule(_build)
    done_event.wait()  # Block calling thread until dialog is closed

    # on_save runs in the calling (background) thread, not on TkUIThread
    if save_triggered.is_set() and on_save:
        on_save()
