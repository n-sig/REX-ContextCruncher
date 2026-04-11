"""
main.py — Entry point for ContextCruncher.

Wires up: tray icon, hotkeys, overlay, OCR engine, clipboard, feedback,
variant picker, and settings dialog.
"""

from __future__ import annotations

import sys
import os
import threading

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# -----------------------------------------------------------------------
# Guard: Windows-only + WinRT availability check
# -----------------------------------------------------------------------
if sys.platform != "win32":
    print("ContextCruncher requires Windows 10 or later.")
    sys.exit(1)

from ocrclipstack.ocr import is_ocr_available

if not is_ocr_available():
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            "ContextCruncher requires Windows 10 (1903+) or Windows 11.\n\n"
            "The package 'winrt' could not be loaded.\n"
            "Please install it with:\n"
            "pip install winrt-Windows.Media.Ocr winrt-Windows.Graphics.Imaging",
            "ContextCruncher - Error",
            0x10,
        )
    except Exception:
        print("ERROR: winrt is not available.")
    sys.exit(1)

# -----------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------
from ocrclipstack.stack import TextStack, Variant
from ocrclipstack.overlay import select_region
from ocrclipstack.ocr import recognise
from ocrclipstack.clipboard import set_clipboard
from ocrclipstack.feedback import beep_success, beep_empty, flash_region, show_toast
from ocrclipstack.hotkeys import HotkeyManager
from ocrclipstack.tray import TrayApp
from ocrclipstack.normalize import compact_variant
from ocrclipstack.config import get_hotkeys, hotkey_display_name, load_config
from ocrclipstack.text_processor import minify_for_ai
from ocrclipstack.clipboard_monitor import ClipboardMonitor
from ocrclipstack.variant_picker import show_variant_picker

# For accessing system clipboard outside of our own get/set
import pyperclip
from ocrclipstack.settings import open_settings

# -----------------------------------------------------------------------
# Global state
# -----------------------------------------------------------------------
stack = TextStack()
tray: TrayApp | None = None
hotkey_bindings = get_hotkeys()
hotkey_mgr: HotkeyManager | None = None
clip_monitor: ClipboardMonitor | None = None


# -----------------------------------------------------------------------
# Variant builder helpers
# -----------------------------------------------------------------------

def _build_variants(text: str, compact_text: str | None = None) -> list[Variant]:
    """Build a list of variants for a text entry.

    Always creates: Original, optionally Compact (for numbers),
    then AI Level 1, 2, 3, and 4 — but only if they actually differ
    and compress more than the previous level.
    """
    variants = [Variant(label="Original", text=text, saved_percent=0.0)]

    # Compact (number normalization)
    if compact_text and compact_text != text:
        pct = ((len(text) - len(compact_text)) / len(text)) * 100.0 if len(text) > 0 else 0.0
        variants.append(Variant(label="Compact", text=compact_text, saved_percent=round(pct, 1)))

    # Track previous savings for "meaningful difference" gating
    prev_saved = 0.0

    # AI Level 1
    ai1, saved1 = minify_for_ai(text, level=1)
    if ai1 != text and saved1 > 2:
        variants.append(Variant(label="AI Lv.1", text=ai1, saved_percent=round(saved1, 1)))
        prev_saved = saved1

    # AI Level 2
    ai2, saved2 = minify_for_ai(text, level=2)
    if saved2 > prev_saved + 3:
        variants.append(Variant(label="AI Lv.2", text=ai2, saved_percent=round(saved2, 1)))
        prev_saved = saved2

    # AI Level 3
    ai3, saved3 = minify_for_ai(text, level=3)
    if saved3 > prev_saved + 3:
        variants.append(Variant(label="AI Lv.3", text=ai3, saved_percent=round(saved3, 1)))
        prev_saved = saved3

    # AI Level 4 (Experimentell — Vokal-Entfernung)
    ai4, saved4 = minify_for_ai(text, level=4)
    if saved4 > prev_saved + 3:
        variants.append(Variant(label="⚠ Lv.4 Exp.", text=ai4, saved_percent=round(saved4, 1)))

    return variants


# -----------------------------------------------------------------------
# Hotkey callbacks
# -----------------------------------------------------------------------

def _on_scan() -> None:
    """Open overlay, OCR the selected area, push to stack."""
    def _do_scan() -> None:
        def _handle_selection(image, bbox) -> None:
            if image is None:
                return

            text = recognise(image)
            if text:
                compact = compact_variant(text)
                variants = _build_variants(text, compact)
                stack.push_variants(variants)
                set_clipboard(text)
                beep_success()
                flash_region(bbox)

                n_variants = len(variants)
                if n_variants > 1:
                    toggle_key = hotkey_bindings.get("toggle_compact", "")
                    hint = f" → {hotkey_display_name(toggle_key)}" if toggle_key else ""
                    show_toast(f"✓ {stack.label()}\n{n_variants} variants available{hint}")
                else:
                    show_toast(f"✓ {stack.label()}")
            else:
                beep_empty()
                show_toast("⚠ No text recognized")

            if tray:
                tray.update_menu()

        select_region(_handle_selection)

    threading.Thread(target=_do_scan, daemon=True).start()


