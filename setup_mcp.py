#!/usr/bin/env python3
"""
setup_mcp.py — Auto-register ContextCruncher MCP server in AI IDEs.

Run this from the ContextCruncher directory to automatically configure
your AI coding tools to use ContextCruncher as an MCP server.

Supports:
  • Claude Desktop / Claude Code
  • Cursor
  • Windsurf
  • Continue.dev
  • Generic MCP-compatible clients

Usage:
    python setup_mcp.py              # Interactive — pick your tools
    python setup_mcp.py --all        # Register in all detected tools
    python setup_mcp.py --claude     # Register in Claude Desktop only
    python setup_mcp.py --cursor     # Register in Cursor only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# The MCP server entry to inject
MCP_ENTRY = {
    "command": "python",
    "args": ["-m", "contextcruncher.mcp_server"],
    "env": {}
}


def get_claude_config_path() -> Path | None:
    """Get the Claude Desktop config path."""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        p = Path(appdata) / "Claude" / "claude_desktop_config.json"
    elif sys.platform == "darwin":
        p = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    else:
        p = Path.home() / ".config" / "claude" / "claude_desktop_config.json"
    return p


def get_cursor_config_path() -> Path | None:
    """Get the Cursor MCP config path."""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        p = Path(appdata) / "Cursor" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "settings" / "cline_mcp_settings.json"
    else:
        p = Path.home() / ".cursor" / "mcp.json"
    return p


def get_continue_config_path() -> Path | None:
    """Get the Continue.dev config path."""
    return Path.home() / ".continue" / "config.json"


def get_windsurf_config_path() -> Path | None:
    """Get the Windsurf config path."""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        return Path(appdata) / "Windsurf" / "User" / "globalStorage" / "codeium.windsurf" / "mcp_config.json"
    return Path.home() / ".windsurf" / "mcp.json"


TOOLS = {
    "claude": ("Claude Desktop", get_claude_config_path),
    "cursor": ("Cursor", get_cursor_config_path),
    "windsurf": ("Windsurf", get_windsurf_config_path),
    "continue": ("Continue.dev", get_continue_config_path),
}


def register_in_config(config_path: Path, tool_name: str) -> bool:
    """Register ContextCruncher MCP server in a config file."""
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing config or create new
    config = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            print(f"  ⚠️  Could not parse existing config at {config_path}")
            print(f"     Creating backup and writing fresh config.")
            backup = config_path.with_suffix(".json.bak")
            config_path.rename(backup)
            config = {}

    # Ensure mcpServers key exists
    if "mcpServers" not in config:
        config["mcpServers"] = {}

    # Check if already registered
    if "contextcruncher" in config["mcpServers"]:
        print(f"  ✅ {tool_name}: Already registered!")
        return True

    # Add our entry
    config["mcpServers"]["contextcruncher"] = MCP_ENTRY

    # Write back
    try:
        config_path.write_text(
            json.dumps(config, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8"
        )
        print(f"  ✅ {tool_name}: Registered at {config_path}")
        return True
    except Exception as e:
        print(f"  ❌ {tool_name}: Failed to write config: {e}")
        return False


def interactive_setup():
    """Interactive mode — let user pick tools."""
    print()
    print("  🦖 ContextCruncher MCP Setup")
    print("  " + "=" * 40)
    print()

    available = []
    for key, (name, get_path) in TOOLS.items():
        path = get_path()
        exists = path.exists() if path else False
        status = "detected" if exists else "not found"
        available.append((key, name, path, exists))
        marker = "✅" if exists else "⬚ "
        print(f"  {marker} {name:<20} ({status})")

    print()
    print("  Enter tool names to register (comma-separated), or 'all':")
    print("  Example: claude,cursor")
    print()

    try:
        choice = input("  > ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n  Cancelled.")
        return

    if choice == "all":
        targets = [k for k, _, _, _ in available]
    else:
        targets = [c.strip() for c in choice.split(",") if c.strip()]

    print()
    for key in targets:
        if key in TOOLS:
            name, get_path = TOOLS[key]
            path = get_path()
            if path:
                register_in_config(path, name)
            else:
                print(f"  ❌ {name}: Config path not available on this OS")
        else:
            print(f"  ❌ Unknown tool: {key}")
    print()
    print("  Done! Restart your AI tools to pick up the changes.")
    print()


def main():
    parser = argparse.ArgumentParser(description="Register ContextCruncher MCP server in AI tools")
    parser.add_argument("--all", action="store_true", help="Register in all supported tools")
    parser.add_argument("--claude", action="store_true", help="Register in Claude Desktop")
    parser.add_argument("--cursor", action="store_true", help="Register in Cursor")
    parser.add_argument("--windsurf", action="store_true", help="Register in Windsurf")
    parser.add_argument("--continue-dev", action="store_true", help="Register in Continue.dev")
    args = parser.parse_args()

    explicit = any([args.all, args.claude, args.cursor, args.windsurf, args.continue_dev])

    if not explicit:
        interactive_setup()
        return

    print()
    print("  🦖 ContextCruncher MCP Setup")
    print("  " + "=" * 40)
    print()

    targets = []
    if args.all:
        targets = list(TOOLS.keys())
    else:
        if args.claude:
            targets.append("claude")
        if args.cursor:
            targets.append("cursor")
        if args.windsurf:
            targets.append("windsurf")
        if args.continue_dev:
            targets.append("continue")

    for key in targets:
        name, get_path = TOOLS[key]
        path = get_path()
        if path:
            register_in_config(path, name)
        else:
            print(f"  ❌ {name}: Config path not available on this OS")

    print()
    print("  Done! Restart your AI tools to pick up the changes.")
    print()


if __name__ == "__main__":
    main()
