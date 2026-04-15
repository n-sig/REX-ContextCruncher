"""
main.py — Entry point for ContextCruncher.

Wires up: tray icon, hotkeys, overlay, OCR engine, clipboard, feedback,
variant picker, and settings dialog.

FIXES applied:
  Bug #3  — _scan_active lock prevents two overlays from opening at once.
  Bug #8  — DPI-awareness is set once here at startup, not per scan.
  Bug #9  — Tray/stack interaction uses public TextStack API (set_cursor,
             get_entry) instead of accessing _items / _cursor directly.
  Bug #10 — Windows named-mutex singleton guard: second instance shows a
             message box and exits.
  Bug #11 — Structured logging to %APPDATA%/ContextCruncher/app.log.
"""

from __future__ import annotations

import ctypes
import logging
import logging.handlers
import os
import sys
import threading

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# -----------------------------------------------------------------------
# Guard: Windows-only
# -----------------------------------------------------------------------
if sys.platform != "win32":
    print("ContextCruncher requires Windows 10 or later.")
    sys.exit(1)

# -----------------------------------------------------------------------
# Logging setup (before anything else so all modules can use it)
# -----------------------------------------------------------------------
_LOG_DIR = os.path.join(os.environ.get("APPDATA", "."), "ContextCruncher")
os.makedirs(_LOG_DIR, exist_ok=True)
_LOG_PATH = os.path.join(_LOG_DIR, "app.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    handlers=[
        logging.handlers.RotatingFileHandler(
            _LOG_PATH, maxBytes=2 * 1024 * 1024, backupCount=2, encoding="utf-8"
        ),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)
log.info("ContextCruncher starting")

# -----------------------------------------------------------------------
# Singleton guard — only one instance allowed
# -----------------------------------------------------------------------
_MUTEX_NAME = "ContextCruncher_SingleInstance_Mutex"
_instance_mutex = None  # Keep reference so GC doesn't release the mutex


def _acquire_singleton() -> bool:
    """Create a named Windows mutex.  Returns False if already running."""
    global _instance_mutex
    _instance_mutex = ctypes.windll.kernel32.CreateMutexW(None, True, _MUTEX_NAME)
    last_err = ctypes.windll.kernel32.GetLastError()
    if last_err == 183:  # ERROR_ALREADY_EXISTS
        return False
    return True


if not _acquire_singleton():
    try:
        ctypes.windll.user32.MessageBoxW(
            0,
            "ContextCruncher is already running.\n\nSee system tray.",
            "ContextCruncher",
            0x40,  # MB_ICONINFORMATION
        )
    except Exception:
        pass
    sys.exit(0)

# -----------------------------------------------------------------------
# DPI awareness — set once at startup (Bug #8)
# -----------------------------------------------------------------------
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# -----------------------------------------------------------------------
# WinRT availability check
# -----------------------------------------------------------------------
from contextcruncher.ocr import is_ocr_available

