"""AI 호출 없이 판정 로직만 검사. 실행: python tests/test_judge.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from judge import judge

PET_LABEL = {"item": "pet_bottle", "observations": {"is_transparent": "true", "label_attached": "true", "liquid_inside": "false"}}
PET_CLEAN = {"item": "pet_bottle", "observations": {"is_transparent": "true", "label_attached": "false", "liquid_inside": "false"}}

# (이름, 관찰 결과, attempt, prev_item, 기대 status)
cases = [
    ("라벨 붙은 투명 페트병", PET_LABEL, 1, None, "need_action"),
    ("깨끗한 투명 페트병", PET_CLEAN, 1, None, "pass"),
    ("라벨이 안 보임", {"item": "pet_bottle", "observations": {"is_transparent": "true", "label_attached": "unknown", "liquid_inside": "false"}}, 1, None, "retake"),
    ("3번째에도 라벨이 안 보임", {"item": "pet_bottle", "observations": {"is_transparent": "true", "label_attached": "unknown", "liquid_inside": "false"}}, 3, None, "fallback"),
    ("3번째에도 착색 남음", {"item": "cup_noodle", "observations": {"food_residue": "none", "red_oil_stain": "true"}}, 3, None, "fallback"),
    ("재촬영: 같은 페트병, 라벨 제거됨", PET_CLEAN, 2, "pet_bottle", "pass"),
    ("재촬영: 다른 품목을 찍음", {"item": "receipt", "observations": {}}, 2, "pet_bottle", "different_item"),
    ("재촬영: AI가 다른 물건이라고 봄", {**PET_CLEAN, "same_item": "false"}, 2, "pet_bottle", "different_item"),
    ("영수증", {"item": "receipt", "observations": {}}, 1, None, "pass"),
    ("숟가락", {"item": "unsupported"}, 1, None, "unsupported"),
]

failed = 0
for name, obs, attempt, prev_item, expected in cases:
    got = judge(obs, attempt, prev_item=prev_item)
    ok = got["status"] == expected and got.get("message")
    failed += not ok
    print("O" if ok else "X", name, "→", got["status"])

print(f"\n{len(cases) - failed}/{len(cases)} 통과")
sys.exit(1 if failed else 0)
