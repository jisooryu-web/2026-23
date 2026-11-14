"""관찰 결과 + 판정기준표(rules.json) → 판정. 배출 기준은 전부 rules.json에서만 가져온다.

status 종류 (프론트 화면 분기 기준, API.md 참고)
  pass           통과 → 배출 방법 안내 (정보 안내형 품목도 pass)
  need_action    처리할 일이 남음 → 체크리스트 + 재촬영
  retake         AI가 일부를 못 봄 → 다시 찍기
  question       사진으로 알 수 없는 것 → 질문 (품목 확인, 체크박스, 정보 안내형 질문)
  fallback       재촬영 한도 도달 또는 오염도 5단계 → 대체 안내로 종료
  different_item 처음과 다른 물건을 찍음 → 같은 물건 다시
  unsupported    지원하지 않는 품목 (X00)

조건 종류 (기준표 '구분')
  required       필수. 미통과면 체크리스트, unknown이면 조건표의 'unknown 시'(retake/fail/ignore)
  tip            권고. 미통과면 팁으로만 표시 (재촬영 유발 안 함)
  branch         분기. 통과 값이 아니면 다른 품목(to)이나 배출처(to_disposal)로 전환
  contamination  오염도 1~5단계. 단계별 결과는 rules.json의 contamination
"""
import json, os

from config import CONFIRM_BELOW, MAX_ATTEMPTS
from schemas import UNSUPPORTED, RuleSet, clean_observations

with open(os.path.join(os.path.dirname(__file__), "rules.json"), encoding="utf-8") as f:
    RULESET = RuleSet.model_validate(json.load(f))   # 구조가 틀리면 여기서 바로 오류 (서버가 안 켜짐)
RULES = RULESET.items                                # {"P01": Rule, ...}
MESSAGES = RULESET.messages                          # 화면 문구도 rules.json에서
LEVELS = RULESET.contamination                       # 오염도 5단계

YES_NO = [{"label": "예", "value": "true"}, {"label": "아니요", "value": "false"}]
CHECKBOX_KEY = "checkbox"                            # answers에서 체크박스 답의 키


def _norm(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v).strip().lower()


def _related(a, b):
    """같은 물건으로 볼 수 있는 품목인지 (분기로 이어진 품목: P01↔P02, P07↔I06)"""
    if a == b:
        return True
    to = lambda x: {c.to for c in RULES[x].conditions if c.to} if x in RULES else set()
    return b in to(a) or a in to(b)


def _done(out, status, message=None):
    out["status"] = status
    out["message"] = message or MESSAGES[status]
    return out


def judge(result, attempt=1, answers=None, prev_item=None):
    """result: Observation 모양의 dict (item, confidence, same_item, observations)
    attempt: 몇 번째 촬영인지 (1부터)
    answers: 질문 답 {"checkbox": "true", "confirm_P01": "true", "ice_content": "gel", ...}
    prev_item: 재촬영이면 처음 판정된 품목 (같은 물건인지 확인용)"""
    answers = {k: _norm(v) for k, v in (answers or {}).items()}
    item = str(result.get("item") or UNSUPPORTED).strip().upper()
    out = {"item": item, "attempt": attempt, "max_attempts": MAX_ATTEMPTS,
           "checklist": [], "questions": [], "retake": [], "tips": [], "warnings": []}

    if item not in RULES:
        return _done(out, "unsupported", MESSAGES["not_confirmed"] if item == "UNKNOWN" else None)

    # 재촬영인데 다른 물건이면 판정하지 않음 (깨끗한 다른 병으로 통과하는 꼼수 방지)
    if prev_item and (not _related(item, prev_item.strip().upper()) or result.get("same_item") == "false"):
        return _done(out, "different_item")

    # AI가 품목을 확신하지 못하면, 기준을 적용하기 전에 사용자에게 품목부터 확인
    confirm_key = f"confirm_{item}"
    confidence = result.get("confidence")
    if confidence is not None and confidence < CONFIRM_BELOW:
        answer = answers.get(confirm_key)
        if answer not in ("true", "false"):
            out.update(name=RULES[item].name)
            out["questions"].append({"key": confirm_key, "options": YES_NO,
                                     "text": MESSAGES["confirm_question"].replace("{name}", RULES[item].name)})
            return _done(out, "question")
        if answer == "false":
            return _done(out, "unsupported", MESSAGES["not_confirmed"])

    return _evaluate(item, clean_observations(result.get("observations")), attempt, answers, out)


