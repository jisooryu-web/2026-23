"""데이터 모양(스키마) 정의

1) rules.json 이 올바른 구조인지 (서버 켤 때)
2) AI가 돌려준 관찰 JSON이 올바른 모양인지 (요청마다)
3) API 응답 모양 (FastAPI가 /docs 문서를 만들 때 사용)

"""
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# vision.py 프롬프트가 AI에게 채우라고 하는 관찰 필드. 규칙의 key는 이 중 하나여야 한다.
OBSERVATION_FIELDS = {
    "is_transparent", "label_attached", "liquid_inside",
    "food_residue", "red_oil_stain", "material",
}


# ---------- 1) rules.json ----------

class Option(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str                      # 버튼에 보일 글자
    value: str                      # 눌렀을 때 보낼 값


class Check(BaseModel):
    model_config = ConfigDict(extra="forbid")   # 모르는 키(오타)가 있으면 오류
    key: str
    method: Literal["photo", "question"]
    ok: str                                     # 이 값이면 통과
    action: Optional[str] = None                # 통과 못 하면 할 일 → 체크리스트
    redirect_disposal: Optional[str] = None     # 처리로 해결 안 되면 배출처 변경
    question: Optional[str] = None              # method가 question일 때 질문 문구
    options: Optional[List[Option]] = None      # 질문 선택지 (없으면 예/아니요)

    @model_validator(mode="after")
    def _check_fields(self):
        if self.method == "photo" and self.key not in OBSERVATION_FIELDS:
            raise ValueError(f"'{self.key}'는 AI가 관찰하는 필드가 아니에요: {sorted(OBSERVATION_FIELDS)}")
        if self.method == "question" and not self.question:
            raise ValueError(f"'{self.key}': question 방식은 question 문구가 필요해요")
        if not self.action and not self.redirect_disposal:
            raise ValueError(f"'{self.key}': action 또는 redirect_disposal 중 하나가 필요해요")
        return self


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    type: Literal["state", "info"]
    disposal: str
    fallback_disposal: Optional[str] = None
    source: str
    verified: bool = False                      # 기획팀이 확정한 기준인지
    checks: List[Check] = []
    warnings: List[str] = []

    @model_validator(mode="after")
    def _check_type(self):
        if self.type == "state" and not self.checks:
            raise ValueError(f"'{self.name}': state 품목은 checks가 하나 이상 필요해요")
        if self.type == "state" and not self.fallback_disposal:
            raise ValueError(f"'{self.name}': state 품목은 fallback_disposal이 필요해요")
        return self


class RuleSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    items: Dict[str, Rule]


# ---------- 2) AI 관찰 결과 ----------

class Observation(BaseModel):
    item: str = "unsupported"
    confidence: float = 0.0
    same_item: Literal["true", "false", "unknown"] = "unknown"
    observations: Dict[str, str] = {}
    notes: str = ""


# ---------- 3) API 응답 ----------

class ChecklistItem(BaseModel):
    key: str
    text: str


class Question(BaseModel):
    key: str
    text: str
    options: List[Option]


class Judgement(BaseModel):
    status: Literal["pass", "need_action", "retake", "question",
                    "fallback", "different_item", "unsupported"]
    message: str
    item: str
    attempt: int
    max_attempts: int
    checklist: List[ChecklistItem] = []
    questions: List[Question] = []
    retake: List[str] = []
    warnings: List[str] = []
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