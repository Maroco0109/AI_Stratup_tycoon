- Run locally:

```
pip install streamlit requests python-dotenv
streamlit run app.py
```

- Ollama quickstart:

```
ollama create eeve -f modelfile
ollama run eeve
```

- Model note (GGUF):
- EEVE runs as a GGUF model compatible with llama.cpp executors (Ollama). Use a local `.gguf` path in `modelfile`.

- Known limits:
- One `st.chat_input` per page. Keep responses short (one paragraph). Engine and model must output JSON-only in a single fenced block.
- OpenAI scores responses; EEVE handles qualitative outputs and events.
