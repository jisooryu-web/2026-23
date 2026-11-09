"""API 서버. 계약(요청·응답 형식)은 backend/API.md 참고.

실행:  cd backend && python app.py   → http://localhost:5000
"""
import json, os
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
from vision import observe, prepare_image
from judge import judge

load_dotenv()
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024        # 업로드 최대 15MB
CORS(app, origins=[o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")])


def error(code, message, http_status):
    return jsonify({"error": {"code": code, "message": message}}), http_status


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/judge")
def judge_api():
    image = request.files.get("image")
    if image is None:
        return error("NO_IMAGE", "사진이 없어요.", 400)

    try:
        attempt = max(1, int(request.form.get("attempt", 1)))
        answers = json.loads(request.form.get("answers") or "{}")
    except (ValueError, json.JSONDecodeError):
        return error("BAD_REQUEST", "요청 형식이 올바르지 않아요.", 400)
    prev_item = request.form.get("prev_item") or None
    prev_file = request.files.get("prev_image")

    # 사진은 메모리에서만 처리하고 디스크에 저장하지 않는다 (개인정보)
    try:
        cur = prepare_image(image.read())
        prev = prepare_image(prev_file.read()) if prev_file else None
    except ValueError:
        return error("BAD_IMAGE", "사진을 읽을 수 없어요. JPG나 PNG로 다시 올려 주세요.", 400)

    try:
        observation = observe(cur, prev)
    except Exception as e:                        # API 키 없음, 네트워크, 모델 오류 등
        app.logger.exception("vision failed")
        return error("AI_FAILED", "AI 분석에 실패했어요. 잠시 후 다시 시도해 주세요.", 502)

    return jsonify({"observation": observation,
                    "judgement": judge(observation, attempt, answers, prev_item)})


@app.errorhandler(413)
def too_large(_):
    return error("TOO_LARGE", "사진 용량이 너무 커요 (최대 15MB).", 413)


if __name__ == "__main__":
    app.run(port=5001, debug=True)
