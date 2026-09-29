"""
The trigger layer. Without this, ingestion only happens when someone calls
POST /deals/{id}/ingest by hand — nothing watches for new mail on its own.

This runs a background poll: every INTERVAL_SECONDS, it re-checks every
open deal's connectors for anything new. This is polling, not a true push
webhook — for real Gmail, a push webhook needs a Google Cloud Pub/Sub topic
and a public HTTPS endpoint Google can call, which is a deployment concern
(needs a reachable server), not something that runs standalone on a laptop.
Polling is the correct default for a local-first tool; swap to push later
if/when this runs on a server with a public endpoint.
"""
import threading
import time
from core.db import get_conn

INTERVAL_SECONDS = 60
_stop_flag = threading.Event()


def _poll_loop():
    from main import run_ingest  # deferred import, avoids circular import at module load
    while not _stop_flag.is_set():
        conn = get_conn()
        open_deals = conn.execute(
            "SELECT id FROM deals WHERE outcome IS NULL"
        ).fetchall()
        conn.close()
        for row in open_deals:
            run_ingest(row["id"])
        _stop_flag.wait(INTERVAL_SECONDS)


def start_scheduler():
    """Call once at app startup. Runs the poll loop in a background thread
    so it doesn't block the API server."""
    thread = threading.Thread(target=_poll_loop, daemon=True)
    thread.start()
    return thread


def stop_scheduler():
    _stop_flag.set()
