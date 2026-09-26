from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    code: str = Field(min_length=1)
    question: str = Field(min_length=1)
    conversation_id: str | None = None
    # Optional plain-English task description (e.g. the LeetCode problem).
    problem: str | None = None


class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    stage: str | None = None
    concluded: bool = False
