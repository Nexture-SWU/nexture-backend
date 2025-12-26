from app.core.database import db
from typing import Dict, Any, List
import time
import json
from app.config.errors import *
from langchain_core.messages import HumanMessage, AIMessage
from ast import literal_eval


class ReportService:
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


    def llm_retry(self, llm, system_prompt: str, user_prompt: str, retries=3, delay=1):
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

    def reports_to_text(self, reports: list[dict]) -> str:
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
        
        final_reports_to_text = self.reports_to_text(final_reports)
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
        raw_total_report = self.llm_retry(llm, system_prompt, user_prompt)

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
            
            
        
        

        
