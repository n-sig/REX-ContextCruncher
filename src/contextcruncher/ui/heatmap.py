"""
heatmap.py - Visual token budget UI.

Shows a popup window highlighting expensive LLM tokens in red
and efficient tokens in green.

FIX (Audit F-03): Uses tk.Toplevel owned by the global TkManager instead of
creating a new tk.Tk(), which violated design decision #1 (single Tk root)
and could cause tkinter crashes.

v2.0.1: Palette and layout aligned with settings.py / search_picker.py /
variant_picker.py. Previous #1a1a2e / #aaaacc / default-white Text widget
looked like a different application — now the dark `#121212` + `#D9060D`
red-accent theme is consistent everywhere. Categorical token highlights
use dark-tinted backgrounds so red/amber/green remain readable on dark.
"""

import tkinter as tk
from tkinter import ttk
import logging

from contextcruncher.feedback import get_tk_manager, show_toast

try:
    import tiktoken
except ImportError:
    tiktoken = None

from contextcruncher.token_counter import (  # FR-02 / FR-03
    cost_estimate, format_cost,
    context_window_usage, CONTEXT_WINDOW_TABLE, CONTEXT_WARN_PCT, CONTEXT_ALERT_PCT,
)

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------
# Dark theme — synchronized with settings.py, search_picker.py and
# variant_picker.py so the heatmap doesn't look like a separate app.
# -----------------------------------------------------------------------
_BG = "#121212"          # main window background
_BG_FIELD = "#1e1e1e"    # text widget / panels
_BG_TRACK = "#2d2d2d"    # progress bar track
_FG = "#ffffff"
_FG_DIM = "#888888"
_ACCENT = "#D9060D"      # app red

# Heatmap category colors — dark-tinted so saturated FG stays readable.
_EXPENSIVE_BG = "#4a1515"   # dark crimson
_EXPENSIVE_FG = "#ff9090"
_MEDIUM_BG = "#4a3a10"      # dark amber
_MEDIUM_FG = "#ffd166"
_CHEAP_BG = "#143a24"       # dark forest green
_CHEAP_FG = "#78d9a0"

# Context-window bar colors (green/yellow/red traffic-light semantic).
_BAR_SAFE = "#06d6a0"
_BAR_WARN = "#ffd166"
_BAR_DANGER = "#ff6b6b"


def show_heatmap(text: str) -> None:
    """Show the token heatmap in a background thread."""
    if not text:
        show_toast("Heatmap: clipboard is empty")
        return

    if not tiktoken:
        logger.error("tiktoken not installed. Cannot show heatmap.")
        show_toast("Heatmap unavailable — tiktoken not installed")
        return

    get_tk_manager().schedule(_create_heatmap, text)


