import json
import pytest
import sys
from pathlib import Path

# Add src to python path for testing
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from contextcruncher.skeletonizer import (
    crunch_skeleton,
    _json_skeleton,
    _xml_skeleton,
    _reduce_value,
)


# ---------------------------------------------------------------------------
# Python skeleton (pre-existing tests, kept unchanged)
# ---------------------------------------------------------------------------

def test_python_skeleton():
    code = """
import os

class MyClass:
    def method_one(self, a: int):
        print(a)
        return a * 2

def global_func():
    \"\"\"This is a docstring.\"\"\"
    x = 10
    if x > 5:
        print("Hello")

async def async_func():
    await something()
"""
    skeleton = crunch_skeleton(code, "test.py")

    assert "class MyClass:" in skeleton
    assert "def method_one(self, a: int):" in skeleton
    assert "def global_func():" in skeleton
    assert "async def async_func():" in skeleton

    # Bodies should be gone
    assert "print(a)" not in skeleton
    assert "return a * 2" not in skeleton
    assert 'print("Hello")' not in skeleton
    assert "This is a docstring" not in skeleton


def test_js_skeleton():
    code = """
import { useState } from 'react';

export class App {
    private doThing() {
        console.log("doing thing");
    }
}

export const helper = (args) => {
    return true;
}
"""
    skeleton = crunch_skeleton(code, "app.ts")
    assert "export class App" in skeleton
    assert "export const helper" in skeleton
    assert "console.log" not in skeleton


# ---------------------------------------------------------------------------
# JS/TS skeleton — extended patterns (Task 4.2)
# ---------------------------------------------------------------------------

def test_js_skeleton_getter_setter():
    """get/set accessors should appear in skeleton."""
    code = """\
class MyStore {
    get items() {
        return this._items;
    }
    set items(val) {
        this._items = val;
    }
}
"""
    skeleton = crunch_skeleton(code, "store.ts")
    assert "get items()" in skeleton
    assert "set items(val)" in skeleton
    assert "this._items" not in skeleton


def test_js_skeleton_static_method():
    """Static methods and properties should appear in skeleton."""
    code = """\
class Utils {
    static create(name) {
        return new Utils(name);
    }
    static DEFAULT_TIMEOUT = 5000;
}
"""
    skeleton = crunch_skeleton(code, "utils.js")
    assert "static create" in skeleton
    assert "static DEFAULT_TIMEOUT" in skeleton
    assert "new Utils" not in skeleton


def test_js_skeleton_arrow_property():
    """Arrow function class properties should appear in skeleton."""
    code = """\
class Handler {
    onClick = (event) => {
        event.preventDefault();
    }
    fetchData = async (url) => {
        return await fetch(url);
    }
}
"""
    skeleton = crunch_skeleton(code, "handler.ts")
    assert "onClick = (event) =>" in skeleton
    assert "fetchData = async (url) =>" in skeleton
    assert "event.preventDefault" not in skeleton


def test_js_skeleton_method_shorthand():
    """Method shorthand (foo() {) should appear in skeleton."""
    code = """\
class Router {
    navigate(path) {
        window.location = path;
    }
    render() {
        return this.view;
    }
}
"""
    skeleton = crunch_skeleton(code, "router.js")
    assert "navigate(path)" in skeleton
    assert "render()" in skeleton
    assert "window.location" not in skeleton


def test_js_skeleton_control_flow_excluded():
    """Control flow lines must NOT appear in skeleton."""
    code = """\
function process(data) {
    if (data.length > 0) {
        for (let i = 0; i < data.length; i++) {
            switch (data[i].type) {
                case 'a': break;
            }
            return data[i];
        }
    }
    throw new Error("empty");
}
"""
    skeleton = crunch_skeleton(code, "process.js")
    # function should appear
    assert "function process(data)" in skeleton
    # control flow should NOT appear
    for kw in ("if (data", "for (let", "switch (data", "throw new"):
        assert kw not in skeleton, f"control flow '{kw}' should be excluded"


# ---------------------------------------------------------------------------
# JSON skeleton — _reduce_value helper
# ---------------------------------------------------------------------------

def test_reduce_value_short_string_unchanged():
    assert _reduce_value("hello", 40, 2) == "hello"

def test_reduce_value_long_string_truncated():
    long = "a" * 100
    result = _reduce_value(long, 40, 2)
    assert result.startswith("a" * 40)
    assert "60 more chars" in result

def test_reduce_value_array_capped():
    arr = [1, 2, 3, 4, 5]
    result = _reduce_value(arr, 40, 2)
    assert result[0] == 1
    assert result[1] == 2
    assert "3 more items" in result[2]

def test_reduce_value_array_within_limit():
    arr = [1, 2]
    result = _reduce_value(arr, 40, 2)
    assert result == [1, 2]