def _on_navigate_up() -> None:
    """Navigate to a newer entry."""
    text = stack.navigate(-1)
    if text:
        set_clipboard(text)
        beep_success()
        show_toast(stack.label())
    if tray:
        tray.update_menu()


def _on_navigate_down() -> None:
    """Navigate to an older entry."""
    text = stack.navigate(+1)
    if text:
        set_clipboard(text)
        beep_success()
        show_toast(stack.label())
    if tray:
        tray.update_menu()


def _on_toggle_compact() -> None:
    """Cycle variant or open popup, depending on config."""
    cfg = load_config()
    mode = cfg.get("variant_mode", "cycle")
    entry = stack.current_entry()

    if entry is None:
        beep_empty()
        return

    if len(entry.variants) <= 1:
        beep_empty()
        show_toast("Only 1 variant available")
        return

    if mode == "popup":
        _show_popup(entry)
    else:
        _cycle_variant()


def _cycle_variant() -> None:
    """Cycle to the next variant (Option A)."""
    result = stack.cycle_variant()
    if result is not None:
        set_clipboard(result.text)
        beep_success()

        entry = stack.current_entry()
        n = len(entry.variants) if entry else 0
        idx = entry.active_index + 1 if entry else 0

        savings_info = f"  (-{result.saved_percent:.0f}%)" if result.saved_percent > 0 else ""
        show_toast(f"[{idx}/{n}] {result.label}{savings_info}")
    else:
        beep_empty()
    if tray:
        tray.update_menu()


def _show_popup(entry) -> None:
    """Show the variant picker popup (Option C)."""
    def _on_variant_selected(idx: int):
        result = stack.set_variant(idx)
        if result:
            set_clipboard(result.text)
            beep_success()
            savings_info = f"  (-{result.saved_percent:.0f}%)" if result.saved_percent > 0 else ""
            show_toast(f"✓ {result.label}{savings_info}")
        if tray:
            tray.update_menu()

    show_variant_picker(
        variants=entry.variants,
        active_index=entry.active_index,
        on_select=_on_variant_selected,
    )


def _on_ai_compact_from_clipboard() -> None:
    """Reads normal clipboard, builds all variants, pushes to stack."""
    text = pyperclip.paste()
    if not text or not str(text).strip():
        beep_empty()
        show_toast("⚠ Clipboard is empty")
        return

    text = str(text)

    # Read the level from config
    cfg = load_config()
    lvl = cfg.get("ai_compact_level", 1)
    wrap = cfg.get("xml_wrap", False)
    tag = cfg.get("xml_tag", "context")

    # Build all variants (now includes Level 4)
    compact = compact_variant(text)
    variants = _build_variants(text, compact)

    # If XML wrapping is enabled, add a wrapped variant of the configured level
    if wrap and tag:
        xml_text, xml_saved = minify_for_ai(text, level=lvl, xml_wrap=True, xml_tag=tag)
        variants.append(Variant(label=f"XML Lv.{lvl}", text=xml_text, saved_percent=round(xml_saved, 1)))

    # Push with all variants
    stack.push_variants(variants)

    # Set the active variant to the user-configured level
    best_idx = 0
    for i, v in enumerate(variants):
        # Match the configured level (handles Lv.1, Lv.2, Lv.3, Lv.4)
        if f"Lv.{lvl}" in v.label:
            best_idx = i
            # Don't break — prefer the last match (XML wrapped version if available)
    # Fallback: use the most compressed variant
    if best_idx == 0 and len(variants) > 1:
        best_idx = len(variants) - 1

    entry = stack.current_entry()
    if entry:
        entry.active_index = best_idx
        active_v = entry.active_variant
        if active_v:
            set_clipboard(active_v.text)
            toggle_key = hotkey_bindings.get("toggle_compact", "")
            hint = f"\n{hotkey_display_name(toggle_key)} = switch" if toggle_key else ""
            show_toast(f"✓ {active_v.label} active (-{active_v.saved_percent:.0f}%)\n{len(variants)} variants{hint}")

    beep_success()
    if tray:
        tray.update_menu()


