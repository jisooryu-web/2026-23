"""POST /judge  (form-data: image 파일, attempt 숫자)"""
import os, tempfile
from flask import Flask, request, jsonify
from vision import observe
from judge import judge
from flask_cors import CORS

CORS(app, origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(","))

app = Flask(__name__)


@app.post("/judge")
def judge_api():
    f = request.files["image"]
    attempt = int(request.form.get("attempt", 1))
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        f.save(tmp.name)
    try:
        result = observe(tmp.name)
    finally:
        os.remove(tmp.name)                     # 사진은 저장하지 않는다
    return jsonify({"observation": result, "judgement": judge(result, attempt)})


if __name__ == "__main__":
    app.run(port=5000, debug=True)
