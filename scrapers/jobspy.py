from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone

from .base import Job, Scraper, normalize_contract

try:
    from jobspy import scrape_jobs
    HAS_JOBSPY = True
except ImportError:
    scrape_jobs = None
    HAS_JOBSPY = False


class JobSpy(Scraper):
    name = "jobspy"

    def is_configured(self) -> bool:
        return HAS_JOBSPY

    def search(self, keywords, location=None, contract=None, remote=False, limit=50, max_age_hours=None):
        if not HAS_JOBSPY:
            raise RuntimeError("python-jobspy n'est pas installé")

        site_names = ["linkedin", "indeed", "glassdoor", "google"]
        per_site = max(5, math.ceil(max(limit, 1) / len(site_names)))
        kwargs: dict = {
            "site_name": site_names,
            "search_term": keywords,
            "location": location or None,
            "results_wanted": per_site,
            "verbose": 0,
            "linkedin_fetch_description": True,
            "country_indeed": "France",
        }
        if remote:
            kwargs["is_remote"] = True
        if max_age_hours is not None:
            kwargs["hours_old"] = max(1, math.ceil(max_age_hours))
        google_bits = [keywords]
        if location:
            google_bits.append(location)
        google_bits.append("jobs")
        if remote:
            google_bits.append("remote")
        kwargs["google_search_term"] = " ".join(part for part in google_bits if part)

        results = scrape_jobs(**kwargs)
        records = results.to_dict(orient="records") if hasattr(results, "to_dict") else list(results or [])

        jobs: list[Job] = []
        c = normalize_contract(contract)
        for raw in records[: max(limit * 2, limit)]:
            row = {str(k).lower(): v for k, v in raw.items()}
            site = str(row.get("site") or row.get("source") or "jobspy").strip().lower() or "jobspy"
            title = str(row.get("title") or "").strip()
            company = str(row.get("company") or "").strip() or "N/A"
            city = str(row.get("city") or "").strip()
            state = str(row.get("state") or "").strip()
            location_str = ", ".join(part for part in (city, state) if part)
            url = str(row.get("job_url") or row.get("url") or "").strip()
            contract_label = _job_type_to_contract(row.get("job_type"))
            if c and not _matches_contract(c, contract_label, title, company, location_str, str(row.get("description") or "")):
                continue

            jobs.append(Job(
                title=title,
                company=company,
                location=location_str or (location or ""),
                url=url,
                source=f"jobspy/{site}",
                contract=contract_label,
                salary=_format_salary(row),
                date_posted=_format_date(row),
                description=(str(row.get("description") or "")[:500] or None),
                remote=bool(row.get("is_remote")) if row.get("is_remote") is not None else None,
            ))
            if len(jobs) >= limit:
                break
        return jobs


def _job_type_to_contract(value) -> str | None:
    if not value:
        return None
    text = str(value).strip().lower()
    mapping = {
        "fulltime": "CDI",
        "full-time": "CDI",
        "permanent": "CDI",
        "contract": "CDD",
        "temporary": "CDD",
        "internship": "Stage",
        "parttime": None,
    }
    return mapping.get(text, str(value))


def _matches_contract(requested: str, contract: str | None, title: str, company: str, location: str, description: str) -> bool:
    if contract and normalize_contract(contract) == requested:
        return True
    haystack = " ".join([title, company, location, description])
    normalized = re.sub(r"[^a-z0-9]+", " ", haystack.lower()).strip()
    if requested == "alternance":
        return any(term in normalized for term in ("alternance", "apprentissage", "apprenti", "apprentice", "contrat pro", "professionalisation"))
    aliases = {
        "cdi": ("cdi", "permanent", "full time", "fulltime"),
        "cdd": ("cdd", "contract", "temporary"),
        "freelance": ("freelance", "independant", "independent", "contractor", "consultant"),
        "stage": ("stage", "intern", "internship"),
        "interim": ("interim", "temporary", "temp"),
    }.get(requested, ())
    return any(alias in normalized for alias in aliases)


def _format_salary(row: dict) -> str | None:
    low = row.get("min_amount")
    high = row.get("max_amount")
    interval = row.get("interval")
    if low and high:
        return f"{low}-{high}" + (f" {interval}" if interval else "")
    if low:
        return f"{low}+" + (f" {interval}" if interval else "")
    if high:
        return f"{high}" + (f" {interval}" if interval else "")
    return None


def _format_date(row: dict) -> str | None:
    for key in ("date_posted", "date", "posted_at", "publication_date", "created_at"):
        value = row.get(key)
        if value:
            if isinstance(value, datetime):
                return value.astimezone(timezone.utc).isoformat()
            return str(value)
    return None