def test_reduce_value_nested_dict():
    data = {"key": {"nested": "x" * 60}}
    result = _reduce_value(data, 40, 2)
    assert "nested" in result["key"]
    assert "20 more chars" in result["key"]["nested"]

def test_reduce_value_number_unchanged():
    assert _reduce_value(42, 40, 2) == 42
    assert _reduce_value(3.14, 40, 2) == 3.14
    assert _reduce_value(True, 40, 2) is True
    assert _reduce_value(None, 40, 2) is None


# ---------------------------------------------------------------------------
# JSON skeleton — full round-trip via crunch_skeleton
# ---------------------------------------------------------------------------

_SAMPLE_JSON = json.dumps({
    "name": "ContextCruncher",
    "version": "0.2.0",
    "description": "A" * 200,
    "features": ["OCR", "compression", "MCP server", "clipboard history", "tray icon"],
    "config": {
        "level": 2,
        "token_limit": 100000
    }
})

def test_json_skeleton_keys_preserved():
    result = crunch_skeleton(_SAMPLE_JSON, "config.json")
    parsed = json.loads(result)
    assert "name" in parsed
    assert "version" in parsed
    assert "description" in parsed
    assert "features" in parsed
    assert "config" in parsed

def test_json_skeleton_long_string_truncated():
    result = crunch_skeleton(_SAMPLE_JSON, "config.json")
    parsed = json.loads(result)
    assert len(parsed["description"]) < 200
    assert "more chars" in parsed["description"]

def test_json_skeleton_array_capped():
    result = crunch_skeleton(_SAMPLE_JSON, "config.json")
    parsed = json.loads(result)
    # Default max_arr_items=2, original has 5 items
    assert len(parsed["features"]) == 3  # 2 items + "...N more items" string
    assert "more items" in parsed["features"][2]

def test_json_skeleton_nested_values_preserved():
    result = crunch_skeleton(_SAMPLE_JSON, "config.json")
    parsed = json.loads(result)
    assert parsed["config"]["level"] == 2
    assert parsed["config"]["token_limit"] == 100000

def test_json_skeleton_token_count_reduced():
    """The skeleton must be shorter (in chars) than the original."""
    result = crunch_skeleton(_SAMPLE_JSON, "config.json")
    assert len(result) < len(_SAMPLE_JSON)

def test_json_skeleton_invalid_json_fallback():
    """Bad JSON must not raise — must return original text."""
    bad = "{ this is not json }"
    result = crunch_skeleton(bad, "data.json")
    assert result == bad


# ---------------------------------------------------------------------------
# XML skeleton — via crunch_skeleton
# ---------------------------------------------------------------------------

_SAMPLE_XML = """<?xml version="1.0"?>
<root>
    <item id="1" type="text">
        <title>Short title</title>
        <body>This is a very long body text that should be truncated because it exceeds the maximum character limit set in the XML skeletonizer function.</body>
    </item>
    <item id="2" type="image">
        <title>Another item</title>
        <body>Short.</body>
    </item>
</root>"""

def test_xml_skeleton_tags_preserved():
    result = crunch_skeleton(_SAMPLE_XML, "data.xml")
    assert "<root>" in result or "root" in result
    assert "item" in result
    assert "title" in result
    assert "body" in result

def test_xml_skeleton_attributes_preserved():
    result = crunch_skeleton(_SAMPLE_XML, "data.xml")
    assert 'id="1"' in result
    assert 'type="text"' in result

def test_xml_skeleton_long_text_truncated():
    result = crunch_skeleton(_SAMPLE_XML, "data.xml")
    # The long body text must be cut off
    assert "This is a very long body text" not in result or "…" in result

def test_xml_skeleton_short_text_preserved():
    result = crunch_skeleton(_SAMPLE_XML, "data.xml")
    assert "Short." in result

def test_xml_skeleton_invalid_xml_fallback():
    bad = "<unclosed tag"
    result = crunch_skeleton(bad, "data.xml")
    assert result == bad


# ---------------------------------------------------------------------------
# Unsupported extensions — graceful no-op
# ---------------------------------------------------------------------------

def test_unsupported_extension_returns_original():
    text = "some random content here"
    assert crunch_skeleton(text, "file.csv") == text
    assert crunch_skeleton(text, "file.log") == text
    assert crunch_skeleton(text, "noextension") == text

def test_empty_string_all_types():
    for fname in ("code.py", "data.json", "page.xml"):
        # Empty string goes through the dispatcher but returns empty
        # (parsers may raise or return "" — both are acceptable as long as
        # no exception propagates)
        try:
            result = crunch_skeleton("", fname)
            assert isinstance(result, str)
        except Exception as exc:
            pytest.fail(f"crunch_skeleton raised for {fname}: {exc}")
