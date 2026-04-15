"""
skeletonizer.py - Generates an AST-based "semantic skeleton" for code and
structured data files.

For code (Python, JS/TS): strips all function bodies and keeps only class /
function signatures — drastically reduces token count while preserving
architectural context.

For structured data (JSON, XML, YAML): truncates long string values and
large arrays so the schema/shape is preserved while payload noise is removed.
"""

import ast
import json
import re
import logging
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Python  (AST-based — accurate)
# ---------------------------------------------------------------------------

class PythonSkeletonizer(ast.NodeTransformer):
    """AST Transformer that strips function bodies."""

    def visit_FunctionDef(self, node):
        node.body = [ast.Pass()]
        return node

    def visit_AsyncFunctionDef(self, node):
        node.body = [ast.Pass()]
        return node


def crunch_python(code: str) -> str:
    """Parse Python code and return an unparsed skeleton (signatures only)."""
    try:
        tree = ast.parse(code)
        transformer = PythonSkeletonizer()
        tree = transformer.visit(tree)
        ast.fix_missing_locations(tree)
        return ast.unparse(tree)
    except Exception as e:
        logger.warning(f"AST parsing failed, falling back to original code: {e}")
        return code


# ---------------------------------------------------------------------------
# JavaScript / TypeScript  (Regex-based — approximate)
# ---------------------------------------------------------------------------

def _crude_js_ts_skeleton(code: str) -> str:
    """
    Crude Regex-based skeletonizer for JS/TS.
    Keeps lines that likely define architecture, drops the rest.
    """
    lines = code.split("\n")
    skeleton_lines = []

    patterns = [
        re.compile(r"^\s*import\s+"),
        re.compile(r"^\s*export\s+"),
        re.compile(r"^\s*(?:export\s+)?class\s+\w+"),
        re.compile(r"^\s*(?:export\s+)?interface\s+\w+"),
        re.compile(r"^\s*(?:export\s+)?type\s+\w+"),
        re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+\w+"),
        re.compile(
            r"^\s*(?:public|private|protected)?\s*(?:async\s+)?\w+\s*\([^)]*\)\s*(?::\s*[\w\<\>\[\]]+)?\s*\{?"
        ),
        re.compile(r"^\s*const\s+\w+\s*=\s*(?:async\s*)?\([^)]*\)\s*=>"),
    ]

    for line in lines:
        for p in patterns:
            if p.match(line):
                clean_line = re.sub(r"\{\s*$", "{ /* stripped */ }", line)
                skeleton_lines.append(clean_line)
                break

    return "\n".join(skeleton_lines)


def _tree_sitter_js_ts_skeleton(code: str, ext: str) -> str:
    """
    Parse JS/TS using tree-sitter and strip method/function bodies.
    Requires `tree-sitter`, `tree-sitter-javascript`, `tree-sitter-typescript`.
    Falls back to _crude_js_ts_skeleton.
    """
    try:
        import tree_sitter
        if ext in ("ts", "tsx"):
            import tree_sitter_typescript
            lang_func = tree_sitter_typescript.language_tsx if ext == "tsx" else tree_sitter_typescript.language_typescript
            LANGUAGE = tree_sitter.Language(lang_func())
        else:
            import tree_sitter_javascript
            LANGUAGE = tree_sitter.Language(tree_sitter_javascript.language())
    except ImportError:
        logger.debug(f"tree-sitter packages missing, using fallback for .{ext}")
        return _crude_js_ts_skeleton(code)

    try:
        parser = tree_sitter.Parser(LANGUAGE)
        # tree_sitter in python < 0.22 vs 0.22 API change guard
        if hasattr(parser, "set_language"):
            parser.set_language(LANGUAGE) # Older API

        code_bytes = code.encode("utf8")
        tree = parser.parse(code_bytes)

        blocks = []
        def walk(node):
            if node.type == 'statement_block':
                # Check if it's a function-like body
                if node.parent and node.parent.type in (
                    'function_declaration', 'method_definition', 'arrow_function', 
                    'function', 'generator_function', 'generator_function_declaration'
                ):
                    blocks.append((node.start_byte, node.end_byte))
            for child in node.children:
                walk(child)
        
        walk(tree.root_node)

        # Replace from back to front to avoid shifting offsets
        blocks.sort(key=lambda x: x[0], reverse=True)
        mutable_bytes = bytearray(code_bytes)
        for start, end in blocks:
            # Replaces the insides of { ... }
            if mutable_bytes[start:start+1] == b'{' and mutable_bytes[end-1:end] == b'}':
                mutable_bytes[start+1:end-1] = b" /* stripped */ "
            
        return mutable_bytes.decode("utf8")
    except Exception as e:
        logger.warning(f"Tree-sitter parse failed, using fallback: {e}")
        return _crude_js_ts_skeleton(code)


