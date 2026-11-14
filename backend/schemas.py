"""데이터 모양(스키마) 정의

1) rules.json 이 판정기준표 구조대로 쓰였는지 (서버 켤 때)
2) AI가 돌려준 관찰 JSON 정리 (요청마다. 약속 밖 값은 unknown으로)
3) API 응답 모양 (FastAPI가 /docs 문서를 만들 때 사용)
"""
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# AI 출력 키와 허용 값 (판정기준표 ⑤AI출력스키마). 규칙의 key는 이 중 하나여야 한다.
FIELD_VALUES = {
    "is_clear":            {"true", "false"},
    "label":               {"present", "absent"},
    "liquid":              {"present", "absent"},
    "crushed":             {"true", "false"},
    "cap":                 {"closed", "present", "absent"},
    "contamination_level": {"1", "2", "3", "4", "5"},
    "stain":               {"present", "absent"},
    "other_material":      {"present", "absent"},
    "plastic_part":        {"present", "absent"},
    "broken":              {"true", "false"},
    "foreign_object":      {"present", "absent"},
    "pump_attached":       {"true", "false"},
    "is_white":            {"true", "false"},
    "tape_label":          {"present", "absent"},
    "umbrella_type":       {"long", "folding"},
}
OBSERVATION_FIELDS = set(FIELD_VALUES)
UNSUPPORTED = "X00"            # 지원하지 않는 품목 (기준표 품목ID)


# ---------- 1) rules.json ----------

