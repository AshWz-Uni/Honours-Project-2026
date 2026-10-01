"""Tests for JavaScript support (no Ollama required).

Covers: language normalisation/detection, JavaScript recursion analysis, the
language-aware guards and prompts, the state flow on a JavaScript problem, the
API ``language`` field, and the integrity of the JavaScript LeetCode set
(including, when Node.js is installed, proof that every intentional bug is real
and every reference fix works).

As with the other test files these check the agent's own logic, not Code
Llama's quality.
"""

import difflib
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.agent import prompts
from backend.agent import tutor_agent as ta
from backend.agent.conversation import Conversation, get_conversation
from backend.agent.language import (
    code_uses_recursion,
    detect_language,
    normalise_language,
    resolve_language,
)
from backend.main import app
from backend.tests.test_socratic_agent import FakeLLM, diag, install
from dataset.leetcode_eval import PROBLEMS, PROBLEMS_BY_LANGUAGE, get_problems
from dataset.leetcode_eval_js import JS_PROBLEMS
from dataset.leetcode_eval_js_checks import CHECKS, FIX_DIFF_LINES

client = TestClient(app)

JS_TWO_SUM = JS_PROBLEMS[0]["code"]
JS_FIB = JS_PROBLEMS[8]["code"]  # iterative
JS_DEPTH = JS_PROBLEMS[4]["code"]  # recursive
JS_QUEUE = JS_PROBLEMS[7]["code"]  # methods named push/pop that call this.stack.push/pop
JS_LIST = JS_PROBLEMS[5]["code"]


def js_turns(turns, problem, language=None):
    cid, replies = None, []
    for message in turns:
        reply, cid = ta.generate_tutor_response(
            code=problem["code"], question=message, conversation_id=cid,
            problem=problem["problem"], language=language,
        )
        replies.append(reply)
    return replies, get_conversation(cid)


# ------------------------------------------------------------ normalisation --

@pytest.mark.parametrize("value, expected", [
    ("python", "python"), ("Python", "python"), (" PY ", "python"), ("python3", "python"),
    ("javascript", "javascript"), ("JavaScript", "javascript"), ("js", "javascript"),
    ("node", "javascript"), ("Node.js", "javascript"),
    ("auto", None), ("", None), (None, None), ("cobol", None),
])
def test_normalise_language(value, expected):
    assert normalise_language(value) == expected


def test_resolve_language_precedence():
    js = "const x = (a) => a;"
    assert resolve_language("python", js) == "python"          # explicit choice wins
    assert resolve_language(None, js, "python") == "javascript"  # detection beats history
    assert resolve_language(None, "x = 1", "javascript") == "javascript"  # ambiguous -> history
    assert resolve_language(None, "x = 1", None) == "python"   # nothing known -> default


# ---------------------------------------------------------------- detection --

@pytest.mark.parametrize("lang", ["python", "javascript"])
def test_detection_is_correct_on_every_leetcode_problem(lang):
    for p in get_problems(lang):
        assert detect_language(p["code"]) == lang, (lang, p["name"])


@pytest.mark.parametrize("code, expected", [
    ("def add(a, b):\n    return a + b", "python"),
    ("class A:\n    def __init__(self):\n        self.x = None", "python"),
    ("for i in range(3):\n    print(i)", "python"),
    ("function add(a, b) {\n  return a + b;\n}", "javascript"),
    ("const add = (a, b) => a + b;", "javascript"),
    ("console.log('hi');", "javascript"),
    ("let total = 0;\nfor (const n of nums) { total += n; }", "javascript"),
    ("x = 1", None),          # valid in both languages: refuse to guess
    ("", None),
    ("   \n  ", None),
])
def test_detect_language_snippets(code, expected):
    assert detect_language(code) == expected


# ---------------------------------------------------------------- recursion --

