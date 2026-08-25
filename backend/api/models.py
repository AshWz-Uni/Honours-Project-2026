from pydantic import BaseModel

class ChatRequest(BaseModel):
    code: str
    question: str

class ChatResponse(BaseModel):
    response: str
