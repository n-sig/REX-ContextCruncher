"""
heatmap.py - Visual token budget UI.

Shows a popup window highlighting expensive LLM tokens in red
and efficient tokens in green.

FIX (Audit F-03): Uses tk.Toplevel owned by the global TkManager instead of
creating a new tk.Tk(), which violated design decision #1 (single Tk root)
and could cause tkinter crashes.
"""

import tkinter as tk
from tkinter import ttk
import logging
import threading

from contextcruncher.feedback import get_tk_manager

try:
    import tiktoken
except ImportError:
    tiktoken = None

from contextcruncher.token_counter import (  # FR-02 / FR-03
    cost_estimate, format_cost,
    context_window_usage, CONTEXT_WINDOW_TABLE, CONTEXT_WARN_PCT, CONTEXT_ALERT_PCT,
)

logger = logging.getLogger(__name__)


def show_heatmap(text: str) -> None:
    """Show the token heatmap in a background thread."""
    if not text:
        return
        
    if not tiktoken:
        logger.error("tiktoken not installed. Cannot show heatmap.")
        return

    get_tk_manager().schedule(_create_heatmap, text)


def _create_heatmap(text: str) -> None:
    """Build the heatmap as a Toplevel on TkUIThread."""
    mgr = get_tk_manager()
    if mgr.root is None:
        return
    top = tk.Toplevel(mgr.root)
    top.title("ContextCruncher 🌡️ Token Heatmap")
    top.geometry("800x600")
    top.attributes("-topmost", True)
    
    # Optional dark theme tweaks
    top.configure(bg="#1a1a2e")
    
    # Stats Label
    stats_lbl = ttk.Label(top, text="Calculating tokens...", font=("Segoe UI", 11, "bold"), background="#1a1a2e", foreground="#ffffff")
    stats_lbl.pack(side="top", pady=(10, 2), fill="x", padx=10)

    # FR-02 — Cost estimate label (populated after tokenisation)
    cost_lbl = tk.Label(top, text="", font=("Segoe UI", 10),
                        bg="#1a1a2e", fg="#aaaacc", justify="left")
    cost_lbl.pack(side="top", fill="x", padx=14, pady=(0, 2))

    # FR-03 — Context window usage frame (populated after tokenisation)
    ctx_frame = tk.Frame(top, bg="#1a1a2e")
    ctx_frame.pack(side="top", fill="x", padx=14, pady=(0, 6))

    # Legend
    legend_frame = ttk.Frame(top)
    legend_frame.pack(side="top", fill="x", padx=10, pady=5)
    tk.Label(legend_frame, text=" 🟥 Expensive (1 char/token) ", bg="#ffcccc").pack(side="left", padx=5)
    tk.Label(legend_frame, text=" 🟨 Medium (2-3 chars/token) ", bg="#fff3cc").pack(side="left", padx=5)
    tk.Label(legend_frame, text=" 🟩 Cheap (4+ chars/token) ", bg="#ccffcc").pack(side="left", padx=5)
    
    # Text Widget
    text_widget = tk.Text(top, wrap="word", font=("Consolas", 14))
    text_widget.pack(fill="both", expand=True, padx=10, pady=10)
    
    # Define color tags
    text_widget.tag_config("t_expensive", background="#ffcccc")
    text_widget.tag_config("t_medium", background="#fff3cc")
    text_widget.tag_config("t_cheap", background="#ccffcc")
    text_widget.tag_config("t_whitespace", background="#f0f0f0") # just plain for pure space
    
    try:
        enc = tiktoken.get_encoding("o200k_base")
        tokens = enc.encode(text)
        
        for t in tokens:
            b_tok = enc.decode_single_token_bytes(t)
            s_tok = b_tok.decode("utf-8", errors="replace")
            
            stripped = s_tok.strip()
            
            if not stripped:
                # purely whitespace
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
            f"Total Tokens: {n_tokens:,} | "
            f"Total Chars: {len(text):,} | "
            f"Efficiency: {len(text)/max(1, n_tokens):.1f} chars/token"
        )
        stats_lbl.config(text=stats_text)

        # FR-02 — per-model cost estimate (using exact per-model tokens)
        costs = cost_estimate(text)
        cost_parts = []
        for model, c in costs.items():
            label = f"{model}: {format_cost(c)}"
            if "Claude" in model:
                label += " (~est)"
            cost_parts.append(label)
            
        cost_lbl.config(text="💰 Input cost est.:  " + "   |   ".join(cost_parts))

        # FR-03 — context window usage bars (using exact per-model tokens)
        usage = context_window_usage(text)
        _render_context_bars(ctx_frame, usage)

    except Exception as e:
        logger.error(f"Heatmap error: {e}", exc_info=True)
        text_widget.insert("end", f"Error generating heatmap: {e}\n\n{text}")
        
    text_widget.config(state="disabled")
    
    # Position: center of screen 
    top.update_idletasks()
    w = max(top.winfo_reqwidth(), 800)
    h = top.winfo_reqheight()
    sw = top.winfo_screenwidth()
    sh = top.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    top.geometry(f"{w}x{h}+{x}+{y}")
    
    top.focus_force()


def _render_context_bars(parent: tk.Frame, usage: dict[str, float]) -> None:
    """FR-03 — Render one mini progress bar per model inside *parent*.

    Color coding:
      < CONTEXT_WARN_PCT  → green  (safe)
      < CONTEXT_ALERT_PCT → yellow (caution)
      >= CONTEXT_ALERT_PCT → red   (danger)
    """
    _BG = "#1a1a2e"
    _TRACK = "#2a2a4e"
    BAR_W = 120   # canvas width in pixels
    BAR_H = 10    # canvas height in pixels

    header = tk.Label(parent, text="📐 Context window usage:",
                      font=("Segoe UI", 10), bg=_BG, fg="#aaaacc")
    header.grid(row=0, column=0, columnspan=99, sticky="w", pady=(0, 2))

    for col, (model, pct) in enumerate(usage.items()):
        if pct >= CONTEXT_ALERT_PCT:
            bar_color = "#ff6b6b"   # red
            txt_color = "#ff6b6b"
        elif pct >= CONTEXT_WARN_PCT:
            bar_color = "#ffd166"   # yellow
            txt_color = "#ffd166"
        else:
            bar_color = "#06d6a0"   # green
            txt_color = "#aaffcc"

        fill_w = max(1, min(int(BAR_W * min(pct, 100) / 100), BAR_W))

        cell = tk.Frame(parent, bg=_BG)
        cell.grid(row=1, column=col, padx=(0, 12), sticky="w")

        name_lbl = tk.Label(cell, text=model, font=("Segoe UI", 8),
                            bg=_BG, fg="#888899")
        name_lbl.pack(anchor="w")

        canvas = tk.Canvas(cell, width=BAR_W, height=BAR_H,
                           bg=_TRACK, highlightthickness=0)
        canvas.pack()
        canvas.create_rectangle(0, 0, fill_w, BAR_H, fill=bar_color, outline="")

        pct_text = f"{pct:.1f}%" if pct < 100 else f"{pct:.0f}% ⚠"
        pct_lbl = tk.Label(cell, text=pct_text, font=("Segoe UI", 8),
                           bg=_BG, fg=txt_color)
        pct_lbl.pack(anchor="w")
