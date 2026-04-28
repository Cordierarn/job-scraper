from __future__ import annotations

from .base import Scraper, Job


class Remotive(Scraper):
    name = "remotive"

    def search(self, keywords, location=None, contract=None, remote=False, limit=50, max_age_hours=None):
        params = {"search": keywords, "limit": min(limit, 100)}
        r = self.session.get("https://remotive.com/api/remote-jobs", params=params, timeout=self.timeout)
        if r.status_code != 200:
            return []
        data = r.json()
        jobs = []
        for item in data.get("jobs", [])[:limit]:
            jobs.append(Job(
                title=item.get("title", ""),
                company=item.get("company_name", "N/A"),
                location=item.get("candidate_required_location", "Remote"),
                url=item.get("url", ""),
                source=self.name,
                contract=item.get("job_type"),
                salary=item.get("salary"),
                date_posted=item.get("publication_date"),
                description=(item.get("description") or "")[:500],
                remote=True,
            ))
        return jobs
