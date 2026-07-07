"""Static artifact validation — never executes generated code."""
from app.infrastructure.validation.validators import MAX_FILE_BYTES, validate_content


class TestPython:
    def test_valid(self):
        result = validate_content("main.py", "def f():\n    return 1\n", "python")
        assert result == {"tool": "python-ast", "ok": True, "issues": []}

    def test_syntax_error_reported_with_line(self):
        result = validate_content("main.py", "def f(:\n", "python")
        assert result["ok"] is False
        assert "line 1" in result["issues"][0]

    def test_extension_fallback(self):
        assert validate_content("x.py", "1 +", "")["tool"] == "python-ast"


class TestJson:
    def test_valid(self):
        assert validate_content("package.json", '{"a": 1}', "json")["ok"]

    def test_invalid(self):
        result = validate_content("package.json", "{nope}", "json")
        assert result["ok"] is False


class TestYaml:
    def test_valid(self):
        assert validate_content("ci.yml", "a: 1\nb: [1, 2]\n", "yaml")["ok"]

    def test_invalid(self):
        result = validate_content("ci.yml", "a: [1,\nb: }{", "yaml")
        assert result["ok"] is False


class TestTypescript:
    def test_balanced_braces(self):
        assert validate_content("app.tsx", "function f() { return 1; }", "typescript")["ok"]

    def test_unbalanced_braces(self):
        result = validate_content("app.tsx", "function f() { return 1;", "typescript")
        assert result["ok"] is False
        assert "unbalanced braces" in result["issues"]


class TestGuards:
    def test_oversize_rejected(self):
        result = validate_content("big.txt", "x" * (MAX_FILE_BYTES + 1), "text")
        assert result["tool"] == "size"
        assert result["ok"] is False

    def test_binary_rejected(self):
        result = validate_content("bin.dat", "abc\x00def", "text")
        assert result["tool"] == "encoding"
        assert result["ok"] is False

    def test_unknown_language_passes(self):
        assert validate_content("notes.txt", "hello", "text")["ok"]
