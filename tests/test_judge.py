"""AI 호출 없이 판정 로직만 검사. 실행: python tests/test_judge.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from judge import judge

PET_LABEL = {"item": "pet_bottle", "observations": {"is_transparent": "true", "label_attached": "true", "liquid_inside": "false"}}
PET_CLEAN = {"item": "pet_bottle", "observations": {"is_transparent": "true", "label_attached": "false", "liquid_inside": "false"}}

PET_HIDDEN = {"item": "pet_bottle", "observations": {"is_transparent": "true", "label_attached": "unknown", "liquid_inside": "false"}}
YES = {"rinsed": "true"}      # "내부를 물로 헹구셨나요?"에 '예'
NO = {"rinsed": "false"}      # '아니요'

# (이름, 관찰 결과, attempt, prev_item, 질문 답, 기대 status)
cases = [
    ("라벨 붙은 투명 페트병", PET_LABEL, 1, None, YES, "need_action"),
    ("깨끗한 투명 페트병", PET_CLEAN, 1, None, YES, "pass"),
    ("라벨이 안 보임", PET_HIDDEN, 1, None, YES, "retake"),
    ("3번째에도 라벨이 안 보임", PET_HIDDEN, 3, None, YES, "fallback"),
    ("3번째에도 착색 남음", {"item": "cup_noodle", "observations": {"food_residue": "none", "red_oil_stain": "true"}}, 3, None, {}, "fallback"),
    ("재촬영: 같은 페트병, 라벨 제거됨", PET_CLEAN, 2, "pet_bottle", YES, "pass"),
    ("재촬영: 다른 품목을 찍음", {"item": "receipt", "observations": {}}, 2, "pet_bottle", {}, "different_item"),
    ("재촬영: AI가 다른 물건이라고 봄", {**PET_CLEAN, "same_item": "false"}, 2, "pet_bottle", YES, "different_item"),
    ("영수증", {"item": "receipt", "observations": {}}, 1, None, {}, "pass"),
    ("숫가락", {"item": "unsupported"}, 1, None, {}, "unsupported"),
    ("질문: 아직 답 안 함", PET_CLEAN, 1, None, {}, "question"),
    ("질문: '아니요' → 헹구기가 체크리스트로", PET_CLEAN, 1, None, NO, "need_action"),
    ("질문: 라벨도 붙어 있으면 질문이 먼저", PET_LABEL, 1, None, {}, "question"),
    ("확신 낮음: 품목 확인 질문", {**PET_CLEAN, "confidence": 0.4}, 1, None, YES, "question"),
    ("확신 낮음: '예' → 평소대로 판정", {**PET_CLEAN, "confidence": 0.4}, 1, None, {**YES, "confirm_pet_bottle": "true"}, "pass"),
    ("확신 낮음: '아니요' → 판정 안 함", {**PET_CLEAN, "confidence": 0.4}, 1, None, {"confirm_pet_bottle": "false"}, "unsupported"),
    ("확신 높음: 확인 질문 없음", {**PET_CLEAN, "confidence": 0.9}, 1, None, YES, "pass"),
]

failed = 0
for name, obs, attempt, prev_item, answers, expected in cases:
    got = judge(obs, attempt, answers, prev_item=prev_item)
    ok = got["status"] == expected and got.get("message")
    failed += not ok
    print("O" if ok else "X", name, "→", got["status"])

print(f"\n{len(cases) - failed}/{len(cases)} 통과")
sys.exit(1 if failed else 0)
