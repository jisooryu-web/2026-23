# API 명세 (프론트 ↔ 백엔드 약속)

## 실행과 문서

- 서버: `cd backend && uvicorn app:app --reload --port 5001` (FastAPI)
- 자동 문서·테스트 화면: http://127.0.0.1:5001/docs
- 요청·응답 모양의 기준은 `backend/schemas.py`. 이 문서와 다르면 schemas.py가 맞음
- 규칙표 `rules.json` 구조도 `schemas.py`의 `RuleSet`을 따름. 구조가 틀리면 서버가 켜지지 않고 어느 줄이 틀렸는지 알려줌

## POST /judge

사진 한 장을 판정한다. 요청은 `multipart/form-data`.

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `image` | O | 지금 찍은 사진 (JPG/PNG/HEIC, 최대 15MB) |
| `attempt` | O | 몇 번째 촬영인지. 1부터 시작, 처리 후 재촬영할 때마다 +1 |
| `prev_image` | 재촬영 시 | 처음 찍은 사진. AI가 전후를 비교해 오염도와 같은 물건인지 판단 |
| `prev_item` | 재촬영 시 | 첫 판정의 `judgement.item`. 다른 품목이면 `different_item` |
| `answers` | 질문 답변 시 | JSON 문자열. 예: `{"checkbox": "true"}`, `{"confirm_P01": "true"}`, `{"ice_content": "gel"}` |
| `observation` | 질문 답변 시 (선택) | 직전 응답의 `observation`을 그대로 JSON 문자열로. 보내면 서버가 AI를 다시 부르지 않음 (`image` 생략 가능) |

### 성공 응답 (200)

```json
{
  "observation": {
    "item": "P01",
    "confidence": 0.95,
    "same_item": "unknown",
    "observations": {"is_clear": "true", "label": "present", "liquid": "absent", "crushed": "false", "cap": "closed"},
    "notes": "Blue label wraps a clear, empty bottle."
  },
  "judgement": {
    "status": "need_action",
    "message": "버리기 전에 아래 항목을 처리하고 다시 찍어 주세요.",
    "item": "P01",
    "name": "투명 페트병",
    "type": "state",
    "attempt": 1,
    "max_attempts": 3,
    "disposal": "투명 페트병 전용 수거함",
    "checklist": [
      {"key": "label", "text": "라벨을 떼어 주세요. 뗀 라벨은 비닐류로 버려요."},
      {"key": "checkbox", "text": "내용물을 비우고 물로 헹궈 주세요."}
    ],
    "questions": [],
    "retake": [],
    "tips": ["찌그러뜨리면 더 좋아요."],
    "warnings": ["뚜껑은 분리하지 말고 닫아서 함께 버려요."],
    "source": "S03, S04, S06"
  }
}
```

- `observation`: AI가 사진에서 본 것 (판정 근거 표시용)
- `judgement`: 판정기준표(`rules.json`)로 내린 판정. **화면은 `judgement.status`로 분기**하고, 문구는 `message`를 그대로 쓰면 된다.
- `item`: 판정기준표의 품목ID (P01~P09 상태 판정형, I01~I11 정보 안내형, X00 지원 안 함). 분기가 일어나면 바뀐 품목 (예: 유색 페트병이면 P02)
- `tips`: 권고 조건 (안 해도 배출 가능). 통과 화면에도 나올 수 있음
- `source`: 출처ID (판정기준표 ⑥출처 탭)

### status별 화면

| status | 뜻 | 화면 |
| --- | --- | --- |
| `pass` | 통과 (정보 안내형 품목 포함) | `message` + `disposal` 크게 + `tips` + `warnings` |
| `need_action` | 처리할 일 남음 | `checklist` 체크박스 → 다 체크하면 "다시 찍기" (attempt +1). `checklist`에 `key: "checkbox"`가 있었으면 다음 요청 `answers`에 `{"checkbox": "true"}`를 넣어 다시 묻지 않게 |
| `retake` | AI가 일부를 못 봄 | `message` + "다시 찍기" (attempt +1) |
| `question` | 사진으로 알 수 없음 | `questions[].text` + `options` 버튼 → 같은 사진으로 `answers` 붙여 재요청 (attempt 그대로). 질문은 3종류: 품목 확인(`confirm_P01`), 체크박스(`checkbox`, 예: "헹궜어요"), 정보 안내형 질문(`ice_content`, `tumbler_single`) |
| `fallback` | 재촬영 한도 도달, 또는 오염도 5단계 | `message`(품목별 대체 안내)와 `disposal` 안내하고 종료 |
| `different_item` | 처음과 다른 물건 | "같은 물건 다시 찍기" (attempt 그대로) |
| `unsupported` | 지원하지 않는 품목 | `message` + 처음으로 |

### 오류 응답

```json
{"error": {"code": "BAD_IMAGE", "message": "사진을 읽을 수 없어요. JPG나 PNG로 다시 올려 주세요."}}
```

| HTTP | code | 상황 |
| --- | --- | --- |
| 400 | `NO_IMAGE` | `image` 없음 |
| 400 | `BAD_REQUEST` | `attempt`가 숫자가 아니거나 `answers`가 JSON이 아님 |
| 400 | `BAD_IMAGE` | 이미지로 읽을 수 없는 파일 |
| 413 | `TOO_LARGE` | 15MB 초과 |
| 502 | `AI_FAILED` | AI 호출 실패 (키 없음, 네트워크 등) |

프론트는 `error.message`를 그대로 보여주면 된다.

## GET /health

서버가 켜져 있는지 확인. `{"ok": true}`
