from app.core.database import db
from datetime import datetime, timezone
from langchain_core.messages import HumanMessage, AIMessage
from typing import Literal
from ast import literal_eval
import time
import uuid

from app.config.errors import (
    ChatNotFoundError,
    BookReportNotFoundError,
    CurriculumNotFoundError,
    InvalidChatStateError,
    LLMRetryFailedError,
    FinalReportNotFoundError
)


class FirebaseChatService:

    # ================================
    # Firestore Helper
    # ================================
    @staticmethod
    def get_chat_ref(user_uuid: str, chat_id: str):
        return (
            db.collection("users").document(user_uuid)
            .collection("chats").document(chat_id)
        )

    # ================================
    # 채팅방 생성
    # ================================
    
    def get_latest_chat(self, user_uuid: str):
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

    def get_next_curriculum(self, current_step: int, current_id: int):
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

    def create_chat(self, user_uuid: str):
        latest_chat = self.get_latest_chat(user_uuid)

        # 시작 step/id 결정
        if latest_chat is None:
            current_step, current_id = 1, 1
        else:
            current_step = latest_chat["current_step"]
            current_id = latest_chat["current_id"]
            current_step, current_id = self.get_next_curriculum(current_step, current_id)

        # chat 생성
        chat_id = str(uuid.uuid4())
        chat_ref = self.get_chat_ref(user_uuid, chat_id)

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

    # ================================
    # 채팅방 목록
    # ================================
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


    # ================================
    # 메시지 로딩/저장
    # ================================
    @staticmethod
    def save_message(user_uuid: str, chat_id: str, role: str, content: str):
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
    def save_assistant_message(user_uuid: str, chat_id: str, role: str, content: str):
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
    def load_messages(user_uuid: str, chat_id: str):
        ref = (
            db.collection("users").document(user_uuid)
            .collection("chats").document(chat_id)
            .collection("messages")
        )
        docs = ref.order_by("timestamp").stream()

        return [{"role": d.to_dict()["role"], "content": d.to_dict()["content"]} for d in docs]
    
    @staticmethod
    def load_assistant_messages(user_uuid: str, chat_id: str):
        ref = (
            db.collection("users").document(user_uuid)
            .collection("chats").document(chat_id)
            .collection("assistant")
        )
        docs = ref.order_by("timestamp").stream()

        return [{"role": d.to_dict()["role"], "content": d.to_dict()["content"]} for d in docs]

    # ================================
    # 커리큘럼 로딩
    # ================================
    @staticmethod
    def load_curriculum(step: int, index: int):
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

    # ================================
    # LLM 호출 재시도 공통 함수
    # ================================
    @staticmethod
    def llm_retry(llm, system_prompt: str, user_prompt: str, retries=3, delay=1):

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
    # 채팅 프로세스
    # ================================
    def process_chat(self, llm, user_uuid: str, chat_id: str, user_message: str):

        FirebaseChatService.save_message(user_uuid, chat_id, "user", user_message)

        chat_ref = self.get_chat_ref(user_uuid, chat_id)
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

        curriculum = self.load_curriculum(step, idx)
        questions = curriculum["questions"]

        # 첫 질문
        if q_index == 0:
            chat_ref.update({"current_question_index": 1})
            first_q = questions[0]
            self.save_message(user_uuid, chat_id, "assistant", first_q)
            return first_q

        # 공감 생성
        empathy_prompt = f"""
        사용자가 이렇게 말했어요:
        "{user_message}"
        너무 길지 않게, 따뜻하고 자연스럽게 공감해주세요. 해요(~요, 비격식 존대)체를 써서 대답해주세요.
        """

        empathy_text = llm.invoke([HumanMessage(content=empathy_prompt)]).content
        self.save_message(user_uuid, chat_id, "assistant", empathy_text)

        # 다음 질문 존재?
        if q_index + 1 < len(questions):
            next_q = questions[q_index + 1]
            chat_ref.update({"current_question_index": q_index + 1})
            self.save_message(user_uuid, chat_id, "assistant", next_q)
            return empathy_text + "\n\n" + next_q

        # 마지막 질문 → 종료
        end_msg = "오늘 질문은 모두 끝났어요. 이제 감상문을 작성해볼까요?"
        self.save_message(user_uuid, chat_id, "assistant", end_msg)

        chat_ref.update({
            "current_question_index": None
        })

        return empathy_text + "\n\n" + end_msg
    
    # ================================
    # 어시스턴트 채팅 프로세스
    # ================================
    def process_assistant_chat(self, llm, user_uuid: str, chat_id: str, user_message: str):

        FirebaseChatService.save_assistant_message(user_uuid, chat_id, "user", user_message)

        chat_ref = self.get_chat_ref(user_uuid, chat_id)
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

        curriculum = self.load_curriculum(step, idx)
        contents = curriculum["contents"]
        messages = self.load_assistant_messages(chat_id)

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
        self.save_assistant_message(user_uuid, chat_id, "assistant", answer)


        return answer

    # ================================
    # 감상문 저장
    # ================================
    def create_book_report(self, user_uuid: str, chat_id: str, subject: str, summary: str, book_review: str, debate_review: str):
        ref = self.get_chat_ref(user_uuid, chat_id).collection("book_report").document("data")

        ref.set({
            "subject": subject,
            "summary": summary,
            "book_review": book_review,
            "debate_review": debate_review,
            "created_at": datetime.now(timezone.utc)
        })
        return True

    # ================================
    # 최종 보고서 생성
    # ================================
    def create_final_report(self, llm, user_uuid: str, chat_id: str):

        chat_ref = self.get_chat_ref(user_uuid, chat_id)
        chat_data = chat_ref.get().to_dict()

        if chat_data is None:
            raise ChatNotFoundError()

        step, idx = chat_data.get("current_step"), chat_data.get("current_id")
        if step is None or idx is None:
            raise InvalidChatStateError("토론이 종료되었거나 손상되었습니다.")

        # book report
        book_report_doc = chat_ref.collection("book_report").document("data").get().to_dict()
        if book_report_doc is None:
            raise BookReportNotFoundError()

        # curriculum
        curriculum_ref = db.collection("curriculums").document(f"step{step}").get()
        if not curriculum_ref.exists:
            raise CurriculumNotFoundError()

        curriculum_data = curriculum_ref.to_dict().get(str(idx))
        if curriculum_data is None:
            raise CurriculumNotFoundError()

        title, author, contents = (
            curriculum_data.get("title", ""),
            curriculum_data.get("author", ""),
            curriculum_data.get("contents", ""),
        )

        messages = self.load_messages(user_uuid, chat_id)

        # 줄거리 요약 LLM
        summary_prompt_system = f"""
        다음은 '{title}'라는 책의 정보입니다.
        저자: {author}
        내용: {contents}
        """

        summary_prompt_user = """
        이 책의 줄거리를 간단하게 2단락 이내로 요약해 주세요.
        해요체로 작성하고, '단락'이라는 단어를 넣지 마세요.
        """
        summary = self.llm_retry(llm, summary_prompt_system, summary_prompt_user)

        max_retries = 3 
        delay = 1 
        for attempt in range(1, max_retries + 1): 
            try:

                # 최종 평가 LLM
                eval_system = f""" 
                당신은 청소년 교육 전문가입니다. 다음 내용에 기초하여 학생의 독서감상 능력에 대한 최종 평가를 내려주세요. 
                책 제목: {title} 
                저자: {author} **출력물은 반드시 아래 JSON 형식으로 작성해 주세요.** 
                [출력 JSON 형식] 
                {{ "summary_accuracy": 숫자, # 줄거리와 학생요약이 일치하는지(1~5점),
                "expression": 숫자, # 표현력이나 문장 구성이 풍부한지, 자신의 감정을 잘 드러냈는지(1~5점) 
                "logical_thinking": 숫자, # 논리적 사고력을 가지고 있는지, 구조가 잘 잡혀있는지, 논리적 비약이 없는지(1~5점) 
                "manner": 숫자, # 독서 감상 대화에 성의를 가지고 임했는지, 말투가 적절했는지, 독서 감상문의 길이가 충분히 긴 지(1~5점) 
                "reason": "문자열" # 각 평가 항목에 대한 구체적인 피드백과 점수를 준 이유를 5~7 문장으로 설명, 말투는 비격식 존대(해요체)로 작성 
                }} """
                eval_user = f""" 
                [입력정보] 
                줄거리: {summary} 
                학생 요약: {book_report_doc["summary"]} 
                학생의 책을 읽고 느낀점: {book_report_doc["book_review"]} 
                학생의 토론 내용: {messages} 
                학생의 토론 후 느낀점: {book_report_doc["debate_review"]}
                """

                raw_eval = self.llm_retry(llm, eval_system, eval_user)
                print(raw_eval)

                processed_eval = raw_eval.replace('```json', '').replace('```python', '').replace('```', '').strip()
                processed_eval = processed_eval.replace('true', 'True').replace('false', 'False')
                start = None
                depth = 0

                for i, ch in enumerate(processed_eval):
                    if ch == '{':
                        if depth == 0:
                            start = i
                        depth += 1
                    elif ch == '}':
                        if depth > 0:
                            depth -= 1
                            if depth == 0 and start is not None:
                                json_str = processed_eval[start:i+1]
                                break
                else:
                    print(processed_eval)
                    raise ValueError("JSON 객체를 찾지 못했습니다.")
                
                json_str = json_str.replace('다요.', '다.').replace('요요.', '요.')
                eval_data = literal_eval(json_str)
            

                final_report = {
                    "title": title,
                    "author": author,
                    "subject": book_report_doc["subject"],
                    "summary": summary,
                    "summary_accuracy": eval_data["summary_accuracy"],
                    "expression": eval_data["expression"],
                    "logical_thinking": eval_data["logical_thinking"],
                    "manner": eval_data["manner"],
                    "reason": eval_data["reason"],
                    "created_at": datetime.now(timezone.utc)
                }

                chat_ref.collection("final_report").document("data").set(final_report)
                return final_report
            except Exception as e:
                if attempt == max_retries:
                    raise LLMRetryFailedError("LLM 호출이 3회 모두 실패했습니다.: ", str(e))
                time.sleep(delay)


    def get_chat_detail(self, user_uuid: str, chat_id: str, mode: Literal["book_report", "chat_messages", "final_report"]="chat_messages"):

        chat_ref = self.get_chat_ref(user_uuid, chat_id)
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
        title, author, contents = (
            curriculum_data.get("title", ""),
            curriculum_data.get("author", ""),
            curriculum_data.get("contents", ""),
        )

        if mode == "chat_messages":
            chat_messages = self.load_messages(user_uuid, chat_id)
            return {
                "title": title,
                "author": author,
                "step": step,
                "step_idx": idx,
                "chat_messages": chat_messages
            }

            # book report
        book_report_doc = chat_ref.collection("book_report").document("data").get().to_dict()
        if book_report_doc is None:
            raise BookReportNotFoundError()
            
        if mode == "book_report":
            book_report = {
                "title": title,
                "author": author,
                "subject": book_report_doc["subject"],
                "summary": book_report_doc["summary"],
                "book_review": book_report_doc["book_review"],
                "debate_review": book_report_doc["debate_review"],
                "created_at": book_report_doc["created_at"]
            }

            return book_report

        else:
            final_report_doc = chat_ref.collection("final_report").document("data").get().to_dict()
            if final_report_doc is None:
                raise FinalReportNotFoundError()
            
            final_report = {
                "title": title,
                "author": author,
                "subject": book_report_doc["subject"],
                "gold_summary": final_report_doc["summary"],
                "students_summary": book_report_doc["summary"],
                "summary_accuracy": final_report_doc["summary_accuracy"],
                "expression": final_report_doc["expression"],
                "logical_thinking": final_report_doc["logical_thinking"],
                "manner": final_report_doc["manner"],
                "reason": final_report_doc["reason"],
                "created_at": final_report_doc["created_at"]
            }

            return final_report


    # ------------------------------------------------------
    # 책 정보 조회
    # ------------------------------------------------------
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
