# AI 스타트업 타이쿤 (AI Startup Tycoon)

로컬 LLM(Ollama EEVE)과 Streamlit을 활용한 7일차 AI 스타트업 경영 시뮬레이션 게임입니다.
사용자는 매일 발생하는 사업 이슈에 대해 한 문단으로 대응 전략을 제시하고, LLM 기반 채점 시스템으로부터 피드백과 점수를 받습니다.

---

## 📋 프로젝트 개요

### 목적
- **AI/LLM 기반 의사결정 시뮬레이션**: 실제 스타트업이 직면하는 기술적 문제(데이터 유출, API 비용, 과적합 등)를 체험
- **로컬 LLM 활용**: Ollama를 통해 완전히 로컬 환경에서 실행 가능한 LLM 게임 구현
- **교육적 가치**: AI/LLM 스타트업 운영에 필요한 기술적 고려사항 학습

### 핵심 특징
- **7일 시뮬레이션**: Day 1(아이디어 제출) → Days 2-5(기술 문제 해결) → Day 6(투자 피칭) → Day 7(최종 리포트)
- **단일 페이지 채팅 UI**: Streamlit의 chat interface를 활용한 직관적인 대화형 인터페이스
- **3단계 Fallback 시스템**: LLM 실패 시에도 안정적인 게임 진행 보장
- **터미널 스타일 UI**: 클래식 녹색 터미널 테마로 레트로 게임 감성 구현

---

## 🏗️ 프로젝트 구조

```
AI_Stratup_tycoon/
├── app.py                      # Streamlit UI (메인 진입점)
├── engine.py                   # 게임 엔진 (이벤트/채점/리포트 생성)
├── config.py                   # 설정 (Ollama URL, 모델명, 점수 범위)
├── state.py                    # Streamlit session state 초기화
├── log.py                      # 인터랙션 로깅 (JSONL)
├── prompts/
│   └── templates.py           # 프롬프트 템플릿 및 루브릭
├── logs/
│   ├── interactions.jsonl     # 일일 인터랙션 로그
│   └── final.jsonl            # 최종 리포트 로그
├── tests/
│   └── smoke_local.py         # Ollama 연결 테스트
├── requirements.txt           # Python 의존성
└── .env                       # 환경 변수 (OLLAMA_BASE_URL, OPENAI_API_KEY)
```

---

## 🛠️ 기술 스택

### 프론트엔드
- **Streamlit 1.32+**: 웹 UI 프레임워크
- **Custom CSS**: 터미널 스타일 테마 (녹색 모노스페이스)

### 백엔드 & LLM
- **Python 3.11.14**: 메인 프로그래밍 언어
- **Ollama**: Runpod
- **EEVE 10.8B GGUF**: 한국어 Instruct 모델 (메인)
- **OpenAI GPT-4o-mini**: 채점용 (옵션, 실패 시 로컬 fallback)
- **requests**: HTTP 통신
- **python-dotenv**: 환경 변수 관리

### 데이터 & 로깅
- **JSONL**: 구조화된 로그 저장
- **Session State**: Streamlit 세션 간 상태 유지

---

## 🤖 사용 모델

### EEVE (로컬 Ollama)
- **모델**: EEVE 10.8B GGUF
- **역할**:
  - Event Card Summary 생성 (Day 1-6)
  - 정성 평가 (reason, llm_summary) 생성
- **엔드포인트**: `http://localhost:11434/api/chat`
- **설정**: `temperature=0.7`, `num_ctx=4096`

### OpenAI GPT-4o-mini
- **역할**:
    - 정량 채점 (delta, score) + 정성 평가 (reason, llm_summary)
- **Fallback**: OpenAI 미설정 시 `_fallback_llm_score` (EEVE) → `_fallback_delta` (키워드) 사용

---

## 🎮 게임 플로우 & 알고리즘

### Day 별 Event Card 생성 (engine.py)

#### 생성 방식
각 Day의 **title은 하드코딩**되어 있으며, **summary는 EEVE가 생성**을 시도합니다.