def _handle_clipboard_change(text: str) -> str | None:
    """Callback for ClipboardMonitor when auto-crunch is active.

    Builds full variants, pushes to stack with toast feedback,
    and returns the compressed text for the clipboard.
    """
    cfg = load_config()
    if not cfg.get("auto_crunch", False):
        return None

    lvl = cfg.get("ai_compact_level", 1)
    wrap = cfg.get("xml_wrap", False)
    tag = cfg.get("xml_tag", "context")

    # Build all variants and push to stack (same UX as OCR scan)
    compact = compact_variant(text)
    variants = _build_variants(text, compact)

    stack.push_variants(variants)

    # Set active variant to the configured level
    best_idx = 0
    for i, v in enumerate(variants):
        if f"Lv.{lvl}" in v.label:
            best_idx = i
    if best_idx == 0 and len(variants) > 1:
        best_idx = len(variants) - 1

    entry = stack.current_entry()
    if entry:
        entry.active_index = best_idx

    # Show toast so user knows variants are available
    n = len(variants)
    if n > 1:
        toggle_key = hotkey_bindings.get("toggle_compact", "")
        hint = f" → {hotkey_display_name(toggle_key)}" if toggle_key else ""
        show_toast(f"🔄 Auto-Crunch: {n} variants{hint}")

    if tray:
        tray.update_menu()

    # Return the compressed text to write back to clipboard
    minified, _ = minify_for_ai(text, level=lvl, xml_wrap=wrap, xml_tag=tag)
    return minified

def _on_toggle_auto_crunch(enabled: bool) -> None:
    """Callback when user toggles auto-crunch from tray."""
    cfg = load_config()
    cfg["auto_crunch"] = enabled
    from ocrclipstack.config import save_config
    save_config(cfg)
    
    if enabled and clip_monitor:
        clip_monitor.start()
        show_toast("🔄 Auto-Crunch Monitor: ENABLED")
    elif not enabled and clip_monitor:
        clip_monitor.stop()
        show_toast("🔄 Auto-Crunch Monitor: DISABLED")

# -----------------------------------------------------------------------
# Tray callbacks
# -----------------------------------------------------------------------

def _on_select_entry(index: int) -> None:
    """User clicked a history entry in the tray → copy original to clipboard."""
    if 0 <= index < stack.size():
        entry = stack._items[index]
        set_clipboard(entry.original)
        stack._cursor = index
        beep_success()
        show_toast(f"📋 Copied: {entry.original[:40]}")
        if tray:
            tray.update_menu()


def _on_select_compact(index: int) -> None:
    """User clicked the compact variant in the tray submenu."""
    if 0 <= index < stack.size():
        entry = stack._items[index]
        if entry.compact:
            set_clipboard(entry.compact)
            entry.use_compact = True
            stack._cursor = index
            beep_success()
            show_toast(f"🔢 Compact: {entry.compact[:40]}")
            if tray:
                tray.update_menu()


def _on_clear() -> None:
    """Clear the entire stack."""
    stack.clear()
    show_toast("🗑️ Stack cleared")
    if tray:
        tray.update_menu()


def _on_settings() -> None:
    """Open the settings dialog. Reloads hotkeys after save."""
    def _after_save() -> None:
        global hotkey_bindings, hotkey_mgr
        # Reload config.
        hotkey_bindings = get_hotkeys()
        # Restart hotkey manager with new bindings.
        if hotkey_mgr:
            hotkey_mgr.stop()
        hotkey_mgr = HotkeyManager(
            on_scan=_on_scan,
            on_navigate_up=_on_navigate_up,
            on_navigate_down=_on_navigate_down,
            on_toggle_compact=_on_toggle_compact,
            on_ai_compact=_on_ai_compact_from_clipboard,
            hotkey_bindings=hotkey_bindings,
        )
        hotkey_mgr.start()
        show_toast("✓ Settings saved\nHotkeys reloaded!")
        if tray:
            tray._hotkeys = hotkey_bindings
            tray.update_menu()

    open_settings(on_save=_after_save)


def _on_quit() -> None:
    """Shut everything down cleanly."""
    if hotkey_mgr:
        hotkey_mgr.stop()
    if tray:
        tray.stop()
    if clip_monitor:
        clip_monitor.stop()


# -----------------------------------------------------------------------
# Bootstrap
# -----------------------------------------------------------------------

def main() -> None:
    global tray, hotkey_mgr, clip_monitor

    hotkey_mgr = HotkeyManager(
        on_scan=_on_scan,
        on_navigate_up=_on_navigate_up,
        on_navigate_down=_on_navigate_down,
        on_toggle_compact=_on_toggle_compact,
        on_ai_compact=_on_ai_compact_from_clipboard,
        hotkey_bindings=hotkey_bindings,
    )
    hotkey_mgr.start()

    clip_monitor = ClipboardMonitor(check_interval=0.5, on_clipboard_changed=_handle_clipboard_change)
    cfg = load_config()
    if cfg.get("auto_crunch", False):
        clip_monitor.start()

    # Tray is the main blocking loop.
    tray = TrayApp(
        stack=stack,
        on_scan=_on_scan,
        on_clear=_on_clear,
        on_quit=_on_quit,
        on_settings=_on_settings,
        on_select_entry=_on_select_entry,
        on_select_compact=_on_select_compact,
        on_ai_compact=_on_ai_compact_from_clipboard,
        on_toggle_auto_crunch=_on_toggle_auto_crunch,
        hotkey_bindings=hotkey_bindings,
    )
    tray.start()


if __name__ == "__main__":
    main()
