from __future__ import annotations

import json
import time
from pathlib import Path

STATE_DIR = Path(__file__).parent.parent / "data"
STATE_DIR.mkdir(exist_ok=True)
SEEN_FILE = STATE_DIR / "seen.json"

# Garde 60 jours d'historique pour ne pas re-notifier ce qui a expiré puis
# réapparu, mais éviter de gonfler le fichier indéfiniment.
RETENTION_SECONDS = 60 * 24 * 3600


def load_seen() -> dict[str, dict[str, float]]:
    if not SEEN_FILE.exists():
        return {}
    try:
        return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_seen(seen: dict[str, dict[str, float]]) -> None:
    SEEN_FILE.write_text(json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8")


def filter_new(alert_name: str, urls: list[str], seen: dict) -> list[str]:
    """Return only urls not yet recorded for this alert."""
    bucket = seen.setdefault(alert_name, {})
    return [u for u in urls if u and u not in bucket]


def record(alert_name: str, urls: list[str], seen: dict) -> None:
    bucket = seen.setdefault(alert_name, {})
    now = time.time()
    for u in urls:
        if u:
            bucket[u] = now
    # GC old entries.
    cutoff = now - RETENTION_SECONDS
    seen[alert_name] = {u: t for u, t in bucket.items() if t >= cutoff}