```python
# engine.py: get_event_card()
def get_event_card(day: int):
    if day == 1:
        title = "Day 1: AI 관련 사업 아이디어 제출"
        summary = _generate_summary_with_eeve(title) or "fallback summary"
        return {
            "day": 1,
            "title": title,
            "summary": summary,  # EEVE 생성 or fallback
            "constraints": [...],
            "eval_focus": [...],
            "response_instructions": "..."
        }
```

#### Day 별 이벤트 주제

| Day | 주제 | Title 예시 | Summary 생성 |
|-----|------|-------------|--------------|
| **1** | 사업 아이디어 제출 | "Day 1: AI 관련 사업 아이디어 제출" | 모델 요약 시도 |
| **2** | 데이터 유출 위험 | "Day 2: 데이터 유출 위험 발생" | 모델 요약 시도 |
| **3** | API 비용 급증 | "Day 3: 최근 1주간 API 요청 증가..." | 모델 요약 시도 |
| **4** | 모델 과적합 | "Day 4: 모델 성능 하락 (과적합)" | 모델 요약 시도 |
| **5** | 기기 발열 문제 | "Day 5: 사용자 피드백 - 기기 발열..." | 모델 요약 시도 |
| **6** | 투자자 피칭 | "Day 6: 투자자 피칭" | 모델 요약 시도 |
| **7** | 최종 리포트 | - | 전체 로그 기반 위험/권고사항 생성 |

#### Summary 생성 함수

```python
def _generate_summary_with_eeve(title: str) -> str:
    """EEVE로 title을 1문장 한국어로 요약"""
    sys_prompt = "Summarize the title in 1 Korean sentence. Output only the summary."
    user_prompt = f"Title: {title}\nSummary:"
    raw = _ollama_chat([
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt}
    ])
    return raw.strip()[:200]  # 200자 제한
```

**실패 시**: 하드코딩된 fallback summary 사용

---

## 📊 채점 시스템 (3-Tier Fallback)

### 채점 플로우 (engine.py: judge_day)

```
┌─────────────────────────────────────────┐
 1) Event Card 생성
    - get_event_card
        → 실패시 hard-coded text 출력
└─────────────────────────────────────────┘
    ↓
사용자 입력
    ↓
┌─────────────────────────────────────────┐
 2) EEVE Qualitative
    - reason, llm_summary 생성 시도
    - 실패해도 계속 진행
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
 3) Scorer (3단계 fallback)
    ① OpenAI/EEVE (_fallback_llm_score)         
      → 실패 시                          
    ② Keyword (_fallback_delta)           
      → 최후 안전망              
└─────────────────────────────────────────┘
    ↓
병합: EEVE reason/llm_summary + Scorer delta/score
    ↓
Daily Report 반환
```

### Tier 1: OpenAI/EEVE Scorer

```python
def _openai_score(day, user_text, prev_score):
    messages = [
        {"role": "system", "content": _openai_system_prompt(day)},
        {"role": "user", "content": _scoring_user_payload(day, user_text, prev_score)}
    ]
    obj = _openai_chat_json(messages)  # 실제로는 Ollama EEVE 호출
    return {
        "delta": int(obj.get("delta", 0)),
        "score": max(0, prev_score + delta),
        "reason": obj.get("reason", ""),
        "llm_summary": obj.get("llm_summary", "")
    }
```

**출력**: `{delta, score, reason, llm_summary}`

### Tier 2: Fallback-LLM (EEVE, 의미론적 평가)

```python
def _fallback_llm_score(day, user_text, prev_score):
    sys = "Judge semantically, not by keywords. Delta bounds: [-8, +5]."
    raw = _ollama_chat([{"role": "system", "content": sys}, ...])
    obj = _safe_json(raw)
    return {"delta": ..., "score": ..., "reason": ..., "llm_summary": ...}
```

**특징**: 키워드 매칭 대신 의미 기반 평가 (LLM 기반)

### Tier 3: Keyword Fallback

