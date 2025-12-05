from app.core.database import db
from datetime import datetime, timezone
from langchain_core.messages import HumanMessage, AIMessage
import uuid


class FirebaseChatService:

    # ------------------------------------------------------
    #  채팅방 생성
    # ------------------------------------------------------
    def create_chat(self, user_uuid: str, current_step: int = 1, current_id: int = 1):
        chat_id = str(uuid.uuid4())

        chat_ref = (
            db.collection("users").document(user_uuid)
            .collection("chats").document(chat_id)
        )

        # 처음부터 커리큘럼 시작: step1 / id1 / 0번 질문부터
        book_data = db.collection("curriculums").document(f"step{1}").get().to_dict()[str(1)]

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
            "contents": book_data.get("contents", ""),
        }
    # ------------------------------------------------------
    #  채팅방 목록 불러오기
    # ------------------------------------------------------
    def list_chats(self, user_uuid: str):
        chats_ref = (
            db.collection("users").document(user_uuid)
            .collection("chats")
        )

        docs = chats_ref.order_by("created_at", direction="DESCENDING").stream()

        chats = []
        for doc in docs:
            data = doc.to_dict()
            chats.append({
                "chat_id": data["chat_id"],
                "created_at": data["created_at"],
                "title": data["title"],
                "current_step": data["current_step"],
                "current_id": data["current_id"],
                "current_question_index": data["current_question_index"],
            })

        return chats
    # ------------------------------------------------------
    # 기본 메시지 저장/불러오기
    # ------------------------------------------------------
    @staticmethod
    def save_message(user_uuid: str, chat_id: str, role: str, content: str):
        message_ref = (
            db.collection("users").document(user_uuid)
            .collection("chats").document(chat_id)
            .collection("messages").document()
        )

        message_ref.set({
            "messageId": message_ref.id,
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc)
        })

    @staticmethod
    def load_messages(user_id: str, chat_id: str):
        messages_ref = (
            db.collection("users").document(user_id)
            .collection("chats").document(chat_id)
            .collection("messages")
        )

        docs = messages_ref.order_by("timestamp").stream()

        messages = []
        for doc in docs:
            data = doc.to_dict()
            messages.append({
                "role": data["role"],
                "content": data["content"]
            })

        return messages

    # ------------------------------------------------------
    # 커리큘럼 로딩
    # ------------------------------------------------------
    @staticmethod
    def load_curriculum(step: int, index: int):
        ref = (
            db.collection("curriculums")
            .document(f"step{step}")
        )

        data = ref.get().to_dict()[str(index)] if ref.get().exists else None

        if data is None:
            return {}
        return {
            "title": data.get("title", ""),
            "contents": data.get("contents", ""),
            "questions": data.get("questions", [])
        }
    # ------------------------------------------------------
    # 단일 엔드포인트에서 자동 분기 처리
    # ------------------------------------------------------
    @staticmethod
    def process_chat(llm, user_uuid: str, chat_id: str, user_message: str):

        FirebaseChatService.save_message(user_uuid, chat_id, "user", user_message)

        chat_ref = (
            db.collection("users").document(user_uuid)
            .collection("chats").document(chat_id)
        )
        chat_data = chat_ref.get().to_dict()

        step = chat_data["current_step"]
        idx = chat_data["current_id"]
        q_index = chat_data["current_question_index"]

        curriculum = FirebaseChatService.load_curriculum(step, idx)
        questions = curriculum["questions"]
        
        # ---------------------
        # 첫 질문
        # ---------------------
        if q_index == 0:
            chat_ref.update({
                "current_question_index": 1
            })
            FirebaseChatService.save_message(user_uuid, chat_id, "assistant", questions[q_index])
            return questions[q_index]
        
        # ---------------------
        # 공감 생성
        # ---------------------
        empathy_prompt = f"""
        사용자가 이렇게 말했어:

        "{user_message}"

        너무 길지 않게, 따뜻하고 자연스럽게 공감해줘. 
        """
        empathy_text = llm.invoke([HumanMessage(content=empathy_prompt)]).content

        FirebaseChatService.save_message(user_uuid, chat_id, "assistant", empathy_text)

        # ---------------------
        # 다음 질문 존재?
        # ---------------------
        if q_index + 1 < len(questions):

            next_q = questions[q_index + 1]

            chat_ref.update({
                "current_question_index": q_index + 1
            })

            FirebaseChatService.save_message(user_uuid, chat_id, "assistant", next_q)

            return empathy_text + "\n\n" + next_q

        # ---------------------
        # 마지막 질문 → 종료
        # ---------------------
        end_msg = "오늘 준비된 질문은 모두 끝났어요. 진심으로 답해줘서 고마워요. 그럼 이제 감상문을 작성해볼까요?"

        FirebaseChatService.save_message(user_uuid, chat_id, "assistant", end_msg)

        # 일반 대화 모드로 전환
        chat_ref.update({
            "current_step": None,
            "current_id": None,
            "current_question_index": None
        })

        return empathy_text + "\n\n" + end_msg