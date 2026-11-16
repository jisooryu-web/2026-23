"""API 서버 (FastAPI). 계약(요청·응답 형식)은 backend/API.md 참고.

실행:  cd backend && uvicorn app:app --reload --port 5001
배포:  uvicorn app:app --host 0.0.0.0 --port $PORT     (Render 등의 Start Command)
문서:  http://127.0.0.1:5001/docs  (브라우저에서 바로 테스트 가능)
"""
import json
import logging
import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import ALLOWED_ORIGINS, HOST, MAX_BYTES, PORT, RATE_LIMIT_PER_MIN
from judge import LABELS, MESSAGES, item_options, judge, normalize_item, RULES
from schemas import ErrorResponse, JudgeResponse, Observation
from concurrent.futures import ThreadPoolExecutor

from vision import compare_same, observe, prepare_image

log = logging.getLogger("uvicorn.error")

app = FastAPI(title="분리배출 판정 API", version="0.3.0")


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


ERRORS = {400: {"model": ErrorResponse}, 413: {"model": ErrorResponse},
          429: {"model": ErrorResponse}, 502: {"model": ErrorResponse}}


# ---------- 요청 보호: 너무 큰 요청, 너무 잦은 요청 ----------

_recent = defaultdict(deque)                            # IP → 최근 1분 요청 시각


def _client_ip(request: Request) -> str:
    # Render·Vercel 같은 배포 환경은 프록시를 거치므로 원래 IP가 X-Forwarded-For 맨 앞에 있다
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


@app.middleware("http")
async def guard(request: Request, call_next):
    if request.method == "POST" and request.url.path == "/judge":
        # 1) 본문을 다 받기 전에 크기부터 확인 (사진 2장 + 여유)
        size = request.headers.get("content-length")
        if size and size.isdigit() and int(size) > 2 * MAX_BYTES + 1024 * 1024:
            return JSONResponse({"error": {"code": "TOO_LARGE", "message": "사진 용량이 너무 커요 (최대 15MB)."}},
                                status_code=413)
        # 2) 같은 IP의 1분 요청 수 제한 (메모리에만 기록, 서버 재시작 시 초기화)
        if RATE_LIMIT_PER_MIN > 0:
            now, q = time.monotonic(), _recent[_client_ip(request)]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= RATE_LIMIT_PER_MIN:
                return JSONResponse({"error": {"code": "RATE_LIMITED",
                                               "message": "요청이 너무 많아요. 잠시 후 다시 시도해 주세요."}},
                                    status_code=429)
            q.append(now)
    return await call_next(request)


# CORS는 guard보다 나중에 등록해야 바깥쪽에서 감싼다 → 413·429 응답에도 CORS 헤더가 붙어
# 브라우저가 "CORS 오류" 대신 실제 안내 문구("요청이 너무 많아요")를 보여 줄 수 있다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
log.info("CORS allowed origins: %s", ALLOWED_ORIGINS)


def read_upload(f: UploadFile) -> bytes:
    """업로드 파일을 bytes로 읽는다. 15MB를 넘으면 413."""
    data = f.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ApiError("TOO_LARGE", "사진 용량이 너무 커요 (최대 15MB).", 413)
    return data


def _same_item(prev: bytes, cur: bytes) -> str:
    """같은 물건 비교는 실패해도 판정을 막지 않는다 (모르면 unknown → 품목이 이어지는지만 본다)"""
    try:
        return compare_same(prev, cur)
    except Exception:
        log.warning("same-item check failed", exc_info=True)
        return "unknown"


# ---------- API ----------

@app.get("/health")
def health():
    return {"ok": True}


@app.get("/items")
def items():
    """품목 직접 선택 목록 ("품목이 달라요" 버튼). 고른 값은 answers의 item_hint로 보낸다"""
    return {"text": MESSAGES["pick_item_question"], "items": item_options()}


