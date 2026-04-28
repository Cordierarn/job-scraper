from __future__ import annotations

import re
from urllib.parse import urlencode
from bs4 import BeautifulSoup
from .base import Scraper, Job, normalize_contract

CONTRACT_HINTS = {
    "cdi": ("cdi", "permanent"),
    "cdd": ("cdd", "temporary"),
    "freelance": ("freelance", "indépendant", "independent"),
    "stage": ("stage", "internship"),
    "alternance": ("alternance", "apprentissage"),
    "interim": ("intérim", "interim"),
}

BASE = "https://fr.talent.com/jobs"


class TalentCom(Scraper):
    name = "talent_com"

    def search(self, keywords, location=None, contract=None, remote=False, limit=50, max_age_hours=None):
        params = {"k": keywords}
        if location:
            params["l"] = location
        url = f"{BASE}?{urlencode(params)}"
        r = self.session.get(url, timeout=self.timeout)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "lxml")

        results: list[Job] = []
        seen: set[str] = set()
        c = normalize_contract(contract)

        for card in soup.select("article[class*='JobCard_card']"):
            link = card.select_one("a[href*='/view?id=']")
            if not link:
                continue
            href = link.get("href", "")
            if href.startswith("/"):
                href = f"https://fr.talent.com{href}"
            href = href.split("&")[0]
            if href in seen:
                continue
            seen.add(href)

            title_el = card.select_one("[class*='JobCard_title']")
            company_el = card.select_one("[class*='JobCard_company']")
            loc_el = card.select_one("[class*='JobCard_location']")
            snippet_el = card.select_one("[class*='JobCard_snippet']")
            footer_el = card.select_one("[class*='JobCard_footer']")
            body_el = card.select_one("[class*='JobCard_body']")

            description = (snippet_el.get_text(" ", strip=True) if snippet_el else "")[:400]
            body_txt = (body_el.get_text(" ", strip=True) if body_el else "").lower()

            contract_label = None
            for canonical, hints in CONTRACT_HINTS.items():
                if any(h in body_txt for h in hints):
                    contract_label = canonical.upper() if canonical in ("cdi", "cdd") else canonical.title()
                    break

            if c and c in CONTRACT_HINTS:
                if not any(h in body_txt for h in CONTRACT_HINTS[c]):
                    continue

            is_remote = "télétravail" in body_txt or "remote" in body_txt or "à distance" in body_txt
            if remote and not is_remote:
                continue

            date_match = None
            if footer_el:
                m = re.search(r"il y a\s+\d+\s+\w+", footer_el.get_text(" ", strip=True), re.I)
                date_match = m.group(0) if m else None

            results.append(Job(
                title=(title_el.get_text(" ", strip=True) if title_el else link.get_text(" ", strip=True))[:200],
                company=company_el.get_text(strip=True) if company_el else "N/A",
                location=loc_el.get_text(strip=True) if loc_el else (location or ""),
                url=href,
                source=self.name,
                contract=contract_label,
                date_posted=date_match,
                description=description,
                remote=is_remote or None,
            ))
            if len(results) >= limit:
                break
        return results
