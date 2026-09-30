# Deal AI

Local deal tracker: one live document per deal, one AI per deal (Ollama), hindsight from closed deals.

## Run

1. Choose a model provider. For local development, install [Ollama](https://ollama.com) and start it. A model must be pulled, for example:

   ```text
   ollama pull qwen2.5-coder:3b
   ```

   For deployment, Gemini can be selected with environment variables. Never commit the API key:

   ```text
   LLM_PROVIDER=gemini
   GEMINI_API_KEY=<your Google AI Studio key>
   GEMINI_MODEL=gemini-2.5-flash-lite
   ```

2. Python 3.11+ (3.13 works). From this folder:

   ```text
   cd deal-intel-agent
   py -3.13 -m pip install -r requirements.txt
   py -3.13 -m uvicorn api:app --host 127.0.0.1 --port 8765
   ```

3. Open [http://127.0.0.1:8765/](http://127.0.0.1:8765/)

Ollama is detected automatically. Sidebar shows the model name when it is ready.

Provider options:

- `LLM_PROVIDER=auto` — use Gemini when `GEMINI_API_KEY` is present, otherwise Ollama (default).
- `LLM_PROVIDER=ollama` — force the local Ollama provider.
- `LLM_PROVIDER=gemini` — force Gemini; requires `GEMINI_API_KEY`.
- `OLLAMA_MODEL=qwen3:8b` — pick a specific local model (slower if large).
- `GEMINI_DISABLE_THINKING=1` — disable Gemini 2.5 thinking for faster direct responses (default).
- `USE_OLLAMA=0` — disable the local provider for tests or fallback mode.
- `DEAL_INTEL_DISABLE_SCHEDULER=1` — skip background file polling.

Database options:

- Local development defaults to SQLite at `data/deals.db`.
- Set `DATABASE_PROVIDER=firestore` and `FIREBASE_PROJECT_ID=dealagent-b1e72` to use Firebase Firestore.
- Local Firestore authentication uses `GOOGLE_APPLICATION_CREDENTIALS` pointing to a service-account JSON file. Vercel uses the secret `FIREBASE_SERVICE_ACCOUNT_JSON` instead.
- Firestore imports missing predefined records from the bundled SQLite database once, without replacing existing cloud records.
- Never commit Firebase service-account JSON files or API keys.

Data stays on this machine: `data/deals.db`.

## How to use it

| Tab | What it is |
| --- | --- |
| **Ask** | Chat. Right side (or below on phone): the document and hindsight the AI is using. |
| **Document** | Full track in numbered blocks: snapshot, people, signals, log, your notes, AI memory. |
| **Hindsight** | Closest closed deals to this one, plus the full closed-deal library. |
| **Add update** | Paste mail or notes into the document. |
| **Close** | Won / lost / stalled + why. Writes this deal into hindsight. |

On a phone, tap **Deals** to open the deal list. Ask keeps the composer pinned; the thread scrolls above it.

## Tests

```text
py -3.13 tests/test_api.py
```

Uses a throwaway database and `USE_OLLAMA=0`.
