"""설정값을 한 곳에 모은다. 실험하거나 배포할 때 바꿀 값은 .env(환경 변수)로 덮어쓸 수 있다.

예) .env 에 CONFIRM_BELOW=0.5 를 넣으면 코드를 고치지 않고 확신도 기준을 바꿔 볼 수 있다.
"""
import os
import secrets

from dotenv import load_dotenv

load_dotenv()

# ---------- AI ----------
AI_PROVIDER = os.getenv("AI_PROVIDER", "openai")       # 어떤 AI로 관찰할지 (app.py의 OBSERVERS 참고)
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
AI_TIMEOUT = float(os.getenv("AI_TIMEOUT", "30"))      # 초. 넘으면 AI_FAILED
PREV_IMAGE_DETAIL = os.getenv("PREV_IMAGE_DETAIL", "low")  # 처음 사진은 같은 물건인지만 보면 돼서 저해상도

# ---------- 판정 ----------
MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "3"))      # 재촬영 한도
CONFIRM_BELOW = float(os.getenv("CONFIRM_BELOW", "0.6"))  # 품목 확신도가 이보다 낮으면 "○○ 맞나요?"

# ---------- 업로드·이미지 ----------
MAX_BYTES = 15 * 1024 * 1024        # 업로드 최대 15MB
MAX_SIDE = 1024                     # AI에 보내기 전 긴 변 픽셀
MAX_PIXELS = 50_000_000             # 이보다 픽셀이 많으면 열기 전에 거부 (픽셀 폭탄 방지)

# ---------- 서버 ----------
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")]
# 관찰 결과에 서명할 비밀값. 없으면 서버가 켜질 때마다 새로 만든다(재시작하면 이전 서명은 무효 → AI를 다시 부름).
# 배포할 때는 환경 변수로 고정하세요.
SESSION_SECRET = os.getenv("SESSION_SECRET") or secrets.token_hex(32)