# ---------------------------------------------------------------------------
# JSON  (stdlib — accurate)
# ---------------------------------------------------------------------------

def _reduce_value(obj, max_str_len: int, max_arr_items: int):
    """Recursively reduce a JSON-decoded value to its skeleton."""
    if isinstance(obj, dict):
        return {k: _reduce_value(v, max_str_len, max_arr_items) for k, v in obj.items()}
    if isinstance(obj, list):
        trimmed = obj[:max_arr_items]
        result = [_reduce_value(item, max_str_len, max_arr_items) for item in trimmed]
        omitted = len(obj) - max_arr_items
        if omitted > 0:
            result.append(f"...({omitted} more items)")
        return result
    if isinstance(obj, str) and len(obj) > max_str_len:
        return obj[:max_str_len] + f"...({len(obj) - max_str_len} more chars)"
    return obj


def _json_skeleton(text: str, max_str_len: int = 40, max_arr_items: int = 2) -> str:
    """
    Parse *text* as JSON and return a compacted skeleton.

    All keys are preserved (the schema is the valuable part).  String values
    longer than *max_str_len* chars are truncated.  Arrays are capped at
    *max_arr_items* entries with a count annotation for the remainder.
    """
    data = json.loads(text)
    reduced = _reduce_value(data, max_str_len, max_arr_items)
    return json.dumps(reduced, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# XML  (stdlib ElementTree — accurate for well-formed XML)
# ---------------------------------------------------------------------------

def _slim_element(elem: ET.Element, max_text: int = 60) -> ET.Element:
    """Return a copy of *elem* with truncated text content (attributes kept)."""
    slim = ET.Element(elem.tag, attrib=elem.attrib)
    if elem.text and elem.text.strip():
        raw = elem.text.strip()
        slim.text = raw[:max_text] + ("…" if len(raw) > max_text else "")
    for child in elem:
        slim.append(_slim_element(child, max_text))
    return slim


def _xml_skeleton(text: str, max_text: int = 60) -> str:
    """
    Parse *text* as XML and return a skeleton with truncated text nodes.

    Tag names, attributes, and tree structure are preserved.  Text content
    longer than *max_text* characters is truncated.
    """
    root = ET.fromstring(text)
    slim_root = _slim_element(root, max_text)
    return ET.tostring(slim_root, encoding="unicode")


# ---------------------------------------------------------------------------
# YAML  (optional — requires PyYAML; graceful fallback if not installed)
# ---------------------------------------------------------------------------

def _yaml_skeleton(text: str, max_str_len: int = 40, max_arr_items: int = 2) -> str:
    """
    Parse *text* as YAML and return a compacted skeleton.

    Requires PyYAML (``pip install pyyaml``).  If PyYAML is not installed,
    the original text is returned unchanged.
    """
    try:
        import yaml  # optional dependency — not in requirements.txt
    except ImportError:
        logger.debug("PyYAML not installed; returning YAML text unchanged.")
        return text

    try:
        data = yaml.safe_load(text)
        reduced = _reduce_value(data, max_str_len, max_arr_items)
        return yaml.dump(reduced, allow_unicode=True, default_flow_style=False, sort_keys=False)
    except Exception as e:
        logger.warning(f"YAML skeleton failed, returning original: {e}")
        return text


# ---------------------------------------------------------------------------
# Public dispatcher
# ---------------------------------------------------------------------------

def crunch_skeleton(text: str, filename: str = "code.py") -> str:
    """
    Generate a semantic skeleton of *text* based on the file extension in
    *filename*.

    Supported formats
    -----------------
    - ``.py`` / ``.pyw``    — AST-based Python skeleton (signatures only)
    - ``.js`` / ``.ts`` / ``.jsx`` / ``.tsx`` — Regex JS/TS skeleton
    - ``.json``             — JSON schema skeleton (keys + truncated values)
    - ``.xml``              — XML structure skeleton (tags + truncated text)
    - ``.yaml`` / ``.yml``  — YAML schema skeleton (requires PyYAML)
    - Everything else       — returned unchanged (graceful no-op)

    Returns the original text if parsing fails, so callers are always safe.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext in ("py", "pyw"):
        return crunch_python(text)

    if ext in ("js", "ts", "jsx", "tsx"):
        return _tree_sitter_js_ts_skeleton(text, ext)

    if ext == "json":
        try:
            return _json_skeleton(text)
        except Exception as e:
            logger.warning(f"JSON skeleton failed for {filename!r}: {e}")
            return text

    if ext == "xml":
        try:
            return _xml_skeleton(text)
        except Exception as e:
            logger.warning(f"XML skeleton failed for {filename!r}: {e}")
            return text

    if ext in ("yaml", "yml"):
        return _yaml_skeleton(text)

    # Unsupported extension — return unchanged
    return text
