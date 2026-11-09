"""관찰 결과 + 규칙표 → 판정. 배출 기준은 전부 rules.json에서만 가져온다.

status 종류 (프론트 화면 분기 기준, API.md 참고)
  pass           통과 → 배출 방법 안내
  need_action    처리할 일이 남음 → 체크리스트 + 재촬영
  retake         AI가 일부를 못 봄 → 다시 찍기
  question       사진으로 알 수 없는 것 → 질문
  fallback       재촬영 한도 도달 → 대체 배출 방법으로 종료
  different_item 처음과 다른 물건을 찍음 → 같은 물건 다시
  unsupported    지원하지 않는 품목
"""
import json, os

MAX_ATTEMPTS = 3
with open(os.path.join(os.path.dirname(__file__), "rules.json"), encoding="utf-8") as f:
    RULES = json.load(f)

# 질문 선택지 기본값. 조건마다 rules.json의 "options"로 바꿀 수 있음
# 예: "내용물을 비우셨나요?" → [{"label": "예", "value": "false"}, {"label": "아니요", "value": "true"}]
DEFAULT_OPTIONS = [{"label": "예", "value": "true"}, {"label": "아니요", "value": "false"}]

MESSAGES = {
    "pass": "분리배출할 수 있어요!",
    "need_action": "버리기 전에 아래 항목을 처리하고 다시 찍어 주세요.",
    "retake": "잘 보이지 않는 부분이 있어요. 밝은 곳에서, 안쪽이 보이게 다시 찍어 주세요.",
    "question": "사진으로는 확인하기 어려운 부분이 있어요. 아래 질문에 답해 주세요.",
    "fallback": "여러 번 확인했지만 처리가 어려워 보여요. 아래 방법으로 배출해 주세요.",
    "different_item": "처음 찍은 물건과 다른 물건 같아요. 같은 물건을 다시 찍어 주세요.",
    "unsupported": "아직 지원하지 않는 품목이에요.",
}


def _done(out, status):
    out["status"] = status
    out["message"] = MESSAGES[status]
    return out


def judge(result, attempt=1, answers=None, prev_item=None):
    """result: vision.observe() 결과
    attempt: 몇 번째 촬영인지 (1부터)
    answers: 질문 답 {key: "true"/"false"}
    prev_item: 재촬영이면 처음 판정된 품목 (같은 물건인지 확인용)"""
    answers = answers or {}
    item = result.get("item", "unsupported")
    out = {"item": item, "attempt": attempt, "max_attempts": MAX_ATTEMPTS,
           "checklist": [], "questions": [], "retake": [], "warnings": []}

    if item not in RULES:
        return _done(out, "unsupported")

    # 재촬영인데 다른 물건이면 판정하지 않음 (깨끗한 다른 병으로 통과하는 꼼수 방지)
    if prev_item and (item != prev_item or result.get("same_item") == "false"):
        return _done(out, "different_item")

    rule, obs = RULES[item], result.get("observations", {})
    out.update({"name": rule["name"], "type": rule["type"], "disposal": rule["disposal"],
                "warnings": rule["warnings"], "source": rule["source"]})

    if rule["type"] == "info":
        return _done(out, "pass")

    for c in rule["checks"]:
        value = answers.get(c["key"]) if c["method"] == "question" else obs.get(c["key"], "unknown")
        if value is None:                       # 아직 안 물어본 질문
            out["questions"].append({"key": c["key"], "text": c["question"],
                                     "options": c.get("options", DEFAULT_OPTIONS)})
        elif value == "unknown":                # 사진으로 판단 못 함
            out["retake"].append(c["key"])
        elif value != c["ok"]:
            if "redirect_disposal" in c:        # 처리로 해결 안 되는 조건 → 배출처 변경
                out["disposal"] = c["redirect_disposal"]
            else:
                out["checklist"].append({"key": c["key"], "text": c["action"]})

    if out["questions"]:
        return _done(out, "question")
    if out["checklist"] or out["retake"]:
        if attempt >= MAX_ATTEMPTS:             # 재촬영 한도 → 대체 안내로 종료
            out["disposal"] = rule["fallback_disposal"]
            return _done(out, "fallback")
        return _done(out, "need_action" if out["checklist"] else "retake")
    return _done(out, "pass")
