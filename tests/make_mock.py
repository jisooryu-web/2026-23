"""프론트 Mock 응답(responses.json)을 실제 judge.py로 만들어 낸다. AI 호출 없음.
실행: 프로젝트 맨 위 폴더에서  python tests/make_mock.py

rules.json이나 judge.py 문구가 바뀌면 이걸 다시 돌리면 Mock도 같이 맞춰진다.
(손으로 고친 responses.json이 실제 응답과 달라지는 문제를 막기 위함)
"""
import json, os, sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

from judge import judge, MAX_ATTEMPTS
from schemas import JudgeResponse, Observation

OUT = os.path.join(HERE, "..", "frontend", "src", "services", "responses.json")

PET = {"is_clear": "true", "label": "absent", "liquid": "absent", "crushed": "true", "cap": "closed"}
CUP = {"contamination_level": "1", "stain": "absent"}

# 상태 이름: (가짜 관찰, attempt, 질문 답, prev_item)
SCENARIOS = {
    "pass": ({"item": "P01", "confidence": 0.95, "observations": PET,
              "notes": "Clear, empty bottle with no label."}, 1, {"checkbox": "true"}, None),
    "need_action": ({"item": "P01", "confidence": 0.95,
                     "observations": {**PET, "label": "present", "liquid": "present", "crushed": "false"},
                     "notes": "Blue label wraps a clear bottle with some liquid left."}, 1, {}, None),
    "retake": ({"item": "P04", "confidence": 0.85,
                "observations": {"contamination_level": "unknown", "stain": "absent"},
                "notes": "Interior not visible because of the lid."}, 1, {}, None),
    "question": ({"item": "P01", "confidence": 0.9, "observations": PET,
                  "notes": "Clear bottle, no label."}, 1, {}, None),
    "fallback": ({"item": "P04", "confidence": 0.9, "same_item": "true",
                  "observations": {**CUP, "stain": "present"},
                  "notes": "Orange stain remains on the inner wall."}, MAX_ATTEMPTS, {}, "P04"),
    "different_item": ({"item": "I01", "confidence": 0.9, "same_item": "false", "observations": {},
                        "notes": "A receipt, not the bottle from the first photo."}, 2, {}, "P01"),
    "unsupported": ({"item": "X00", "confidence": 0.8, "observations": {},
                     "notes": "A metal spoon."}, 1, {}, None),
}

mocks = {}
for status, (fake, attempt, answers, prev_item) in SCENARIOS.items():
    obs = Observation.model_validate(fake).model_dump()
    result = judge(obs, attempt, answers, prev_item)
    assert result["status"] == status, f"{status} 시나리오가 {result['status']}로 나옴. 시나리오를 고치세요"
    # 실제 API처럼 응답 모양을 검사하고, 값이 None인 필드는 뺀다
    mocks[status] = JudgeResponse.model_validate({"observation": obs, "judgement": result}).model_dump(exclude_none=True)

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(mocks, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(f"{len(mocks)}개 상태를 {os.path.relpath(OUT)}에 썼어요: {', '.join(mocks)}")