@pytest.mark.parametrize("code", [
    "function f(n){ return n <= 1 ? 1 : n * f(n - 1); }",
    "var f = function(n){ return f(n - 1); };",
    "const f = (n) => { return f(n - 1); };",
    "const f = n => n <= 1 ? 1 : n * f(n - 1);",
    "class A { walk(n){ return this.walk(n - 1); } }",
    "A.prototype.walk = function(n){ return this.walk(n - 1); };",
    "function f(a = (1 + 2), n){ return f(a, n - 1); }",
    JS_DEPTH,
])
def test_javascript_recursion_is_found(code):
    assert code_uses_recursion(code, "javascript")


@pytest.mark.parametrize("code", [
    "Q.prototype.pop = function(){ return this.stack.pop(); };",   # different object
    "function push(x){ arr.push(x); }",
    "function f(n){ return 'f(n - 1)'; }",                          # in a string
    "function f(n){ // f(n - 1)\n return n; }",                     # in a comment
    "function g(x){ if (x) { while (x) { x--; } } return x; }",     # control flow is not a method
    JS_FIB, JS_QUEUE, JS_TWO_SUM, JS_LIST,
])
def test_javascript_non_recursion_is_not_flagged(code):
    assert not code_uses_recursion(code, "javascript")


def test_recursion_dispatch_uses_detection_when_language_omitted():
    assert code_uses_recursion(JS_DEPTH)                       # detected as JS
    assert code_uses_recursion(PROBLEMS[4]["code"])            # detected as Python
    assert not code_uses_recursion(JS_FIB)


def test_off_topic_recursion_is_blocked_for_iterative_javascript():
    conv = Conversation(code=JS_FIB, problem=JS_PROBLEMS[8]["problem"], language="javascript")
    assert ta._off_topic_recursion("What is the base case of your recursion?", conv, "my base case is wrong")
    tree = Conversation(code=JS_DEPTH, language="javascript")
    assert not ta._off_topic_recursion("What does your recursion do for a leaf?", tree, "")
    queue = Conversation(code=JS_QUEUE, language="javascript")
    assert ta._off_topic_recursion("Why does pop call itself here?", queue, "")


# ------------------------------------------------------------------- guards --

@pytest.mark.parametrize("text", [
    "You should push num onto seen. What happens then?",
    "You could also splice the array here. Does that help?",
    "Try using a Map to store each value. What lookups get cheaper?",
    "Consider declaring a temporary variable first. What would it hold?",
    "Try pushing the value inside the loop. What changes?",
    "You need to use === instead. Why?",
    "Using Math.floor there fixes it. Can you see why?",
    "The answer is to return [i, j].",
])
def test_javascript_solution_leaks_are_detected(text):
    assert ta._contains_solution_leak(text, "javascript"), text


@pytest.mark.parametrize("text", [
    "What value does `seen` hold after the first iteration?",
    "Could you trace `nums = [2, 7, 11, 15]` and tell me which branch runs?",
    "What does `return [i]` give back, and does it match the expected shape?",
    "Which value is `undefined` when the loop ends?",
    "How many times does the `while` loop run for an array with one element?",
])
def test_legitimate_javascript_questions_are_not_leaks(text):
    assert not ta._contains_solution_leak(text, "javascript"), text


def test_javascript_only_leak_patterns_do_not_change_python_behaviour():
    text = "You could also splice the array here."
    assert ta._contains_solution_leak(text, "javascript")
    assert not ta._contains_solution_leak(text, "python")
    assert not ta._contains_solution_leak(text)


def test_fenced_javascript_block_is_a_leak():
    assert ta._contains_solution_leak("Here you go:\n```javascript\nreturn [i, j];\n```", "javascript")


