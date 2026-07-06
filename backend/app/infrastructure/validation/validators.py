"""Static validation of generated artifacts. Never executes generated code."""
import ast
import json
from typing import Any

import yaml

MAX_FILE_BYTES = 1_000_000


def validate_content(path: str, content: str, language: str) -> dict[str, Any]:
    """Returns {tool, ok, issues[]}. Failures don't block storage; QA sees them."""
    issues: list[str] = []
    size = len(content.encode("utf-8", errors="replace"))
    if size > MAX_FILE_BYTES:
        return {"tool": "size", "ok": False, "issues": [f"file too large ({size} bytes)"]}
    if "\x00" in content:
        return {"tool": "encoding", "ok": False, "issues": ["binary content not allowed"]}

    lang = (language or "").lower()
    if lang == "python" or path.endswith(".py"):
        try:
            ast.parse(content)
            return {"tool": "python-ast", "ok": True, "issues": []}
        except SyntaxError as exc:
            return {
                "tool": "python-ast",
                "ok": False,
                "issues": [f"line {exc.lineno}: {exc.msg}"],
            }
    if lang == "json" or path.endswith(".json"):
        try:
            json.loads(content)
            return {"tool": "json", "ok": True, "issues": []}
        except json.JSONDecodeError as exc:
            return {"tool": "json", "ok": False, "issues": [str(exc)]}
    if lang in ("yaml", "yml") or path.endswith((".yaml", ".yml")):
        try:
            yaml.safe_load(content)
            return {"tool": "yaml", "ok": True, "issues": []}
        except yaml.YAMLError as exc:
            return {"tool": "yaml", "ok": False, "issues": [str(exc)[:300]]}
    if lang in ("typescript", "javascript", "tsx", "jsx"):
        # No TS compiler in-process; balance-check braces as a cheap sanity signal.
        if content.count("{") != content.count("}"):
            issues.append("unbalanced braces")
        return {"tool": "braces", "ok": not issues, "issues": issues}
    return {"tool": "none", "ok": True, "issues": []}