def _evaluate(item, obs, attempt, answers, out):
    rule = RULES[item]
    out.update({"item": item, "name": rule.name, "type": rule.type, "disposal": rule.disposal,
                "warnings": list(rule.warnings), "source": rule.source})
    if rule.type == "info":
        return _info(rule, obs, answers, out)

    checkbox, checkbox_action = rule.checkbox, rule.checkbox_action
    for c in rule.conditions:
        value = obs.get(c.key, "unknown")

        if c.kind == "contamination":
            if value == "unknown":
                if c.unknown == "retake":
                    out["retake"].append(c.key)
                continue
            level = LEVELS[value]
            if level.result == "discard":              # 5단계: 세척으로 해결 안 됨 → 바로 대체 안내
                out["disposal"] = rule.fallback_disposal
                return _done(out, "fallback", level.text)
            if level.result == "fail":
                out["checklist"].append({"key": c.key, "text": level.text})
            elif level.result == "checkbox":           # 2단계: 헹굼 체크 시 통과
                checkbox, checkbox_action = level.checkbox, level.text
            continue

        if value in c.pass_:
            continue
        if value == "unknown" and c.unknown != "branch":
            if c.kind == "tip" or c.unknown == "ignore":
                continue
            if c.unknown == "retake":
                out["retake"].append(c.key)
                if c.kind == "branch":                 # 어느 품목 기준을 쓸지 모르면 나머지는 보지 않고 재촬영
                    out["checklist"] = []
                    break
                continue
            # unknown == "fail": 보이지 않으면 미통과로 (보수적 판정)

        if c.kind == "branch":
            if c.to:                                   # 다른 품목으로 전환해 처음부터 다시 판정
                fresh = {k: out[k] for k in ("attempt", "max_attempts")}
                fresh.update({"checklist": [], "questions": [], "retake": [], "tips": [], "warnings": []})
                return _evaluate(c.to, obs, attempt, answers, fresh)
            out["disposal"] = c.to_disposal            # 배출처만 바뀌고 끝
            return _done(out, "pass", c.to_message)
        if c.kind == "tip":
            out["tips"].append(c.action)
        else:
            out["checklist"].append({"key": c.key, "text": c.action})

    checked = answers.get(CHECKBOX_KEY) == "true"
    if out["checklist"] or out["retake"]:
        # 처리할 일이 있으면 체크박스도 체크리스트에 함께 (다시 찍을 때 체크하면 재질문 안 함)
        if out["checklist"] and checkbox and not checked:
            out["checklist"].append({"key": CHECKBOX_KEY, "text": checkbox_action})
        if attempt >= MAX_ATTEMPTS:                    # 재촬영 한도 → 대체 안내로 종료
            out["disposal"] = rule.fallback_disposal
            return _done(out, "fallback", rule.fallback_message)
        return _done(out, "need_action" if out["checklist"] else "retake")

    if checkbox and not checked:
        if answers.get(CHECKBOX_KEY) == "false":       # 아직 안 했다고 함 → 할 일로
            out["checklist"].append({"key": CHECKBOX_KEY, "text": checkbox_action})
            if attempt >= MAX_ATTEMPTS:
                out["disposal"] = rule.fallback_disposal
                return _done(out, "fallback", rule.fallback_message)
            return _done(out, "need_action")
        out["questions"].append({"key": CHECKBOX_KEY, "text": checkbox,
                                 "options": [{"label": MESSAGES["checkbox_yes"], "value": "true"},
                                             {"label": MESSAGES["checkbox_no"], "value": "false"}]})
        return _done(out, "question", MESSAGES["checkbox_question"])
    return _done(out, "pass")


def _info(rule, obs, answers, out):
    """정보 안내형: 처리 없이 결과만. 사진 조건이나 질문 1개로 결과가 갈릴 수 있음"""
    split = rule.split
    if not split:
        return _done(out, "pass", rule.message)
    if split.method == "photo":
        value = obs.get(split.key, "unknown")
    else:
        value = answers.get(split.key)
        if value not in {o.value for o in split.options}:
            out["questions"].append({"key": split.key, "text": split.question,
                                     "options": [o.model_dump() for o in split.options]})
            return _done(out, "question")
    case = next(c for c in split.cases if value in c.when)
    out["disposal"] = case.disposal
    return _done(out, "pass", case.message)
