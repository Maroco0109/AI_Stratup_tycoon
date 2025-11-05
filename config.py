"""
프로젝트 구성(config)

- 모델 엔드포인트와 점수 범위를 중앙에서 관리합니다.
- 기본 동작: OpenAI는 채점 전용, EEVE(Ollama)는 발행/질적 판단 담당.
- python-dotenv가 있으면 .env를 로드해 환경 변수를 주입합니다.
"""

import os

# Load .env (optional) early so env vars are available
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except Exception:
    # It’s okay if python-dotenv isn’t installed; env vars may still come from OS
    pass

# EEVE (Ollama) generation endpoint and model
# 한국어 설명: EEVE(Ollama) 서버 주소/모델명. 로컬 또는 원격 런팟의 Ollama REST 엔드포인트를 가정합니다.
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/api")  # Ollama REST base URL
MODEL_NAME = os.getenv("MODEL_NAME", "eeve-10.8b")                            # Local GGUF-backed model in Ollama

# Model options passed to Ollama
# 한국어 설명: 생성 다양성과 문맥 길이를 조절합니다.
TEMPERATURE = 0.7
NUM_CTX = 4096

# JSON parsing policy used by engine._safe_json
# 한국어 설명: STRICT_JSON=True면 모델 응답이 반드시 단일 ```json 코드 펜스여야 하며,
# ALLOW_FALLBACK=True면 실패 시 관대한 파싱으로 2차 시도를 허용합니다.
STRICT_JSON = True       # Require a ```json fenced block when True
ALLOW_FALLBACK = True    # Allow lenient parsing fallback if needed

# Scoring ranges (centralized for easy tuning)
# 한국어 설명: Day1 보너스 최대치, 패널티 범위 등을 중앙에서 조절합니다.
DAY1_CREATIVE_MAX = 5
DAY1_FEASIBLE_MAX = 5
PENALTY_MIN = -20
PENALTY_MAX = -5

# Final grade buckets
# A: >= 80, B: 60–79, C: 30–59, D: 0–29

# OpenAI (scorer) settings — OpenAI scores user input, EEVE does the rest
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# The engine reads the API key from this environment variable
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
