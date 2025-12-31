from app.core.database import db
from datetime import datetime, timezone
from langchain_core.messages import HumanMessage, AIMessage
from typing import Literal
from ast import literal_eval
import time
import uuid

from app.config.errors import (
    ChatNotFoundError,
    CurriculumNotFoundError,
    InvalidChatStateError,
    LLMRetryFailedError,
)


class FirebaseChatService:

    # ================================
    # Firestore Helper
    # ================================
    def _get_chat_ref(self, user_uuid: str, chat_id: str):
        return (
            db.collection("users").document(user_uuid)
            .collection("chats").document(chat_id)
        )
    
    def _get_latest_chat(self, user_uuid: str):
        chats_ref = (
            db.collection("users")
            .document(user_uuid)
            .collection("chats")
            .order_by("created_at", direction="DESCENDING")
            .limit(1)
            .stream()
        )

        for chat in chats_ref:
            return chat.to_dict()

        return None

    def _get_next_curriculum(self, current_step: int, current_id: int):
        curriculum_ref = db.collection("curriculums").document(f"step{current_step}")
        curriculum = curriculum_ref.get().to_dict()

        if curriculum is None:
            raise CurriculumNotFoundError(f"step{current_step} 커리큘럼 없음")

        next_id = current_id + 1

        # 같은 step에 다음 id가 있으면
        if str(next_id) in curriculum:
            return current_step, next_id

        # 없으면 다음 step으로
        next_step = current_step + 1
        next_step_ref = db.collection("curriculums").document(f"step{next_step}")
        next_curriculum = next_step_ref.get().to_dict()

        if next_curriculum is None or "1" not in next_curriculum:
            raise CurriculumNotFoundError("다음 커리큘럼이 존재하지 않습니다")

        return next_step, 1

    @staticmethod
    def _save_message(user_uuid: str, chat_id: str, role: str, content: str):
        ref = (
            db.collection("users").document(user_uuid)
            .collection("chats").document(chat_id)
            .collection("messages").document()
        )
        ref.set({
            "messageId": ref.id,
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc)
        })

    @staticmethod
    def _save_assistant_message(user_uuid: str, chat_id: str, role: str, content: str):
        ref = (
            db.collection("users").document(user_uuid)
            .collection("chats").document(chat_id)
            .collection("assistant").document()
        )
        ref.set({
            "messageId": ref.id,
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc)
        })

    @staticmethod
    def _load_messages(user_uuid: str, chat_id: str):
        ref = (
            db.collection("users").document(user_uuid)
            .collection("chats").document(chat_id)
            .collection("messages")
        )
        docs = ref.order_by("timestamp").stream()

        return [{"role": d.to_dict()["role"], "content": d.to_dict()["content"]} for d in docs]
    
    @staticmethod
    def _load_assistant_messages(user_uuid: str, chat_id: str):
        ref = (
            db.collection("users").document(user_uuid)
            .collection("chats").document(chat_id)
            .collection("assistant")
        )
        docs = ref.order_by("timestamp").stream()

        return [{"role": d.to_dict()["role"], "content": d.to_dict()["content"]} for d in docs]


    @staticmethod
    def _load_curriculum(step: int, index: int):
        ref = db.collection("curriculums").document(f"step{step}").get()

        if not ref.exists:
            raise CurriculumNotFoundError(f"step{step} 문서를 찾을 수 없습니다.")

        data = ref.to_dict().get(str(index))
        if data is None:
            raise CurriculumNotFoundError(f"step{step}/{index} 데이터를 찾을 수 없습니다.")

        return {
            "title": data.get("title", ""),
            "contents": data.get("contents", ""),
            "questions": data.get("questions", [])
        }

    @staticmethod
    def _llm_retry(llm, system_prompt: str, user_prompt: str, retries=3, delay=1):

        for attempt in range(1, retries + 1):
            try:
                response = llm.invoke([
                    AIMessage(content=system_prompt),
                    HumanMessage(content=user_prompt)
                ])

                text = response.content if response else ""

                if not text.strip():
                    raise ValueError("빈 응답")

                return text

            except Exception as e:
                if attempt == retries:
                    raise LLMRetryFailedError("LLM 호출이 3회 모두 실패했습니다.", str(e))
                time.sleep(delay)

    # ================================
    # Public Methods
    # ================================

    def create_chat(self, user_uuid: str):
        latest_chat = self._get_latest_chat(user_uuid)

        # 시작 step/id 결정
        if latest_chat is None:
            current_step, current_id = 1, 1
        else:
            current_step = latest_chat["current_step"]
            current_id = latest_chat["current_id"]
            current_step, current_id = self._get_next_curriculum(current_step, current_id)

        # chat 생성
        chat_id = str(uuid.uuid4())
        chat_ref = self._get_chat_ref(user_uuid, chat_id)

        curriculum = (
            db.collection("curriculums")
            .document(f"step{current_step}")
            .get()
            .to_dict()
        )

        if curriculum is None:
            raise CurriculumNotFoundError(f"step{current_step} 커리큘럼을 찾을 수 없습니다")

        if str(current_id) not in curriculum:
            raise CurriculumNotFoundError(
                f"step{current_step} 커리큘럼에서 {current_id} 데이터를 찾을 수 없습니다"
            )

        book_data = curriculum[str(current_id)] 

        chat_ref.set({
            "chat_id": chat_id,
            "title": book_data.get("title", ""),
            "created_at": datetime.now(timezone.utc),
            "current_step": current_step,
            "current_id": current_id,
            "current_question_index": 0
        })

        return chat_id, {
            "title": book_data.get("title", ""),
            "contents": book_data.get("contents", "")
        }
    
    def process_chat(self, llm, user_uuid: str, chat_id: str, user_message: str):
        """
        독서 완료 후 토론식 대화
        
        :param llm: request.app.state.llm
        :type user_uuid: str
        :type chat_id: str
        :type user_message: str
        """

        FirebaseChatService._save_message(user_uuid, chat_id, "user", user_message)

        chat_ref = self._get_chat_ref(user_uuid, chat_id)
        chat_data = chat_ref.get().to_dict()

        if chat_data is None:
            raise ChatNotFoundError("chat_id 없음")

        step, idx, q_index = (
            chat_data.get("current_step"),
            chat_data.get("current_id"),
            chat_data.get("current_question_index"),
        )

        if q_index is None:
            raise InvalidChatStateError()

        curriculum = self._load_curriculum(step, idx)
        questions = curriculum["questions"]

        # 첫 질문
        if q_index == 0:
            chat_ref.update({"current_question_index": 1})
            first_q = questions[0]
            self._save_message(user_uuid, chat_id, "assistant", first_q)
            return first_q

        # 공감 생성
        empathy_prompt = f"""
        사용자가 이렇게 말했어요:
        "{user_message}"
        너무 길지 않게, 따뜻하고 자연스럽게 공감해주세요. 해요(~요, 비격식 존대)체를 써서 대답해주세요.
        """

        empathy_text = llm.invoke([HumanMessage(content=empathy_prompt)]).content
        self._save_message(user_uuid, chat_id, "assistant", empathy_text)

        # 다음 질문 존재?
        if q_index + 1 < len(questions):
            next_q = questions[q_index + 1]
            chat_ref.update({"current_question_index": q_index + 1})
            self._save_message(user_uuid, chat_id, "assistant", next_q)
            return empathy_text + "\n\n" + next_q

        # 마지막 질문 → 종료
        end_msg = "오늘 질문은 모두 끝났어요. 이제 감상문을 작성해볼까요?"
        self._save_message(user_uuid, chat_id, "assistant", end_msg)

        chat_ref.update({
            "current_question_index": None
        })

        return empathy_text + "\n\n" + end_msg
    
    def list_chats(self, user_uuid: str):
        chats_ref = db.collection("users").document(user_uuid).collection("chats")
        docs = chats_ref.order_by("created_at", direction="DESCENDING").stream()

        results = []
        for doc in docs:
            data = doc.to_dict()
            chat_ref = doc.reference

            has_book_report = (
                len(
                    list(
                        chat_ref
                        .collection("book_report")
                        .limit(1)
                        .stream()
                    )
                ) > 0
            )

            has_final_report = (
                len(
                    list(
                        chat_ref
                        .collection("final_report")
                        .limit(1)
                        .stream()
                    )
                ) > 0
            )

            results.append({
                "chat_id": data["chat_id"],
                "created_at": data["created_at"],
                "title": data["title"],
                "current_step": data["current_step"],
                "current_id": data["current_id"],
                "current_question_index": data["current_question_index"],
                "has_book_report": has_book_report,
                "has_final_report": has_final_report,
            })

        return results
    
    def process_assistant_chat(self, llm, user_uuid: str, chat_id: str, user_message: str):
        """
        독서 도우미와의 대화
        
        :param llm: request.app.state.llm
        :type user_uuid: str
        :type chat_id: str
        :type user_message: str
        """

        FirebaseChatService._save_assistant_message(user_uuid, chat_id, "user", user_message)

        chat_ref = self._get_chat_ref(user_uuid, chat_id)
        chat_data = chat_ref.get().to_dict()

        if chat_data is None:
            raise ChatNotFoundError("chat_id 없음")

        step, idx, q_index = (
            chat_data.get("current_step"),
            chat_data.get("current_id"),
            chat_data.get("current_question_index"),
        )

        if q_index is None:
            raise InvalidChatStateError()

        curriculum = self._load_curriculum(step, idx)
        contents = curriculum["contents"]
        messages = self.load_assistant_messages(user_uuid, chat_id)

        # 공감 생성
        empathy_prompt = f"""
        책 내용:
        {contents}

        {f"이전 대화 내용: {messages[-3:-1]}" if len(messages)>2 else ""}
        사용자가 이렇게 물어봤어요:
        "{user_message}"
        너무 길지 않게, 따뜻하고 자연스럽게 답변해주세요. 해요(~요, 비격식 존대)체를 써서 대답해주세요.
        """

        answer = llm.invoke([HumanMessage(content=empathy_prompt)]).content
        self._save_assistant_message(user_uuid, chat_id, "assistant", answer)

        return answer


    def get_chat_detail(self, user_uuid: str, chat_id: str):
        """
        채팅 1개에 대한 세부 정보
        
        :type user_uuid: str
        :type chat_id: str
        """

        chat_ref = self._get_chat_ref(user_uuid, chat_id)
        chat_data = chat_ref.get().to_dict()
        if chat_data is None:
            raise ChatNotFoundError()
        step, idx = chat_data.get("current_step"), chat_data.get("current_id")
        if step is None or idx is None:
            raise InvalidChatStateError("토론이 종료되었거나 손상되었습니다.")
        
        # curriculum
        curriculum_ref = db.collection("curriculums").document(f"step{step}").get()
        if not curriculum_ref.exists:
            raise CurriculumNotFoundError()
        curriculum_data = curriculum_ref.to_dict().get(str(idx))
        if curriculum_data is None:
            raise CurriculumNotFoundError()
        title, author = (
            curriculum_data.get("title", ""),
            curriculum_data.get("author", ""),
        )

        chat_messages = self.load_messages(user_uuid, chat_id)
        return {
            "title": title,
            "author": author,
            "step": step,
            "step_idx": idx,
            "chat_messages": chat_messages
        }