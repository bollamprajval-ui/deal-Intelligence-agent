"""
One place every LLM call goes through. Ollama is used when it is running;
tests can force the stub with USE_OLLAMA=0.
"""
import os

OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:latest")
_cached_ok = None
_cached_model = None
_last_error = None


def _force_flag():
    return os.environ.get("USE_OLLAMA")


def ollama_ready() -> bool:
    global _cached_ok, _cached_model, _last_error
    force = _force_flag()
    if force == "0":
        _cached_ok, _cached_model = False, None
        return False
    if _cached_ok is True and force != "1":
        return True
    try:
        import ollama
        listing = ollama.list()
        models = listing.get("models") if isinstance(listing, dict) else getattr(listing, "models", []) or []
        names = []
        for m in models:
            if isinstance(m, dict):
                names.append(m.get("model") or m.get("name") or "")
            else:
                names.append(getattr(m, "model", None) or getattr(m, "name", "") or "")
        names = [n for n in names if n]
        preferred = os.environ.get("OLLAMA_MODEL")
        picked = None
        if preferred and any(preferred in n for n in names):
            picked = next(n for n in names if preferred in n)
        elif names:
            def _rank(n):
                nl = n.lower()
                if "3b" in nl or "1.5b" in nl:
                    size = 0
                elif "7b" in nl:
                    size = 1
                else:
                    size = 2
                return (size, n)
            picked = sorted(names, key=_rank)[0]
        if not picked and force == "1":
            picked = OLLAMA_MODEL
        _cached_ok = bool(picked) or force == "1"
        _cached_model = picked or OLLAMA_MODEL
        _last_error = None
        return _cached_ok
    except Exception as exc:
        _last_error = str(exc)
        _cached_ok = force == "1"
        _cached_model = OLLAMA_MODEL if _cached_ok else None
        return _cached_ok


def llm_status() -> dict:
    ok = ollama_ready()
    detail = "ready" if ok else "Start Ollama and pull a model (e.g. ollama pull llama3)"
    if not ok and _last_error:
        detail = f"{detail} ({_last_error})"
    if _force_flag() == "0":
        detail = "Ollama disabled (USE_OLLAMA=0)"
    return {
        "ollama": ok,
        "model": (_cached_model or OLLAMA_MODEL) if ok else None,
        "detail": detail,
    }


def call_llm(prompt: str, system: str = None) -> str:
    if ollama_ready():
        return _call_ollama(prompt, system)
    return _call_fallback(prompt, system)


def _call_ollama(prompt: str, system: str = None) -> str:
    import re
    import ollama
    model = _cached_model or OLLAMA_MODEL
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    client = ollama.Client(timeout=90)
    resp = client.chat(
        model=model,
        messages=messages,
        think=False,
        options={"num_predict": 350, "temperature": 0.3},
    )
    text = resp["message"]["content"] or ""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip() or text.strip()


def _call_fallback(prompt: str, system: str = None) -> str:
    if "Summarize this deal interaction" in prompt:
        body = prompt.split("\n", 1)[-1].strip()
        text = " ".join(body.split())
        return text if len(text) <= 280 else text[:277] + "…"
    return (
        "Ollama is not running, so I cannot reason yet. "
        "Start Ollama, pull a model (`ollama pull llama3`), and ask again. "
        "Your deal log is still being saved."
    )