def test_new_javascript_code_is_flagged_but_quoting_student_code_is_not():
    code = JS_LIST
    assert ta._introduces_new_code("Try `const next = current.next;` first.", code, "javascript")
    assert ta._introduces_new_code("What about `return [i, j];`?", JS_TWO_SUM, "javascript")
    assert ta._introduces_new_code("Would `seen.push(num)` help?", JS_PROBLEMS[6]["code"], "javascript")
    assert ta._introduces_new_code("What if `x => x + 1` ran?", JS_TWO_SUM, "javascript")
    assert ta._introduces_new_code("What if `total += num` ran?", JS_TWO_SUM, "javascript")
    assert not ta._introduces_new_code("What does `current.next = previous` do to the list?", code, "javascript")
    assert not ta._introduces_new_code("Trace `nums = [2, 7, 11, 15]` with `target = 9`.", JS_TWO_SUM, "javascript")
    assert not ta._introduces_new_code("Does `nums[i] + nums[j] === target` ever hold?", JS_TWO_SUM, "javascript")
    # Strict-equality comparisons in a suggested test input are not assignments.
    assert not ta._introduces_new_code("Is `i === 0` true on the first pass?", JS_TWO_SUM + "\ni === 0", "javascript")


def test_python_new_code_detection_is_unchanged_by_the_language_parameter():
    code = PROBLEMS[5]["code"]
    assert ta._introduces_new_code("Try `next_node = current.next` first.", code)
    assert ta._introduces_new_code("Try `next_node = current.next` first.", code, "python")
    # `const` is meaningless in Python, so it must not be treated as a keyword there.
    assert not ta._introduces_new_code("What is `const`?", code, "python")
    assert ta._introduces_new_code("What is `const`?", code, "javascript")


# ------------------------------------------------------- student heuristics --

@pytest.mark.parametrize("problem", JS_PROBLEMS, ids=lambda p: p["name"])
def test_heuristics_recognise_each_javascript_first_response(problem):
    result = ta._infer_explicit_student_progress(problem["code"], problem["first_response"])
    assert result["problem_identified"], problem["first_response"]


@pytest.mark.parametrize("message", [
    "I have no idea. Do I need to return the total to the caller?",
    "Something is wrong with my result.",
    "It doesn't work, can you help me?",
    "I'm not sure why it logs undefined, maybe I should add a console.log to see it",
    "Both i and j are used in the loop, so why is the answer wrong?",
])
def test_heuristics_do_not_treat_vague_javascript_messages_as_progress(message):
    result = ta._infer_explicit_student_progress(JS_TWO_SUM, message)
    assert not result["problem_identified"], message
    assert not result["solution_proposed"], message
    assert not result["solution_correct"]


@pytest.mark.parametrize("message", [
    "I should push num onto seen at the end of each loop iteration.",
    "I would declare a temporary variable before changing the pointer.",
    "I think I need to assign the saved node back before moving on.",
])
def test_heuristics_recognise_javascript_style_proposals(message):
    assert ta._infer_explicit_student_progress(JS_TWO_SUM, message)["solution_proposed"], message


def test_debug_only_javascript_plan_is_not_a_proposal():
    result = ta._infer_explicit_student_progress(
        JS_TWO_SUM, "I should add a console.log inside the loop to see what happens.")
    assert not result["solution_proposed"]


@pytest.mark.parametrize("py, js", list(zip(PROBLEMS, JS_PROBLEMS)), ids=lambda p: p["name"] if isinstance(p, dict) else None)
def test_heuristics_treat_javascript_fix_and_validation_like_python(py, js):
    """The heuristics are a conservative safety net (they miss some phrasings and the LLM
    diagnostic covers the rest), so the requirement is *parity*: the JavaScript wording must
    never be recognised less often than the Python wording it mirrors, and they never assert
    correctness."""
    for field, flag in (("fix", "solution_proposed"), ("validation", "solution_validated")):
        py_result = ta._infer_explicit_student_progress(py["code"], py[field])
        js_result = ta._infer_explicit_student_progress(js["code"], js[field])
        assert js_result[flag] == py_result[flag], (js["name"], field)
        assert not js_result["solution_correct"]


# ------------------------------------------------------------------ prompts --

def _socratic(language, **kw):
    return prompts.build_socratic_prompt(
        code="x", question="q", history="h", diagnostic="{}", stage="trace",
        question_number=1, language=language, **kw)