```python
def _fallback_delta(day, user_text) -> Dict[str, Any]:
    text = user_text.lower()

    if day == 1:
        keywords = ["개인정보", "프라이버시", "ai", "llm", "rag", ...]
        found = [k for k in keywords if k in text]
        creativity = len(user_text) // 90
        feasibility = 5 if found else 2
        delta = creativity + feasibility
        reason = f"창의성 {creativity}점, 실현가능성 {feasibility}점. 발견: {found[:3]}"

    elif day == 2:
        keywords = ["롤백", "복구", "모니터링", "알림", "유출", "마스킹", ...]
        hits = len([k for k in keywords if k in text])
        delta = 3 if hits >= 5 else (1 if hits >= 3 else -10)
        reason = f"대응책 {hits}개 발견: {keywords_found}"

    # ... Day 3-6 동일 패턴

    return {"delta": delta, "reason": reason, "llm_summary": llm_summary}
```

**키워드 리스트 (Day별)**:

- **Day 1**: 개인정보, 프라이버시, 모더레이션, 가드레일, ai, llm, rag
- **Day 2**: 롤백, 복구, 모니터링, 알림, 경보, 캐시, 로깅, 유출, 마스킹, 보호
- **Day 3**: 적합, 풋프린트, 용량, 컨텍스트, 길이, 모델, ddos
- **Day 4**: 과적합, 정규화, l2, l1, 드롭아웃, 하이퍼파라미터, 데이터 증강
- **Day 5**: 양자화, 크기, 파라미터, 변경, 교체, 모델
- **Day 6**: 문제, 고객, ai, llm, 모델, 시장, 세그먼트, 해자, 트랙션, 지표, 팀, 펀딩

---

## 📝 각 모델이 생성하는 텍스트

### EEVE (Ollama)

#### 1. Event Card Summary (Day 1-6)
```json
// 입력
{"role": "system", "content": "Summarize the title in 1 Korean sentence."}
{"role": "user", "content": "Title: Day 2: 데이터 유출 위험 발생\nSummary:"}

// 출력 (EEVE)
"학습 데이터에서 개인정보가 유출되는 문제가 발견되었습니다."
```

#### 2. Qualitative Evaluation (reason, llm_summary)
```json
// 입력 (매우 간소화된 프롬프트)
{"role": "system", "content": "JSON output only. Format: {\"reason\": \"keywords found: X, Y\" or \"no keywords\", \"llm_summary\": \"good\" or \"needs improvement\"}"}
{"role": "user", "content": "Day 1 text:\n사용자의 AI 사업 아이디어...\n\nFind keywords. Output JSON."}

// 출력 (EEVE - 시도)
{"reason": "keywords found: ai, llm", "llm_summary": "good"}
```

**Note**: EEVE qualitative는 자주 실패하므로 fallback scorer의 reason/llm_summary를 사용

#### 3. Scorer (delta, score 계산)
```json
// 입력
{"role": "system", "content": "Judge semantically... Delta bounds: [-8, +5]."}
{"role": "user", "content": "Day: 2\nPrev Score: 100\nUser Paragraph: 데이터 유출 방지를 위해...\n"}

// 출력 (EEVE)
{
  "day": 2,
  "delta": -5,
  "score": 95,
  "reason": "대응책이 부족합니다",
  "llm_summary": "모니터링 체계 보완 필요"
}
```

### Keyword Fallback

```json
// 입력: 사용자 텍스트 "롤백, 모니터링, 알림 시스템 구축"

// 출력 (Keyword 시스템)
{
  "delta": 1,
  "reason": "[Keyword] 일부 대응책이 제시되었으나 보완 필요. 발견: 롤백, 모니터링, 알림",
  "llm_summary": "[Keyword] 기본 대응 방안은 있으나 추가 안전장치 필요"
}
```

---

## 🎯 점수 시스템

### 점수 범위
- **Day 1**: +0 ~ +10 (보너스)
  - 창의성: 0~5점
  - 실현가능성: 0~5점 (키워드 매칭)
- **Day 2-6**: -20 ~ +5 (페널티 중심)
  - 적절한 대응: 0~+5
  - 불충분한 대응: -5 ~ -20

### 최종 등급
- **A**: 80점 이상
- **B**: 60~79점
- **C**: 30~59점
- **D**: 0~29점

