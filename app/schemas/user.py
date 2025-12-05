from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime

class User(BaseModel):
    id: str
    name: str
    role: Literal["학생", "학부모", "관리자"]

class RequestUserLogin(BaseModel):
    id: str
    password: str

class RequestUserCreate(BaseModel):
    id: str
    password: str
    name: str
    role: Literal["학생", "학부모", "관리자"] = "학생"
    relation: Optional[str] = ""

class ResponseUserLogin(BaseModel):
    id: str
    name: str
    access_token: str

class RequestUserProfile(BaseModel):
    my_role: Literal["학생", "학부모", "관리자"] = "학생"