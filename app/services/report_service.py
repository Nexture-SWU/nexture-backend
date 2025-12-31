from app.core.database import db
from typing import Dict, Any, List, Literal
import time
from datetime import datetime, timezone
import json
from app.config.errors import *
from langchain_core.messages import HumanMessage, AIMessage
from ast import literal_eval


class ReportService:
    # ==========================================
    # 0) helper 함수
    # ==========================================
    def _get_chat_ref(self, user_uuid: str, chat_id: str):
        return (
            db.collection("users").document(user_uuid)
            .collection("chats").document(chat_id)
        )
    
    def _llm_retry(self, llm, system_prompt: str, user_prompt: str, retries=3, delay=1):
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

    def _final_reports_to_text(self, reports: list[dict]) -> str:
        lines = []

        for idx, report in enumerate(reports, start=1):
            title = report.get("title", "").strip()
            author = report.get("author", "").strip()

            expression = report.get("expression", "")
            summary_accuracy = report.get("summary_accuracy", "")
            manner = report.get("manner", "")
            reason = report.get("reason", "").strip()

            block = (
                f"{idx}. {title}-{author}\n"
                f"- 표현력: {expression}점\n"
                f"- 요약능력: {summary_accuracy}점\n"
                f"- 학습태도: {manner}점\n"
                f"- 총평: {reason}"
            )

            lines.append(block)

        return "\n\n".join(lines)
    
    def _load_messages(self, user_uuid: str, chat_id: str):
        ref = (
            db.collection("users").document(user_uuid)
            .collection("chats").document(chat_id)
            .collection("messages")
        )
        docs = ref.order_by("timestamp").stream()

        return [{"role": d.to_dict()["role"], "content": d.to_dict()["content"]} for d in docs]
    
    
    # ================================
    # 감상문 저장
    # ================================
    def create_book_report(self, user_uuid: str, chat_id: str, subject: str, summary: str, book_review: str, debate_review: str):
        ref = self._get_chat_ref(user_uuid, chat_id).collection("book_report").document("data")

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

        chat_ref = self._get_chat_ref(user_uuid, chat_id)
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

        messages = self._load_messages(user_uuid, chat_id)

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
        summary = self._llm_retry(llm, summary_prompt_system, summary_prompt_user)

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

                raw_eval = self._llm_retry(llm, eval_system, eval_user)
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
    # ==========================================
    # 2) final_report가 존재하는 모든 작품의 점수 반환
    # ==========================================
    def list_all_final_reports(self, user_uuid: str) -> List[Dict[str, Any]]:
        """
        특정 user_uuid 의 모든 chat 중 final_report 가 있는 항목을 반환
        """
        chats_ref = db.collection("users").document(user_uuid).collection("chats")
        chat_docs = chats_ref.order_by("created_at", direction="DESCENDING").stream()

        results = []

        for chat_doc in chat_docs:
            chat_id = chat_doc.id

            # final_report 존재 여부 확인
            final_doc = (
                chats_ref.document(chat_id)
                .collection("final_report")
                .document("data")
                .get()
            )

            if not final_doc.exists:
                continue  # final_report 없는 채팅은 스킵

            final_data = final_doc.to_dict()

            results.append({
                "chat_id": chat_id,
                "title": final_data.get("title", ""),
                "author": final_data.get("author", ""),
                "summary_accuracy": final_data.get("summary_accuracy"),
                "expression": final_data.get("expression"),
                "logical_thinking": final_data.get("logical_thinking"),
                "manner": final_data.get("manner"),
                "reason": final_data.get("reason"),
                "created_at": final_data.get("created_at"),
            })

        return results
    
    # ==========================================
    # 3) book_report가 존재하는 모든 작품의 점수 반환
    # ==========================================
    def list_all_book_reports(self, user_uuid: str) -> List[Dict[str, Any]]:
        """
        특정 user_uuid 의 모든 chat 중 final_report 가 있는 항목을 반환
        """
        chats_ref = db.collection("users").document(user_uuid).collection("chats")
        chat_docs = chats_ref.order_by("created_at", direction="DESCENDING").stream()

        results = []

        for chat_doc in chat_docs:
            chat_id = chat_doc.id

            book_doc = (
                chats_ref.document(chat_id)
                .collection("book_report")
                .document("data")
                .get()
            )

            if not book_doc.exists:
                continue  # book_doc 없는 채팅은 스킵

            final_data = book_doc.to_dict()

            results.append({
                "subject": final_data.get("subject", ""),
                "book_review": final_data.get("book_review", ""),
                "debate_review": final_data.get("debate_review", ""),
                "summary": final_data.get("summary"),
                "created_at": final_data.get("created_at"),
            })

        return results
    
    def get_total_report(self, user_uuid: str):
        snap = (
            db.collection("users")
            .document(user_uuid)
            .collection("total_report")
            .document("data")
            .get()
        )

        if not snap.exists:
            return None

        return snap.to_dict()
    
    
    def create_total_report(self, llm, user_uuid: str):
        user_ref = db.collection("users").document(user_uuid)

        # ================================
        # 1. 기존 total_report 조회
        # ================================
        total_report_ref = (
            user_ref
            .collection("total_report")
            .document("data")
        )

        existing_snap = total_report_ref.get()
        existing_data = existing_snap.to_dict() if existing_snap.exists else None
        existing_reports = existing_data.get("reports") if existing_data else None

        # ================================
        # 2. 최신 final_report 최대 4개 수집
        # ================================
        chats_docs = (
            user_ref
            .collection("chats")
            .order_by("created_at", direction="DESCENDING")
            .stream()
        )

        final_reports = []

        for chat_doc in chats_docs:
            data_doc = (
                chat_doc.reference
                .collection("final_report")
                .document("data")
                .get()
            )

            if data_doc.exists:
                final_reports.append(data_doc.to_dict())

            if len(final_reports) == 4:
                break

        # ================================
        # 3. reports 변경 여부 비교
        # ================================
        def normalize(obj):
            return json.dumps(
                obj,
                ensure_ascii=False,
                sort_keys=True,
                default=str  # DatetimeWithNanoseconds 대응
            )

        if existing_reports is not None:
            if normalize(existing_reports) == normalize(final_reports):
                # ✅ 동일하면 재생성 안 함
                return existing_data

        # ================================
        # 4. LLM 호출
        # ================================
        
        final_reports_to_text = self._final_reports_to_text(final_reports)
        system_prompt = f"""
        당신은 한국인 아동 독서 토론 교육 전문가입니다. 
        입력정보를 보고 학생의 장점과 개선점을 작성하여 주세요. 개선점 작성시에는 태도, 사고력, 논리력, 상상력, 창의력 등의 측면에서 작성해주세요.
        한국어 외 다른 언어는 절대 사용하지 마세요.
        **출력물은 반드시 아래 JSON 형식으로 작성해 주세요.** 
        [출력 JSON 형식] 
        {{ "pros": "문자열", # 구체적인 피드백을 1~2 문장으로 설명, 말투는 비격식 존대(해요체)로 작성 
            "cons": "문자열"  # 구체적인 피드백을 1~2 문장으로 설명, 말투는 비격식 존대(해요체)로 작성 
        }}
        """
        user_prompt = f""" 
        [입력정보] 
        다음은 학생의 독서토론 결과를 평가한 {len(final_reports)}개의 보고서들입니다.
        {final_reports_to_text}
        """
        raw_total_report = self._llm_retry(llm, system_prompt, user_prompt)

        processed_total_report = raw_total_report.replace('```json', '').replace('```python', '').replace('```', '').strip()
        processed_total_report = processed_total_report.replace('true', 'True').replace('false', 'False')
        start = None
        depth = 0

        for i, ch in enumerate(processed_total_report):
            if ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                if depth > 0:
                    depth -= 1
                    if depth == 0 and start is not None:
                        json_str = processed_total_report[start:i+1]
                        break
        else:
            print(processed_total_report)
            raise ValueError("JSON 객체를 찾지 못했습니다.")
        
        json_str = json_str.replace('다요.', '다.').replace('요요.', '요.')
        total_report_dict = literal_eval(json_str)
        total_report = {
            "pros": total_report_dict["pros"],
            "cons": total_report_dict["cons"],
            "reports": final_reports
        }
        user_ref.collection("total_report").document("data").set(total_report)

        return total_report
            
    def get_report_detail(self, user_uuid: str, chat_id: str, mode: Literal["book_report", "final_report"]):

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
        title, author, contents = (
            curriculum_data.get("title", ""),
            curriculum_data.get("author", ""),
            curriculum_data.get("contents", ""),
        )

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
        

        
