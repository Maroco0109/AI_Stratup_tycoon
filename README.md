# AI 스타트업 타이쿤 — Local LLM + Streamlit

로컬 Ollama(GGUF) + Streamlit UI로 즐기는 7일 경영 게임입니다. EEVE 10.8B(또는 호환 Instruct) 모델을 사용하며, 점수는 OpenAI로 산정(선택)하거나 안전한 폴백 규칙으로 계산됩니다.

## 주요 특징
- 단일 페이지 채팅 UI: `st.chat_message` + `st.chat_input`(페이지당 1개)
- 로컬 LLM: Ollama `/api/chat`으로 EEVE(GGUF) 호출
- 7일 루프: 일자별 이벤트 → 사용자 한 문단 입력 → 채점/로그 → 다음 날
- 최종 보고서: `final_score`, `final_grade`, `risk_report[]`, `next_recommendations[]`

## 폴더 구조
```
app.py                 # Streamlit UI
engine.py              # 게임 오케스트레이터(이벤트/채점/최종 보고)
config.py              # 엔드포인트/스코어링 범위/옵션
modelfile              # Ollama 모델 빌드 파일(EEVE GGUF)
prompts/rulebook.md    # SYSTEM 프롬프트(JSON-only 규칙)
prompts/templates.py   # 간단한 프롬프트 빌더
tests/smoke_local.py   # Day 2 질적 응답 스모크 테스트
requirements.txt       # 최소 의존성
```

## 빠른 실행(로컬)
사전 준비: Python 3.10+, Ollama 설치, EEVE GGUF 또는 `modelfile` 준비

1) 의존성 설치
- `pip install -r requirements.txt`

2) Ollama 모델 빌드/실행
- `ollama create eeve -f modelfile`
- `ollama run eeve`

3) 앱 실행
- `streamlit run app.py`

4) 스모크 테스트(선택)
- `python -m tests.smoke_local`

기본 구성은 `config.py`를 따르며, Ollama REST 기본값은 `http://localhost:11434/api`, 모델명은 `eeve-10.8b`입니다.

## RunPod에서 실행(동일 Pod)
Streamlit(웹)과 Ollama(LLM)를 동일 Pod에서 실행하고, 외부에는 Streamlit(8501)만 노출하는 구성을 권장합니다.

1) 의존성 설치
- `pip install -r requirements.txt`

2) Ollama 데몬/모델 준비
- `export OLLAMA_HOST=0.0.0.0`
- `ollama serve &`  (백그라운드 실행)
- `ollama create eeve -f modelfile`
- (선택) `ollama run eeve`로 워밍업

3) 환경 변수/시크릿
- OpenAI 점수 산정 사용 시 `.env` 또는 Pod 환경변수에 `OPENAI_API_KEY` 설정
- `config.py` 기본값으로 Ollama는 `http://127.0.0.1:11434/api`를 사용합니다.

4) 앱 구동 및 포트
- `streamlit run app.py --server.address 0.0.0.0 --server.port 8501`
- RunPod에서 8501만 외부로 노출, 11434는 내부 전용 유지 권장

5) 확인
- `python -m tests.smoke_local`
- 브라우저로 `http://<pod-host>:8501` 접속

## Streamlit Community Cloud 배포
Cloud에서는 로컬 Ollama를 띄울 수 없습니다. 원격 Ollama API를 HTTPS로 공개하고, 앱은 그 URL을 사용해야 합니다.

1) 원격 Ollama 서버 준비
- 서버에서 모델 생성: `ollama create eeve -f modelfile`
- `ollama serve`를 서비스로 실행
- 리버스 프록시(Nginx/Caddy)로 `https://llm.example.com/api`(→ `127.0.0.1:11434`) 노출
- 접근 제어(허용 IP/Basic Auth 등) 적용 권장

2) Streamlit Cloud 설정
- 저장소에 `requirements.txt` 포함(`streamlit`, `requests`, `python-dotenv`)
- 배포 시 메인 파일로 `app.py` 선택
- App settings → Secrets:
  - `OLLAMA_BASE_URL = "https://llm.example.com/api"`
  - `MODEL_NAME = "eeve-10.8b"`
  - (선택) `OPENAI_API_KEY = ...`

3) 주의 사항
- Cloud에서 `http://localhost:11434`는 동작하지 않습니다.
- HTTPS 권장(일부 플랫폼은 HTTP/임의 포트 제한)
- Ollama 엔드포인트는 반드시 보호(앱 자체 인증 없음)

## 설정 가이드
- `config.py`
  - `OLLAMA_BASE_URL = "http://localhost:11434/api"`
  - `MODEL_NAME = "eeve-10.8b"`
  - `TEMPERATURE = 0.7`, `NUM_CTX = 4096`
  - `STRICT_JSON = True`, `ALLOW_FALLBACK = True`
  - 점수 버킷: A(80+), B(60–79), C(30–59), D(0–29)
- `.env`(선택)
  - `OPENAI_API_KEY=...`
  - 필요 시 `OLLAMA_BASE_URL`, `MODEL_NAME` 재정의 가능

## 테스트
- `python -m tests.smoke_local`
  - Ollama에 Day 2 질의 → JSON 펜스 블록에서 `day`, `reason`, `llm_summary` 추출 검증

## 알려진 제약
- Streamlit은 페이지 당 `st.chat_input` 1개 제한
- 모델 출력은 JSON-only(코드펜스) 기대, 파싱 실패 시 친화적 오류 처리
- OpenAI 미설정 시 보수적 폴백 점수 사용

