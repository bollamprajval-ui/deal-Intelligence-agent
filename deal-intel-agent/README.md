# Deal AI

Local deal tracker: one live document per deal, one AI per deal (Ollama), hindsight from closed deals.

## Run

1. Install [Ollama](https://ollama.com) and start it. A model must be pulled, for example:

   ```text
   ollama pull qwen2.5-coder:3b
   ```

2. Python 3.11+ (3.13 works). From this folder:

   ```text
   cd deal-intel-agent
   py -3.13 -m pip install -r requirements.txt
   py -3.13 -m uvicorn api:app --host 127.0.0.1 --port 8765
   ```

3. Open [http://127.0.0.1:8765/](http://127.0.0.1:8765/)

Ollama is detected automatically. Sidebar shows the model name when it is ready.

Optional:

- `OLLAMA_MODEL=qwen3:8b` — pick a specific model (slower if large).
- `USE_OLLAMA=0` — run without a model (log still saves; Ask will say Ollama is off).
- `DEAL_INTEL_DISABLE_SCHEDULER=1` — skip background file polling.

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
