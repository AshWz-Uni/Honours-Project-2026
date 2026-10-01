"""Language support for the tutoring agent (Python and JavaScript).

Everything that depends on *which* language the student is writing lives here,
so the rest of the agent stays language-neutral:

* ``normalise_language`` - map user input ("js", "Python3", "auto") to a name.
* ``detect_language``    - score a snippet when the student does not say.
* ``code_uses_recursion``- does any function in the code call itself?

Python recursion is found with the standard-library ``ast`` module. JavaScript
has no parser in the standard library, and adding a Node dependency to a Python
backend is heavy, so JavaScript is analysed with a small scanner: strip
comments and strings, locate function definitions, match braces, and look for a
self-call inside each body. It handles the forms that appear in student code
and on LeetCode (declarations, ``var f = function``, arrow functions, class and
object methods, ``X.prototype.f = function``).
"""

from __future__ import annotations

import ast
import re

PYTHON = "python"
JAVASCRIPT = "javascript"
SUPPORTED_LANGUAGES = (PYTHON, JAVASCRIPT)
DEFAULT_LANGUAGE = PYTHON

LANGUAGE_LABELS = {PYTHON: "Python", JAVASCRIPT: "JavaScript"}

_ALIASES = {
    "python": PYTHON,
    "py": PYTHON,
    "python3": PYTHON,
    "javascript": JAVASCRIPT,
    "js": JAVASCRIPT,
    "node": JAVASCRIPT,
    "nodejs": JAVASCRIPT,
    "node.js": JAVASCRIPT,
    "ecmascript": JAVASCRIPT,
}


def normalise_language(value: str | None) -> str | None:
    """Return ``"python"``, ``"javascript"`` or ``None`` (unspecified / auto)."""
    if not value:
        return None
    return _ALIASES.get(value.strip().lower())


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #

_PY_SIGNALS = (
    (r"^\s*def\s+\w+\s*\(.*\)\s*(?:->\s*[^:]+)?:\s*$", 3),
    (r"^\s*class\s+\w+\s*(?:\([^)]*\))?\s*:\s*$", 3),
    (r"^\s*(?:elif|except|finally)\b.*:\s*$", 3),
    (r"^\s*(?:if|for|while|else|try|with)\b[^{};]*:\s*$", 2),
    (r"\bself\.\w+", 2),
    (r"\b(?:None|True|False)\b", 2),
    (r"\brange\s*\(", 1),
    (r"\blen\s*\(", 1),
    (r"^\s*print\s*\(", 1),
    (r"^\s*from\s+[\w.]+\s+import\b", 2),
    (r"^\s*import\s+[\w.]+\s*$", 2),
    (r"\bdef\s+__\w+__\b", 3),
    (r"^\s*#(?!!)", 1),
    (r"\bis\s+not\s+None\b|\bnot\s+in\b|\bis\s+None\b", 2),
)

_JS_SIGNALS = (
    (r"\b(?:const|let|var)\s+[\w$]+", 3),
    (r"=>", 3),
    (r"\bfunction\b\s*[\w$]*\s*\(", 3),
    (r"\bconsole\.\w+\s*\(", 3),
    (r"[!=]==", 3),
    (r"\bnull\b|\bundefined\b|\bNaN\b", 2),
    (r"\.prototype\.", 3),
    (r"\bmodule\.exports\b|\brequire\s*\(", 3),
    (r"^\s*(?:export|import)\b.*(?:from\s+['\"]|default|\{)", 3),
    (r"\.length\b", 1),
    (r"\b(?:Math|Object|Array|JSON|Number|Promise)\.\w+", 2),
    (r"\bnew\s+(?:Map|Set|Array|Promise|Error|Object)\b", 2),
    (r"\b(?:async|await)\b", 2),
    (r"\bthis\.\w+", 1),
    (r"[;{}]\s*$", 1),
    (r"^\s*//", 1),
    (r"\bfor\s*\(\s*(?:const|let|var)\b", 3),
    (r"\b(?:if|while|for|switch)\s*\(.*\)\s*\{?\s*$", 1),
    (r"\bpush\s*\(|\.(?:map|filter|reduce|forEach|includes|slice|splice)\s*\(", 1),
)


