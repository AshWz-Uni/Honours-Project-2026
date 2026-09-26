"""Deterministic tests for the Socratic tutor (no Ollama required).

The LLM is replaced by a scripted fake, so these tests verify the agent's own
logic: state machine, guards and heuristics, not Code Llama's quality.
"""

import re

import pytest

from backend.agent import tutor_agent as ta
from backend.agent.conversation import Conversation, add_message, get_conversation
from dataset.leetcode_eval import PROBLEMS

TWO_SUM = PROBLEMS[0]["code"]


# ----------------------------------------------------------------- helpers --

def diag(identified=False, proposed=False, correct=False, validated=False):
    return (
        '{"problem_identified": %s, "solution_proposed": %s, "solution_correct": %s, '
        '"solution_validated": %s, "student_evidence": "x", "next_step": "diagnose"}'
        % tuple(str(v).lower() for v in (identified, proposed, correct, validated))
    )


class FakeLLM:
    """Diagnostic JSON and tutor replies come from separate scripted queues."""

    def __init__(self, diagnostics, replies, conclusion="You found it, fixed it, and checked it. Run one more edge case."):
        self.diagnostics = iter(diagnostics)
        self.replies = iter(replies)
        self.conclusion = conclusion
        self.prompts = []

    def __call__(self, prompt, *args, **kwargs):
        low = prompt.lower()
        if "private diagnostic component" in low:
            return next(self.diagnostics)
        if "concluding a socratic" in low:
            return self.conclusion
        self.prompts.append(prompt)
        return next(self.replies)


def install(monkeypatch, llm):
    monkeypatch.setattr(ta, "ask_llm", llm)


def run_turns(turns, problem=None, code=TWO_SUM):
    cid = None
    out = []
    for message in turns:
        reply, cid = ta.generate_tutor_response(code=code, question=message, conversation_id=cid, problem=problem)
        out.append(reply)
    return out, get_conversation(cid)


# ------------------------------------------------------------ leak / guards --

@pytest.mark.parametrize("text", [
    "The answer is to change line 4.",
    "You should replace x with y.",
    "You might want to use a dictionary here. What lookups would that make cheaper?",
    "Try using a second stack. What order do the items come out in?",
    "You should use a hash map: store each value's index.",
    "A fix would be to check 15 first. Does that sound right?",
])
def test_solution_leaks_are_detected(text):
    assert ta._contains_solution_leak(text)


@pytest.mark.parametrize("text", [
    "What value does x have here?",
    "Could you trace i = 15 through the branches and tell me which one runs?",
    "You could trace n = 3 by hand. What do prev and curr hold after the loop?",
    "Consider what `return [i]` gives back. Does it match the expected shape?",
])
def test_legitimate_questions_are_not_flagged_as_leaks(text):
    assert not ta._contains_solution_leak(text)


def test_line_by_line_is_not_a_leak():
    text = "Pick a small input and trace your change line by line. What result do you get?"
    assert not ta._contains_solution_leak(text)


def test_new_code_is_flagged_but_quoting_student_code_and_inputs_is_not():
    code = PROBLEMS[5]["code"]  # reverse linked list
    assert ta._introduces_new_code("Try `next_node = current.next` first.", code)
    assert ta._introduces_new_code("What about `return [i, j]`?", TWO_SUM)
    assert not ta._introduces_new_code("What does `current.next = previous` do to the list?", code)
    assert not ta._introduces_new_code("Trace `nums = [2, 7, 11, 15]` with `target = 9`.", TWO_SUM)


def test_naming_the_cause_is_only_checked_by_pattern():
    assert ta._names_the_cause("The problem is that you never store the values.")
    assert not ta._names_the_cause("What happens to seen after each iteration?")


def test_repetition_question_detection():
    assert ta._is_repetition_question("Can you repeat the question?", "How can I fix this testcase?")
    assert not ta._is_repetition_question(
        "What value does n have when the failing case reaches this statement?",
        "How can I fix this testcase where n = 0?",
    )