if not is_ocr_available():
    try:
        ctypes.windll.user32.MessageBoxW(
            0,
            "ContextCruncher requires Windows 10 (1903+) or Windows 11.\n\n"
            "The 'winrt' package could not be loaded.\n"
            "Please install with:\n"
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
from contextcruncher.stack import TextStack, Variant
from contextcruncher.overlay import select_region
from contextcruncher.ocr import recognise
from contextcruncher.clipboard import set_clipboard
from contextcruncher.feedback import beep_success, beep_empty, flash_region, show_toast
from contextcruncher.hotkeys import HotkeyManager
from contextcruncher.tray import TrayApp
from contextcruncher.normalize import compact_variant
from contextcruncher.config import get_hotkeys, hotkey_display_name, load_config
from contextcruncher.text_processor import minify_for_ai
from contextcruncher.token_counter import count_tokens, context_window_warning  # FR-03
from contextcruncher.clipboard_monitor import ClipboardMonitor
from contextcruncher.variant_picker import show_variant_picker
from contextcruncher.search_picker import show_search_picker
from contextcruncher.ui.heatmap import show_heatmap

import pyperclip
from contextcruncher.settings import open_settings

# -----------------------------------------------------------------------
# Global state
# -----------------------------------------------------------------------
stack = TextStack(min_length=5)  # mirrors ClipboardMonitor.min_text_length
tray: TrayApp | None = None
hotkey_bindings = get_hotkeys()
hotkey_mgr: HotkeyManager | None = None
clip_monitor: ClipboardMonitor | None = None

# Bug #3 — prevent concurrent scans
_scan_active = threading.Event()


# -----------------------------------------------------------------------
# Variant builder helpers
# -----------------------------------------------------------------------

def _build_variants(text: str, compact_text: str | None = None) -> list[Variant]:
    """Build the full list of variants for a text entry."""
    variants = [Variant(label="Original", text=text, saved_percent=0.0)]
    seen_texts = {text}

    if compact_text and compact_text not in seen_texts:
        pct = ((len(text) - len(compact_text)) / len(text)) * 100.0 if len(text) > 0 else 0.0
        variants.append(Variant(label="Compact", text=compact_text, saved_percent=round(pct, 1)))
        seen_texts.add(compact_text)

    ai1, stats1 = minify_for_ai(text, level=1)
    if ai1 not in seen_texts:
        variants.append(Variant(label="AI Lv.1", text=ai1, saved_percent=round(stats1["saved_percent"], 1)))
        seen_texts.add(ai1)

    ai2, stats2 = minify_for_ai(text, level=2)
    if ai2 not in seen_texts:
        variants.append(Variant(label="AI Lv.2", text=ai2, saved_percent=round(stats2["saved_percent"], 1)))
        seen_texts.add(ai2)

    ai3, stats3 = minify_for_ai(text, level=3)
    if ai3 not in seen_texts:
        variants.append(Variant(label="AI Lv.3", text=ai3, saved_percent=round(stats3["saved_percent"], 1)))
        seen_texts.add(ai3)

    return variants


# -----------------------------------------------------------------------
# Hotkey callbacks
# -----------------------------------------------------------------------

def _on_scan() -> None:
    """Open overlay, OCR the selected area, push to stack."""

    # Bug #3 — reject if a scan is already in progress
    if _scan_active.is_set():
        log.debug("_on_scan: scan already active, ignoring")
        return

    def _do_scan() -> None:
        _scan_active.set()
        try:
            def _handle_selection(image, bbox) -> None:
                if image is None:
                    return

                cfg = load_config()
                lang = cfg.get("ocr_language", "auto")
                text = recognise(image, language=lang)

                if text:
                    compact = compact_variant(text)
                    variants = _build_variants(text, compact)
                    stack.push_variants(variants)
                    set_clipboard(text)
                    beep_success()
                    flash_region(bbox)

                    n_variants = len(variants)
                    if n_variants > 1:
                        show_toast(f"✓ {stack.label()}\n{n_variants} Variants")
                    else:
                        show_toast(f"✓ {stack.label()}")
                    log.info("Scan OK — %d variants, text length %d", len(variants), len(text))
                else:
                    beep_empty()
                    show_toast("⚠ No text recognized")
                    log.info("Scan returned no text")

                if tray:
                    tray.update_menu()

            select_region(_handle_selection)
        except Exception:
            log.exception("_on_scan: unhandled error")
        finally:
            _scan_active.clear()

    threading.Thread(target=_do_scan, daemon=True).start()


def _on_navigate_up() -> None:
    """Navigate to a newer entry."""
    text = stack.navigate(-1)
    if text is not None:
        set_clipboard(text)
        beep_success()
        show_toast(stack.label())
    if tray:
        tray.update_menu()


def _on_navigate_down() -> None:
    """Navigate to an older entry."""
    text = stack.navigate(+1)
    if text is not None:
        set_clipboard(text)
        beep_success()
        show_toast(stack.label())
    if tray:
        tray.update_menu()


def _cycle_variant() -> None:
    """Cycle to the next variant."""
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
    """Show the variant picker popup."""
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


def _on_search_stack() -> None:
    """Show the stack search UI."""
    def _on_search_select(idx: int) -> None:
        entry = stack.get_entry(idx)
        if entry:
            stack.set_cursor(idx)
            if tray:
                tray.update_menu()
            _show_popup(entry)

    def _on_search_select_pinned(idx: int) -> None:
        if 0 <= idx < stack.pinned_size():
            entry = stack.get_pinned_items()[idx]
            if tray:
                tray.update_menu()
            _show_popup(entry)

    show_search_picker(stack, _on_search_select, _on_search_select_pinned)


def _on_screenshot_full() -> None:
    """FR-01 — Capture full screen, OCR it, push result to stack."""

    if _scan_active.is_set():
        log.debug("_on_screenshot_full: scan already active, ignoring")
        return

    def _do_screenshot() -> None:
        _scan_active.set()
        try:
            from PIL import ImageGrab
            cfg = load_config()
            lang = cfg.get("ocr_language", "auto")

            img = ImageGrab.grab(all_screens=False)
            text = recognise(img, language=lang)

            if text:
                compact = compact_variant(text)
                variants = _build_variants(text, compact)
                stack.push_variants(variants)
                set_clipboard(text)
                beep_success()

                n_variants = len(variants)
                if n_variants > 1:
                    show_toast(f"🖥 Full Screen OCR\n{stack.label()}\n{n_variants} Variants")
                else:
                    show_toast(f"🖥 Full Screen OCR\n{stack.label()}")
                log.info("Full-screen OCR OK — %d variants, text length %d", len(variants), len(text))
            else:
                beep_empty()
                show_toast("⚠ No text recognized on screen")
                log.info("Full-screen OCR returned no text")

            if tray:
                tray.update_menu()
        except Exception:
            log.exception("_on_screenshot_full: unhandled error")
        finally:
            _scan_active.clear()

    threading.Thread(target=_do_screenshot, daemon=True).start()


def _on_ai_compact_from_clipboard() -> None:
    """Reads clipboard, builds all variants, pushes to stack."""
    text = pyperclip.paste()
    if not text or not str(text).strip():
        beep_empty()
        show_toast("⚠ Clipboard is empty")
        return

    text = str(text)

    cfg = load_config()

    # FR-03 — context window warning
    warn_pct = cfg.get("context_warn_pct", 75)
    n_tokens = count_tokens(text)
    hit = context_window_warning(n_tokens, warn_pct=warn_pct)
    if hit:
        model, pct = hit
        show_toast(
            f"⚠ Context Window Warning\n"
            f"{n_tokens:,} tokens = {pct:.1f}% of {model}\n"
            f"Consider compressing before sending!"
        )
        log.warning("Context window warning: %d tokens = %.1f%% of %s", n_tokens, pct, model)
    lvl = max(1, min(3, cfg.get("ai_compact_level", 1)))
    wrap = cfg.get("xml_wrap", False)
    tag = cfg.get("xml_tag", "context")

    compact = compact_variant(text)
    variants = _build_variants(text, compact)

    if wrap and tag:
        xml_text, xml_stats = minify_for_ai(text, level=lvl, xml_wrap=True, xml_tag=tag)
        variants.append(Variant(label=f"XML Lv.{lvl}", text=xml_text, saved_percent=round(xml_stats["saved_percent"], 1)))

    stack.push_variants(variants)

    best_idx = 0
    for i, v in enumerate(variants):
        if f"Lv.{lvl}" in v.label:
            best_idx = i
    if best_idx == 0 and len(variants) > 1:
        best_idx = len(variants) - 1

    entry = stack.current_entry()
    if entry:
        entry.active_index = best_idx
        active_v = entry.active_variant
        if active_v:
            set_clipboard(active_v.text)
            show_toast(
                f"✓ {active_v.label} active (-{active_v.saved_percent:.0f}%)\n"
                f"{len(variants)} Variants"
            )

    beep_success()
    if tray:
        tray.update_menu()


def _on_show_heatmap() -> None:
    """Show the token heatmap for the current clipboard contents."""
    text = pyperclip.paste()
    if not text or not str(text).strip():
        beep_empty()
        show_toast("⚠ Clipboard is empty")
        return
    show_heatmap(str(text))


def _handle_clipboard_change(text: str) -> str | None:
    """Callback for ClipboardMonitor. Always adds to stack, auto-crunches if enabled."""
    cfg = load_config()

    lvl = max(1, min(3, cfg.get("ai_compact_level", 1)))
    wrap = cfg.get("xml_wrap", False)
    tag = cfg.get("xml_tag", "context")

    compact = compact_variant(text)
    variants = _build_variants(text, compact)
    stack.push_variants(variants)

    best_idx = 0
    for i, v in enumerate(variants):
        if f"Lv.{lvl}" in v.label:
            best_idx = i
    if best_idx == 0 and len(variants) > 1:
        best_idx = len(variants) - 1

    entry = stack.current_entry()
    if entry:
        entry.active_index = best_idx

    n = len(variants)
    
    if tray:
        tray.update_menu()

    # If auto-crunch is disabled, don't modify the OS clipboard
    if not cfg.get("auto_crunch", False):
        return None

    # Auto-crunch is enabled, notify user and return minified text
    if n > 1:
        show_toast(f"🔄 Auto-Crunch: {n} Variants")

    minified, _ = minify_for_ai(text, level=lvl, xml_wrap=wrap, xml_tag=tag)
    return minified


def _on_toggle_auto_crunch(enabled: bool) -> None:
    """Callback when user toggles auto-crunch from tray."""
    cfg = load_config()
    cfg["auto_crunch"] = enabled
    from contextcruncher.config import save_config
    save_config(cfg)

    # The monitor is always running to capture history.
    # Auto-crunch config purely handles auto-overwriting.
    if enabled:
        show_toast("🔄 Auto-Crunch: ACTIVE")
    else:
        show_toast("🔄 Auto-Crunch: INACTIVE")


# -----------------------------------------------------------------------
# Tray callbacks
# -----------------------------------------------------------------------

def _on_select_entry(index: int) -> None:
    """User clicked a history entry in the tray — copy original to clipboard."""
    # Bug #9 — use public API instead of _items / _cursor
    entry = stack.get_entry(index)
    if entry is not None:
        set_clipboard(entry.original)
        stack.set_cursor(index)
        beep_success()
        show_toast(f"📋 Copied: {entry.original[:40]}")
        if tray:
            tray.update_menu()


def _on_select_compact(index: int) -> None:
    """User clicked the compact variant in the tray submenu."""
    entry = stack.get_entry(index)
    if entry is not None and entry.compact:
        set_clipboard(entry.compact)
        entry.use_compact = True
        stack.set_cursor(index)
        beep_success()
        show_toast(f"🔢 Compact: {entry.compact[:40]}")
        if tray:
            tray.update_menu()


def _on_select_pinned_entry(index: int) -> None:
    """User clicked a pinned entry in the tray."""
    if 0 <= index < stack.pinned_size():
        entry = stack.get_pinned_items()[index]
        set_clipboard(entry.original)
        entry.active_index = 0
        beep_success()
        show_toast(f"📌 Copied: {entry.original[:40]}")

def _on_select_pinned_compact(index: int) -> None:
    if 0 <= index < stack.pinned_size():
        entry = stack.get_pinned_items()[index]
        if entry.compact:
            set_clipboard(entry.compact)
            entry.active_index = 1
            beep_success()
            show_toast(f"📌 Compact: {entry.compact[:40]}")


def _on_clear() -> None:
    """Clear the entire stack."""
    stack.clear()
    show_toast("🗑️ Stack cleared")
    if tray:
        tray.update_menu()


def _on_settings() -> None:
    """Open the settings dialog.  Reloads hotkeys after save."""
    def _after_save() -> None:
        global hotkey_bindings, hotkey_mgr
        hotkey_bindings = get_hotkeys()
        if hotkey_mgr:
            hotkey_mgr.stop()
        hotkey_mgr = HotkeyManager(
            on_scan=_on_scan,
            on_navigate_up=_on_navigate_up,
            on_navigate_down=_on_navigate_down,
            on_ai_compact=_on_ai_compact_from_clipboard,
            on_heatmap=_on_show_heatmap,
            on_screenshot_full=_on_screenshot_full,
            hotkey_bindings=hotkey_bindings,
        )
        hotkey_mgr.start()
        show_toast("✓ Settings saved\nHotkeys reloaded!")
        if tray:
            tray._hotkeys = hotkey_bindings
            tray.update_menu()
        log.info("Settings saved and hotkeys reloaded")

    open_settings(on_save=_after_save)


def _on_quit() -> None:
    """Shut everything down cleanly."""
    log.info("Quit requested")
    if hotkey_mgr:
        hotkey_mgr.stop()
    if clip_monitor:
        clip_monitor.stop()
    if tray:
        tray.stop()


# -----------------------------------------------------------------------
# Bootstrap
# -----------------------------------------------------------------------

def main() -> None:
    global tray, hotkey_mgr, clip_monitor

    hotkey_mgr = HotkeyManager(
        on_scan=_on_scan,
        on_navigate_up=_on_navigate_up,
        on_navigate_down=_on_navigate_down,
        on_search_stack=_on_search_stack,
        on_ai_compact=_on_ai_compact_from_clipboard,
        on_heatmap=_on_show_heatmap,
        on_screenshot_full=_on_screenshot_full,
        hotkey_bindings=hotkey_bindings,
    )
    hotkey_mgr.start()

    clip_monitor = ClipboardMonitor(
        check_interval=0.5,
        on_clipboard_changed=_handle_clipboard_change,
    )
    # Always run the clipboard monitor even if auto-crunch isn't enabled
    # to populate the local stack history for manual hotkey access.
    clip_monitor.start()

    tray = TrayApp(
        stack=stack,
        on_scan=_on_scan,
        on_clear=_on_clear,
        on_quit=_on_quit,
        on_settings=_on_settings,
        on_select_entry=_on_select_entry,
        on_select_compact=_on_select_compact,
        on_select_pinned_entry=_on_select_pinned_entry,
        on_select_pinned_compact=_on_select_pinned_compact,
        on_ai_compact=_on_ai_compact_from_clipboard,
        on_search_stack=_on_search_stack,
        on_toggle_auto_crunch=_on_toggle_auto_crunch,
        hotkey_bindings=hotkey_bindings,
    )
    tray.start()  # Blocking — runs pystray's message loop


if __name__ == "__main__":
    main()
