from __future__ import annotations

import math
import os
from .base import Scraper, Job, normalize_contract

BASE = "https://api.adzuna.com/v1/api/jobs/fr/search/{page}"

CONTRACT_MAP = {
    "cdi": "permanent",
    "cdd": "contract",
    "stage": "internship",
}


class Adzuna(Scraper):
    name = "adzuna"
    requires_credentials = True

    def __init__(self, **kw):
        super().__init__(**kw)
        self.app_id = os.getenv("ADZUNA_APP_ID", "")
        self.app_key = os.getenv("ADZUNA_APP_KEY", "")

    def is_configured(self) -> bool:
        return bool(self.app_id and self.app_key)

    def search(self, keywords, location=None, contract=None, remote=False, limit=50, max_age_hours=None):
        results: list[Job] = []
        per_page = 50
        pages = max(1, (limit + per_page - 1) // per_page)
        c = normalize_contract(contract)
        for page in range(1, pages + 1):
            params = {
                "app_id": self.app_id,
                "app_key": self.app_key,
                "results_per_page": per_page,
                "what": keywords,
                "content-type": "application/json",
            }
            if location:
                params["where"] = location
            if c and c in CONTRACT_MAP:
                params["contract_type"] = CONTRACT_MAP[c]
            if max_age_hours is not None:
                params["max_days_old"] = max(1, math.ceil(max_age_hours / 24))
            r = self.session.get(BASE.format(page=page), params=params, timeout=self.timeout)
            if r.status_code != 200:
                break
            data = r.json()
            for item in data.get("results", []):
                title = item.get("title", "")
                desc = item.get("description", "")
                if remote and "remote" not in (title + desc).lower() and "télétravail" not in (title + desc).lower():
                    continue
                results.append(Job(
                    title=title,
                    company=(item.get("company") or {}).get("display_name", "N/A"),
                    location=(item.get("location") or {}).get("display_name", ""),
                    url=item.get("redirect_url", ""),
                    source=self.name,
                    contract=item.get("contract_type"),
                    salary=self._format_salary(item),
                    date_posted=item.get("created"),
                    description=desc[:500],
                ))
                if len(results) >= limit:
                    return results
            if len(data.get("results", [])) < per_page:
                break
        return results

    @staticmethod
    def _format_salary(item):
        lo, hi = item.get("salary_min"), item.get("salary_max")
        if lo and hi:
            return f"{int(lo)}-{int(hi)} EUR"
        if lo:
            return f"{int(lo)}+ EUR"
        return None