def test_near_duplicate_tutor_question_is_detected():
    conv = Conversation()
    add_message(conv, "assistant", "What does your function return for the input [2, 7, 11, 15]?")
    assert ta._repeats_previous_tutor_question("What does your function return for the input [2, 7, 11, 15]?", conv)
    assert not ta._repeats_previous_tutor_question("Which branch of the loop runs first?", conv)


@pytest.mark.parametrize("text", [
    "What do you think is causing the wrong result?",
    "Can you identify which line is wrong?",
    "Can you explain why you are only returning one index?",
])
def test_diagnosis_reasking_is_detected(text):
    assert ta._re_asks_diagnosis(text)


@pytest.mark.parametrize("text", [
    "How could you test your idea using [2, 7, 11, 15] with a target of 9?",
    "In your own words, why does your change make the failing case work?",
])
def test_validation_and_consolidation_questions_are_not_diagnosis(text):
    assert not ta._re_asks_diagnosis(text)


def test_asking_what_the_problem_requires_is_not_re_asking_the_diagnosis():
    text = "Does the result match what the problem requires?"
    assert not ta._re_asks_diagnosis(text)


def test_recursion_detection_matches_the_students_code():
    fib_iterative = PROBLEMS[8]["code"]
    max_depth = PROBLEMS[4]["code"]
    queue = PROBLEMS[7]["code"]  # method `pop` calls self.stack.pop(): NOT recursion
    assert not ta._code_uses_recursion(fib_iterative)
    assert ta._code_uses_recursion(max_depth)
    assert not ta._code_uses_recursion(queue)


def test_off_topic_recursion_is_blocked_for_iterative_fibonacci():
    """Regression: the tutor once introduced recursion into an iterative Fibonacci."""
    conv = Conversation(code=PROBLEMS[8]["code"], problem=PROBLEMS[8]["problem"])
    assert ta._off_topic_recursion("What is the base case of your recursion?", conv, "my base case is wrong")
    # ...but is allowed for genuinely recursive code, or if the student raised it.
    tree = Conversation(code=PROBLEMS[4]["code"])
    assert not ta._off_topic_recursion("What does your recursion do for a leaf?", tree, "")
    assert not ta._off_topic_recursion("Is your recursion needed?", conv, "should I use recursion?")


def test_markers_are_stripped():
    cleaned = ta._clean_student_response("Hint: Trace the return value.\nQuestion: What does the function return when the match is found?")
    assert "Hint" not in cleaned and "Question:" not in cleaned
    assert cleaned.count("?") == 1
    cleaned = ta._clean_student_response("Nice start. Hint: it is the return.\nQuestion: What does it return?")
    assert cleaned == "Nice start. What does it return?"


# --------------------------------------------------------------- diagnostics --

def test_diagnostic_parser_handles_fences_prose_and_string_booleans():
    fenced = '```json\n{"problem_identified": true, "solution_proposed": false}\n```'
    assert ta._parse_diagnostic(fenced)["problem_identified"] is True
    assert ta._parse_diagnostic('Sure! {"problem_identified": true} done')["problem_identified"] is True
    # Regression: bool("false") is True in Python.
    assert ta._parse_diagnostic('{"problem_identified": "false"}')["problem_identified"] is False
    assert ta._parse_diagnostic("not json")["problem_identified"] is False


# The ten first responses in the test plan are the development set for the heuristics, so passing here shows coverage, not generalisation.
@pytest.mark.parametrize("problem", PROBLEMS, ids=lambda p: p["name"])
def test_heuristics_recognise_each_test_plan_first_response(problem):
    result = ta._infer_explicit_student_progress(problem["code"], problem["first_response"])
    assert result["problem_identified"], problem["first_response"]


@pytest.mark.parametrize("message", [
    "I have no idea. Do I need to return the total to the caller?",
    "Something is wrong with my result.",
    "It doesn't work, can you help me?",
    "The problem is that it fails. I don't know how to fix it.",
    "Both i and j are used in the loop, so why is the answer wrong?",
    "I'm not sure why the output is wrong, maybe I should add a print to see it",
])
def test_heuristics_do_not_treat_vague_messages_as_progress(message):
    """Regression: these used to be scored as diagnosis and/or correct fix."""
    result = ta._infer_explicit_student_progress(TWO_SUM, message)
    assert not result["problem_identified"], message
    assert not result["solution_proposed"], message
    assert not result["solution_correct"]  # heuristics never assert correctness


