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


def test_tutor_returns_hint_and_question_and_advances_stage(monkeypatch):
    outputs = iter([
        "likely_issue: condition\nnext_step: trace the condition",
        "Hint: Trace the loop boundary with the failing input.\nQuestion: What value does the condition evaluate with on the first iteration?",
    ])
    monkeypatch.setattr(tutor_agent, "ask_llm", lambda *args, **kwargs: next(outputs))

    response, conversation_id = tutor_agent.generate_tutor_response(
        code="for i in range(3):\n    print(i)",
        question="Why does this behave differently than I expected?",
    )

    conversation = get_conversation(conversation_id)
    assert response.count("?") == 1
    assert "Hint:" in response
    assert "Question:" in response
    assert conversation is not None
    assert conversation.stage == 1
    assert conversation.question_count == 1
    assert len(conversation.messages) == 2


def test_repetition_generation_falls_back_to_safe_question(monkeypatch):
    outputs = iter([
        "diagnostic notes",
        "Can you repeat the question?",
        "Can you restate the problem?",
    ])
    monkeypatch.setattr(tutor_agent, "ask_llm", lambda *args, **kwargs: next(outputs))

    response, _ = tutor_agent.generate_tutor_response(
        code="print('x')",
        question="Can you fix this?",
    )

    assert response.count("?") == 1
    assert "Hint:" in response
    assert "repeat the question" not in response.lower()
    assert "restate the problem" not in response.lower()


def test_no_conclusion_before_five_questions(monkeypatch):
    def fake_llm(prompt, *args, **kwargs):
        if "PRIVATE DIAGNOSTIC NOTES" in prompt:
            return "diagnostic notes"
        return "Hint: Trace the relevant value before changing the code.\nQuestion: What value do you observe at this step?"

    monkeypatch.setattr(tutor_agent, "ask_llm", fake_llm)

    conversation_id = None
    for i in range(5):
        response, conversation_id = tutor_agent.generate_tutor_response(
            code="print('x')",
            question=f"My reasoning attempt {i}",
            conversation_id=conversation_id,
        )
        assert "Question:" in response
        assert response.count("?") == 1

    conversation = get_conversation(conversation_id)
    assert conversation.question_count == 5
    assert conversation.concluded is False


def test_concludes_after_five_questions_without_another_question(monkeypatch):
    calls = []

    def fake_llm(prompt, *args, **kwargs):
        calls.append(prompt)
        if "concluding a Socratic" in prompt:
            return "You identified the relevant control-flow behaviour. Verify your own change with the edge case and a nearby valid input."
        if "PRIVATE DIAGNOSTIC NOTES" in prompt:
            return "diagnostic notes"
        return "Hint: Trace the relevant value before changing the code.\nQuestion: What value do you observe at this step?"

    monkeypatch.setattr(tutor_agent, "ask_llm", fake_llm)

    conversation_id = None
    for i in range(5):
        _, conversation_id = tutor_agent.generate_tutor_response(
            code="print('x')",
            question=f"attempt {i}",
            conversation_id=conversation_id,
        )

    response, conversation_id = tutor_agent.generate_tutor_response(
        code="print('x')",
        question="I think I understand the issue now.",
        conversation_id=conversation_id,
    )

    conversation = get_conversation(conversation_id)
    assert "?" not in response
    assert conversation.concluded is True
    assert conversation.question_count == 5
    assert "concluding a Socratic" in calls[-1]
