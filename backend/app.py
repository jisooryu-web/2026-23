"""POST /judge  (form-data: image 파일, attempt 숫자)"""
import json, os, tempfile
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from vision import observe, prepare_image
from judge import judge
from flask_cors import CORS

load_dotenv()
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024
CORS(app, origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(","))

def error(code, message, http_status):
    return jsonify({"error": {"code": code, "message": message}}), http_status

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/judge")
def judge_api():
    image = request.files["image"]
    if image is None:
        return error("NO_IMAGE", "사진이 없어요.", 400)
    try:
        attempt = max(1, int(request.form.get("attempt", 1)))
        answer = json.loads(request.form.get("answers") or "{}")
    except (ValueError, json.JSONDecodeError):
        return error("BAD_REQUEST", "요청 형식이 올바르지 않아요.", 400)
    prev_item = request.form.get("prev_item") or None
    prev_file = request.files.get("prev_image")
    try:
        cur = prepare_image(image.read())
        prev = prepare_image(prev_file.read()) if prev_file else None
    except ValueError:
        return error("BAD_IMAGE", "사진을 읽을 수 없어요. JPG나 PNG로 다시 올려 주세요.", 400)

    try:
        observation = observe(cur, prev)
    except Exception:                             # API 키 없음, 네트워크, 모델 오류 등
        app.logger.exception("vision failed")
        return error("AI_FAILED", "AI 분석에 실패했어요. 잠시 후 다시 시도해 주세요.", 502)

    return jsonify({"observation": observation,
                    "judgement": judge(observation, attempt, answers, prev_item)})

@app.errorhandler(413)
def too_large(_):
    return error("TOO_LARGE", "사진 용량이 너무 커요 (최대 15MB).", 413)


if __name__ == "__main__":
    app.run(port=5000, debug=True)
