from __future__ import annotations

import re
from urllib.parse import urlencode
from bs4 import BeautifulSoup
from .base import Scraper, Job, normalize_contract

CONTRACT_MAP = {
    "cdi": "CDI",
    "cdd": "CDD",
    "freelance": "Freelance",
    "stage": "Stage",
    "alternance": "Alternance",
    "interim": "Intérim",
}

BASE = "https://www.hellowork.com/fr-fr/emploi/recherche.html"


class HelloWork(Scraper):
    name = "hellowork"

    def search(self, keywords, location=None, contract=None, remote=False, limit=50, max_age_hours=None):
        results: list[Job] = []
        seen_urls: set[str] = set()
        c = normalize_contract(contract)
        per_page = 20
        for page in range(1, max(2, (limit // per_page) + 2)):
            params = {"k": keywords, "p": page}
            if location:
                params["l"] = location
            if c and c in CONTRACT_MAP:
                params["c"] = CONTRACT_MAP[c]
            if remote:
                params["rm"] = "FullRemote"
            url = f"{BASE}?{urlencode(params)}"
            r = self.session.get(url, timeout=self.timeout)
            if r.status_code != 200:
                break
            soup = BeautifulSoup(r.text, "lxml")
            new = 0
            for a in soup.select("a[href*='/fr-fr/emplois/']"):
                href = a.get("href", "")
                if not re.search(r"/fr-fr/emplois/\d+\.html", href):
                    continue
                if href.startswith("/"):
                    href = f"https://www.hellowork.com{href}"
                if href in seen_urls:
                    continue
                seen_urls.add(href)
                container = a.find_parent(["article", "li", "div"]) or a
                title = a.get_text(" ", strip=True)
                if not title:
                    title_el = container.select_one("h3, h2, [class*='title']")
                    title = title_el.get_text(" ", strip=True) if title_el else ""
                title = title[:200]
                company_el = container.select_one("[class*='company'], [class*='Company'], [data-cy*='company']")
                loc_el = container.select_one("[class*='location'], [class*='Location'], [data-cy*='localis']")
                contract_el = container.select_one("[class*='contract'], [class*='Contract']")
                if not title or len(title) < 3:
                    continue
                results.append(Job(
                    title=title,
                    company=company_el.get_text(strip=True) if company_el else "N/A",
                    location=loc_el.get_text(strip=True) if loc_el else (location or ""),
                    url=href,
                    source=self.name,
                    contract=contract_el.get_text(strip=True) if contract_el else None,
                ))
                new += 1
                if len(results) >= limit:
                    return results
            if new == 0:
                break
        return results
