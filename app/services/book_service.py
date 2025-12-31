from app.core.database import db
from typing import Dict, Any, List, Literal
import time
from datetime import datetime, timezone
import json
from app.config.errors import *
from langchain_core.messages import HumanMessage, AIMessage
from ast import literal_eval


class BookService:
    # ==========================================
    # 1) 모든 커리큘럼(step1 ~ n, 각 index까지) 불러오기
    # ==========================================
    def load_all_curriculums(self) -> Dict[str, Any]:
        ref = db.collection("curriculums")
        docs = ref.stream()

        all_curriculums = {}

        for doc in docs:
            step_key = doc.id 
            step_data = doc.to_dict()
            all_curriculums[step_key] = step_data

        return all_curriculums
    
    # ==========================================
    # 2) final_report가 존재하는 모든 작품의 점수 반환
    # ==========================================
    def get_current_book(self, user_uuid: str, chat_id: str):
        # 채팅 문서 조회
        chat_ref = (
            db.collection("users")
            .document(user_uuid)
            .collection("chats")
            .document(chat_id)
        )

        chat_doc = chat_ref.get()
        if not chat_doc.exists:
            raise ValueError("Chat not found")

        chat_data = chat_doc.to_dict()
        current_step = chat_data.get("current_step")
        current_id = chat_data.get("current_id")

        # 커리큘럼 문서 조회
        curriculum_ref = db.collection("curriculums").document(f"step{current_step}")
        curriculum_doc = curriculum_ref.get()

        if not curriculum_doc.exists:
            raise ValueError("Curriculum step not found")

        curriculum_data = curriculum_doc.to_dict()
        book_data = curriculum_data.get(str(current_id))

        if not book_data:
            raise ValueError("Book data not found")

        return {
            "author": book_data.get("author", ""),
            "title": book_data.get("title", ""),
            "contents": book_data.get("contents", "")
        }
