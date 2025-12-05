from pydantic import BaseModel

class ChatCreateRequest(BaseModel):
    step_id: str
    book_title: str

class ChatMessageRequest(BaseModel):
    message: str