def test_javascript_prompts_use_javascript_fence_and_language_note():
    for builder in (
        lambda: _socratic("javascript"),
        lambda: prompts.build_diagnostic_prompt("x", "q", "h", language="javascript"),
        lambda: prompts.build_conclusion_prompt("x", "q", "h", "{}", language="javascript"),
    ):
        text = builder()
        assert "```javascript" in text and "```python" not in text
        assert "JavaScript" in text


def test_python_prompts_are_unchanged_by_the_language_layer():
    text = _socratic("python")
    assert "```python" in text and "LANGUAGE:" not in text
    assert _socratic(None) == _socratic("python")  # default is Python
    diagnostic = prompts.build_diagnostic_prompt("x", "q", "h")
    assert "```python" in diagnostic and "LANGUAGE NOTE" not in diagnostic


def test_javascript_note_forbids_python_terms_and_fixes():
    note = prompts.LANGUAGE_NOTES["javascript"]
    assert "Never use Python" in note and "without naming the fix" in note
    assert "===" in note and "undefined" in note


# --------------------------------------------------------------- state flow --

def test_javascript_language_reaches_every_llm_prompt(monkeypatch):
    llm = FakeLLM([diag()], ["Which value does i hold on the first pass through the outer loop?"])
    seen = []
    original = llm.__call__

    def spy(prompt, *a, **k):
        seen.append(prompt)
        return original(prompt, *a, **k)

    install(monkeypatch, spy)
    _, conv = js_turns(["The result is wrong for some inputs."], JS_PROBLEMS[0], language="javascript")
    assert conv.language == "javascript"
    assert len(seen) == 2  # diagnostic pass + tutor pass
    assert all("```javascript" in p for p in seen)


def test_language_is_autodetected_when_not_supplied(monkeypatch):
    install(monkeypatch, FakeLLM([diag()], ["Which value does i hold on the first pass?"]))
    _, conv = js_turns(["The result is wrong for some inputs."], JS_PROBLEMS[0])
    assert conv.language == "javascript"
    install(monkeypatch, FakeLLM([diag()], ["Which value does i hold on the first pass?"]))
    _, conv = js_turns(["The result is wrong for some inputs."], PROBLEMS[0])
    assert conv.language == "python"


def test_explicit_language_overrides_detection(monkeypatch):
    install(monkeypatch, FakeLLM([diag()], ["Which value does i hold on the first pass?"]))
    _, conv = js_turns(["The result is wrong."], JS_PROBLEMS[0], language="python")
    assert conv.language == "python"


def test_language_follows_the_code_when_the_student_switches(monkeypatch):
    install(monkeypatch, FakeLLM([diag(), diag()], ["Which value does i hold at the start?",
                                                    "Which branch runs for the input 15?"]))
    reply, cid = ta.generate_tutor_response(PROBLEMS[0]["code"], "It is wrong.", None)
    assert get_conversation(cid).language == "python"
    ta.generate_tutor_response(JS_TWO_SUM, "Now it is in JavaScript and still wrong.", cid)
    assert get_conversation(cid).language == "javascript"


def test_javascript_recursion_guard_runs_inside_the_pipeline(monkeypatch):
    """Iterative JS code + a reply about recursion -> rejected twice -> fallback."""
    bad = "What is the base case of your recursion here?"
    llm = FakeLLM([diag()], [bad, bad])
    install(monkeypatch, llm)
    (reply,), conv = js_turns(["Something is wrong with my result."], JS_PROBLEMS[8], language="javascript")
    assert len(llm.prompts) == 2 and "Do NOT mention recursion" in llm.prompts[1]
    assert "recursion" not in reply.lower()


def test_javascript_leak_triggers_retry_then_fallback(monkeypatch):
    leak = "You could also splice the array here. What do you think?"
    llm = FakeLLM([diag()], [leak, leak])
    install(monkeypatch, llm)
    (reply,), conv = js_turns(["It gives the wrong output and I do not know why."], JS_PROBLEMS[0], language="javascript")
    assert len(llm.prompts) == 2 and "Do NOT tell the student" in llm.prompts[1]
    assert reply in ta._FALLBACK_QUESTIONS["clarify"]