def _create_heatmap(text: str) -> None:
    """Build the heatmap as a Toplevel on TkUIThread."""
    mgr = get_tk_manager()
    if mgr.root is None:
        return
    top = tk.Toplevel(mgr.root)
    top.title("ContextCruncher 🌡️ Token Heatmap")
    top.geometry("900x620")
    top.minsize(780, 520)
    top.configure(bg=_BG)

    # ── Top header row: Total Tokens / Chars / Efficiency ──
    header_frame = tk.Frame(top, bg=_BG, padx=16, pady=(14, 4))
    header_frame.pack(side="top", fill="x")

    stats_lbl = tk.Label(
        header_frame,
        text="Calculating tokens...",
        font=("Segoe UI", 11, "bold"),
        bg=_BG,
        fg=_FG,
        anchor="w",
    )
    stats_lbl.pack(side="left", fill="x", expand=True)

    # ── Cost-estimate row ──
    cost_lbl = tk.Label(
        top,
        text="",
        font=("Segoe UI", 10),
        bg=_BG,
        fg=_FG_DIM,
        justify="left",
        anchor="w",
    )
    cost_lbl.pack(side="top", fill="x", padx=16, pady=(0, 4))

    # ── Context-window usage bars ──
    ctx_frame = tk.Frame(top, bg=_BG)
    ctx_frame.pack(side="top", fill="x", padx=16, pady=(0, 8))

    # ── Legend row ──
    legend_frame = tk.Frame(top, bg=_BG, padx=16, pady=6)
    legend_frame.pack(side="top", fill="x")

    _legend_chip(legend_frame, "Expensive (1 char/token)",
                 _EXPENSIVE_BG, _EXPENSIVE_FG)
    _legend_chip(legend_frame, "Medium (2–3 chars/token)",
                 _MEDIUM_BG, _MEDIUM_FG)
    _legend_chip(legend_frame, "Cheap (4+ chars/token)",
                 _CHEAP_BG, _CHEAP_FG)

    # ── Heatmap text widget (with vertical scrollbar) ──
    text_frame = tk.Frame(top, bg=_BG)
    text_frame.pack(fill="both", expand=True, padx=16, pady=(6, 14))

    text_widget = tk.Text(
        text_frame,
        wrap="word",
        font=("Consolas", 13),
        bg=_BG_FIELD,
        fg=_FG,
        insertbackground=_FG,
        selectbackground=_ACCENT,
        selectforeground=_FG,
        borderwidth=0,
        relief="flat",
        padx=12,
        pady=10,
    )

    # Try to theme a red vertical scrollbar — same trick as settings.py
    # (clam theme is the only Windows Tk theme that honors per-widget
    # scrollbar colors).
    try:
        style = ttk.Style()
        if style.theme_use() != "clam":
            style.theme_use("clam")
        style.configure(
            "Red.Vertical.TScrollbar",
            background=_ACCENT,
            troughcolor=_BG_FIELD,
            bordercolor=_BG,
            arrowcolor=_FG,
            lightcolor=_ACCENT,
            darkcolor=_ACCENT,
            gripcount=0,
            relief="flat",
        )
        style.map(
            "Red.Vertical.TScrollbar",
            background=[("!active", _ACCENT), ("active", "#b40309")],
            arrowcolor=[("disabled", _FG_DIM), ("!disabled", _FG)],
        )
        vscroll = ttk.Scrollbar(
            text_frame, orient="vertical",
            style="Red.Vertical.TScrollbar",
            command=text_widget.yview,
        )
    except tk.TclError:
        # Fallback — native tk scrollbar. Still works, just grey.
        vscroll = tk.Scrollbar(
            text_frame, orient="vertical", command=text_widget.yview
        )

    text_widget.config(yscrollcommand=vscroll.set)
    vscroll.pack(side="right", fill="y")
    text_widget.pack(side="left", fill="both", expand=True)

    # ── Token category tags ──
    text_widget.tag_config(
        "t_expensive", background=_EXPENSIVE_BG, foreground=_EXPENSIVE_FG
    )
    text_widget.tag_config(
        "t_medium", background=_MEDIUM_BG, foreground=_MEDIUM_FG
    )
    text_widget.tag_config(
        "t_cheap", background=_CHEAP_BG, foreground=_CHEAP_FG
    )
    # whitespace stays bare — no highlight — so blank lines don't get
    # distracting coloured blocks.
    text_widget.tag_config("t_whitespace", background=_BG_FIELD)

    try:
        enc = tiktoken.get_encoding("o200k_base")
        tokens = enc.encode(text)

        for t in tokens:
            b_tok = enc.decode_single_token_bytes(t)
            s_tok = b_tok.decode("utf-8", errors="replace")

            stripped = s_tok.strip()

            if not stripped:
                tag = "t_whitespace"
            else:
                l = len(stripped)
                if l <= 1:
                    tag = "t_expensive"
                elif l <= 3:
                    tag = "t_medium"
                else:
                    tag = "t_cheap"

            text_widget.insert("end", s_tok, tag)

        n_tokens = len(tokens)
        stats_text = (
            f"Total Tokens: {n_tokens:,}   |   "
            f"Total Chars: {len(text):,}   |   "
            f"Efficiency: {len(text)/max(1, n_tokens):.1f} chars/token"
        )
        stats_lbl.config(text=stats_text)

        # FR-02 — per-model cost estimate
        costs = cost_estimate(text)
        cost_parts = []
        for model, c in costs.items():
            label = f"{model}: {format_cost(c)}"
            if "Claude" in model:
                label += " (~est)"
            cost_parts.append(label)

        cost_lbl.config(
            text="💰 Input cost est.:   " + "    |    ".join(cost_parts)
        )

        # FR-03 — context window usage bars
        usage = context_window_usage(text)
        _render_context_bars(ctx_frame, usage)

    except Exception as e:
        logger.error(f"Heatmap error: {e}", exc_info=True)
        text_widget.insert(
            "end", f"Error generating heatmap: {e}\n\n{text}"
        )

    text_widget.config(state="disabled")

    # ESC and window-close both quit the heatmap.
    top.bind("<Escape>", lambda _e: top.destroy())
    top.protocol("WM_DELETE_WINDOW", top.destroy)

    # Position: center of screen
    top.update_idletasks()
    w = max(top.winfo_reqwidth(), 900)
    h = max(top.winfo_reqheight(), 620)
    sw = top.winfo_screenwidth()
    sh = top.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    top.geometry(f"{w}x{h}+{x}+{y}")

    top.focus_force()