def _score(code: str, signals) -> int:
    total = 0
    for pattern, weight in signals:
        if weight and re.search(pattern, code, re.MULTILINE):
            total += weight
    return total


def detect_language(code: str) -> str | None:
    """Best-effort guess: ``"python"``, ``"javascript"`` or ``None`` if unclear.

    Returns ``None`` rather than guessing when the evidence is thin or evenly
    split, so the caller can fall back to what the conversation already knows.
    """
    if not code or not code.strip():
        return None

    py = _score(code, _PY_SIGNALS)
    js = _score(code, _JS_SIGNALS)

    # Valid Python syntax is strong evidence *for* Python only when the code has some structure; a bare ``x = 1`` parses in both languages.
    try:
        ast.parse(code)
        if py > 0:
            py += 3
    except (SyntaxError, ValueError):
        js += 1 if js else 0

    if py == js or max(py, js) < 2:
        return None
    return PYTHON if py > js else JAVASCRIPT


def resolve_language(
    explicit: str | None, code: str, previous: str | None = None
) -> str:
    """Pick the language for a turn: explicit choice > detection > previous > default."""
    return (
        normalise_language(explicit)
        or detect_language(code)
        or normalise_language(previous)
        or DEFAULT_LANGUAGE
    )


# --------------------------------------------------------------------------- #
# Recursion: Python (ast)
# --------------------------------------------------------------------------- #

def _python_uses_recursion(code: str) -> bool:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id == fn.name:
                return True
            if (
                isinstance(func, ast.Attribute)
                and func.attr == fn.name
                and isinstance(func.value, ast.Name)
                and func.value.id in ("self", "cls")
            ):
                return True
    return False


# --------------------------------------------------------------------------- #
# Recursion: JavaScript (scanner)
# --------------------------------------------------------------------------- #

