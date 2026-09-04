from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    code: str = Field(min_length=1)
    question: str = Field(min_length=1)
    conversation_id: str | None = None
    language: Literal["python", "javascript"] = "python"


class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    stage: str | None = None
