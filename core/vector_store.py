"""
Hindsight retrieval store. Uses a simple hashing-based bag-of-words vector
so it runs fully offline with zero model download — swap _embed() for
sentence-transformers (all-MiniLM-L6-v2) + a real LanceDB table once you
want semantic rather than lexical similarity. The retrieval interface
(add/search) stays the same either way, so nothing upstream changes.
"""
import json
import math
import os
import re
from collections import Counter
from pathlib import Path

STORE_PATH = Path(os.environ.get(
    "DEAL_INTEL_VECTORS",
    str(Path(__file__).parent.parent / "data" / "hindsight_vectors.jsonl"),
))


def _embed(text: str) -> Counter:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return Counter(tokens)


def _cosine(a: Counter, b: Counter) -> float:
    common = set(a) & set(b)
    dot = sum(a[t] * b[t] for t in common)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def add(deal_id: str, text: str, metadata: dict):
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {"deal_id": deal_id, "text": text, "metadata": metadata}
    with open(STORE_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")


def search(text: str, top_k: int = 3):
    """Returns top_k closed-deal hindsight records most similar to `text`,
    each with a similarity score, highest first."""
    if not STORE_PATH.exists():
        return []
    query_vec = _embed(text)
    scored = []
    with open(STORE_PATH) as f:
        for line in f:
            record = json.loads(line)
            score = _cosine(query_vec, _embed(record["text"]))
            scored.append((score, record))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"score": round(s, 3), **r} for s, r in scored[:top_k] if s > 0]
