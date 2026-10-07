import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
DB_PATH = ROOT / "preflight.sqlite"
MODEL = os.getenv("PREFLIGHT_MODEL", "claude-sonnet-5-5")
# local: 혼자 쓰는 개발 모드(작업 공간 코드 없이 'local' 하나). public: 작업 공간 코드로 사용자별 격리.
PUBLIC_MODE = os.getenv("PREFLIGHT_MODE", "local").lower() == "public"
# AI 호출 상한(하루, KST). 공개 배포 시 API 비용 폭주를 막는다. 환경변수로 조절.
DAILY_LLM_LIMIT_PER_WORKSPACE = int(os.getenv("PREFLIGHT_DAILY_LIMIT", "30"))
DAILY_LLM_LIMIT_GLOBAL = int(os.getenv("PREFLIGHT_GLOBAL_DAILY_LIMIT", "300"))

# 캠페인 문구 최대 글자 수(한글 1자 = 1자). 화면 입력 제한과 서버 검증에 함께 쓴다.
MAX_CHARS = 500
SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3}
# 이 단계 이상이면 "사람 확인 필요"로 표시한다.
REVIEW_THRESHOLD = "medium"