def test_heuristics_detect_proposal_and_validation_but_never_correctness():
    p = PROBLEMS[0]
    fix = ta._infer_explicit_student_progress(p["code"], p["fix"])
    val = ta._infer_explicit_student_progress(p["code"], p["validation"])
    assert fix["solution_proposed"] and not fix["solution_correct"]
    assert val["solution_validated"] and not val["solution_correct"]


# ---------------------------------------------------------------- state flow --

def test_tutor_hides_internal_markers(monkeypatch):
    install(monkeypatch, FakeLLM([diag()], ["Hint: Trace the return value.\nQuestion: What does the function return when the condition is met?"]))
    (reply,), conv = run_turns(["Something is wrong with my result."])
    assert "Hint:" not in reply and "Question:" not in reply
    assert reply.count("?") == 1 and conv.question_count == 1


def test_diagnosis_only_moves_to_propose_and_does_not_conclude(monkeypatch):
    llm = FakeLLM([diag(identified=True)], ["That is a useful diagnosis. Which input could you trace to confirm it?"])
    install(monkeypatch, llm)
    (reply,), conv = run_turns(["I think the problem is that only one index is returned when the pair is found."])
    assert conv.stage_name == "propose" and not conv.concluded
    assert conv.problem_identified and not conv.solution_proposed
    assert "STAGE GUIDANCE" in llm.prompts[0] and "NEVER ask them to identify" in llm.prompts[0]


def test_explicit_diagnosis_does_not_restart_diagnosis(monkeypatch):
    """Priority behaviour: identified bug -> never asked to identify it again."""
    # The model asks a diagnosis question anyway; the guard must reject it (twice), then fall back.
    bad = "What do you think is causing the wrong result?"
    llm = FakeLLM([diag()], [bad, bad])  # model diagnostic misses it: heuristics must catch it
    install(monkeypatch, llm)
    p = PROBLEMS[6]
    (reply,), conv = run_turns([p["first_response"]], code=p["code"], problem=p["problem"])
    assert conv.problem_identified
    assert conv.stage_name != "clarify"
    assert not ta._re_asks_diagnosis(reply)
    assert reply in ta._FALLBACK_QUESTIONS[conv.stage_name]


