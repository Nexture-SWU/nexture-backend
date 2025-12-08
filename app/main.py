import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from langchain_openai import ChatOpenAI

from app.services.chat_service import FirebaseChatService

from app.api import (auth, user, chat)
from app.config.errors import *

# FastAPI 앱 생성
app = FastAPI(
    title="nexture",
    version="1.0.0",
    description="A simple FastAPI example with clean structure.",
)

# 
app.state.llm = ChatOpenAI(
    model=os.getenv("OPENAI_API_MODEL", "gpt-4o-mini"),
    api_key=os.getenv("OPENAI_API_KEY")
)
app.state.chat_service = FirebaseChatService()

# CORS 설정 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(auth.router)
app.include_router(user.router)
app.include_router(chat.router)

@app.get("/api/healthz")
def health_check():
    return {"status": "ok"}

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="nexture",
        version="1.0.0",
        description="API 문서",
        routes=app.routes,
    )

    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        }
    }
    for path in openapi_schema["paths"].values():
        for method in path.values():
            method.setdefault("security", [{"BearerAuth": []}])

    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

def make_handler(status_code: int, default_detail: str):
    async def handler(request: Request, exc: Exception):
        detail = str(exc) or default_detail
        return JSONResponse(status_code=status_code, content={"detail": detail})
    return handler

app.add_exception_handler(ChatNotFoundError, make_handler(404, "채팅방을 찾을 수 없습니다."))
app.add_exception_handler(BookReportNotFoundError, make_handler(404, "감상문을 찾을 수 없습니다."))
app.add_exception_handler(FinalReportNotFoundError, make_handler(404, "최종 보고서를 찾을 수 없습니다."))
app.add_exception_handler(CurriculumNotFoundError, make_handler(500, "커리큘럼 데이터가 없습니다."))
app.add_exception_handler(InvalidChatStateError, make_handler(400, "잘못된 토론 상태입니다."))
app.add_exception_handler(LLMRetryFailedError, make_handler(500, "LLM 재시도 실패"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)