---

## 🚀 실행 방법

### 로컬 환경

#### 1. 의존성 설치
```bash
pip install -r requirements.txt
```

#### 2. Ollama 설치 & 모델 생성
```bash
# Ollama 설치 (https://ollama.com)
curl -fsSL https://ollama.com/install.sh | sh

# EEVE 모델 생성
ollama create eeve -f modelfile

# 모델 확인
ollama run eeve
```

#### 3. 환경 변수 설정 (선택)
`.env` 파일 생성:
```env
OLLAMA_BASE_URL=http://localhost:11434/api
MODEL_NAME=eeve
OPENAI_API_KEY=sk-...
```

#### 4. Streamlit 실행
```bash
streamlit run app.py
```

브라우저에서 `http://localhost:8501` 접속

#### 5. 테스트
```bash
python test_ollama_connection.py  # Ollama 연결 테스트
python -m tests.smoke_local        # Day 2 응답 테스트
```

---

### RunPod 환경

#### 1. Pod 준비
- GPU Pod 생성 (VRAM 12GB+ 권장)
- Ollama 설치

#### 2. Ollama 서버 시작
```bash
export OLLAMA_HOST=0.0.0.0
ollama serve &  # 백그라운드 실행
ollama create eeve -f modelfile
```

#### 3. 의존성 설치
```bash
pip install -r requirements.txt
```

#### 4. 환경 변수 설정
`.env` 파일:
```env
OLLAMA_BASE_URL=https://your-runpod-url.proxy.runpod.net/api
MODEL_NAME=eeve
OPENAI_API_KEY=sk-...
```

#### 5. Streamlit 실행
```bash
streamlit run app.py
```

#### 6. 포트 노출
- **8501**: Streamlit (외부 노출)
- **11434**: Ollama (내부 전용)

---

## 🐛 디버깅 & 로깅

### 디버그 로그 확인
`engine.py`에 상세한 디버그 로깅이 추가되어 있습니다:

```python
# 콘솔 출력 예시
[DEBUG] Ollama chat URL: http://localhost:11434/api/chat
[DEBUG] Model: eeve
[DEBUG] Status code: 200
[DEBUG] Content length: 156
[DEBUG] judge_day called: day=1, score=100
[DEBUG] EEVE qualitative...
[DEBUG] Keyword fallback success - delta: 6, new_score: 106
```

### 로그 파일
- `logs/interactions.jsonl`: 일일 인터랙션 기록

```jsonl
{"ts": "2025-11-06T...", "day": 1, "delta": 6, "score": 106, "reason": "[Keyword] ...", ...}
```

---

## ⚙️ 설정 (config.py)

```python
# Ollama 설정
OLLAMA_BASE_URL = "http://localhost:11434/api"
MODEL_NAME = "eeve"
TEMPERATURE = 0.7
NUM_CTX = 4096

# JSON 파싱
STRICT_JSON = True      # ```json fence 필수
ALLOW_FALLBACK = True   # 관대한 파싱 허용

# 점수 범위
DAY1_CREATIVE_MAX = 5
DAY1_FEASIBLE_MAX = 5
PENALTY_MIN = -20
PENALTY_MAX = -5

# OpenAI
OPENAI_BASE_URL = "https://api.openai.com/v1"
OPENAI_MODEL = "gpt-4o-mini"
```

---

## 🎨 UI 커스터마이징

### 터미널 스타일 CSS (app.py)
```css
:root {
    --term-fg: #33ff33;  /* 녹색 텍스트 */
    --term-bg: #000000;  /* 검은 배경 */
    --term-border: #1a521a;  /* 어두운 녹색 테두리 */
}
```

---

## 📚 알려진 제약사항

1. **Streamlit 제한**: 페이지당 `st.chat_input` 1개만 허용
2. **EEVE 한계**: 소형 모델로 JSON 생성 실패 시 fallback 사용
3. **OpenAI 의존성**: 미설정 시 로컬 fallback만 사용 (정확도 낮음)
4. **토큰 제한**: 한 문단 입력 제한 (긴 답변 처리 불가)
