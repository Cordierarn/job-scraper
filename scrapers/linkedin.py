from __future__ import annotations

import random
import time
from urllib.parse import urlencode
from bs4 import BeautifulSoup
from .base import Scraper, Job, normalize_contract

CONTRACT_MAP = {
    "cdi": "F",
    "cdd": "C",
    "freelance": "C",
    "stage": "I",
    "alternance": "P",
    "interim": "T",
}

GUEST_API = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"


class LinkedIn(Scraper):
    name = "linkedin"

    def search(self, keywords, location=None, contract=None, remote=False, limit=50, max_age_hours=None):
        results: list[Job] = []
        seen: set[str] = set()
        c = normalize_contract(contract)
        per_page = 25
        for start in range(0, limit, per_page):
            params = {"keywords": keywords, "start": start}
            if location:
                params["location"] = location
            if c and c in CONTRACT_MAP:
                params["f_JT"] = CONTRACT_MAP[c]
            if remote:
                params["f_WT"] = "2"
            if max_age_hours is not None and max_age_hours <= 24:
                params["f_TPR"] = "r86400"
            url = f"{GUEST_API}?{urlencode(params)}"
            r = self.session.get(url, timeout=self.timeout)
            if r.status_code != 200:
                break
            soup = BeautifulSoup(r.text, "lxml")
            cards = soup.select("li, div.base-card")
            new = 0
            for card in cards:
                link = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
                if not link:
                    continue
                href = link.get("href", "").split("?")[0]
                if not href or href in seen:
                    continue
                seen.add(href)
                title_el = card.select_one("h3, .base-search-card__title")
                company_el = card.select_one("h4, .base-search-card__subtitle a, .base-search-card__subtitle")
                loc_el = card.select_one(".job-search-card__location")
                date_el = card.select_one("time")
                results.append(Job(
                    title=title_el.get_text(strip=True) if title_el else "",
                    company=company_el.get_text(strip=True) if company_el else "N/A",
                    location=loc_el.get_text(strip=True) if loc_el else (location or ""),
                    url=href,
                    source=self.name,
                    date_posted=date_el.get("datetime") if date_el else None,
                ))
                new += 1
                if len(results) >= limit:
                    return results
            if new == 0:
                break
            if start + per_page < limit:
                time.sleep(random.uniform(1.5, 3.0))
        return results
