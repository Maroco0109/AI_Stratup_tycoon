"""
Project configuration knobs

- Centralizes model endpoints and scoring ranges
- OpenAI handles scoring only; EEVE(Ollama) handles everything else
- Loads environment variables from a local .env if present (python-dotenv)
"""

# Load .env (optional) early so env vars are available
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except Exception:
    # It’s okay if python-dotenv isn’t installed; env vars may still come from OS
    pass

# EEVE (Ollama) generation endpoint and model
OLLAMA_BASE_URL = "http://localhost:11434/api"  # Ollama REST base URL
MODEL_NAME = "eeve-10.8b"                        # Local GGUF-backed model in Ollama

# Model options passed to Ollama
TEMPERATURE = 0.7
NUM_CTX = 4096

# JSON parsing policy used by engine._safe_json
STRICT_JSON = True       # Require a ```json fenced block when True
ALLOW_FALLBACK = True    # Allow lenient parsing fallback if needed

# Scoring ranges (centralized for easy tuning)
DAY1_CREATIVE_MAX = 5
DAY1_FEASIBLE_MAX = 5
PENALTY_MIN = -20
PENALTY_MAX = -5

# Final grade buckets
# A: >= 80, B: 60–79, C: 30–59, D: 0–29

# OpenAI (scorer) settings — OpenAI scores user input, EEVE does the rest
OPENAI_BASE_URL = "https://api.openai.com/v1"
OPENAI_MODEL = "gpt-4o-mini"

# The engine reads the API key from this environment variable
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
