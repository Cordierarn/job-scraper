from __future__ import annotations

import os
from .base import Scraper, Job


class Jooble(Scraper):
    name = "jooble"
    requires_credentials = True

    def __init__(self, **kw):
        super().__init__(**kw)
        self.api_key = os.getenv("JOOBLE_API_KEY", "")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def search(self, keywords, location=None, contract=None, remote=False, limit=50):
        url = f"https://jooble.org/api/{self.api_key}"
        body = {"keywords": keywords, "ResultOnPage": min(limit, 50)}
        if location:
            body["location"] = location
        if remote:
            body["keywords"] = f"{keywords} télétravail"

        r = self.session.post(url, json=body, timeout=self.timeout)
        if r.status_code != 200:
            return []
        data = r.json()
        jobs = []
        for item in data.get("jobs", [])[:limit]:
            jobs.append(Job(
                title=item.get("title", ""),
                company=item.get("company", "N/A"),
                location=item.get("location", ""),
                url=item.get("link", ""),
                source=self.name,
                contract=item.get("type"),
                salary=item.get("salary"),
                date_posted=item.get("updated"),
                description=(item.get("snippet") or "")[:500],
            ))
        return jobs
