#!/usr/bin/env python3
"""
claude_md_benchmark.py — Fidelity benchmark for AI instruction files.

Measures not only token savings but also FIDELITY — the percentage of
high-value elements (file paths, constraint keywords, CLI commands, and
identifiers) that survive compression.  For an agent-instruction file
like CLAUDE.md, a 60% token reduction that drops half the filenames is
a disaster; a 15% reduction that keeps 100% of them is a win.

The benchmark runs TWO pipelines side-by-side:
  1. `minify_for_ai()` — the deterministic text processor.  On a file
     detected as `agent_config` via content_router, this is still the
     general-purpose compressor.
  2. `smart_route()`  — the content-aware router.  For `agent_config`,
     this routes to the skeletonizer/minifier with structure awareness.

For each, we report:
  - tokens saved
  - filenames preserved  (e.g. `main.py`, `config.json`)
  - constraint keywords preserved (NEVER, ALWAYS, MUST NOT, DO NOT, IMMER,
    MUSS, NIEMALS ...)
  - CLI commands preserved (lines starting with `$`, `>`, or containing
    `npm run`, `python -m`, `pyinstaller`, ...)
  - identifiers preserved (backtick-quoted snake_case / camelCase)

Usage:
    python evals/claude_md_benchmark.py                   # use project CLAUDE.md
    python evals/claude_md_benchmark.py --input FILE.md   # custom file
    python evals/claude_md_benchmark.py --json results/claude_md.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

# Force UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from contextcruncher.text_processor import minify_for_ai  # noqa: E402
from contextcruncher.token_counter import count_tokens  # noqa: E402
from contextcruncher.content_router import (  # noqa: E402
    smart_route,
    detect_content_type,
)


# ---------------------------------------------------------------------------
# Fidelity extractors
# ---------------------------------------------------------------------------

# Filenames — word.ext with known extensions.  Short (<4 char base name)
# words are filtered out to avoid counting false positives like `a.b`.
_FILENAME_RE = re.compile(
    r'\b[\w.-]{2,}\.(?:py|js|ts|jsx|tsx|json|md|yaml|yml|toml|cfg|ini|'
    r'spec|lock|html|css|sh|bash|ps1|txt|log|csv|pdf|docx|xlsx)\b'
)

_CONSTRAINT_RE = re.compile(
    r'\b(?:NEVER|ALWAYS|MUST(?:\s+NOT)?|DO\s+NOT|SHOULD(?:\s+NOT)?|'
    r'IMMER|NIEMALS|MUSS(?:\s+NICHT)?|DARF\s+NICHT|KEIN[EN]?)\b',
    re.IGNORECASE,
)

_COMMAND_RE = re.compile(
    r'(?:^|\n)\s*[$>]\s*\S.*|'
    r'\b(?:npm|pip|python|python3|pytest|node|npx|yarn|pyinstaller|'
    r'git|docker|make|cargo|go)\s+[\w.-]+[^`\n]*'
)

_BACKTICK_IDENT_RE = re.compile(r'`([A-Za-z_][\w.]*)`')


@dataclass
class FidelityMetrics:
    tokens_original: int
    tokens_compressed: int
    tokens_saved_pct: float
    # Sets of preserved/lost items
    filenames_original: int
    filenames_preserved: int
    filenames_lost: list
    constraints_original: int
    constraints_preserved: int
    commands_original: int
    commands_preserved: int
    idents_original: int
    idents_preserved: int
    content_type: str
    technique_summary: list


def _extract_set(pattern: re.Pattern, text: str) -> set:
    """Extract all matches.  Uses group(1) when the pattern has a capture
    group (so for ``pattern = `(id)` `` we get just `id`, not `` `id` ``),
    otherwise the full match."""
    out = set()
    for m in pattern.finditer(text):
        out.add(m.group(1) if m.groups() else m.group(0))
    return out


def _count_pattern(pattern: re.Pattern, text: str) -> int:
    return len(pattern.findall(text))


def measure_fidelity(original: str, compressed: str,
                     content_type: str,
                     techniques: list[str]) -> FidelityMetrics:
    """Compute a full fidelity report by comparing original to compressed."""
    # Filenames — preserved if present in compressed output (case-sensitive)
    orig_files = _extract_set(_FILENAME_RE, original)
    kept_files = {f for f in orig_files if f in compressed}
    lost_files = sorted(orig_files - kept_files)[:10]  # top 10 losses

    # Constraints — count occurrences (keyword density matters)
    orig_cons = _count_pattern(_CONSTRAINT_RE, original)
    kept_cons = _count_pattern(_CONSTRAINT_RE, compressed)

    # Commands — same idea
    orig_cmds = _count_pattern(_COMMAND_RE, original)
    kept_cmds = _count_pattern(_COMMAND_RE, compressed)

    # Identifiers — backtick-quoted names.  An identifier is "preserved"
    # if it still appears in the compressed output (with or without the
    # surrounding backticks).  We require a word-boundary match so short
    # names like `a` don't spuriously match every word that contains "a".
    orig_idents = _extract_set(_BACKTICK_IDENT_RE, original)
    kept_idents = {
        i for i in orig_idents
        if f"`{i}`" in compressed
        or re.search(rf'(?<!\w){re.escape(i)}(?!\w)', compressed)
    }

    orig_tok = count_tokens(original)
    comp_tok = count_tokens(compressed)
    saved_pct = 0.0 if orig_tok == 0 else (orig_tok - comp_tok) / orig_tok * 100.0

    return FidelityMetrics(
        tokens_original=orig_tok,
        tokens_compressed=comp_tok,
        tokens_saved_pct=round(saved_pct, 1),
        filenames_original=len(orig_files),
        filenames_preserved=len(kept_files),
        filenames_lost=lost_files,
        constraints_original=orig_cons,
        constraints_preserved=kept_cons,
        commands_original=orig_cmds,
        commands_preserved=kept_cmds,
        idents_original=len(orig_idents),
        idents_preserved=len(kept_idents),
        content_type=content_type,
        technique_summary=techniques,
    )


# ---------------------------------------------------------------------------
# Pipeline runners
# ---------------------------------------------------------------------------

def run_minify_for_ai(text: str) -> FidelityMetrics:
    compressed, stats = minify_for_ai(text)
    return measure_fidelity(
        text, compressed,
        content_type=stats.get("content_type", "unknown"),
        techniques=stats.get("techniques_applied", []),
    )


def run_smart_route(text: str, filename: str = "") -> FidelityMetrics:
    ct = detect_content_type(text, filename=filename)
    result = smart_route(text, filename=filename)
    compressed = result.text if hasattr(result, "text") else str(result)
    techniques = (
        list(result.techniques) if hasattr(result, "techniques") else [ct]
    )
    return measure_fidelity(
        text, compressed, content_type=ct, techniques=techniques,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _score_line(label: str, kept: int, total: int) -> str:
    pct = 0.0 if total == 0 else (kept / total) * 100.0
    bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
    return f"  {label:<22} {kept:>4}/{total:<4} ({pct:>5.1f}%)  {bar}"


def print_report(name: str, pipe_name: str, m: FidelityMetrics) -> None:
    print(f"\n── {name}  ·  pipeline: {pipe_name}  ·  content_type: {m.content_type}")
    print(f"  Tokens: {m.tokens_original:,} → {m.tokens_compressed:,} "
          f"({m.tokens_saved_pct:+.1f}% saved)")
    print(_score_line("Filenames preserved", m.filenames_preserved, m.filenames_original))
    print(_score_line("Constraints (hits)", m.constraints_preserved, m.constraints_original))
    print(_score_line("Commands (hits)", m.commands_preserved, m.commands_original))
    print(_score_line("Backtick idents", m.idents_preserved, m.idents_original))
    if m.filenames_lost:
        print(f"  ⚠ Lost filenames (sample): {', '.join(m.filenames_lost[:5])}")


def print_header(title: str) -> None:
    print()
    print("=" * 80)
    print(f"  🧠 {title}")
    print("=" * 80)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _load_default_claude_md() -> str:
    """Load the project's CLAUDE.md — falls back to a synthetic sample."""
    here = Path(__file__).resolve().parent
    candidates = [
        here.parent / "CLAUDE.md",
        here.parent / "AGENTS.md",
        here.parent / "GEMINI.md",
    ]
    for c in candidates:
        if c.is_file():
            text = c.read_text(encoding="utf-8", errors="replace")
            if text.strip():
                return text

    # Synthetic fallback so the benchmark is always runnable
    return (
        "# CLAUDE.md\n\n"
        "## Project Overview\n\n"
        "Python 3.11+ project. Tkinter GUI. NEVER store secrets in "
        "config.json. ALWAYS use the security_scanner module before "
        "writing to disk.\n\n"
        "## Common Commands\n\n"
        "- `python src/contextcruncher/main.py`\n"
        "- `python -m pytest tests/ -v`\n"
        "- `pyinstaller build.spec`\n\n"
        "## Key Design Decisions\n\n"
        "1. Single Tk root: never create additional `tk.Tk()`, always `Toplevel`.\n"
        "2. In-memory only: `TextStack` uses `deque(maxlen=50)`.\n"
        "3. Deterministic compression: `minify_for_ai()` is a pure function.\n"
        "4. DO NOT import network libraries in core modules.\n"
        "5. MUST NOT write bare `.py` paths to the Windows registry.\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fidelity benchmark for AI instruction files"
    )
    parser.add_argument("--input", "-i",
                        help="Path to a file (default: project CLAUDE.md)")
    parser.add_argument("--json", "-j",
                        help="Write full results to JSON")
    args = parser.parse_args()

    if args.input:
        text = Path(args.input).read_text(encoding="utf-8", errors="replace")
        filename = Path(args.input).name
        name = filename
    else:
        text = _load_default_claude_md()
        filename = "CLAUDE.md"
        name = "CLAUDE.md (project default)"

    print_header(f"CLAUDE.md Fidelity Benchmark — {name}")

    start = time.perf_counter()
    m_minify = run_minify_for_ai(text)
    m_smart = run_smart_route(text, filename=filename)
    elapsed = time.perf_counter() - start

    print_report(name, "minify_for_ai (deterministic)", m_minify)
    print_report(name, "smart_route (content-aware)", m_smart)

    print()
    print("-" * 80)
    print("  📊 Head-to-head (higher = better for fidelity):")
    for label, key in [
        ("Tokens saved",    "tokens_saved_pct"),
        ("Filenames kept",
            lambda x: (x.filenames_preserved / max(1, x.filenames_original)) * 100),
        ("Constraints kept",
            lambda x: (x.constraints_preserved / max(1, x.constraints_original)) * 100),
        ("Commands kept",
            lambda x: (x.commands_preserved / max(1, x.commands_original)) * 100),
        ("Idents kept",
            lambda x: (x.idents_preserved / max(1, x.idents_original)) * 100),
    ]:
        if callable(key):
            a, b = key(m_minify), key(m_smart)
        else:
            a, b = getattr(m_minify, key), getattr(m_smart, key)
        winner = " ✅ smart_route" if b > a else (
            " ✅ minify_for_ai" if a > b else " ≡ tie"
        )
        print(f"  {label:<20} minify={a:>5.1f}%   smart={b:>5.1f}%  {winner}")
    print("=" * 80)
    print(f"  ⏱  Completed in {elapsed:.2f}s")

    if args.json:
        out = {
            "name": name,
            "input_path": str(args.input) if args.input else "(default)",
            "minify_for_ai": asdict(m_minify),
            "smart_route": asdict(m_smart),
            "elapsed_seconds": round(elapsed, 3),
        }
        p = Path(args.json)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  💾 JSON written to {p}")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
