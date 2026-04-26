from __future__ import annotations

import re
from urllib.parse import urlencode
from bs4 import BeautifulSoup
from .base import Scraper, Job


class WTTJ(Scraper):
    """
    Welcome to the Jungle est une SPA dont les clés Algolia changent.
    On scrape la page de recherche en best-effort: on récupère les liens
    visibles, ce qui est limité mais évite de dépendre de clés volatiles.
    """
    name = "wttj"

    def search(self, keywords, location=None, contract=None, remote=False, limit=50):
        params = {"query": keywords}
        if location:
            params["query"] = f"{keywords} {location}"
        if remote:
            params["refinementList[remote][]"] = "fulltime"
        url = f"https://www.welcometothejungle.com/fr/jobs?{urlencode(params)}"
        r = self.session.get(url, timeout=self.timeout)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "lxml")
        results: list[Job] = []
        seen: set[str] = set()
        for a in soup.select("a[href*='/jobs/']"):
            href = a.get("href", "")
            if not re.search(r"/companies/[^/]+/jobs/", href):
                continue
            if href.startswith("/"):
                href = f"https://www.welcometothejungle.com{href}"
            if href in seen:
                continue
            seen.add(href)
            results.append(Job(
                title=a.get_text(" ", strip=True)[:200] or "Offre WTTJ",
                company="N/A",
                location=location or "",
                url=href,
                source=self.name,
            ))
            if len(results) >= limit:
                break
        return results