class Option(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str                      # 버튼에 보일 글자
    value: str                      # 눌렀을 때 보낼 값


class Place(BaseModel):
    """배출 장소 안내 (예: 플라스틱류 → 아파트는 어디, 주택은 어디)"""
    model_config = ConfigDict(extra="forbid")
    title: str
    where: List[str]


class Condition(BaseModel):
    """조건표 한 줄 (C01, C02 ...)"""
    model_config = ConfigDict(extra="forbid")   # 모르는 키(오타)가 있으면 오류
    id: str
    key: str
    kind: Literal["required", "tip", "branch", "contamination"]   # 필수 / 권고 / 분기 / 오염도
    pass_: List[str] = Field(default=[], alias="pass")             # 이 값이면 통과
    unknown: Literal["retake", "fail", "ignore", "branch"] = "ignore"
    action: Optional[str] = None                # 미통과 시 안내 (체크리스트·팁 문구)
    to: Optional[str] = None                    # 분기: 다른 품목ID로 전환
    to_disposal: Optional[str] = None           # 분기: 배출처만 바뀌고 끝
    to_message: Optional[str] = None
    to_places: List[str] = []                   # 분기 시 배출 장소 (places의 키)

    @model_validator(mode="after")
    def _check(self):
        if self.key not in FIELD_VALUES:
            raise ValueError(f"{self.id}: '{self.key}'는 AI 출력 키가 아니에요: {sorted(FIELD_VALUES)}")
        bad = set(self.pass_) - FIELD_VALUES[self.key]
        if bad:
            raise ValueError(f"{self.id}: 통과 값 {sorted(bad)}는 '{self.key}'에서 나올 수 없어요: {sorted(FIELD_VALUES[self.key])}")
        if self.kind == "contamination":
            if self.key != "contamination_level":
                raise ValueError(f"{self.id}: contamination 조건의 key는 contamination_level이어야 해요")
            return self
        if not self.pass_:
            raise ValueError(f"{self.id}: pass(통과 값)가 필요해요")
        if self.kind in ("required", "tip") and not self.action:
            raise ValueError(f"{self.id}: 미통과 시 안내 문구(action)가 필요해요")
        if self.kind == "branch" and not (self.to or self.to_disposal):
            raise ValueError(f"{self.id}: 분기는 to(품목ID) 또는 to_disposal이 필요해요")
        if self.to_disposal and not self.to_message:
            raise ValueError(f"{self.id}: to_disposal에는 to_message도 필요해요")
        if self.unknown == "branch" and self.kind != "branch":
            raise ValueError(f"{self.id}: unknown=branch는 분기 조건에서만 쓸 수 있어요")
        return self


class SplitCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    when: List[str]
    disposal: str
    message: str
    places: List[str] = []


class Split(BaseModel):
    """정보 안내형에서 결과를 가르는 사진 조건 또는 질문 1개"""
    model_config = ConfigDict(extra="forbid")
    key: str
    method: Literal["photo", "question"]
    question: Optional[str] = None
    options: List[Option] = []
    cases: List[SplitCase]

    @model_validator(mode="after")
    def _check(self):
        covered = {v for c in self.cases for v in c.when}
        if self.method == "photo":
            if self.key not in FIELD_VALUES:
                raise ValueError(f"split '{self.key}'는 AI 출력 키가 아니에요")
            need = FIELD_VALUES[self.key] | {"unknown"}
        else:
            if not self.question or not self.options:
                raise ValueError(f"split '{self.key}': 질문 방식은 question과 options가 필요해요")
            need = {o.value for o in self.options}
        if need - covered:
            raise ValueError(f"split '{self.key}': {sorted(need - covered)} 값일 때의 결과가 없어요")
        return self


class Rule(BaseModel):
    """품목표 한 줄 (P01 ... I11)"""
    model_config = ConfigDict(extra="forbid")
    name: str
    type: Literal["state", "info"]
    ai_key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")   # AI가 답할 영어 이름 (예: pet_bottle). P10·I10처럼 비슷한 ID를 헷갈리지 않게
    ai_hint: str                                # AI 프롬프트에 들어갈 품목 설명 (영어)
    disposal: str                               # 통과 시 배출처 (한 줄 요약)
    how: List[str] = []                         # 버리는 순서 (통과 화면에 번호로)
    places: List[str] = []                      # 어디에 버리는지 (places의 키)
    source: str                                 # 출처ID (S01 ...)
    warnings: List[str] = []                    # 주의사항 (항상 표시)
    # 상태 판정형
    conditions: List[Condition] = []
    checkbox: Optional[str] = None              # 사용자 확인 (품목당 최대 1개)
    checkbox_action: Optional[str] = None       # 체크하지 않았을 때 할 일
    fallback_disposal: Optional[str] = None     # 재촬영 한도 초과 시
    fallback_message: Optional[str] = None
    fallback_places: List[str] = []
    # 정보 안내형
    message: Optional[str] = None
    split: Optional[Split] = None

    @model_validator(mode="after")
    def _check(self):
        if self.type == "state":
            if not self.conditions:
                raise ValueError(f"'{self.name}': 상태 판정형은 conditions가 하나 이상 필요해요")
            if not (self.fallback_disposal and self.fallback_message):
                raise ValueError(f"'{self.name}': 상태 판정형은 fallback_disposal과 fallback_message가 필요해요")
            if self.checkbox and not self.checkbox_action:
                raise ValueError(f"'{self.name}': checkbox에는 checkbox_action도 필요해요")
            keys = [c.key for c in self.conditions]
            dup = {k for k in keys if keys.count(k) > 1}
            if dup:
                raise ValueError(f"'{self.name}': 같은 key의 조건이 두 번 있어요: {sorted(dup)}")
        elif not self.message:
            raise ValueError(f"'{self.name}': 정보 안내형은 message가 필요해요")
        return self


class Level(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    result: Literal["pass", "checkbox", "fail", "discard"]
    text: str
    checkbox: Optional[str] = None


STATUSES = ("pass", "need_action", "retake", "question", "fallback", "different_item", "unsupported")
REQUIRED_MESSAGES = set(STATUSES) | {"not_confirmed", "confirm_question", "same_item_question", "pick_item_question",
                                     "checkbox_question", "checkbox_yes", "checkbox_no"}


class RuleSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    messages: Dict[str, str]                    # 화면 문구. 기획팀이 파이썬 없이 고칠 수 있게
    field_labels: Dict[str, str]                # AI 출력 키의 한국어 이름 (재촬영 이유 안내용)
    places: Dict[str, Place]                    # 배출 장소 안내 (아파트 / 단독주택)
    contamination: Dict[str, Level]             # 오염도 5단계
    items: Dict[str, Rule]

    @model_validator(mode="after")
    def _check(self):
        missing = REQUIRED_MESSAGES - set(self.messages)
        if missing:
            raise ValueError(f"messages에 빠진 문구가 있어요: {sorted(missing)}")
        if "{name}" not in self.messages["confirm_question"]:
            raise ValueError("confirm_question 문구에는 품목 이름 자리 {name}이 필요해요")
        if set(self.field_labels) != set(FIELD_VALUES):
            raise ValueError(f"field_labels에는 AI 출력 키가 모두 있어야 해요: {sorted(set(FIELD_VALUES) ^ set(self.field_labels))}")
        if set(self.contamination) != FIELD_VALUES["contamination_level"]:
            raise ValueError("contamination에는 1~5단계가 모두 있어야 해요")
        if self.contamination["2"].result == "checkbox" and not self.contamination["2"].checkbox:
            raise ValueError("contamination 2단계에는 checkbox 문구가 필요해요")
        ai_keys = [r.ai_key for r in self.items.values()]
        dup = {k for k in ai_keys if ai_keys.count(k) > 1} | ({"other", "unknown"} & set(ai_keys))
        if dup:
            raise ValueError(f"ai_key가 겹치거나 예약어(other, unknown)예요: {sorted(dup)}")
        if UNSUPPORTED in self.items:
            raise ValueError(f"'{UNSUPPORTED}'는 '지원 안 함'을 뜻하는 예약 ID예요")
        for item_id, rule in self.items.items():
            refs = rule.places + rule.fallback_places
            for c in rule.conditions:
                if c.to and c.to not in self.items:
                    raise ValueError(f"{item_id}.{c.id}: 분기 대상 '{c.to}'가 품목표에 없어요")
                refs += c.to_places
            if rule.split:
                refs += [p for case in rule.split.cases for p in case.places]
            missing = set(refs) - set(self.places)
            if missing:
                raise ValueError(f"{item_id}: places에 없는 배출 장소 {sorted(missing)}")
            if not rule.places:
                raise ValueError(f"{item_id}: 배출 장소(places)가 하나 이상 필요해요")
        return self


# ---------- 2) AI 관찰 결과 ----------

def _norm(v) -> str:
    """AI 값 정리: True/1/" TRUE " → "true"/"1"/"true" """
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v).strip().lower()


def clean_observations(v) -> Dict[str, str]:
    """약속한 키만 남기고, 허용 값이 아니면 unknown (예: 'yes' → unknown)"""
    if not isinstance(v, dict):
        return {}
    out = {}
    for k, val in v.items():
        if k in FIELD_VALUES:
            val = _norm(val)
            out[k] = val if val in FIELD_VALUES[k] else "unknown"
    return out


class Observation(BaseModel):
    item: str = UNSUPPORTED
    confidence: Optional[float] = Field(default=None, ge=0, le=1)   # 범위 밖이면 AI 오류
    same_item: str = "unknown"
    observations: Dict[str, str] = {}
    subject: str = ""                           # AI가 본 물건의 한국어 이름 (예: "안경"). 지원 안 함일 때 안내·로그용
    notes: str = ""

    @field_validator("subject", mode="before")
    @classmethod
    def _subject(cls, v):
        return str(v or "").strip()[:30]

    @field_validator("item", mode="before")
    @classmethod
    def _item(cls, v):
        return str(v).strip().upper() if v else UNSUPPORTED

    @field_validator("same_item", mode="before")
    @classmethod
    def _same(cls, v):
        v = _norm(v)
        return v if v in ("true", "false") else "unknown"

    @field_validator("observations", mode="before")
    @classmethod
    def _obs(cls, v):
        return clean_observations(v)


# ---------- 3) API 응답 ----------

class ChecklistItem(BaseModel):
    key: str
    text: str


class Question(BaseModel):
    key: str
    text: str
    options: List[Option]


class PlaceOut(BaseModel):
    title: str
    where: List[str]


class Judgement(BaseModel):
    status: Literal[STATUSES]
    message: str
    item: str
    attempt: int
    max_attempts: int
    checklist: List[ChecklistItem] = []
    questions: List[Question] = []
    retake: List[str] = []
    tips: List[str] = []
    warnings: List[str] = []
    how: List[str] = []                         # 버리는 순서
    places: List[PlaceOut] = []                 # 어디에 버리는지
    name: Optional[str] = None
    type: Optional[str] = None
    disposal: Optional[str] = None
    source: Optional[str] = None


class JudgeResponse(BaseModel):
    observation: Observation
    judgement: Judgement


class ErrorBody(BaseModel):
    code: str = Field(examples=["BAD_IMAGE"])
    message: str = Field(examples=["사진을 읽을 수 없어요. JPG나 PNG로 다시 올려 주세요."])


class ErrorResponse(BaseModel):
    error: ErrorBody
