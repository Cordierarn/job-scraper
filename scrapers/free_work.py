from __future__ import annotations

from .base import Scraper, Job, normalize_contract

API = "https://www.free-work.com/api/job_postings"

# Free-Work uses ATS-style "contract" tags
CONTRACT_MAP = {
    "cdi": "permanent",
    "cdd": "fixed-term",
    "freelance": "contractor",
    "stage": "internship",
    "alternance": "apprenticeship",
}


class FreeWork(Scraper):
    name = "free_work"

    def search(self, keywords, location=None, contract=None, remote=False, limit=50, max_age_hours=None):
        params = {
            "searchKeywords": keywords,
            "itemsPerPage": min(limit, 50),
        }
        if location:
            params["searchLocations[]"] = location
        c = normalize_contract(contract)
        if c and c in CONTRACT_MAP:
            params["contracts[]"] = CONTRACT_MAP[c]
        if remote:
            params["remoteMode[]"] = "full"

        try:
            r = self.session.get(
                API,
                params=params,
                headers={"Accept": "application/json"},
                timeout=self.timeout,
            )
            if r.status_code != 200:
                return []
            items = r.json()
        except Exception:
            return []
        if not isinstance(items, list):
            return []

        jobs: list[Job] = []
        for item in items[:limit]:
            slug = item.get("slug", "")
            job_cat = item.get("job") or {}
            cat_slug = (job_cat.get("category") or {}).get("slug") if isinstance(job_cat, dict) else None
            job_slug = job_cat.get("slug") if isinstance(job_cat, dict) else None
            if cat_slug and job_slug and slug:
                url = f"https://www.free-work.com/fr/{cat_slug}/{job_slug}/job-mission/{slug}"
            else:
                url = f"https://www.free-work.com/fr/jobs/{slug}" if slug else ""

            company = (item.get("company") or {}).get("name", "N/A") if isinstance(item.get("company"), dict) else "N/A"
            loc_obj = item.get("location") or {}
            if isinstance(loc_obj, dict):
                parts = [loc_obj.get(k) for k in ("locality", "adminLevel2", "adminLevel1")]
                loc_str = ", ".join(p for p in parts if p) or loc_obj.get("country", "")
            else:
                loc_str = ""

            contracts = item.get("contracts") or []
            contract_str = ", ".join(contracts) if isinstance(contracts, list) else None
            salary = self._format_salary(item)
            remote_mode = item.get("remoteMode")

            jobs.append(Job(
                title=item.get("title", "")[:200],
                company=company,
                location=loc_str,
                url=url,
                source=self.name,
                contract=contract_str,
                salary=salary,
                date_posted=(item.get("publishedAt") or "")[:10] or None,
                description=(item.get("description") or "")[:500],
                remote=remote_mode in ("full", "partial"),
            ))
        return jobs

    @staticmethod
    def _format_salary(item):
        cur = item.get("currency") or "EUR"
        a_min, a_max = item.get("minAnnualSalary"), item.get("maxAnnualSalary")
        d_min, d_max = item.get("minDailySalary"), item.get("maxDailySalary")
        if a_min and a_max:
            return f"{a_min}-{a_max} {cur}/an"
        if a_min:
            return f"{a_min}+ {cur}/an"
        if d_min and d_max:
            return f"{d_min}-{d_max} {cur}/jour"
        if d_min:
            return f"{d_min}+ {cur}/jour"
        return None
