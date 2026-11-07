"""관찰 결과 + 규칙표 → 판정. 배출 기준은 전부 rules.json에서만 가져온다."""
import json, os

MAX_ATTEMPTS = 3
with open(os.path.join(os.path.dirname(__file__), "rules.json"), encoding="utf-8") as f:
    RULES = json.load(f)


def judge(result, attempt=1, answers=None):
    """result: vision.observe() 결과, attempt: 몇 번째 촬영인지, answers: 질문 답 {key: "true"/"false"}"""
    answers = answers or {}
    item = result.get("item", "unsupported")
    if item not in RULES:
        return {"status": "unsupported", "message": "지원하지 않는 품목입니다"}

    rule, obs = RULES[item], result.get("observations", {})
    out = {"item": item, "name": rule["name"], "attempt": attempt,
           "disposal": rule["disposal"], "warnings": rule["warnings"], "source": rule["source"],
           "checklist": [], "questions": [], "retake": []}

    if rule["type"] == "info":
        out["status"] = "pass"
        return out

    for c in rule["checks"]:
        value = answers.get(c["key"]) if c["method"] == "question" else obs.get(c["key"], "unknown")
        if value is None:                       # 아직 안 물어본 질문
            out["questions"].append({"key": c["key"], "text": c["question"]})
        elif value == "unknown":                # 사진으로 판단 못 함
            out["retake"].append(c["key"])
        elif value != c["ok"]:
            if "redirect_disposal" in c:        # 처리로 해결 안 되는 조건 → 배출처 변경
                out["disposal"] = c["redirect_disposal"]
            else:
                out["checklist"].append({"key": c["key"], "text": c["action"], "done": False})

    if out["questions"]:
        out["status"] = "question"
    elif out["checklist"]:
        if attempt >= MAX_ATTEMPTS:             # 재촬영 한도 → 대체 안내로 종료
            out["status"] = "fallback"
            out["disposal"] = rule["fallback_disposal"]
        else:
            out["status"] = "need_action"
    elif out["retake"]:
        out["status"] = "retake"
        out["message"] = "밝은 곳에서, 안쪽이 보이게 다시 찍어 주세요"
    else:
        out["status"] = "pass"
    return out
