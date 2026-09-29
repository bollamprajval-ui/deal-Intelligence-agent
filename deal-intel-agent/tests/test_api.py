"""Hit every HTTP route against a throwaway database."""
import os
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="deal-intel-"))
os.environ["DEAL_INTEL_DISABLE_SCHEDULER"] = "1"
os.environ["DEAL_INTEL_DB"] = str(TMP / "deals.db")
os.environ["DEAL_INTEL_VECTORS"] = str(TMP / "vectors.jsonl")
os.environ["USE_OLLAMA"] = "0"

from fastapi.testclient import TestClient
from core.db import init_db
from api import app

init_db()


def test_all_endpoints():
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert "ollama" in r.json()

        r = client.get("/hindsight")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

        r = client.get("/deals")
        assert r.status_code == 200, r.text
        assert r.json() == []

        r = client.post("/deals", json={"name": "Northwind ERP", "budget": 240000})
        assert r.status_code == 200, r.text
        deal_id = r.json()["deal_id"]

        r = client.post("/deals", json={"name": "Closed Reference"})
        assert r.status_code == 200
        closed_id = r.json()["deal_id"]

        r = client.get("/deals/does-not-exist")
        assert r.status_code == 404

        r = client.get(f"/deals/{deal_id}")
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["deal"]["name"] == "Northwind ERP"
        assert doc["deal"]["stage"] == "contact"
        assert doc["timeline"] == []

        r = client.get("/deals")
        assert len(r.json()) == 2

        r = client.post(
            f"/deals/{deal_id}/people",
            json={
                "name": "Priya Shah",
                "email": "priya@northwind.test",
                "org": "Northwind",
                "role": "decision_maker",
                "side": "theirs",
            },
        )
        assert r.status_code == 200, r.text
        person_id = r.json()["person_id"]

        r = client.get(f"/deals/{deal_id}/people")
        assert r.status_code == 200
        assert any(p["email"] == "priya@northwind.test" for p in r.json())

        r = client.post(
            f"/deals/{deal_id}/people/{person_id}/role",
            json={"role": "theirs:economic_buyer"},
        )
        assert r.status_code == 200

        r = client.post(
            f"/deals/{deal_id}/inputs",
            json={
                "source": "mail",
                "sender_email": "priya@northwind.test",
                "content": "Thanks for the proposal. Budget looks acceptable. Can you send a revised timeline?",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["input_id"]

        r = client.post(
            f"/deals/{deal_id}/inputs",
            json={
                "source": "meeting",
                "content": "Call: they raised a concern about implementation delay and asked about pricing.",
            },
        )
        assert r.status_code == 200

        r = client.post(
            f"/deals/{closed_id}/inputs",
            json={"source": "mail", "content": "They approved budget and proceeded. Pricing was acceptable."},
        )
        assert r.status_code == 200

        r = client.get(f"/deals/{deal_id}/timeline")
        assert r.status_code == 200
        timeline = r.json()
        assert len(timeline) >= 2
        thread_id = timeline[0]["thread_id"]

        r = client.get(f"/threads/{thread_id}")
        assert r.status_code == 200
        assert len(r.json()) >= 1

        r = client.get("/threads/missing-thread")
        assert r.status_code == 404

        r = client.get(f"/deals/{deal_id}/stages")
        assert r.status_code == 200
        assert r.json()[0]["stage"] == "contact"

        r = client.post(f"/deals/{deal_id}/stage", json={"stage": "discovery"})
        assert r.status_code == 200
        r = client.post(f"/deals/{deal_id}/stage", json={"stage": "not-a-stage"})
        assert r.status_code == 400

        r = client.get(f"/deals/{deal_id}/signals")
        assert r.status_code == 200
        types = {s["signal_type"] for s in r.json()}
        assert "budget_mentioned" in types or "positive_signal" in types or "concern_raised" in types

        r = client.post(f"/deals/{deal_id}/ingest")
        assert r.status_code == 200
        assert r.json()["status"] == "ingested"

        r = client.post(
            f"/deals/{deal_id}/reviews",
            json={"note": "Buyer is engaged; timeline is the remaining risk."},
        )
        assert r.status_code == 200
        r = client.get(f"/deals/{deal_id}/reviews")
        assert r.status_code == 200
        assert len(r.json()) == 1

        r = client.get("/notifications")
        assert r.status_code == 200
        notes = r.json()
        assert isinstance(notes, list)
        if notes:
            nid = notes[0]["id"]
            r = client.post(f"/notifications/{nid}/read")
            assert r.status_code == 200
            r = client.get(f"/notifications?deal_id={deal_id}")
            assert r.status_code == 200

        r = client.post(
            f"/deals/{closed_id}/close",
            json={
                "outcome": "won",
                "outcome_reason": "Fast reply on pricing, champion internally forwarded the proposal.",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["outcome"] == "won"

        r = client.get(f"/deals/{deal_id}/hindsight")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

        r = client.post(f"/deals/{deal_id}/chat", json={"message": "What is stalling this deal?"})
        assert r.status_code == 200, r.text
        assert "reply" in r.json()

        r = client.get(f"/deals/{deal_id}/chat")
        assert r.status_code == 200
        assert len(r.json()) >= 2

        r = client.get(f"/deals/{deal_id}/reasoning")
        assert r.status_code == 200
        assert len(r.json()) >= 1

        r = client.post(f"/deals/{deal_id}/chat", json={"message": "   "})
        assert r.status_code == 400

        r = client.post(f"/deals/{deal_id}/close", json={"outcome": "nope"})
        assert r.status_code == 400

        r = client.get("/")
        assert r.status_code in (200, 404)


if __name__ == "__main__":
    test_all_endpoints()
    print("ALL ENDPOINTS OK")
