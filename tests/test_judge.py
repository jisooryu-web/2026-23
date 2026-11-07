import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from judge import judge

cases = [
    ("라벨 붙은 투명 페트병", {"item": "pet_bottle", "observations": {"is_transparent": "true", "label_attached": "true", "liquid_inside": "false"}}, 1, "need_action"),
    ("깨끗한 투명 페트병",    {"item": "pet_bottle", "observations": {"is_transparent": "true", "label_attached": "false", "liquid_inside": "false"}}, 1, "pass"),
    ("라벨이 안 보임",        {"item": "pet_bottle", "observations": {"is_transparent": "true", "label_attached": "unknown", "liquid_inside": "false"}}, 1, "retake"),
    ("3번째에도 착색 남음",    {"item": "cup_noodle", "observations": {"food_residue": "none", "red_oil_stain": "true"}}, 3, "fallback"),
    ("영수증",               {"item": "receipt", "observations": {}}, 1, "pass"),
    ("숟가락",               {"item": "unsupported"}, 1, "unsupported"),
]

for name, obs, attempt, expected in cases:
    got = judge(obs, attempt)["status"]
    print("O" if got == expected else "X", name, "→", got)