from backend.agent import tutor_agent
from backend.agent.conversation import get_conversation


def test_solution_leak_detection():
    assert tutor_agent._contains_solution_leak("The answer is to change line 4.")
    assert tutor_agent._contains_solution_leak("You should replace x with y.")
    assert not tutor_agent._contains_solution_leak("What value does x have here?")


def test_repetition_question_detection():
    assert tutor_agent._is_repetition_question(
        "Can you repeat the question?",
        "How can I fix this testcase?",
    )
    assert tutor_agent._is_repetition_question(
        "Can you restate the problem?",
        "How can I fix this testcase?",
    )
    assert not tutor_agent._is_repetition_question(
        "What value does n have when the failing case reaches this statement?",
        "How can I fix this testcase where n = 0?",
    )


def test_diagnostic_parser_tracks_student_progress():
    result = tutor_agent._parse_diagnostic(
        '{"problem_identified": true, "solution_proposed": true, '
        '"solution_correct": true, "solution_validated": false, '
        '"student_evidence": "Student proposes returning both indices.", '
        '"next_step": "conclude"}'
    )
    assert result["problem_identified"] is True
    assert result["solution_proposed"] is True
    assert result["solution_correct"] is True
    assert result["solution_validated"] is False


def test_tutor_hides_internal_markers(monkeypatch):
    outputs = iter([
        '{"problem_identified": false, "solution_proposed": false, "solution_correct": false, "solution_validated": false, "student_evidence": "", "next_step": "diagnose"}',
        "Hint: Trace the return value.\nQuestion: What does the function return when the condition is met?",
    ])
    monkeypatch.setattr(tutor_agent, "ask_llm", lambda *args, **kwargs: next(outputs))

    response, conversation_id = tutor_agent.generate_tutor_response(
        code="return x",
        question="Something is wrong with my result.",
    )

    conversation = get_conversation(conversation_id)
    assert "Hint:" not in response
    assert "Question:" not in response
    assert response.count("?") == 1
    assert conversation.question_count == 1


def test_tutor_concludes_immediately_when_student_identifies_and_proposes_correct_fix(monkeypatch):
    outputs = iter([
        '{"problem_identified": true, "solution_proposed": true, "solution_correct": true, '
        '"solution_validated": false, "student_evidence": "Student says only i is returned and proposes returning both i and j.", '
        '"next_step": "conclude"}',
        "You identified that the returned result does not contain all required information and proposed a change that addresses that mismatch. Verify your own change with the example input.",
    ])
    monkeypatch.setattr(tutor_agent, "ask_llm", lambda *args, **kwargs: next(outputs))

    response, conversation_id = tutor_agent.generate_tutor_response(
        code="""class Solution(object):
    def twoSum(self, nums, target):
        for i in range(len(nums)):
            for j in range(i + 1, len(nums)):
                if nums[i] + nums[j] == target:
                    return [i]
        return []""",
        question="Could it be because I only return i? I think I need to return both i and j.",
    )

    conversation = get_conversation(conversation_id)
    assert "?" not in response
    assert "Hint:" not in response
    assert "Question:" not in response
    assert conversation.concluded is True
    assert conversation.question_count == 0
    assert conversation.problem_identified is True
    assert conversation.solution_proposed is True
    assert conversation.solution_correct is True


def test_tutor_does_not_conclude_when_student_only_identifies_problem(monkeypatch):
    outputs = iter([
        '{"problem_identified": true, "solution_proposed": false, "solution_correct": false, "solution_validated": false, "student_evidence": "Student identified the incorrect return behaviour.", "next_step": "propose"}',
        "That is a useful diagnosis. What change could you propose to address the mismatch you found?",
    ])
    monkeypatch.setattr(tutor_agent, "ask_llm", lambda *args, **kwargs: next(outputs))

    response, conversation_id = tutor_agent.generate_tutor_response(
        code="return [i]",
        question="I think the problem is that only one index is returned.",
    )

    conversation = get_conversation(conversation_id)
    assert "?" in response
    assert conversation.concluded is False
    assert conversation.problem_identified is True
    assert conversation.solution_proposed is False
    assert conversation.question_count == 1


def test_questioning_can_continue_past_five_when_problem_not_identified(monkeypatch):
    def fake_llm(prompt, *args, **kwargs):
        if "private diagnostic component" in prompt.lower():
            return '{"problem_identified": false, "solution_proposed": false, "solution_correct": false, "solution_validated": false, "student_evidence": "", "next_step": "diagnose"}'
        return "What value do you observe at this step?"

    monkeypatch.setattr(tutor_agent, "ask_llm", fake_llm)

    conversation_id = None
    for i in range(6):
        response, conversation_id = tutor_agent.generate_tutor_response(
            code="print('x')",
            question=f"I am still unsure about attempt {i}.",
            conversation_id=conversation_id,
        )
        assert "?" in response

    conversation = get_conversation(conversation_id)
    assert conversation.question_count == 6
    assert conversation.concluded is False
