from __future__ import annotations

import html
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
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


def load_alerts() -> list[Alert]:
    if not ALERTS_FILE.exists():
        raise FileNotFoundError(f"alerts.json introuvable ({ALERTS_FILE})")
    raw = json.loads(ALERTS_FILE.read_text(encoding="utf-8"))
    return [Alert(**a) for a in raw if a.get("enabled", True)]


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


def run_alerts(*, dry_run: bool = False, telegram: TelegramClient | None = None) -> dict:
    """Run all enabled alerts; return per-alert summary."""
    alerts = load_alerts()
    seen = load_seen()
    tg = telegram or TelegramClient()
    summary: dict[str, dict] = {}

    for alert in alerts:
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] alerte: {alert.name} (kw={alert.keywords!r}, locs={alert.locations})")
        jobs = collect_alert_jobs(alert)
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
        save_seen(seen)
    return summary
