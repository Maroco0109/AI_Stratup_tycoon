## 0) Prereqs (local VS Code)

```
python --version        # 3.10+ recommended
pip --version
```

```
git clone <this-repo-url>
cd AI_Stratup_tycoon
python -m venv .venv
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

Create `.env` (local):
```
copy .env.example .env        # Windows
# or
cp .env.example .env          # macOS/Linux

# edit .env and set at least:
# OPENAI_API_KEY=sk-...
# OLLAMA_BASE_URL=http://<RUNPOD_HOST>:11434/api   # set after Runpod is ready
```

Optionally set env in shell (instead of .env):
```
# Windows (PowerShell)
$env:OPENAI_API_KEY="sk-..."
$env:OLLAMA_BASE_URL="http://<RUNPOD_HOST>:11434/api"

# macOS/Linux (bash/zsh)
export OPENAI_API_KEY="sk-..."
export OLLAMA_BASE_URL="http://<RUNPOD_HOST>:11434/api"
```

## 1) Runpod: EEVE (Ollama) only

Inside your Runpod container (terminal/SSH):

```
export OLLAMA_HOST=0.0.0.0
ollama serve &     # start the Ollama daemon listening on :11434
```

Place your GGUF next to `modelfile` (e.g., `eeve-10.8b.Q4_K_M.gguf`). Then:
```
ollama create eeve -f modelfile
ollama run eeve    # optional sanity run; Ctrl+C to stop the interactive session
```

Verify Ollama is reachable inside the pod:
```
curl -s http://127.0.0.1:11434/api/tags | jq .
```

Expose port 11434 in Runpod UI (or equivalent) so your local machine can reach:
```
# Target from local: http://<RUNPOD_HOST>:11434/api
```

## 2) Point local app to Runpod EEVE

In your local terminal (VS Code terminal):
```
# Windows (PowerShell)
$env:OLLAMA_BASE_URL="http://<RUNPOD_HOST>:11434/api"

# macOS/Linux (bash/zsh)
export OLLAMA_BASE_URL="http://<RUNPOD_HOST>:11434/api"
```

Confirm connectivity with the smoke test (local):
```
python -m tests.smoke_local
```
It should print a JSON object with `day`, `reason`, `llm_summary`.

## 3) Run the Streamlit app (local)

```
streamlit run app.py
```

- Sidebar shows Day and Score.
- Main area uses one `st.chat_input` (one paragraph per day).

## 4) Useful notes

- Model (GGUF): EEVE runs as a GGUF model under Ollama. `modelfile` must reference your local `.gguf` path inside the pod.
- JSON-only: Both EEVE (Issuer) and OpenAI (Tester) must output exactly one JSON object inside a single ```json fenced block.
- Scoring: OpenAI scores responses (set `OPENAI_API_KEY`). If absent, engine uses a deterministic fallback.
- Known limits: One `st.chat_input` per page; keep responses to one paragraph.

## 5) Test UI page (mock)

Preview the chat UI without engines (no OpenAI or Ollama required):

```
streamlit run pages/01_Test_UI_Mock.py
```

Alternatively run the main app and switch to the page from the Streamlit sidebar:

```
streamlit run app.py
```