def test_full_flow_needs_validation_and_five_questions_before_concluding(monkeypatch):
    p = PROBLEMS[0]
    diagnostics = [
        diag(identified=True, proposed=True, correct=True),                    # t1: diagnosis + vague plan
        diag(identified=True, proposed=True, correct=True),                    # t2: own fix
        diag(identified=True, proposed=True, correct=True, validated=True),    # t3: validation
        diag(True, True, True, True),                                          # t4
        diag(True, True, True, True),                                          # t5
        diag(True, True, True, True),                                          # t6 -> conclude
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
    for role, text in [("d", p["first_response"]), ("f", p["fix"]), ("v", p["validation"])] + [("r", r) for r in p["reflections"]]:
        reply, cid = ta.generate_tutor_response(p["code"], text, cid, problem=p["problem"])
        conv = get_conversation(cid)
        stages.append(conv.stage_name)
        out.append(reply)
        if conv.concluded:
            break

    assert stages == ["validate", "validate", "consolidate", "consolidate", "consolidate", "conclude"]
    assert conv.question_count == 5 and conv.concluded
    assert "?" not in out[-1]
    # Post-validation questions are never diagnostic.
    assert not any(ta._re_asks_diagnosis(r) for r in out[:-1])


def test_validated_fix_below_minimum_keeps_consolidating_not_concluding(monkeypatch):
    install(monkeypatch, FakeLLM([diag(True, True, True, True)], ["In your own words, why does your change work?"]))
    _, conv = run_turns(["I changed it to return both, and for [2, 7] with target 9 it now returns [0, 1]."])
    assert conv.stage_name == "consolidate" and not conv.concluded and conv.question_count == 1


def test_wrong_fix_gets_a_test_stage_not_a_conclusion(monkeypatch):
    install(monkeypatch, FakeLLM([diag(True, True, False, True)], ["Apply that change to [2, 7, 11, 15] with target 9. What do you get?"]))
    _, conv = run_turns(["I would return j instead. For [2, 7, 11, 15] it returns 1."])
    assert conv.stage_name == "test" and not conv.concluded and not conv.solution_correct


def test_questioning_continues_past_five_when_problem_not_identified(monkeypatch):
    def fake(prompt, *a, **k):
        if "private diagnostic component" in prompt.lower():
            return diag()
        return f"Question variant {re.sub(r'[^a-z]', '', prompt[-40:])[:5]}: what value do you observe at step {len(prompt) % 97}?"

    monkeypatch.setattr(ta, "ask_llm", fake)
    cid = None
    for i in range(7):
        reply, cid = ta.generate_tutor_response("print('x')", f"I am still unsure about attempt {i}.", cid)
        assert "?" in reply
    conv = get_conversation(cid)
    assert conv.question_count == 7 and not conv.concluded  # reaching 5 never forces a conclusion


def test_hard_limit_wraps_up_without_claiming_success(monkeypatch):
    install(monkeypatch, FakeLLM([diag()] * 20, ["Which value changes first when you trace the loop by hand?"] * 20))
    conv, cid = None, None
    monkeypatch.setattr(ta, "HARD_QUESTION_LIMIT", 2)
    for _ in range(3):
        reply, cid = ta.generate_tutor_response("x = 1", "still stuck here honestly", cid)
    conv = get_conversation(cid)
    assert conv.concluded and "instructor" in reply and "?" not in reply


def test_a_new_wrong_proposal_supersedes_an_earlier_correct_one(monkeypatch):
    install(monkeypatch, FakeLLM([diag(True, True, True), diag(True, True, False)],
                                 ["How could you test that on a small example?", "Can you trace that new change on [2, 7] and tell me what you get?"]))
    _, conv = run_turns(["I should return both i and j.", "Actually I would return j instead."])
    assert conv.solution_proposed and not conv.solution_correct


def test_validation_without_a_prior_proposal_does_not_count(monkeypatch):
    install(monkeypatch, FakeLLM([diag(True, False, False, True)], ["Which change would you try yourself?"]))
    _, conv = run_turns(["I ran it with [2, 7] and it gives [0], which is wrong."])
    assert not conv.solution_validated


def test_bad_first_reply_triggers_retry_with_reason_then_fallback(monkeypatch):
    leak = "You should use a hash map here. What do you think?"
    llm = FakeLLM([diag()], [leak, leak])
    install(monkeypatch, llm)
    (reply,), conv = run_turns(["It gives the wrong output and I do not know why."])
    assert len(llm.prompts) == 2 and "rejected" in llm.prompts[1] and "Do NOT tell the student" in llm.prompts[1]
    assert reply in ta._FALLBACK_QUESTIONS["clarify"]
    assert not ta._contains_solution_leak(reply)


def test_all_fallback_questions_pass_every_guard():
    conv = Conversation(code=TWO_SUM)
    for stage, questions in ta._FALLBACK_QUESTIONS.items():
        conv.problem_identified = stage not in ta.DIAGNOSIS_STAGES
        for q in questions:
            assert ta._response_problem(q, conv, "some student message") is None, (stage, q)
    for q in ta._CONSOLIDATION_FALLBACKS:
        conv.problem_identified = True
        assert ta._response_problem(q, conv, "x") is None, q


def test_concluded_conversation_is_not_restarted(monkeypatch):
    install(monkeypatch, FakeLLM([diag(True, True, True, True)], [], conclusion="Well done."))
    monkeypatch.setattr(ta, "MIN_SOCRATIC_QUESTIONS", 0)
    cid = None
    reply, cid = ta.generate_tutor_response(TWO_SUM, "I return both and traced [2, 7] -> [0, 1].", cid)
    assert get_conversation(cid).concluded
    again, _ = ta.generate_tutor_response(TWO_SUM, "one more thing", cid)
    assert "already concluded" in again