def test_full_javascript_flow_matches_the_python_flow(monkeypatch):
    p = JS_PROBLEMS[0]
    diagnostics = [
        diag(identified=True, proposed=True, correct=True),
        diag(identified=True, proposed=True, correct=True),
        diag(identified=True, proposed=True, correct=True, validated=True),
        diag(True, True, True, True),
        diag(True, True, True, True),
        diag(True, True, True, True),
    ]
    replies = [
        "That is a promising observation. How could you test your idea using [2, 7, 11, 15] with a target of 9?",
        "Nice. Pick a different small input and trace your change line by line; what result do you get?",
        "In your own words, why does your change make the earlier failing case behave correctly?",
        "Which edge case, such as a single repeated value, would you test next, and what should come back?",
        "Could your change affect any input that already worked?",
    ]
    install(monkeypatch, FakeLLM(diagnostics, replies))
    cid, stages, out = None, [], []
    script = [p["first_response"], p["fix"], p["validation"], *p["reflections"]]
    for text in script:
        reply, cid = ta.generate_tutor_response(p["code"], text, cid, problem=p["problem"], language="javascript")
        conv = get_conversation(cid)
        stages.append(conv.stage_name)
        out.append(reply)
        if conv.concluded:
            break
    assert stages == ["validate", "validate", "consolidate", "consolidate", "consolidate", "conclude"]
    assert conv.question_count == 5 and conv.concluded and conv.language == "javascript"
    assert "?" not in out[-1]


def test_learning_state_reports_language(monkeypatch):
    install(monkeypatch, FakeLLM([diag()], ["Which value does i hold on the first pass?"]))
    _, conv = js_turns(["It is wrong."], JS_PROBLEMS[0], language="js")
    assert ta.learning_state(conv)["language"] == "javascript"


def test_all_fallback_questions_pass_every_guard_for_javascript():
    conv = Conversation(code=JS_TWO_SUM, language="javascript")
    for stage, questions in ta._FALLBACK_QUESTIONS.items():
        conv.problem_identified = stage not in ta.DIAGNOSIS_STAGES
        for q in questions:
            assert ta._response_problem(q, conv, "some student message") is None, (stage, q)
    for q in ta._CONSOLIDATION_FALLBACKS:
        conv.problem_identified = True
        assert ta._response_problem(q, conv, "x") is None, q


# ---------------------------------------------------------------------- API --

@pytest.fixture
def fake_llm(monkeypatch):
    def fake(prompt, *args, **kwargs):
        if "private diagnostic component" in prompt.lower():
            return diag()
        return f"Which value does a hold at step {len(prompt) % 89}?"

    monkeypatch.setattr(ta, "ask_llm", fake)


def test_api_accepts_language_and_echoes_it(fake_llm):
    body = {"code": JS_TWO_SUM, "question": "It is wrong", "language": "javascript"}
    first = client.post("/chat", json=body).json()
    assert first["language"] == "javascript"
    second = client.post("/chat", json={**body, "conversation_id": first["conversation_id"], "language": "auto"}).json()
    assert second["conversation_id"] == first["conversation_id"]
    assert second["language"] == "javascript"  # auto -> detected from the code


@pytest.mark.parametrize("value", ["js", "JS", "Node", "JavaScript"])
def test_api_normalises_language_aliases(fake_llm, value):
    r = client.post("/chat", json={"code": "x", "question": "q", "language": value})
    assert r.status_code == 200 and r.json()["language"] == "javascript"


def test_api_autodetects_without_a_language_field(fake_llm):
    assert client.post("/chat", json={"code": JS_TWO_SUM, "question": "wrong"}).json()["language"] == "javascript"
    assert client.post("/chat", json={"code": PROBLEMS[0]["code"], "question": "wrong"}).json()["language"] == "python"


def test_api_rejects_unsupported_language(fake_llm):
    r = client.post("/chat", json={"code": "x", "question": "q", "language": "cobol"})
    assert r.status_code == 422


