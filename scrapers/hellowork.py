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

_REL_DATE_RE = re.compile(
    r"\b(il y a (?:un|une|\d+)\s*(?:minutes?|mn|h(?:eures?)?|jours?|j|semaines?|mois)|aujourd['’]?hui|hier|à l['’]?instant)",
    re.IGNORECASE,
)


def _extract_relative_date(text: str) -> str | None:
    """Extrait le fragment de date relative dans le texte brut d'une card."""
    if not text:
        return None
    m = _REL_DATE_RE.search(text)
    return m.group(1).strip() if m else None


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
                # Remonter au <li> qui englobe toute la card (titre + footer
                # avec la date relative). `div` matchait un wrapper trop interne
                # qui n'incluait pas la date, d'où le fix.
                container = a.find_parent(["li", "article"]) or a.find_parent("div") or a
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
                # HelloWork affiche la date publication en bas de la card sous
                # forme relative ("il y a 2 jours", "Aujourd'hui", "Hier") dans
                # le texte brut. Notre parse_relative_date côté bot/dates s'en
                # charge — on extrait juste le bout de texte pertinent.
                full_text = container.get_text(" ", strip=True)
                date_posted = _extract_relative_date(full_text)
                results.append(Job(
                    title=title,
                    company=company_el.get_text(strip=True) if company_el else "N/A",
                    location=loc_el.get_text(strip=True) if loc_el else (location or ""),
                    url=href,
                    source=self.name,
                    contract=contract_el.get_text(strip=True) if contract_el else None,
                    date_posted=date_posted,
                ))
                new += 1
                if len(results) >= limit:
                    return results
            if new == 0:
                break
        return results
