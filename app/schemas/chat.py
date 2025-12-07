from pydantic import BaseModel

class ChatCreateRequest(BaseModel):
    step_id: str
    book_title: str

class ChatMessageRequest(BaseModel):
    message: str
    
class BookReportRequest(BaseModel):
    subject: str
    summary: str
    book_review: str
    debate_review: str