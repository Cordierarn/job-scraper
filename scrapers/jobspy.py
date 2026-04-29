from __future__ import annotations

import math
from datetime import datetime, timezone

from .base import Job, Scraper, job_matches_contract

try:
    from jobspy import scrape_jobs
    HAS_JOBSPY = True
except ImportError:
    scrape_jobs = None
    HAS_JOBSPY = False


class JobSpy(Scraper):
    name = "jobspy"
    # On le considère "credentialed" sur l'absence de la lib jobspy : le runner
    # skip silencieusement quand requires_credentials=True et is_configured=False
    # (utile en dev local Python 3.14 où la lib ne s'installe pas).
    requires_credentials = True

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
        requested_contract = contract
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
            job = Job(
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
            )
            if requested_contract and not job_matches_contract(job, requested_contract):
                continue

            jobs.append(job)
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
