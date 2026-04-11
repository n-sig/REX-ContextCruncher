import pytest
import sys
from pathlib import Path

# Add src to python path for testing
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from contextcruncher.skeletonizer import crunch_skeleton

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
    assert "print(\"Hello\")" not in skeleton
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
