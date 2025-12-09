from app.core.database import db
from typing import Dict, Any, List


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

