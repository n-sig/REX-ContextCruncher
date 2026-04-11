#!/usr/bin/env python3
"""
run_eval.py — Benchmark suite for ContextCruncher's compression engine.

Measures token savings across all compression levels using tiktoken
(cl100k_base ≈ GPT-4o / Claude tokenizer). Produces a results JSON
and a human-readable summary table.

Usage:
    python evals/run_eval.py                     # Run against built-in samples
    python evals/run_eval.py --input myfile.txt  # Run against a custom file
    python evals/run_eval.py --dir ./docs        # Run against entire directory
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Force UTF-8 output on Windows (cp1252 can't handle emoji)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from contextcruncher.text_processor import minify_for_ai
from contextcruncher.token_counter import count_tokens, token_stats

# -----------------------------------------------------------------------
# Built-in sample texts for reproducible benchmarks
# -----------------------------------------------------------------------

SAMPLES = {
    "prose_en": (
        "The quick brown fox jumps over the lazy dog. This is a simple sentence "
        "that demonstrates basic English prose. The fox was not only quick but also "
        "very clever and intelligent. It was a beautiful day in the forest where "
        "the animals played and the birds sang their songs. The lazy dog, however, "
        "did not care about any of this and simply continued to sleep under the "
        "old oak tree that had been standing there for hundreds of years."
    ),
    "web_scrape": (
        "Skip to content\n"
        "User navigation overview\n"
        "Repositories Projects Packages Stars\n\n"
        "John Smith\n"
        "@johnsmith · Senior Software Engineer at TechCorp\n"
        "Followers: 1,234 Following: 567\n\n"
        "# README.md\n\n"
        "This project implements a high-performance concurrent data pipeline "
        "for processing large-scale event streams. The architecture uses an "
        "event-driven design pattern with backpressure support for reliable "
        "message handling.\n\n"
        "## Features\n"
        "- Real-time event processing\n"
        "- Horizontal scaling support\n"
        "- Built-in monitoring and alerting\n\n"
        "Footer · Terms · Privacy · Security · Status · Docs · Contact · "
        "Manage cookies · Do not share my personal information\n"
        "© 2026 GitHub, Inc."
    ),
    "code_python": (
        "import asyncio\n"
        "from dataclasses import dataclass, field\n"
        "from typing import Optional, List\n\n"
        "@dataclass\n"
        "class EventProcessor:\n"
        "    \"\"\"Processes incoming events from the message queue.\"\"\"\n"
        "    buffer_size: int = 1024\n"
        "    max_retries: int = 3\n"
        "    _queue: asyncio.Queue = field(default_factory=asyncio.Queue)\n\n"
        "    async def process(self, event: dict) -> Optional[dict]:\n"
        "        \"\"\"Process a single event and return the result.\"\"\"\n"
        "        try:\n"
        "            validated = self._validate(event)\n"
        "            transformed = self._transform(validated)\n"
        "            return await self._persist(transformed)\n"
        "        except Exception as e:\n"
        "            logger.error(f'Failed to process event: {e}')\n"
        "            return None\n"
    ),
    "mixed_de_en": (
        "Sehr geehrte Damen und Herren,\n\n"
        "hiermit möchte ich Ihnen mitteilen, dass die neue Version der Software "
        "ab sofort zur Verfügung steht. Die wichtigsten Änderungen sind:\n\n"
        "1. Performance improvements for the core engine\n"
        "2. Bug fixes in the authentication module\n"
        "3. Neue Benutzeroberfläche mit Dark Mode Unterstützung\n\n"
        "The documentation has been updated accordingly and is available "
        "in both German and English. Please refer to the README for "
        "installation instructions.\n\n"
        "Mit freundlichen Grüßen,\n"
        "Das Entwicklungsteam"
    ),
    "claude_memory": (
        "# CLAUDE.md\n\n"
        "This file provides guidance to Claude Code (claude.ai/code) when working "
        "with code in this repository.\n\n"
        "## Project Overview\n\n"
        "This is a Next.js 14 application using the App Router with TypeScript, "
        "Tailwind CSS, and Supabase as the backend. The project follows a "
        "feature-based directory structure.\n\n"
        "## Common Commands\n\n"
        "- `npm run dev` — Start development server\n"
        "- `npm run build` — Build for production\n"
        "- `npm run test` — Run test suite\n"
        "- `npm run lint` — Run ESLint\n\n"
        "## Architecture Notes\n\n"
        "All API routes are in `app/api/`. Database queries go through the "
        "Supabase client in `lib/supabase.ts`. Authentication is handled by "
        "Supabase Auth with middleware in `middleware.ts`.\n\n"
        "When making changes, ensure you run the test suite and fix any "
        "linting issues before committing. The CI pipeline will reject "
        "PRs with failing tests or lint warnings.\n"
    ),
}

# -----------------------------------------------------------------------
# Level definitions with display names
# -----------------------------------------------------------------------

LEVELS = [
    (1, "🪶 Light"),
    (2, "🦖 Token-Cruncher"),
    (3, "💀 Annihilator"),
    (4, "☢️ Experimental"),
]


def evaluate_sample(name: str, text: str) -> dict:
    """Run all compression levels on a single sample and collect stats."""
    orig_tokens = count_tokens(text)
    results = {
        "name": name,
        "original_chars": len(text),
        "original_tokens": orig_tokens,
        "levels": [],
    }

    for level, label in LEVELS:
        compressed, char_pct = minify_for_ai(text, level=level)
        stats = token_stats(text, compressed)
        results["levels"].append({
            "level": level,
            "label": label,
            "compressed_chars": len(compressed),
            "char_saved_percent": round(char_pct, 1),
            **stats,
        })

    return results


def print_results(all_results: list[dict]) -> None:
    """Print a nice summary table."""
    print()
    print("=" * 90)
    print("  🦖 ContextCruncher Compression Benchmark")
    print("=" * 90)
    print()

    for result in all_results:
        name = result["name"]
        orig_t = result["original_tokens"]
        orig_c = result["original_chars"]
        print(f"  📝 {name}")
        print(f"     Original: {orig_c:,} chars / {orig_t:,} tokens")
        print(f"     {'Level':<25} {'Tokens':>8} {'Saved':>8} {'Chars':>8} {'Chr %':>8}")
        print(f"     {'-'*57}")

        for lv in result["levels"]:
            label = lv["label"]
            comp_t = lv["compressed_tokens"]
            saved = lv["tokens_saved"]
            comp_c = lv["compressed_chars"]
            pct = lv["saved_percent"]
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            print(f"     {label:<25} {comp_t:>8,} {saved:>+8,} {comp_c:>8,} {pct:>6.1f}%  {bar}")
        print()

    # Summary
    print("-" * 90)
    print("  📊 Average token savings across all samples:")
    for level, label in LEVELS:
        avg_pct = sum(
            lv["saved_percent"]
            for r in all_results
            for lv in r["levels"]
            if lv["level"] == level
        ) / len(all_results)
        print(f"     {label:<25} {avg_pct:>6.1f}% average")
    print("=" * 90)
    print()


def load_file(path: str) -> dict[str, str]:
    """Load a single file as a sample."""
    p = Path(path)
    if not p.is_file():
        print(f"ERROR: File not found: {path}", file=sys.stderr)
        sys.exit(1)
    text = p.read_text(encoding="utf-8", errors="replace")
    return {p.stem: text}


def load_dir(path: str) -> dict[str, str]:
    """Load all text files from a directory."""
    p = Path(path)
    if not p.is_dir():
        print(f"ERROR: Directory not found: {path}", file=sys.stderr)
        sys.exit(1)
    samples = {}
    for f in sorted(p.rglob("*")):
        if f.is_file() and f.suffix in {".txt", ".md", ".py", ".js", ".ts", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".log"}:
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
                if text.strip():
                    samples[f.name] = text
            except Exception:
                pass
    if not samples:
        print(f"ERROR: No text files found in {path}", file=sys.stderr)
        sys.exit(1)
    return samples


def main():
    parser = argparse.ArgumentParser(description="ContextCruncher Compression Benchmark")
    parser.add_argument("--input", "-i", help="Path to a single text file to benchmark")
    parser.add_argument("--dir", "-d", help="Path to a directory of text files")
    parser.add_argument("--json", "-j", help="Output results to JSON file")
    args = parser.parse_args()

    # Choose sample source
    if args.input:
        samples = load_file(args.input)
    elif args.dir:
        samples = load_dir(args.dir)
    else:
        samples = SAMPLES

    # Run benchmarks
    start = time.perf_counter()
    all_results = []
    for name, text in samples.items():
        result = evaluate_sample(name, text)
        all_results.append(result)
    elapsed = time.perf_counter() - start

    # Print
    print_results(all_results)
    print(f"  ⏱️  Completed in {elapsed:.2f}s")

    # Optionally save JSON
    if args.json:
        out_path = Path(args.json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
        print(f"  💾 Results saved to {out_path}")
    print()


if __name__ == "__main__":
    main()
