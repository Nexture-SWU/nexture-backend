from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime

class User(BaseModel):
    id: str
    name: str

class RequestUserLogin(BaseModel):
    id: str
    password: str

class RequestUserCreate(BaseModel):
    id: str
    password: str
    name: str

class ResponseUserLogin(BaseModel):
    id: str
    name: str
    access_token: str