@app.post("/judge", response_model=JudgeResponse, response_model_exclude_none=True, responses=ERRORS)
def judge_api(
    image: Optional[UploadFile] = File(None),
    attempt: int = Form(1),
    answers: str = Form("{}"),
    prev_item: Optional[str] = Form(None),
    prev_image: Optional[UploadFile] = File(None),
    observation: Optional[str] = Form(None),
):
    started = time.perf_counter()
    if image is None and observation is None:
        raise ApiError("NO_IMAGE", "사진이 없어요.", 400)
    attempt = max(1, attempt)
    try:
        answer_dict = json.loads(answers or "{}")
        if not isinstance(answer_dict, dict):
            raise ValueError
    except ValueError:                                  # JSONDecodeError도 ValueError의 한 종류
        raise ApiError("BAD_REQUEST", "요청 형식이 올바르지 않아요.", 400)

    if observation is not None:
        # 질문에 답한 재판정: 사진은 그대로이니 직전 관찰을 다시 쓰고 AI는 부르지 않는다
        try:
            obs = Observation.model_validate_json(observation).model_dump()
        except ValueError:
            raise ApiError("BAD_REQUEST", "요청 형식이 올바르지 않아요.", 400)
    else:
        # 사진은 앱에서 파일로 저장하지 않고 메모리에서만 처리한다 (개인정보)
        try:
            cur = prepare_image(read_upload(image))
        except ValueError:
            raise ApiError("BAD_IMAGE", "사진을 읽을 수 없어요. JPG나 PNG로 다시 올려 주세요.", 400)
        try:
            prev = prepare_image(read_upload(prev_image)) if prev_image else None
        except ValueError:                              # 처음 사진만 깨졌으면 비교 없이 지금 사진으로 판정
            log.warning("prev_image unreadable, judging without comparison")
            prev = None

        # 사용자가 품목을 직접 고른 경우(인식 실패 화면에서) → AI에게 알려 주고 그 품목으로 확정
        hint = str(answer_dict.get("item_hint") or "").strip().upper() or None
        # 재촬영이면 품목은 처음 판정 그대로 두고 상태만 새로 본다.
        # 매번 품목을 새로 인식하면 같은 물건인데도 품목이 바뀌어(배달 용기 ↔ 컵라면 용기) '다른 물건'으로 끝나는 일이 있었다.
        # 다른 물건인지는 아래의 같은 물건 비교와 사용자 확인으로만 판단한다.
        if not hint and prev and prev_item and prev_item.strip().upper() in RULES:
            hint = prev_item.strip().upper()
        # 재촬영이면 '지금 사진 관찰'과 '같은 물건인지 비교'를 따로, 동시에 부른다.
        # 한 번에 두 장을 주고 관찰까지 시키면, 처음 사진의 라벨을 지금 사진에도 있다고 답하는 일이 있었다.
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                same = pool.submit(_same_item, prev, cur) if prev else None
                raw = observe(cur, None, hint) if hint else observe(cur)
                same = same.result() if same else "unknown"
            if isinstance(raw, dict):
                raw = dict(raw)                         # 받은 결과를 직접 고치지 않고 복사해서 쓴다
            if isinstance(raw, dict) and same != "unknown":
                raw["same_item"] = same
            if hint and hint in RULES and isinstance(raw, dict):
                raw.update(item=hint, confidence=1.0)
            obs = Observation.model_validate(raw).model_dump()
            obs["item"] = normalize_item(obs["item"])       # "plastic_film_bag" → "P10"
        except Exception:                               # 키 없음, 네트워크, AI가 이상한 JSON을 줌 등
            log.exception("vision failed")
            raise ApiError("AI_FAILED", "AI 분석에 실패했어요. 잠시 후 다시 시도해 주세요.", 502)

    result = judge(obs, attempt, answer_dict, prev_item or None)
    # 요청마다 한 줄 기록 (사진·개인정보 없음). 실제 사용 중 정확도·속도를 볼 수 있다
    log.info("judge %s", json.dumps({
        "status": result["status"], "item": obs["item"], "confidence": obs["confidence"],
        "attempt": attempt, "reused": observation is not None, "same": obs.get("same_item"), "subject": obs.get("subject", ""), "notes": (obs.get("notes") or "")[:150],
        "ms": round((time.perf_counter() - started) * 1000),
    }, ensure_ascii=False))
    labels = {k: LABELS[k] for k in obs.get("observations") or {} if k in LABELS}
    return {"observation": obs, "judgement": result, "labels": labels}


if __name__ == "__main__":                              # python app.py 로도 실행 가능 (개발용, 코드 바꾸면 자동 재시작)
    import uvicorn
    uvicorn.run("app:app", host=HOST, port=PORT, reload=True)