def _strip_js_comments_and_strings(code: str) -> str:
    """Blank out comments and string/template contents, keeping length and newlines.

    Braces and identifiers inside strings or comments must not confuse brace
    matching or call detection. Template-literal ``${...}`` expressions are
    blanked too, which loses a self-call inside a template; that is rare enough
    to accept.
    """
    out: list[str] = []
    i, n = 0, len(code)
    while i < n:
        ch = code[i]
        nxt = code[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            while i < n and code[i] != "\n":
                out.append(" ")
                i += 1
        elif ch == "/" and nxt == "*":
            out.append("  ")
            i += 2
            while i < n and not (code[i] == "*" and i + 1 < n and code[i + 1] == "/"):
                out.append("\n" if code[i] == "\n" else " ")
                i += 1
            out.append("  ")
            i += 2
        elif ch in "'\"`":
            quote = ch
            out.append(quote)
            i += 1
            while i < n and code[i] != quote:
                if code[i] == "\\" and i + 1 < n:
                    out.append("  ")
                    i += 2
                    continue
                if code[i] == "\n" and quote != "`":
                    break  # unterminated string: stop at end of line
                out.append("\n" if code[i] == "\n" else " ")
                i += 1
            if i < n and code[i] == quote:
                out.append(quote)
                i += 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


_JS_KEYWORDS_NOT_METHODS = frozenset(
    "if for while switch catch function return typeof new delete void await yield "
    "else do try with super import export throw case in of".split()
)

_IDENT = r"[A-Za-z_$][\w$]*"
_PARAMS = r"\([^()]*(?:\([^()]*\)[^()]*)*\)"  # one level of nested parens (default args)

# Each pattern captures the function's *name* in group 1 and ends right after the opening ``{`` (block bodies) or ``=>`` (expression-bodied arrows).
_JS_DEFINITIONS = (
    # function name(...) {
    re.compile(rf"\bfunction\s*\*?\s*({_IDENT})\s*{_PARAMS}\s*\{{"),
    # var|let|const name = function (...) {      (optionally async / named)
    re.compile(
        rf"\b(?:var|let|const)\s+({_IDENT})\s*=\s*(?:async\s+)?function\s*\*?\s*(?:{_IDENT})?\s*{_PARAMS}\s*\{{"
    ),
    # obj.prototype.name = function (...) {   /   exports.name = function
    re.compile(
        rf"(?:{_IDENT}\s*\.\s*)+({_IDENT})\s*=\s*(?:async\s+)?function\s*\*?\s*(?:{_IDENT})?\s*{_PARAMS}\s*\{{"
    ),
    # name: function (...) {   (object literal)
    re.compile(rf"\b({_IDENT})\s*:\s*(?:async\s+)?function\s*\*?\s*(?:{_IDENT})?\s*{_PARAMS}\s*\{{"),
    # var|let|const name = (...) => {   /   name = x => {   (block-bodied arrow)
    re.compile(
        rf"\b(?:var|let|const)\s+({_IDENT})\s*=\s*(?:async\s+)?(?:{_PARAMS}|{_IDENT})\s*=>\s*\{{"
    ),
    # class / object method:  name(...) {   with optional async/static/get/set
    re.compile(
        rf"(?:^|[\s;{{}},])(?:(?:async|static|get|set)\s+)*\*?\s*({_IDENT})\s*{_PARAMS}\s*\{{"
    ),
)

# Expression-bodied arrows: ``const f = n => n <= 1 ? 1 : n * f(n - 1);``
_JS_EXPRESSION_ARROW = re.compile(
    rf"\b(?:var|let|const)\s+({_IDENT})\s*=\s*(?:async\s+)?(?:{_PARAMS}|{_IDENT})\s*=>\s*(?!\s*\{{)"
)


def _matching_brace(code: str, open_index: int) -> int:
    depth = 0
    for i in range(open_index, len(code)):
        if code[i] == "{":
            depth += 1
        elif code[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return len(code)


def _expression_end(code: str, start: int) -> int:
    """End of an expression-bodied arrow: next top-level ``;`` or newline."""
    depth = 0
    for i in range(start, len(code)):
        ch = code[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth < 0:
                return i
        elif depth == 0 and ch in ";\n":
            return i
    return len(code)


def _js_self_call(name: str, body: str) -> bool:
    """Bare ``name(...)`` or ``this.name(...)``; NOT ``other.name(...)``.

    ``this.stack.pop()`` inside a method called ``pop`` is a call on a
    different object, so it must not count as recursion.
    """
    escaped = re.escape(name)
    bare = re.search(rf"(?<![\w$.]){escaped}\s*\(", body)
    on_this = re.search(rf"\bthis\s*\.\s*{escaped}\s*\(", body)
    return bool(bare or on_this)


def _javascript_uses_recursion(code: str) -> bool:
    clean = _strip_js_comments_and_strings(code)

    for pattern in _JS_DEFINITIONS:
        for match in pattern.finditer(clean):
            name = match.group(1)
            if name in _JS_KEYWORDS_NOT_METHODS:
                continue
            open_index = match.end() - 1
            close_index = _matching_brace(clean, open_index)
            if _js_self_call(name, clean[open_index + 1 : close_index]):
                return True

    for match in _JS_EXPRESSION_ARROW.finditer(clean):
        body = clean[match.end() : _expression_end(clean, match.end())]
        if _js_self_call(match.group(1), body):
            return True
    return False


# --------------------------------------------------------------------------- #

def code_uses_recursion(code: str, language: str | None = None) -> bool:
    """Does any function in ``code`` call itself?"""
    lang = normalise_language(language) or detect_language(code) or DEFAULT_LANGUAGE
    if lang == JAVASCRIPT:
        return _javascript_uses_recursion(code)
    return _python_uses_recursion(code)
