# ♻️ AI 분리배출 판정 도우미 (HelpingRecycle)

> 2026 인공지능학과 대학 연합 해커톤 23팀
>
> 사진 한 장으로 **지금 버려도 되는지**, 아니면 라벨 제거나 헹굼처럼 **버리기 전에 무엇을 해야 하는지** 알려 주는 서비스

![ci](https://github.com/jisooryu-web/2026-23/actions/workflows/ci.yml/badge.svg)

- 서비스: [배포 주소를 입력하세요]
- 시연 영상: [영상 링크를 입력하세요]

---

## 문제

분리배출 기준은 품목마다, 같은 품목이라도 상태마다 다릅니다. 투명 페트병은 라벨을 떼고 비워야 전용 수거함에 넣을 수 있고, 컵라면 용기는 음식물이나 빨간 기름 자국이 남아 있으면 재활용되지 않습니다. 사용자는 "이거 그냥 버려도 되나?"를 매번 검색해야 합니다.

## 해결

사진을 찍으면 **배출 방법**과 **버리기 전에 할 일**을 알려 주고, 처리한 뒤 다시 찍으면 같은 물건인지 확인해 다시 판정합니다. 사진으로 알 수 없는 것(헹궜는지 등)은 사용자에게 묻습니다.

**지원 품목 20개** (판정기준표 v1, 서울특별시 기준)

| 구분 | 품목 |
| --- | --- |
| 상태 판정형 (처리 → 재촬영) | 투명 페트병, 유색 페트병·일반 플라스틱, 배달 용기, 컵라면 용기, 캔, 부탄가스·스프레이, 유리병, 펌프형 용기, 스티로폼 상자 |
| 정보 안내형 (바로 안내) | 영수증, 건전지, 형광등, 우산, 아이스팩, 깨진 유리, 내열유리·도자기·거울, 칫솔·옷걸이·CD, 텀블러, 빨대, 종이컵 |

---

## 구조

**핵심 원칙: AI는 사진에서 보이는 것만 관찰하고, 판정은 규칙표가 내립니다.**

```
[사진] ── 올리기 전에 1024px로 축소
   ▼
vision.py   AI(OpenAI Vision)가 '보이는 것'만 JSON으로 관찰
   │        품목ID · 확신도 · 라벨 · 내용물 · 오염도(1~5) · 같은 물건 여부 ...
   ▼
schemas.py  약속 밖 값은 unknown으로 정리, 형식이 틀리면 AI 오류로 처리
   ▼
judge.py    rules.json(판정기준표)으로 판정. AI는 판정에 관여하지 않음
   ▼
[7가지 상태] → React 화면이 상태별로 분기
```

| 상태 | 의미 |
| --- | --- |
| `pass` | 배출 가능 (정보 안내형은 바로 안내) |
| `need_action` | 처리할 일이 남음 → 체크리스트 → 재촬영 |
| `retake` | 사진으로 확인이 안 된 부분이 있음 → 그 부분을 알려 주고 다시 찍기 |
| `question` | 사진으로 알 수 없음 → 질문 (품목 확인, "헹궜어요?", 아이스팩 물/젤 등) |
| `fallback` | 3번 찍어도 해결되지 않음 → 대체 배출 방법 + 직접 확인할 항목 |
| `different_item` | 재촬영한 물건이 처음과 다름 |
| `unsupported` | 지원하지 않는 품목 |

### 설계 결정

| 결정 | 이유 |
| --- | --- |
| AI는 관찰만, 판정은 규칙표 | AI가 배출 기준을 지어내지 못하게. 기준이 바뀌면 코드가 아니라 `rules.json`만 수정 |
| 모르면 단정하지 않음 | 안 보이면 `unknown` → 재촬영이나 질문. "처리가 필요한데 통과"라고 안내하는 것을 가장 나쁜 오류로 봄 |
| 질문에 답할 때 AI 재호출 0회 | 같은 사진의 관찰 결과를 재사용해 빠르고, 답이 흔들리지 않음 |
| 규칙표를 서버 시작 시 검사 | 키 오타, 없는 품목으로 분기, 빠진 문구 등이 있으면 서버가 켜지지 않음 |
| 배포 보호 | IP별 요청 수 제한(기본 1분 20회), 큰 요청 조기 차단, 사진은 저장하지 않고 메모리에서만 처리 |

---

## 검증

**AI 없이 도는 자동 테스트** (push·PR마다 GitHub Actions에서 실행)

| 테스트 | 내용 | 결과 |
| --- | --- | --- |
| `tests/test_judge.py` | 판정 규칙 (관찰 → 상태) | 35 / 35 |
| `tests/test_api.py` | API 요청·응답·오류 형식, 관찰 재사용, 요청 수 제한 | 14 / 14 |
| `tests/test_edge_cases.py` | AI의 이상한 값, 이상한 답변, 업로드, 규칙표 실수, 파일 간 동기화 | 48 / 48 |

**실제 사진으로 AI 평가** (`tests/run_tests.py`, API 키 필요)

| 지표 | 개선 전 | 개선 후 |
| --- | --- | --- |
| 최종 판정 정답 (25장) | | |
| 잘못된 통과 (0이어야 함) | | |
| 품목 정확도 | | |
| 3번 돌렸을 때 답이 흔들린 사진 | | |
| 평균 응답 시간 | | |

---

## 실행

```bash
# 백엔드
python3 -m venv venv && source venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env        # OPENAI_API_KEY 입력
cd backend && python app.py                 # http://127.0.0.1:5001/docs

# 프론트엔드 (다른 터미널)
cd frontend && npm install
cp .env.example .env.local                  # VITE_USE_MOCK=true면 백엔드 없이 화면 확인
npm run dev                                 # http://localhost:5173

# 테스트
python tests/test_judge.py && python tests/test_api.py && python tests/test_edge_cases.py
python tests/run_tests.py --repeat 3 --save before.json    # 실제 사진 평가 (tests/images/)
```

### 배포

| | 설정 |
| --- | --- |
| 백엔드 (Render 등) | Root `backend` · Build `pip install -r requirements.txt` · Start `uvicorn app:app --host 0.0.0.0 --port $PORT` · 환경 변수 `OPENAI_API_KEY`, `ALLOWED_ORIGINS=https://프론트주소` |
| 프론트 (Vercel 등) | Root `frontend` · 환경 변수 `VITE_USE_MOCK=false`, `VITE_API_BASE_URL=https://백엔드주소` |

---

## 폴더 구조

```
├── backend/
│   ├── app.py          # FastAPI 서버 (/judge, /health), 오류 형식 통일, 요청 보호, 요청 로그
│   ├── vision.py       # 사진 전처리 + AI 관찰 (프롬프트는 rules.json에서 자동 생성)
│   ├── judge.py        # 판정기준표 기반 판정
│   ├── schemas.py      # Pydantic 스키마 (규칙표 · AI 관찰 · 응답)
│   ├── rules.json      # 판정기준표 v1: 품목 20개, 조건, 오염도 5단계, 화면 문구
│   ├── config.py       # 설정값 (.env로 변경 가능)
│   └── API.md          # 프론트 ↔ 백엔드 약속
├── frontend/           # React (Vite)
└── tests/              # 자동 테스트, Mock 생성, 실제 사진 평가
```

## 다음 단계

- 관찰 부분만 경량 이미지 모델(CNN)로 교체해, 같은 평가 사진으로 정확도·응답 시간 비교 (판정·규칙·화면은 그대로)
- 자치구별 기준 차이 반영, 품목 추가 (`rules.json` 수정만으로 가능)

## 팀

[팀원 이름과 역할을 입력하세요]
