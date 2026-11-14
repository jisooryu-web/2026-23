"""AI 호출 없이 판정 로직만 검사 (판정기준표 v1). 실행: python tests/test_judge.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from judge import judge, MAX_ATTEMPTS


def pet(**obs):
    """투명 페트병. 기본은 '라벨 없음 · 빈 병', 바꿀 필드만 넘긴다."""
    return {"item": "P01", "confidence": 0.9,
            "observations": {"is_clear": "true", "label": "absent", "liquid": "absent", **obs}}


def item(item_id, **obs):
    return {"item": item_id, "confidence": 0.9, "observations": obs}


YES = {"checkbox": "true"}      # 체크박스 '했어요'
NO = {"checkbox": "false"}      # '아직 안 했어요'
LAST = MAX_ATTEMPTS

# (이름, 관찰 결과, attempt, prev_item, 질문 답, 기대 status, 추가 확인 함수 또는 None)
cases = [
    # 투명 페트병 (P01)
    ("깨끗한 페트병: 체크박스 질문", pet(), 1, None, {}, "question", lambda r: r["questions"][0]["key"] == "checkbox"),
    ("깨끗한 페트병 + 체크 → 통과", pet(), 1, None, YES, "pass", lambda r: r["disposal"] == "투명 페트병 전용 수거함"),
    ("체크 '아직' → 할 일로", pet(), 1, None, NO, "need_action", None),
    ("라벨 있음 → 라벨 + 체크박스가 체크리스트에", pet(label="present"), 1, None, {}, "need_action",
     lambda r: [c["key"] for c in r["checklist"]] == ["label", "checkbox"]),
    ("라벨 있음, 이미 체크함 → 체크박스는 다시 안 넣음", pet(label="present"), 1, None, YES, "need_action",
     lambda r: [c["key"] for c in r["checklist"]] == ["label"]),
    ("라벨 안 보임(unknown) → 재촬영", pet(label="unknown"), 1, None, YES, "retake", None),
    ("남은 음료 안 보임(unknown) → 미통과(보수적)", pet(liquid="unknown"), 1, None, YES, "need_action", None),
    ("유색 페트병 → P02로 분기", pet(is_clear="false", label="present"), 1, None, YES, "pass",
     lambda r: r["item"] == "P02" and r["disposal"].startswith("플라스틱류")),
    ("투명 여부 안 보임 → 재촬영", pet(is_clear="unknown"), 1, None, YES, "retake", None),
    ("권고 조건 미통과는 팁만 (통과에 영향 없음)", pet(crushed="false", cap="absent"), 1, None, YES, "pass",
     lambda r: len(r["tips"]) == 2),
    ("권고 조건 unknown은 무시", pet(crushed="unknown"), 1, None, YES, "pass", lambda r: r["tips"] == []),
    ("마지막 촬영에도 라벨 안 보임 → 대체 안내", pet(label="unknown"), LAST, None, YES, "fallback", None),
    # 오염도 (P03, P04, P09)
    ("컵라면 1단계 → 통과 (체크박스 없음)", item("P04", contamination_level="1", stain="absent"), 1, None, {}, "pass", None),
    ("컵라면 2단계 → '헹궜어요' 질문", item("P04", contamination_level="2", stain="absent"), 1, None, {}, "question",
     lambda r: r["questions"][0]["text"] == "헹궜어요"),
    ("컵라면 2단계 + 체크 → 통과", item("P04", contamination_level="2", stain="absent"), 1, None, YES, "pass", None),
    ("컵라면 3단계 → 처리 후 재촬영", item("P04", contamination_level="3", stain="absent"), 1, None, {}, "need_action", None),
    ("컵라면 5단계 → 바로 종량제봉투", item("P04", contamination_level="5", stain="absent"), 1, None, {}, "fallback",
     lambda r: r["disposal"] == "종량제봉투"),
    ("컵라면 착색 남음 → 미통과", item("P04", contamination_level="1", stain="present"), 1, None, {}, "need_action", None),
    ("컵라면 안쪽 안 보임 → 재촬영", item("P04", contamination_level="unknown", stain="absent"), 1, None, {}, "retake", None),
    ("마지막 촬영에도 착색 → 종량제봉투", item("P04", contamination_level="1", stain="present"), LAST, None, {}, "fallback",
     lambda r: r["disposal"] == "종량제봉투"),
    ("색깔 스티로폼 → 종량제봉투 안내", item("P09", is_white="false"), 1, None, {}, "pass", lambda r: r["disposal"] == "종량제봉투"),
    # 분기·정보 안내형
    ("깨진 유리병 → 깨진 유리(I06)", item("P07", broken="true"), 1, None, {}, "pass", lambda r: r["item"] == "I06"),
    ("유리병 깨짐 여부 모름 → 안전 우선으로 깨진 유리", item("P07", broken="unknown"), 1, None, {}, "pass", lambda r: r["item"] == "I06"),
    ("영수증 → 종량제봉투", item("I01"), 1, None, {}, "pass", lambda r: r["disposal"] == "종량제봉투"),
    ("형광등 깨짐 → 종량제봉투 안내", item("I03", broken="true"), 1, None, {}, "pass", lambda r: "종량제봉투" in r["disposal"]),
    ("아이스팩 → 물/젤 질문", item("I05"), 1, None, {}, "question", lambda r: r["questions"][0]["key"] == "ice_content"),
    ("아이스팩 젤 → 종량제봉투", item("I05"), 1, None, {"ice_content": "gel"}, "pass", None),
    ("지원 안 하는 물건(X00)", item("X00"), 1, None, {}, "unsupported", None),
    # 재촬영
    ("재촬영: 같은 페트병, 라벨 제거됨", pet(), 2, "P01", YES, "pass", None),
    ("재촬영: 다른 품목을 찍음", item("I01"), 2, "P01", {}, "different_item", None),
    ("재촬영: AI가 다른 물건이라고 봄", {**pet(), "same_item": "false"}, 2, "P01", YES, "different_item", None),
    ("재촬영: 처음엔 유색(P02)으로 판정, 이번엔 P01로 봄 → 같은 물건으로 인정", pet(is_clear="false"), 2, "P02", YES, "pass", None),
    # 품목 확신도
    ("확신 낮음: 품목 확인 질문", {**pet(), "confidence": 0.4}, 1, None, YES, "question",
     lambda r: r["questions"][0]["key"] == "confirm_P01"),
    ("확신 낮음: '예' → 평소대로 판정", {**pet(), "confidence": 0.4}, 1, None, {**YES, "confirm_P01": "true"}, "pass", None),
    ("확신 낮음: '아니요' → 판정 안 함", {**pet(), "confidence": 0.4}, 1, None, {"confirm_P01": "false"}, "unsupported", None),
]

failed = 0
for name, obs, attempt, prev_item, answers, expected, extra in cases:
    got = judge(obs, attempt, answers, prev_item=prev_item)
    ok = got["status"] == expected and bool(got.get("message")) and (extra is None or extra(got))
    failed += not ok
    print("O" if ok else "X", name, "→", got["status"])

print(f"\n{len(cases) - failed}/{len(cases)} 통과")
sys.exit(1 if failed else 0)
