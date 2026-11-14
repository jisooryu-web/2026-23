"""AI 호출 없이 API(app.py)만 검사. 실행: python tests/test_api.py
AI 대신 정해진 관찰 결과를 돌려주는 가짜 함수를 끼워 넣는다."""
import io, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from fastapi.testclient import TestClient
from PIL import Image

import app as server

FAKE = {"item": "P01", "confidence": 0.9, "same_item": "unknown",
        "observations": {"is_clear": "true", "label": "absent", "liquid": "absent"},
        "notes": "fake"}
server.observe = lambda cur, prev=None: FAKE          # AI 대신 가짜 관찰
client = TestClient(server.app)


def jpg():
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(buf, format="JPEG")
    return ("p.jpg", buf.getvalue(), "image/jpeg")


def status_of(res):
    body = res.json()
    return body["judgement"]["status"] if res.status_code == 200 else body["error"]["code"]


# (이름, 요청 함수, 기대 HTTP 코드, 기대 status 또는 오류 code)
cases = [
    ("서버 확인", lambda: client.get("/health"), 200, None),
    ("첫 판정: 체크박스 질문", lambda: client.post("/judge", files={"image": jpg()}, data={"attempt": "1"}), 200, "question"),
    ("체크하고 다시 판정 → 통과", lambda: client.post("/judge", files={"image": jpg()}, data={"attempt": "1", "answers": '{"checkbox": "true"}'}), 200, "pass"),
    ("사진 없음", lambda: client.post("/judge", data={"attempt": "1"}), 400, "NO_IMAGE"),
    ("attempt가 숫자 아님", lambda: client.post("/judge", files={"image": jpg()}, data={"attempt": "abc"}), 400, "BAD_REQUEST"),
    ("answers가 JSON 아님", lambda: client.post("/judge", files={"image": jpg()}, data={"answers": "{oops"}), 400, "BAD_REQUEST"),
    ("이미지가 아닌 파일", lambda: client.post("/judge", files={"image": ("a.jpg", b"not image", "image/jpeg")}), 400, "BAD_IMAGE"),
    ("재촬영: 다른 품목", lambda: client.post("/judge", files={"image": jpg(), "prev_image": jpg()},
                                         data={"attempt": "2", "prev_item": "I01"}), 200, "different_item"),
]

failed = 0
for name, call, code, expected in cases:
    res = call()
    ok = res.status_code == code and (expected is None or status_of(res) == expected)
    failed += not ok
    print("O" if ok else "X", name, "→", res.status_code, "" if expected is None else status_of(res))

# 응답에 None 값이 섞여 나가지 않는지 (unsupported면 name 등이 아예 빠져야 함)
server.observe = lambda cur, prev=None: {"item": "X00"}
res = client.post("/judge", files={"image": jpg()})
ok = res.status_code == 200 and "name" not in res.json()["judgement"]
failed += not ok
print("O" if ok else "X", "지원 안 하는 품목은 name 없이 응답 →", res.json()["judgement"]["status"])


# AI가 품목을 확신하지 못하면 확인 질문
server.observe = lambda cur, prev=None: {**FAKE, "confidence": 0.3}
res = client.post("/judge", files={"image": jpg()})
q = res.json()["judgement"]["questions"]
ok = res.status_code == 200 and q and q[0]["key"] == "confirm_P01"
failed += not ok
print("O" if ok else "X", "확신 낮음 → 품목 확인 질문 →", q[0]["text"] if q else None)


# 질문에 답할 때 직전 관찰을 보내면 AI를 부르지 않음 (사진도 필요 없음)
calls = []
server.observe = lambda cur, prev=None: calls.append(1) or FAKE
res = client.post("/judge", data={"observation": json.dumps(FAKE), "answers": '{"checkbox": "true"}'})
ok = res.status_code == 200 and status_of(res) == "pass" and not calls
failed += not ok
print("O" if ok else "X", "관찰 재사용 → AI 호출 없이 판정 →", status_of(res), "/ AI 호출", len(calls), "회")


# AI가 실패하면 502
def broken(cur, prev=None):
    raise RuntimeError("no key")
server.observe = broken
res = client.post("/judge", files={"image": jpg()})
ok = res.status_code == 502 and status_of(res) == "AI_FAILED"
failed += not ok
print("O" if ok else "X", "AI 실패 →", res.status_code, status_of(res))

total = len(cases) + 4
print(f"\n{total - failed}/{total} 통과")
sys.exit(1 if failed else 0)