def test_state_endpoint_includes_language(fake_llm, monkeypatch):
    cid = client.post("/chat", json={"code": JS_TWO_SUM, "question": "wrong"}).json()["conversation_id"]
    monkeypatch.setenv("TUTOR_DEBUG", "1")
    assert client.get(f"/chat/{cid}/state").json()["language"] == "javascript"


# ------------------------------------------------------------------ dataset --

def test_dataset_registry():
    assert set(PROBLEMS_BY_LANGUAGE) == {"python", "javascript"}
    assert get_problems("python") is PROBLEMS and get_problems("javascript") is JS_PROBLEMS
    with pytest.raises(ValueError):
        get_problems("ruby")


def test_javascript_set_mirrors_the_python_set():
    assert len(JS_PROBLEMS) == len(PROBLEMS) == 10
    for py, js in zip(PROBLEMS, JS_PROBLEMS):
        assert js["id"] == py["id"] and js["name"] == py["name"], (py["name"], js["name"])
        assert set(js) == set(py), js["name"]  # identical schema
        assert py["language"] == "python" and js["language"] == "javascript"
        assert len(js["reflections"]) == len(py["reflections"]) == 3
        for field in ("code", "problem", "bug", "first_response", "fix", "validation"):
            assert js[field].strip(), (js["name"], field)


def test_javascript_code_contains_no_python_leftovers():
    import re
    banned = re.compile(r"\bdef \w+\(|\bNone\b|\bTrue\b|\bFalse\b|\belif\b|\bself\b|\blen\(|\brange\(|\.append\(|//\s*2\b")
    for js in JS_PROBLEMS:
        assert not banned.search(js["code"]), js["name"]
        for field in ("problem", "first_response", "fix", "validation", *js["reflections"]):
            text = js[field] if field in js else field
            assert not re.search(r"\bNone\b|\bTrue\b|\bFalse\b|\bappend\b", text), (js["name"], text)


def test_every_javascript_problem_has_a_check():
    assert set(CHECKS) == {p["id"] for p in JS_PROBLEMS}
    for c in CHECKS.values():
        assert c["fixed_code"].strip() and c["check"].strip()


def _changed_lines(before: str, after: str) -> int:
    a = [line.strip() for line in before.splitlines() if line.strip()]
    b = [line.strip() for line in after.splitlines() if line.strip()]
    return sum(
        1 for line in difflib.unified_diff(a, b, lineterm="", n=0)
        if line[:1] in "+-" and line[:3] not in ("+++", "---")
    )


@pytest.mark.parametrize("problem", JS_PROBLEMS, ids=lambda p: p["name"])
def test_javascript_fix_is_exactly_the_documented_size(problem):
    """Tripwire for the 'ONE intentional bug' rule: a stray second bug enlarges the diff."""
    actual = _changed_lines(problem["code"], CHECKS[problem["id"]]["fixed_code"])
    assert actual == FIX_DIFF_LINES[problem["id"]], (problem["name"], actual)


NODE = shutil.which("node")


def _run_check(code: str, check: str) -> str:
    script = (
        code + "\n;const __ok = (function () { try {" + check
        + "} catch (e) { return false; } })(); process.stdout.write(String(__ok));"
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "case.js"
        path.write_text(script, encoding="utf-8")
        result = subprocess.run([NODE, str(path)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


@pytest.mark.skipif(NODE is None, reason="Node.js is not installed")
@pytest.mark.parametrize("problem", JS_PROBLEMS, ids=lambda p: p["name"])
def test_javascript_bug_is_real_and_reference_fix_works(problem):
    check = CHECKS[problem["id"]]
    assert _run_check(problem["code"], check["check"]) == "false", "buggy code unexpectedly passes"
    assert _run_check(check["fixed_code"], check["check"]) == "true", "reference fix fails its own check"


@pytest.mark.skipif(NODE is None, reason="Node.js is not installed")
@pytest.mark.parametrize("problem", JS_PROBLEMS, ids=lambda p: p["name"])
def test_javascript_code_is_syntactically_valid(problem):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "case.js"
        path.write_text(problem["code"], encoding="utf-8")
        result = subprocess.run([NODE, "--check", str(path)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
