"""API 서버 (FastAPI). 계약(요청·응답 형식)은 backend/API.md 참고.

실행:  cd backend && uvicorn app:app --reload --port 5001
문서:  http://127.0.0.1:5001/docs  (브라우저에서 바로 테스트 가능)
"""
import json
import logging
import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from judge import judge
from schemas import ErrorResponse, JudgeResponse, Observation
from vision import observe, prepare_image

load_dotenv()
log = logging.getLogger("uvicorn.error")
MAX_BYTES = 15 * 1024 * 1024                    # 업로드 최대 15MB

app = FastAPI(title="분리배출 판정 API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------- 오류: 모든 오류를 {"error": {"code", "message"}} 한 가지 모양으로 ----------

class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int):
        self.code, self.message, self.status = code, message, status


@app.exception_handler(ApiError)
async def handle_api_error(_, e: ApiError):
    return JSONResponse({"error": {"code": e.code, "message": e.message}}, status_code=e.status)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_, e: RequestValidationError):
    # FastAPI 기본값은 422 + {"detail": [...]}. 프론트와 약속한 형식으로 바꾼다.
    return JSONResponse({"error": {"code": "BAD_REQUEST", "message": "요청 형식이 올바르지 않아요."}},
                        status_code=400)


ERRORS = {400: {"model": ErrorResponse}, 413: {"model": ErrorResponse}, 502: {"model": ErrorResponse}}


def read_upload(f: UploadFile) -> bytes:
    """업로드 파일을 bytes로 읽는다. 15MB를 넘으면 413."""
    data = f.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ApiError("TOO_LARGE", "사진 용량이 너무 커요 (최대 15MB).", 413)
    return data


# ---------- API ----------

@app.get("/health")
def health():
    return {"ok": True}


@app.post("/judge", response_model=JudgeResponse, response_model_exclude_none=True, responses=ERRORS)
def judge_api(
    image: Optional[UploadFile] = File(None),
    attempt: int = Form(1),
    answers: str = Form("{}"),
    prev_item: Optional[str] = Form(None),
    prev_image: Optional[UploadFile] = File(None),
):
    if image is None:
        raise ApiError("NO_IMAGE", "사진이 없어요.", 400)
    attempt = max(1, attempt)
    try:
        answer_dict = json.loads(answers or "{}")
        if not isinstance(answer_dict, dict):
            raise ValueError
    except ValueError:                                  # JSONDecodeError도 ValueError의 한 종류
        raise ApiError("BAD_REQUEST", "요청 형식이 올바르지 않아요.", 400)

    # 사진은 앱에서 파일로 저장하지 않고 메모리에서만 처리한다 (개인정보)
    try:
        cur = prepare_image(read_upload(image))
        prev = prepare_image(read_upload(prev_image)) if prev_image else None
    except ValueError:
        raise ApiError("BAD_IMAGE", "사진을 읽을 수 없어요. JPG나 PNG로 다시 올려 주세요.", 400)

    try:
        observation = Observation.model_validate(observe(cur, prev)).model_dump()
    except Exception:                                   # 키 없음, 네트워크, AI가 이상한 JSON을 줌 등
        log.exception("vision failed")
        raise ApiError("AI_FAILED", "AI 분석에 실패했어요. 잠시 후 다시 시도해 주세요.", 502)

    return {"observation": observation,
            "judgement": judge(observation, attempt, answer_dict, prev_item or None)}


if __name__ == "__main__":                              # python app.py 로도 실행 가능
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=5001, reload=True)