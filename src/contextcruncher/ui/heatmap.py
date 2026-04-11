"""
heatmap.py - Visual token budget UI.

Shows a popup window highlighting expensive LLM tokens in red
and efficient tokens in green.
"""

import tkinter as tk
from tkinter import ttk
import logging
import threading

try:
    import tiktoken
except ImportError:
    tiktoken = None

logger = logging.getLogger(__name__)


def show_heatmap(text: str) -> None:
    """Show the token heatmap in a background thread."""
    if not text:
        return
        
    if not tiktoken:
        logger.error("tiktoken not installed. Cannot show heatmap.")
        return

    threading.Thread(
        target=_heatmap_thread,
        args=(text,),
        daemon=True,
    ).start()


def _heatmap_thread(text: str) -> None:
    """Creates a Tk window showing the token heatmap for the given text."""
    top = tk.Tk()
    top.title("ContextCruncher 🌡️ Token Heatmap")
    top.geometry("800x600")
    top.attributes("-topmost", True)
    
    # Optional dark theme tweaks
    top.configure(bg="#1a1a2e")
    
    # Stats Label
    stats_lbl = ttk.Label(top, text="Calculating tokens...", font=("Segoe UI", 11, "bold"), background="#1a1a2e", foreground="#ffffff")
    stats_lbl.pack(side="top", pady=10, fill="x", padx=10)
    
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
        enc = tiktoken.get_encoding("cl100k_base")
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
            
        stats_text = f"Total Tokens: {len(tokens):,} | Total Chars: {len(text):,} | Efficiency: {len(text)/max(1, len(tokens)):.1f} chars/token"
        stats_lbl.config(text=stats_text)
        
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
    top.mainloop()
