"""지금 구조에서 생길 수 있는 문제를 모은 테스트. AI 호출 없음.
실행: python tests/test_edge_cases.py

각 케이스에는 "이래야 한다"는 기대 결과를 적었다.
- known=True  : 지금 코드에서는 실패하는 '알려진 문제'. 고치면 통과로 바뀐다.
- known=False : 지금도 통과해야 하는 안전장치. 실패하면 뭔가 깨진 것.
알려진 문제가 실패하는 건 정상이고, 종료 코드는 '예상 밖 실패'가 있을 때만 1이다.
"""
import copy, io, json, os, sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

from fastapi.testclient import TestClient
from PIL import Image

import app as server
import vision
from judge import judge, MAX_ATTEMPTS
from schemas import JudgeResponse, OBSERVATION_FIELDS, RuleSet

client = TestClient(server.app)
RULES_RAW = json.load(open(os.path.join(HERE, "..", "backend", "rules.json"), encoding="utf-8"))


def pet(**obs):
    """투명 페트병 관찰 결과. 기본은 '깨끗한 빈 병', 바꿀 필드만 넘긴다."""
    base = {"is_transparent": "true", "label_attached": "false", "liquid_inside": "false"}
    base.update(obs)
    return {"item": "pet_bottle", "confidence": 0.9, "observations": base}


YES = {"rinsed": "true"}


def jpg(size=(40, 30)):
    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, format="JPEG")
    return ("p.jpg", buf.getvalue(), "image/jpeg")


def call_api(fake_observation, files=None, data=None):
    """AI 대신 fake_observation을 돌려주게 하고 /judge를 호출."""
    server.observe = lambda cur, prev=None: copy.deepcopy(fake_observation)
    return client.post("/judge", files=files or {"image": jpg()}, data=data or {})


def api_code(res):
    body = res.json()
    return body["judgement"]["status"] if res.status_code == 200 else body["error"]["code"]


def rules_error(mutate):
    """rules.json 복사본을 망가뜨려 보고, 검사에서 잡히면 True."""
    d = copy.deepcopy(RULES_RAW)
    mutate(d)
    try:
        RuleSet.model_validate(d)
        return False
    except Exception:
        return True


