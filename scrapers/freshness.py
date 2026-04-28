from __future__ import annotations

from datetime import datetime, timedelta, timezone

from bot.dates import parse_job_date

from .base import Job


def filter_jobs_by_freshness(jobs: list[Job], max_age_hours: float) -> list[Job]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=max_age_hours)
    fresh: list[Job] = []
    for job in jobs:
        dt = parse_job_date(job.date_posted)
        if dt is None:
            continue
        if cutoff <= dt <= now + timedelta(hours=1):
            fresh.append(job)
    return fresh
