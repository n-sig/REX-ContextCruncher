"""
settings.py — GUI settings dialog with live hotkey recorder.

Opens a tkinter window styled with dark theme, featuring:
  • Hotkey recorder fields (click → press combo → recorded)
  • OCR language selector
  • Stack size spinner
  • Autostart checkbox
  • Save / Cancel buttons
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from pynput import keyboard as kb

from ocrclipstack.config import (
    load_config,
    save_config,
    hotkey_display_name,
    HOTKEY_ACTION_LABELS,
    DEFAULT_HOTKEYS,
    set_autostart,
    get_autostart,
)


# -----------------------------------------------------------------------
# Dark theme colors
# -----------------------------------------------------------------------
_BG = "#121212"
_BG_FIELD = "#1e1e1e"
_BG_ACTIVE = "#2d2d2d"
_FG = "#ffffff"
_FG_DIM = "#888888"
_ACCENT = "#D9060D"       # aggressive red
_ACCENT_BLUE = "#ff3333"  # recording state red
_BTN_BG = "#2d2d2d"
_BTN_HOVER = "#3d3d3d"


# -----------------------------------------------------------------------
# Hotkey recorder widget
# -----------------------------------------------------------------------
class _HotkeyField(tk.Frame):
    """A single-line entry that records a keyboard shortcut when focused."""

    def __init__(self, parent: tk.Widget, initial: str = "", **kw) -> None:
        super().__init__(parent, bg=_BG, **kw)
        self._combo = initial
        self._recording = False
        self._pressed_keys: set[str] = set()
        self._listener: kb.Listener | None = None

        self._label = tk.Label(
            self,
            text=hotkey_display_name(initial) if initial else "Nicht belegt",
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

    @property
    def combo(self) -> str:
        return self._combo

    def _start_recording(self, _event: tk.Event | None = None) -> None:
        if self._recording:
            return
        self._recording = True
        self._pressed_keys.clear()
        self._label.config(text="⌨ Press keys...", bg=_ACCENT_BLUE, fg="#1e1e2e")

        self._listener = kb.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self._listener.start()

    def _key_to_pynput(self, key: kb.Key | kb.KeyCode | None) -> str:
        """Convert a pynput key to pynput hotkey string format."""
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
                kb.Key.f1: "<f1>", kb.Key.f2: "<f2>", kb.Key.f3: "<f3>",
                kb.Key.f4: "<f4>", kb.Key.f5: "<f5>", kb.Key.f6: "<f6>",
                kb.Key.f7: "<f7>", kb.Key.f8: "<f8>", kb.Key.f9: "<f9>",
                kb.Key.f10: "<f10>", kb.Key.f11: "<f11>", kb.Key.f12: "<f12>",
            }
            return mapping.get(key, "")
        if isinstance(key, kb.KeyCode):
            if key.char:
                return key.char.lower()
            if key.vk:
                # Handle number keys and other VK codes.
                if 48 <= key.vk <= 57:  # 0-9
                    return str(key.vk - 48)
                if 65 <= key.vk <= 90:  # A-Z
                    return chr(key.vk).lower()
        return ""

    def _on_key_press(self, key: kb.Key | kb.KeyCode | None) -> None:
        pynput_key = self._key_to_pynput(key)
        if pynput_key:
            self._pressed_keys.add(pynput_key)

    def _on_key_release(self, key: kb.Key | kb.KeyCode | None) -> None:
        if not self._recording:
            return

        # When a non-modifier key is released, finalize the combo.
        pynput_key = self._key_to_pynput(key)
        modifiers = {"<ctrl>", "<shift>", "<alt>", "<cmd>"}

        if pynput_key and pynput_key not in modifiers:
            self._stop_recording()

    def _stop_recording(self) -> None:
        self._recording = False
        if self._listener:
            self._listener.stop()
            self._listener = None

        # Build the combo string: modifiers first, then the key.
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
            # No valid combo recorded.
            self._label.config(
                text=hotkey_display_name(self._combo) if self._combo else "Not set",
                bg=_BG_FIELD,
                fg=_FG,
            )
        self._pressed_keys.clear()


# -----------------------------------------------------------------------
import os
import sys
from PIL import Image, ImageTk

def get_resource_path(relative_path: str) -> str:
    """Gets absolute path to resource, works for dev and for PyInstaller."""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # Running normally from src/ocrclipstack/
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    return os.path.join(base_path, relative_path)

def open_settings(on_save: Callable[[], None] | None = None) -> None:
    """Open the settings dialog. Blocks until closed.

    *on_save* is called after the user clicks "Save" so the caller
    can reload the hotkey bindings.
    """
    cfg = load_config()

    root = tk.Tk()
    
    # Versuche das Logo zu setzen
    try:
        icon_path = get_resource_path(os.path.join("assets", "icon.png"))
        if os.path.exists(icon_path):
            img = Image.open(icon_path)
            # Resize a bit for the window icon if needed, but PhotoImage handles it
            photo = ImageTk.PhotoImage(img)
            # The root must keep a reference to avoid garbage collection!
            root._icon_photo = photo 
            root.wm_iconphoto(True, photo)
    except Exception as e:
        print("Could not load logo:", e)

    root.title("ContextCruncher — Settings")
    root.configure(bg=_BG)
    root.resizable(False, False)
    root.attributes("-topmost", True)

    # ── Title ──
    tk.Label(
        root, text="ContextCruncher", font=("Segoe UI", 20, "bold"),
        fg=_ACCENT, bg=_BG,
    ).pack(pady=(20, 2))
    tk.Label(
        root, text="Settings", font=("Segoe UI", 12),
        fg=_FG_DIM, bg=_BG,
    ).pack(pady=(0, 15))

    # ── Hotkeys section ──
    hotkey_frame = tk.LabelFrame(
        root, text="  Hotkeys  ", font=("Segoe UI", 11, "bold"),
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
        field.pack(side=tk.RIGHT)
        fields[action] = field

    tk.Label(
        hotkey_frame,
        text="Click a field and press the desired key combination.",
        font=("Segoe UI", 9), fg=_FG_DIM, bg=_BG,
    ).pack(pady=(8, 0))

    # ── General settings ──
    general_frame = tk.LabelFrame(
        root, text="  General  ", font=("Segoe UI", 11, "bold"),
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
    stack_spin = tk.Spinbox(
        size_row, from_=5, to=200, textvariable=stack_var, width=6,
        font=("Segoe UI", 11), bg=_BG_FIELD, fg=_FG,
        buttonbackground=_BTN_BG, relief="flat",
    )
    stack_spin.pack(side=tk.RIGHT)

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

    # AI Kompression
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
    level_menu.config(font=("Segoe UI", 10), bg=_BG_FIELD, fg=_FG, activebackground=_BTN_HOVER, activeforeground=_FG, highlightthickness=0, bd=0)
    level_menu["menu"].config(font=("Segoe UI", 10), bg=_BG_FIELD, fg=_FG)
    level_menu.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))

    # XML Wrap Checkbox
    xml_wrap_var = tk.BooleanVar(value=cfg.get("xml_wrap", False))
    xml_wrap_row = tk.Frame(general_frame, bg=_BG)
    xml_wrap_row.pack(fill=tk.X, pady=(10, 3))
    tk.Checkbutton(
        xml_wrap_row, text="  XML Tag Formatting (e.g. <context>)",
        variable=xml_wrap_var, font=("Segoe UI", 11),
        fg=_FG, bg=_BG, selectcolor=_BG_FIELD,
        activebackground=_BG, activeforeground=_FG,
    ).pack(side=tk.LEFT)

    # XML Tag Text
    xml_tag_row = tk.Frame(general_frame, bg=_BG)
    xml_tag_row.pack(fill=tk.X, pady=3)
    tk.Label(
        xml_tag_row, text="XML Tag Name", font=("Segoe UI", 11),
        fg=_FG, bg=_BG, width=18, anchor="w",
    ).pack(side=tk.LEFT)
    xml_tag_var = tk.StringVar(value=cfg.get("xml_tag", "context"))
    xml_tag_entry = tk.Entry(
        xml_tag_row, textvariable=xml_tag_var, font=("Segoe UI", 11),
        bg=_BG_FIELD, fg=_FG, insertbackground=_FG, relief="flat"
    )
    xml_tag_entry.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))

    # Variant Mode (Cycle vs Popup)
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
    variant_mode_menu.config(font=("Segoe UI", 10), bg=_BG_FIELD, fg=_FG, activebackground=_BTN_HOVER, activeforeground=_FG, highlightthickness=0, bd=0)
    variant_mode_menu["menu"].config(font=("Segoe UI", 10), bg=_BG_FIELD, fg=_FG)
    variant_mode_menu.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))

    # ── Buttons ──
    btn_frame = tk.Frame(root, bg=_BG)
    btn_frame.pack(pady=(5, 20))

    def _save() -> None:
        # Collect hotkeys from fields.
        new_hotkeys = {action: field.combo for action, field in fields.items()}
        cfg["hotkeys"] = new_hotkeys
        cfg["max_stack_size"] = stack_var.get()
        cfg["autostart"] = autostart_var.get()
        cfg["ai_compact_level"] = level_options.get(level_var.get(), 1)
        cfg["xml_wrap"] = xml_wrap_var.get()
        cfg["xml_tag"] = xml_tag_var.get()
        cfg["variant_mode"] = variant_mode_options.get(variant_mode_var.get(), "cycle")
        save_config(cfg)
        set_autostart(autostart_var.get())
        root.destroy()
        if on_save:
            on_save()

    def _cancel() -> None:
        root.destroy()

    save_btn = tk.Button(
        btn_frame, text="  ✓ Save  ", command=_save,
        font=("Segoe UI", 11, "bold"), fg="#1e1e2e", bg=_ACCENT,
        activebackground="#94e2d5", activeforeground="#1e1e2e",
        bd=0, padx=20, pady=8, cursor="hand2",
    )
    save_btn.pack(side=tk.LEFT, padx=8)

    cancel_btn = tk.Button(
        btn_frame, text="  ✕ Cancel  ", command=_cancel,
        font=("Segoe UI", 11), fg=_FG, bg=_BTN_BG,
        activebackground=_BTN_HOVER, activeforeground=_FG,
        bd=0, padx=20, pady=8, cursor="hand2",
    )
    cancel_btn.pack(side=tk.LEFT, padx=8)

    # Center on screen.
    root.update_idletasks()
    w = root.winfo_reqwidth()
    h = root.winfo_reqheight()
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"+{x}+{y}")

    root.mainloop()
