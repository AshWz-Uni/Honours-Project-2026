from pydantic import BaseModel, Field, field_validator

from backend.agent.language import normalise_language


class ChatRequest(BaseModel):
    code: str = Field(min_length=1)
    question: str = Field(min_length=1)
    conversation_id: str | None = None
    # Optional plain-English task description (e.g. the LeetCode problem).
    problem: str | None = None
    # "python", "javascript" (aliases such as "js" are accepted) or "auto"/omitted to detect from the code.
    language: str | None = None

    @field_validator("language")
    @classmethod
    def _check_language(cls, value: str | None) -> str | None:
        if value is None or value.strip().lower() in ("", "auto"):
            return None
        normalised = normalise_language(value)
        if normalised is None:
            raise ValueError("Unsupported language. Use 'python', 'javascript' or 'auto'.")
        return normalised


class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    stage: str | None = None
    concluded: bool = False
    # Language the tutor used for this turn (the student's choice, or detected).
    language: str | None = None