# (구분, 이름, 실제 결과를 돌려주는 함수, 기대 결과, known)
cases = [
    # ---------- A. AI가 이상한 값을 줄 때 ----------
    ("AI값", "관찰값이 'yes'처럼 약속 밖 값 → 모르는 것(retake)으로 취급",
     lambda: judge(pet(label_attached="yes"), 1, YES)["status"], "retake", True),
    ("AI값", "관찰값이 대문자 'TRUE' → true로 인정 (투명 병 전용 수거함 안내)",
     lambda: judge(pet(is_transparent="TRUE"), 1, YES)["disposal"], "투명 페트병 전용 수거함", True),
    ("AI값", "item이 'PET_BOTTLE'(대문자) → pet_bottle로 인정",
     lambda: judge({**pet(), "item": "PET_BOTTLE"}, 1, YES)["status"], "pass", True),
    ("AI값", "confidence가 1.5(범위 밖) → AI 오류로 처리",
     lambda: api_code(call_api({**pet(), "confidence": 1.5}, data={"answers": json.dumps(YES)})), "AI_FAILED", True),
    ("AI값", "same_item이 'True'(약속 밖) → 요청 전체 실패 대신 unknown으로 보고 판정",
     lambda: api_code(call_api({**pet(), "same_item": "True"}, data={"answers": json.dumps(YES)})), "pass", True),
    ("AI값", "observations 필드가 빠짐 → retake (unknown으로 처리)",
     lambda: judge({"item": "pet_bottle", "confidence": 0.9}, 1, YES)["status"], "retake", False),
    ("AI값", "규칙표에 없는 item(glass_bottle) → unsupported",
     lambda: judge({"item": "glass_bottle", "confidence": 0.9}, 1)["status"], "unsupported", False),
    ("AI값", "AI 답이 JSON 객체가 아님(문자열) → AI_FAILED",
     lambda: api_code(call_api("not json")), "AI_FAILED", False),

    # ---------- B. 질문 답이 이상할 때 (API를 직접 부르는 경우) ----------
    ("답변", "답이 선택지 밖 값('yes') → 같은 질문을 다시 해야 함",
     lambda: judge(pet(), 1, {"rinsed": "yes"})["status"], "question", True),
    ("답변", "답이 문자열이 아니라 불리언 true → '예'로 인정",
     lambda: judge(pet(), 1, {"rinsed": True})["status"], "pass", True),
    ("답변", "answers가 JSON 배열 → BAD_REQUEST",
     lambda: api_code(call_api(pet(), data={"answers": "[1, 2]"})), "BAD_REQUEST", False),
    ("답변", "answers가 null → BAD_REQUEST",
     lambda: api_code(call_api(pet(), data={"answers": "null"})), "BAD_REQUEST", False),

    # ---------- C. 촬영 횟수와 재촬영 흐름 ----------
    ("흐름", "attempt=0 → 1로 보정되어 정상 판정",
     lambda: api_code(call_api(pet(), data={"attempt": "0", "answers": json.dumps(YES)})), "pass", False),
    ("흐름", "3번째에도 라벨이 안 보임 → fallback",
     lambda: judge(pet(label_attached="unknown"), MAX_ATTEMPTS, YES)["status"], "fallback", False),
    ("흐름", "3번째인데 질문이 남아 있음 → 질문 먼저 (fallback 아님)",
     lambda: judge(pet(label_attached="unknown"), MAX_ATTEMPTS, {})["status"], "question", False),
    ("흐름", "한도를 넘긴 attempt(10)도 fallback으로 끝남",
     lambda: judge(pet(label_attached="true"), 10, YES)["status"], "fallback", False),
    ("흐름", "prev_item만 있고 prev_image가 없음 → 비교 없이 판정 계속",
     lambda: api_code(call_api(pet(), data={"attempt": "2", "prev_item": "pet_bottle", "answers": json.dumps(YES)})), "pass", False),
    ("흐름", "유색 병 + 라벨 → need_action이고 배출처는 플라스틱류로 바뀜",
     lambda: (lambda r: (r["status"], r["disposal"].startswith("플라스틱류")))(
         judge(pet(is_transparent="false", label_attached="true"), 1, YES)), ("need_action", True), False),
    ("흐름", "처음 사진과 같은 물건인데 AI가 same_item=false라고 하면 different_item이 반복될 수 있음 → 사용자 확인 필요",
     lambda: judge({**pet(), "same_item": "false"}, 2, {**YES, "confirm_same_item": "true"}, prev_item="pet_bottle")["status"],
     "pass", True),

    # ---------- D. 품목 확신도 ----------
    ("확신도", "confidence 0.59 → 품목 확인 질문",
     lambda: judge({**pet(), "confidence": 0.59}, 1, YES)["status"], "question", False),
    ("확신도", "confidence 0.6 (경계값) → 확인 질문 없이 판정",
     lambda: judge({**pet(), "confidence": 0.6}, 1, YES)["status"], "pass", False),
    ("확신도", "확인 질문에 '예'라고 한 뒤 AI가 다른 품목으로 보면 그 품목으로 다시 확인",
     lambda: judge({"item": "cup_noodle", "confidence": 0.4, "observations": {}}, 1, {"confirm_pet_bottle": "true"})["questions"][0]["key"],
     "confirm_cup_noodle", False),
    ("확신도", "영수증(info)도 확신도가 낮으면 확인 질문",
     lambda: judge({"item": "receipt", "confidence": 0.3}, 1)["status"], "question", False),

    # ---------- E. 업로드 ----------
    ("업로드", "빈 파일(0바이트) → BAD_IMAGE",
     lambda: api_code(client.post("/judge", files={"image": ("a.jpg", b"", "image/jpeg")})), "BAD_IMAGE", False),
    ("업로드", "15MB 초과 → TOO_LARGE",
     lambda: api_code(client.post("/judge", files={"image": ("big.jpg", b"0" * (15 * 1024 * 1024 + 1), "image/jpeg")})),
     "TOO_LARGE", False),
    ("업로드", "처음 사진(prev_image)만 깨짐 → 지금 사진으로는 판정 계속",
     lambda: api_code(call_api(pet(), files={"image": jpg(), "prev_image": ("x.jpg", b"broken", "image/jpeg")},
                               data={"attempt": "2", "prev_item": "pet_bottle", "answers": json.dumps(YES)})), "pass", True),
    ("업로드", "아주 작은 사진(10x10) → AI까지 보내지 말고 다시 찍기 안내",
     lambda: api_code(call_api(pet(), files={"image": jpg((10, 10))}, data={"answers": json.dumps(YES)})), "BAD_IMAGE", True),

    # ---------- F. 규칙표(rules.json) 실수 ----------
    ("규칙표", "관찰 필드명 오타(label_atached) → 서버 시작 전에 잡힘",
     lambda: rules_error(lambda d: d["items"]["pet_bottle"]["checks"][2].__setitem__("key", "label_atached")), True, False),
    ("규칙표", "필드 이름 오타(acton) → 잡힘",
     lambda: rules_error(lambda d: d["items"]["pet_bottle"]["checks"][2].__setitem__("acton", "x")), True, False),
    ("규칙표", "state 품목에 fallback_disposal 없음 → 잡힘",
     lambda: rules_error(lambda d: d["items"]["cup_noodle"].pop("fallback_disposal")), True, False),
    ("규칙표", "messages에 상태 문구가 빠짐 → 잡힘",
     lambda: rules_error(lambda d: d["messages"].pop("retake")), True, False),
    ("규칙표", "확인 질문 문구에 {name} 자리가 없음 → 잡힘",
     lambda: rules_error(lambda d: d["messages"].__setitem__("confirm_question", "이 물건 맞나요?")), True, False),
    ("규칙표", "품목에 ai_hint(AI용 설명)가 없음 → 잡힘",
     lambda: rules_error(lambda d: d["items"]["receipt"].pop("ai_hint")), True, False),
    ("규칙표", "'unsupported'를 품목 이름으로 씀 → 잡힘",
     lambda: rules_error(lambda d: d["items"].__setitem__("unsupported", d["items"]["receipt"])), True, False),
    ("규칙표", "같은 key의 조건이 두 번 → 잡혀야 함",
     lambda: rules_error(lambda d: d["items"]["pet_bottle"]["checks"].append(dict(d["items"]["pet_bottle"]["checks"][2]))), True, True),
    ("규칙표", "ok 값이 관찰값으로 나올 수 없는 값('yes') → 잡혀야 함",
     lambda: rules_error(lambda d: d["items"]["pet_bottle"]["checks"][1].__setitem__("ok", "yes")), True, True),

    # ---------- G. 파일끼리 맞는지 (품목·필드 동기화) ----------
    ("동기화", "rules.json의 모든 품목이 AI 프롬프트에 있음",
     lambda: [k for k in RULES_RAW["items"] if k not in vision.SYSTEM_PROMPT], [], False),
    ("동기화", "schemas.py의 관찰 필드가 모두 AI 프롬프트에 있음",
     lambda: sorted(f for f in OBSERVATION_FIELDS if f not in vision.SYSTEM_PROMPT), [], False),
    ("동기화", "프론트 Mock(responses.json)이 실제 응답 모양(JudgeResponse)과 같음",
     lambda: [k for k, v in json.load(open(os.path.join(HERE, "..", "frontend", "src", "services", "responses.json"),
                                          encoding="utf-8")).items()
              if not _valid_response(v)], [], False),
]


def _valid_response(v):
    try:
        JudgeResponse.model_validate(v)
        return True
    except Exception:
        return False


ok_count = known_fail = unexpected = fixed = 0
for group, name, run, expected, known in cases:
    try:
        got = run()
    except Exception as e:                      # 테스트 자체가 터지면 그 내용을 결과로
        got = f"예외: {type(e).__name__}: {e}"
    passed = got == expected
    if passed and not known:
        ok_count += 1
        mark = "O"
    elif passed and known:
        fixed += 1
        mark = "★ 고쳐짐 (known 표시를 False로 바꾸세요)"
    elif known:
        known_fail += 1
        mark = "△ 알려진 문제"
    else:
        unexpected += 1
        mark = "X 예상 밖 실패"
    print(f"[{group}] {mark} | {name}")
    if not passed:
        print(f"        기대: {expected!r}  /  지금: {got!r}")

print(f"\n안전장치 통과 {ok_count} · 알려진 문제 {known_fail} · 고쳐짐 {fixed} · 예상 밖 실패 {unexpected}")
sys.exit(1 if unexpected else 0)