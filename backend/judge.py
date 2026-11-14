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
LABELS = RULESET.field_labels                        # "label" → "라벨"
PLACES = RULESET.places                              # "plastic" → {title, where}

YES_NO = [{"label": "예", "value": "true"}, {"label": "아니요", "value": "false"}]
CHECKBOX_KEY = "checkbox"                            # answers에서 체크박스 답의 키
SAME_KEY = "confirm_same_item"                       # "같은 물건이 맞나요?" 답의 키
HINT_KEY = "item_hint"                               # 사용자가 직접 고른 품목ID


def _norm(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v).strip().lower()


# AI는 품목ID(P10, I10…) 대신 영어 이름(plastic_film_bag…)으로 답한다. 비슷한 ID를 헷갈리는 실수를 막기 위해
AI_KEYS = {r.ai_key.upper(): k for k, r in RULES.items()} | {"OTHER": UNSUPPORTED}


def normalize_item(item):
    """AI 답(영어 이름) 또는 품목ID → 품목ID. 모르는 값은 그대로 (→ unsupported)"""
    item = str(item or UNSUPPORTED).strip().upper()
    return AI_KEYS.get(item, item)


def _related(a, b):
    """같은 물건으로 볼 수 있는 품목인지 (분기로 이어진 품목: P01↔P02, P07↔I06)"""
    if a == b:
        return True
    to = lambda x: {c.to for c in RULES[x].conditions if c.to} if x in RULES else set()
    return b in to(a) or a in to(b)


def _places(keys):
    return [PLACES[k].model_dump() for k in keys]


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
    item = normalize_item(result.get("item"))
    out = {"item": item, "attempt": attempt, "max_attempts": MAX_ATTEMPTS,
           "checklist": [], "questions": [], "retake": [], "tips": [], "warnings": [], "how": [], "places": []}

    if item not in RULES:
        if item == "UNKNOWN":
            return _unsupported(out, answers, MESSAGES["not_confirmed"])
        subject = str(result.get("subject") or "").strip()
        # 두 번째 줄에 "(확인된 품목: 안경)" — 문구는 rules.json의 unsupported_subject
        message = MESSAGES["unsupported"] + ("\n" + MESSAGES["unsupported_subject"].replace("{subject}", subject)
                                             if subject else "")
        return _unsupported(out, answers, message)

    # 재촬영인데 다른 물건이면 판정하지 않음 (깨끗한 다른 병으로 통과하는 꼼수 방지)
    if prev_item:
        if not _related(item, prev_item.strip().upper()):
            return _done(out, "different_item")
        if result.get("same_item") == "false" and answers.get(SAME_KEY) != "true":
            # 품목은 같은데 AI만 '다른 물건'이라고 봄 → 사용자에게 한 번 확인 (AI 오판으로 무한 반복 방지)
            if answers.get(SAME_KEY) != "false":
                out["questions"].append({"key": SAME_KEY, "text": MESSAGES["same_item_question"], "options": YES_NO})
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
            return _unsupported(out, answers, MESSAGES["not_confirmed"])

    return _evaluate(item, clean_observations(result.get("observations")), attempt, answers, out)


def _unsupported(out, answers, message=None):
    """인식 실패·지원 안 함 → 사용자가 품목을 직접 고를 수 있게 목록 제공 (이미 골랐으면 다시 묻지 않음)"""
    if not answers.get(HINT_KEY):
        # 자주 찾는 품목을 앞에 → 화면은 앞의 몇 개만 먼저 보여 주고 나머지는 검색으로
        order = RULESET.popular_items + [k for k in RULES if k not in RULESET.popular_items]
        out["questions"].append({"key": HINT_KEY, "text": MESSAGES["pick_item_question"],
                                 "options": [{"label": RULES[k].name, "value": k, "keywords": RULES[k].keywords}
                                             for k in order]})
    return _done(out, "unsupported", message)


def _evaluate(item, obs, attempt, answers, out):
    rule = RULES[item]
    out.update({"item": item, "name": rule.name, "type": rule.type, "disposal": rule.disposal,
                "warnings": list(rule.warnings), "source": rule.source,
                "how": list(rule.how), "places": _places(rule.places)})
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
                out["disposal"], out["places"], out["how"] = rule.fallback_disposal, _places(rule.fallback_places), []
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
                fresh.update({"checklist": [], "questions": [], "retake": [], "tips": [], "warnings": [],
                              "how": [], "places": []})
                return _evaluate(c.to, obs, attempt, answers, fresh)
            out["disposal"] = c.to_disposal            # 배출처만 바뀌고 끝
            out["how"], out["places"] = [], _places(c.to_places)
            return _done(out, "pass", c.to_message)
        if c.kind == "tip":
            out["tips"].append(c.action)
        else:
            out["checklist"].append({"key": c.key, "text": c.action})

    checked = answers.get(CHECKBOX_KEY) == "true"
    if out["checklist"] or out["retake"]:
        if attempt >= MAX_ATTEMPTS:                    # 재촬영 한도 → 남은 항목을 직접 확인하라는 대체 안내로 종료
            actions = {c.key: c.action for c in rule.conditions if c.action}
            out["checklist"] += [{"key": k, "text": actions.get(k) or f"{LABELS[k]} 상태를 직접 확인해 주세요."}
                                 for k in out["retake"]]
            if checkbox and not checked:
                out["checklist"].append({"key": CHECKBOX_KEY, "text": checkbox_action})
            out["disposal"], out["places"], out["how"] = rule.fallback_disposal, _places(rule.fallback_places), []
            return _done(out, "fallback", rule.fallback_message)
        if out["checklist"]:
            # 처리할 일이 있으면 체크박스도 체크리스트에 함께 (다시 찍을 때 체크하면 재질문 안 함)
            if checkbox and not checked:
                out["checklist"].append({"key": CHECKBOX_KEY, "text": checkbox_action})
            return _done(out, "need_action")
        # 무엇이 안 보였는지 알려 줘야 사용자가 그 부분을 찍는다
        fields = ", ".join(dict.fromkeys(LABELS[k] for k in out["retake"]))
        return _done(out, "retake", MESSAGES["retake"].replace("{fields}", fields))

    if checkbox and not checked:
        if answers.get(CHECKBOX_KEY) == "false":       # 아직 안 했다고 함 → 할 일로
            out["checklist"].append({"key": CHECKBOX_KEY, "text": checkbox_action})
            if attempt >= MAX_ATTEMPTS:
                out["disposal"], out["places"], out["how"] = rule.fallback_disposal, _places(rule.fallback_places), []
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
    if case.places:
        out["places"] = _places(case.places)
    return _done(out, "pass", case.message)
