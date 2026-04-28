"""Parsing de date_posted (ISO ou relative FR/EN) en datetime UTC."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone

_UNIT_SECONDS = {
    "minute": 60,
    "min": 60,
    "mn": 60,
    "m": 60,
    "heure": 3600,
    "hour": 3600,
    "hr": 3600,
    "h": 3600,
    "jour": 86400,
    "day": 86400,
    "j": 86400,
    "d": 86400,
    "semaine": 7 * 86400,
    "week": 7 * 86400,
    "w": 7 * 86400,
    "mois": 30 * 86400,
    "month": 30 * 86400,
}

_NOW_TOKENS = (
    "aujourdhui", "today", "just posted", "just now",
    "a l instant", "a linstant", "il y a quelques instants",
    "moins d une minute", "less than a minute",
    "publie aujourdhui", "posted today", "nouveau", "new",
)
_YESTERDAY_TOKENS = ("hier", "yesterday")


def _normalize_for_match(s: str) -> str:
    """Lowercase + strip accents + collapse whitespace, sans toucher aux chiffres."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    # Drop apostrophes (sans espace) pour que "aujourd'hui" matche "aujourdhui".
    s = s.lower().replace("'", "").replace("’", "")
    return re.sub(r"\s+", " ", s).strip()


def parse_relative_date(raw: str, *, now: datetime | None = None) -> datetime | None:
    """Parse une date relative FR/EN ('il y a 2 jours', 'Aujourd'hui', '5 days ago')."""
    if not raw:
        return None
    now = now or datetime.now(timezone.utc)
    text = _normalize_for_match(str(raw))
    if not text:
        return None
    if any(tok in text for tok in _NOW_TOKENS):
        return now
    if any(tok in text for tok in _YESTERDAY_TOKENS):
        return now - timedelta(days=1)
    # "30+ days ago" / "il y a 30+ jours" → on prend la borne basse
    m = re.search(r"(\d+)\s*\+?\s*(minute|min|mn|heure|hour|hr|jour|day|semaine|week|mois|month|[hjdmw])s?\b", text)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        secs = _UNIT_SECONDS.get(unit)
        if secs:
            return now - timedelta(seconds=n * secs)
    return None


def parse_job_date(raw: str | None, *, now: datetime | None = None) -> datetime | None:
    """Parse une date_posted (ISO ou relative FR/EN) en datetime aware UTC."""
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    iso_candidate = s[:-1] + "+00:00" if s.endswith("Z") else s
    try:
        dt = datetime.fromisoformat(iso_candidate)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        pass
    try:
        dt = datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass
    return parse_relative_date(s, now=now)