def _legend_chip(parent: tk.Widget, text: str, bg: str, fg: str) -> None:
    """Pill-shaped legend entry — dark tinted background + saturated text."""
    chip = tk.Label(
        parent,
        text=f"  ■  {text}  ",
        font=("Segoe UI", 9, "bold"),
        bg=bg,
        fg=fg,
        padx=8,
        pady=3,
        borderwidth=0,
    )
    chip.pack(side="left", padx=(0, 8))


def _render_context_bars(parent: tk.Frame, usage: dict[str, float]) -> None:
    """FR-03 — Render one mini progress bar per model inside *parent*.

    Color coding:
      < CONTEXT_WARN_PCT  → green  (safe)
      < CONTEXT_ALERT_PCT → yellow (caution)
      >= CONTEXT_ALERT_PCT → red   (danger)
    """
    BAR_W = 130   # canvas width in pixels
    BAR_H = 8     # canvas height in pixels — slimmer, less visually heavy

    # Clear any previous children (heatmap may be re-rendered).
    for child in parent.winfo_children():
        child.destroy()

    header = tk.Label(
        parent,
        text="📐 Context window usage:",
        font=("Segoe UI", 10),
        bg=_BG,
        fg=_FG_DIM,
    )
    header.grid(row=0, column=0, columnspan=99, sticky="w", pady=(0, 4))

    for col, (model, pct) in enumerate(usage.items()):
        if pct >= CONTEXT_ALERT_PCT:
            bar_color = _BAR_DANGER
            txt_color = _BAR_DANGER
        elif pct >= CONTEXT_WARN_PCT:
            bar_color = _BAR_WARN
            txt_color = _BAR_WARN
        else:
            bar_color = _BAR_SAFE
            txt_color = _BAR_SAFE

        fill_w = max(1, min(int(BAR_W * min(pct, 100) / 100), BAR_W))

        cell = tk.Frame(parent, bg=_BG)
        cell.grid(row=1, column=col, padx=(0, 14), sticky="w")

        name_lbl = tk.Label(
            cell, text=model, font=("Segoe UI", 8, "bold"),
            bg=_BG, fg=_FG,
        )
        name_lbl.pack(anchor="w")

        canvas = tk.Canvas(
            cell, width=BAR_W, height=BAR_H,
            bg=_BG_TRACK, highlightthickness=0,
        )
        canvas.pack(pady=(2, 2))
        canvas.create_rectangle(0, 0, fill_w, BAR_H, fill=bar_color, outline="")

        pct_text = f"{pct:.1f}%" if pct < 100 else f"{pct:.0f}% ⚠"
        pct_lbl = tk.Label(
            cell, text=pct_text, font=("Segoe UI", 8),
            bg=_BG, fg=txt_color,
        )
        pct_lbl.pack(anchor="w")
