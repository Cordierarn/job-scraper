from __future__ import annotations

import html
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scrapers import ALL_SCRAPERS, Job
from scrapers.base import job_matches_contract, normalize_text

from .telegram_client import TelegramClient
from .state import load_seen, save_seen, filter_new, record

ALERTS_FILE = Path(__file__).parent.parent / "alerts.json"


@dataclass
class Alert:
    name: str
    keywords: str
    locations: list[str]
    contract: str | None = None
    remote: bool = False
    sources: list[str] | None = None
    limit: int = 30
    enabled: bool = True
    france_only: bool = True
    # Si défini : ne garde que les offres dont date_posted est parseable et
    # tombe dans la fenêtre [now - max_age_hours, now]. Les offres sans date
    # parseable sont écartées (mode strict — pour les digests "fresh").
    max_age_hours: float | None = None


def load_alerts(path: Path | str | None = None) -> list[Alert]:
    target = Path(path) if path else ALERTS_FILE
    if not target.exists():
        raise FileNotFoundError(f"fichier d'alertes introuvable ({target})")
    raw = json.loads(target.read_text(encoding="utf-8"))
    known = {f for f in Alert.__dataclass_fields__}
    cleaned = [{k: v for k, v in a.items() if k in known} for a in raw]
    return [Alert(**a) for a, orig in zip(cleaned, raw) if orig.get("enabled", True)]


def parse_job_date(raw: str | None) -> datetime | None:
    """Parse une date_posted ISO en datetime aware UTC. None si non parseable."""
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # Normalise le 'Z' final (Zulu/UTC) en +00:00 pour fromisoformat.
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # Date seule au format YYYY-MM-DD
        try:
            dt = datetime.strptime(s[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def filter_by_freshness(jobs: list[Job], max_age_hours: float) -> list[Job]:
    """Garde uniquement les offres avec date_posted parseable dans la fenêtre."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=max_age_hours)
    fresh = []
    for j in jobs:
        dt = parse_job_date(j.date_posted)
        if dt is None:
            continue
        # Tolérance future de 1h (horloges désynchronisées côté source)
        if cutoff <= dt <= now + timedelta(hours=1):
            fresh.append(j)
    return fresh


def is_french_location(job: Job) -> bool:
    if job.source == "remotive":
        return False
    loc = normalize_text(job.location or "")
    if not loc:
        return True
    foreign_hints = (
        "usa", "united states", "brazil", "colombia", "philippines", "canada",
        "argentina", "germany", "latam", "asia", "oceania", "emea", "worldwide",
        "remote", "county", "ky", "uk", "england", "germany", "spain", "italy",
    )
    return not any(hint in loc for hint in foreign_hints)


def run_one_source(scraper, alert: Alert, location: str | None) -> list[Job]:
    if scraper.requires_credentials and not scraper.is_configured():
        return []
    try:
        jobs = scraper.search(
            keywords=alert.keywords,
            location=location,
            contract=alert.contract,
            remote=alert.remote,
            limit=alert.limit,
        )
    except Exception as e:
        print(f"  [{scraper.name}] erreur: {type(e).__name__}: {str(e)[:120]}")
        return []
    if alert.contract:
        jobs = [j for j in jobs if job_matches_contract(j, alert.contract)]
    if alert.france_only:
        jobs = [j for j in jobs if is_french_location(j)]
    return jobs


def collect_alert_jobs(alert: Alert) -> list[Job]:
    sources_names = alert.sources or list(ALL_SCRAPERS.keys())
    scrapers = [ALL_SCRAPERS[n]() for n in sources_names if n in ALL_SCRAPERS]
    locations = alert.locations or [None]

    all_jobs: list[Job] = []
    seen_urls: set[str] = set()
    tasks = [(s, loc) for s in scrapers for loc in locations]
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(tasks)))) as ex:
        futures = {ex.submit(run_one_source, s, alert, loc): (s.name, loc) for s, loc in tasks}
        for fut in as_completed(futures):
            for j in fut.result():
                key = (j.url or "").split("?")[0].rstrip("/").lower()
                if key and key not in seen_urls:
                    seen_urls.add(key)
                    all_jobs.append(j)
    return all_jobs


def format_alert_message(alert: Alert, new_jobs: list[Job]) -> str:
    header = (
        f"🔔 <b>{html.escape(alert.name)}</b>\n"
        f"<i>{len(new_jobs)} nouvelle(s) offre(s)</i>\n"
    )
    blocks = [header]
    for j in new_jobs:
        title = html.escape(j.title or "Sans titre")
        company = html.escape(j.company or "—")
        location = html.escape(j.location or "—")
        contract = html.escape(str(j.contract)) if j.contract else ""
        salary = html.escape(str(j.salary)) if j.salary else ""
        meta_bits = [f"🏢 {company}", f"📍 {location}"]
        if contract:
            meta_bits.append(f"📋 {contract}")
        if salary:
            meta_bits.append(f"💶 {salary}")
        url = j.url or ""
        link = f'<a href="{html.escape(url)}">Voir l\'offre →</a>' if url else ""
        block = (
            f"\n📌 <b>{title}</b>\n"
            f"{' · '.join(meta_bits)}\n"
            f"<code>[{j.source}]</code>  {link}\n"
        )
        blocks.append(block)
    return "".join(blocks)


def run_alerts(
    *,
    dry_run: bool = False,
    telegram: TelegramClient | None = None,
    alerts_file: Path | str | None = None,
    state_file: Path | str | None = None,
) -> dict:
    """Run all enabled alerts; return per-alert summary."""
    alerts = load_alerts(alerts_file)
    seen = load_seen(state_file)
    tg = telegram or TelegramClient()
    summary: dict[str, dict] = {}

    for alert in alerts:
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] alerte: {alert.name} (kw={alert.keywords!r}, locs={alert.locations})")
        jobs = collect_alert_jobs(alert)
        if alert.max_age_hours is not None:
            before = len(jobs)
            jobs = filter_by_freshness(jobs, alert.max_age_hours)
            print(f"    filtre fraîcheur ≤{alert.max_age_hours}h : {before} → {len(jobs)}")
        urls = [(j.url or "").split("?")[0].rstrip("/").lower() for j in jobs]
        new_urls = set(filter_new(alert.name, urls, seen))
        new_jobs = [j for j, u in zip(jobs, urls) if u in new_urls]
        print(f"    {len(jobs)} offres collectées, {len(new_jobs)} nouvelles")

        summary[alert.name] = {
            "total": len(jobs),
            "new": len(new_jobs),
        }

        if new_jobs and not dry_run:
            msg = format_alert_message(alert, new_jobs)
            if tg.send(msg):
                record(alert.name, urls, seen)
        elif dry_run and new_jobs:
            print(f"    [dry-run] aurait notifié:\n{format_alert_message(alert, new_jobs)[:500]}…")

    if not dry_run:
        save_seen(seen, state_file)
    return summary
