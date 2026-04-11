"""
skeletonizer.py - Generates an AST-based "semantic skeleton" for code.

Strips all function bodies and keeps only class/function signatures.
Drastically reduces token count while preserving architectural context.
"""

import ast
import re
import logging

logger = logging.getLogger(__name__)

class PythonSkeletonizer(ast.NodeTransformer):
    """AST Transformer that strips function bodies."""
    
    def visit_FunctionDef(self, node):
        node.body = [ast.Pass()]
        return node
        
    def visit_AsyncFunctionDef(self, node):
        node.body = [ast.Pass()]
        return node


def crunch_python(code: str) -> str:
    """Parses Python code and unparses a skeletonised version."""
    try:
        tree = ast.parse(code)
        transformer = PythonSkeletonizer()
        tree = transformer.visit(tree)
        # Fix locations as we mutated the tree
        ast.fix_missing_locations(tree)
        return ast.unparse(tree)
    except Exception as e:
        logger.warning(f"AST parsing failed, falling back to original code: {e}")
        return code


def _crude_js_ts_skeleton(code: str) -> str:
    """
    Crude Regex-based skeletonizer for JS/TS.
    Keeps lines that likely define architecture, drops the rest.
    """
    lines = code.split('\n')
    skeleton_lines = []
    
    patterns = [
        re.compile(r'^\s*import\s+'),
        re.compile(r'^\s*export\s+'),
        re.compile(r'^\s*(?:export\s+)?class\s+\w+'),
        re.compile(r'^\s*(?:export\s+)?interface\s+\w+'),
        re.compile(r'^\s*(?:export\s+)?type\s+\w+'),
        re.compile(r'^\s*(?:export\s+)?(?:async\s+)?function\s+\w+'),
        re.compile(r'^\s*(?:public|private|protected)?\s*(?:async\s+)?\w+\s*\([^)]*\)\s*(?::\s*[\w\<\>\[\]]+)?\s*\{?'),
        re.compile(r'^\s*const\s+\w+\s*=\s*(?:async\s*)?\([^)]*\)\s*=>')
    ]
    
    for line in lines:
        for p in patterns:
            if p.match(line):
                # Clean up trailing braces to indicate stripped body
                clean_line = re.sub(r'\{\s*$', '{ /* stripped */ }', line)
                skeleton_lines.append(clean_line)
                break
                
    return "\n".join(skeleton_lines)


def crunch_skeleton(text: str, filename: str = "code.py") -> str:
    """
    Generates a semantic skeleton of the provided code depending on extension.
    Returns original code if language is unsupported or parse fails.
    """
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    
    if ext in ('py', 'pyw'):
        return crunch_python(text)
    elif ext in ('js', 'ts', 'jsx', 'tsx'):
        return _crude_js_ts_skeleton(text)
    
    # Unsupported language
    return text
