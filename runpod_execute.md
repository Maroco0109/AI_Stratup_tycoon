# Runpod 실행 가이드 — EEVE(Ollama) 원격 호출 설정

이 문서는 Runpod에서 Ollama(EEVE 모델)를 실행하고, 로컬 앱(Streamlit)에서 원격으로 호출하는 방법을 단계별로 설명합니다.

## 1) 준비 사항
- Runpod GPU Pod 생성 (Ubuntu 기반 이미지 권장). 템플릿에 "Ollama"가 포함된 이미지를 쓰면 설치가 간단합니다.
- 외부에서 접근할 포트: 11434(Ollama), 필요 시 8501(Streamlit)도 공개.
- Pod에 SSH 또는 Web Terminal로 접속.

## 2) Pod에서 Ollama 준비
Ollama가 설치되어 있지 않다면 설치 후 데몬을 기동합니다.

```bash
# (필요 시) 설치
curl -fsSL https://ollama.com/install.sh | sh

# 데몬 시작 및 외부 바인딩
export OLLAMA_HOST=0.0.0.0
ollama serve &

# 내부에서 상태 확인
curl -s http://127.0.0.1:11434/api/tags | jq .
```

정상이라면 JSON으로 설치된 모델 목록이 출력됩니다(초기에는 비어 있을 수 있음).

## 3) 모델(GGUF) 파일 배치 및 생성
- 이 레포의 `modelfile`는 로컬 GGUF 경로를 참조합니다. Pod에 GGUF 파일을 업로드하고 `modelfile`의 `FROM` 경로를 GGUF 파일명에 맞게 수정하세요.
- 예: `./eeve-10.8b.Q4_K_M.gguf`

```bash
# (예) GGUF 업로드 후 같은 디렉터리에 위치했다고 가정
ls -al

# modelfile의 FROM 경로가 GGUF 파일명과 일치하는지 확인/수정 후 모델 생성
ollama create eeve -f Modelfile

# (선택) 인터랙티브 테스트 — 종료하려면 Ctrl+C
ollama run eeve

# 태그 확인
curl -s http://127.0.0.1:11434/api/tags | jq .
```

여기서 모델 이름 `eeve`는 이후 애플리케이션의 `MODEL_NAME`과 일치해야 합니다.

## 4) Runpod 포트/프록시 공개
- Runpod UI의 Ports/Networking에서 11434 포트를 공개(Expose)합니다.
- Runpod가 제공하는 프록시 URL은 보통 다음 형식입니다:
  - `https://<POD_ID>-11434.proxy.runpod.net`
- 외부에서 Ollama API는 `.../api` 경로 아래에 있습니다. 최종 기본 엔드포인트 예:
  - `https://<POD_ID>-11434.proxy.runpod.net/api`

프록시가 활성화되어 있어야 로컬 PC에서 Pod의 Ollama에 접근할 수 있습니다.

## 5) 로컬 애플리케이션 환경 변수 설정
이 레포의 `config.py`는 환경변수를 우선 사용합니다. `.env` 또는 쉘 환경변수로 설정하세요.

`.env` 예시(레포 루트 경로):
```
OLLAMA_BASE_URL=https://<POD_ID>-11434.proxy.runpod.net/api
MODEL_NAME=eeve
OPENAI_API_KEY=sk-...   # (선택) OpenAI 점수 산정용 키 — 없으면 보수적 폴백 점수 사용
```

PowerShell(Windows) 예시:
```powershell
$env:OLLAMA_BASE_URL="https://<POD_ID>-11434.proxy.runpod.net/api"
$env:MODEL_NAME="eeve"
$env:OPENAI_API_KEY="sk-..."   # 선택
```

bash/zsh(macOS/Linux) 예시:
```bash
export OLLAMA_BASE_URL="https://<POD_ID>-11434.proxy.runpod.net/api"
export MODEL_NAME="eeve"
export OPENAI_API_KEY="sk-..."   # 선택
```

주의: URL 끝에 반드시 `/api`를 포함하세요. 엔진은 내부에서 `.../chat` 경로를 추가해 호출합니다.

## 6) 연결 확인 (스모크 테스트)
로컬에서 레포 루트에서 실행합니다.

```bash
python -m tests.smoke_local
```

정상이라면 `{"day": ..., "reason": ..., "llm_summary": ...}` 형태의 JSON이 출력됩니다.

문제 해결 팁:
- 502/504: Runpod 프록시가 닫혀 있거나 Pod가 준비되지 않았을 수 있습니다. 포트 노출과 Ollama 데몬 상태 확인.
- 404: 엔드포인트에 `/api`가 빠졌을 가능성이 큽니다.
- 500: 모델이 로드되지 않았을 수 있습니다. `api/tags`에서 `eeve` 존재 확인 또는 `ollama run eeve`로 점검.

## 7) 앱 실행
로컬에서 Streamlit UI 실행:

```bash
streamlit run app.py
```

사이드바의 `GENERATOR` 항목에 `MODEL_NAME @ OLLAMA_BASE_URL`이 표시됩니다. Runpod 프록시 URL이 보이면 원격 EEVE 호출이 설정된 것입니다.

Pod 내부에서 Streamlit을 구동하려면(선택):
```bash
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```
Runpod에서 8501 포트를 추가로 공개하고 브라우저에서 `http://<POD_HOST>:8501`로 접속하세요.

## 8) 참고 및 주의사항
- 모델 이름 일치: `ollama create <이름>`에서 사용한 이름과 `.env`의 `MODEL_NAME`이 같아야 합니다.
- OpenAI 키: 점수 산정(테스터) 용도로 사용됩니다. 키가 없으면 엔진의 폴백 점수 로직이 적용됩니다.
- JSON-only 규칙: 모델 출력은 반드시 하나의 ```json 펜스 블록 안에 하나의 JSON 객체만 포함해야 합니다. 규칙을 지키지 않으면 파싱 오류로 일(day)이 진행되지 않을 수 있습니다.
- 보안: Runpod 프록시 URL은 외부에 노출될 수 있습니다. 사용 후 포트를 닫거나 접근 제어(허용 IP 제한 등)를 권장합니다.
