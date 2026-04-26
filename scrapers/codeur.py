from __future__ import annotations

import re
from urllib.parse import urlencode
from bs4 import BeautifulSoup
from .base import Scraper, Job, normalize_contract

BASE = "https://www.codeur.com/projects"


class Codeur(Scraper):
    """Codeur.com — projets freelance (ne renvoie que du freelance par nature)."""
    name = "codeur"

    def search(self, keywords, location=None, contract=None, remote=False, limit=50):
        c = normalize_contract(contract)
        # Codeur ne propose que des missions freelance: si l'utilisateur demande
        # explicitement un autre type de contrat, on n'a rien à fournir.
        if c and c not in (None, "freelance"):
            return []

        query_terms = [keywords]
        if location:
            query_terms.append(location)
        params = {"q": " ".join(query_terms)}
        url = f"{BASE}?{urlencode(params)}"
        r = self.session.get(url, timeout=self.timeout)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "lxml")

        results: list[Job] = []
        seen: set[str] = set()
        for a in soup.select("a[href*='/projects/']"):
            href = a.get("href", "")
            if not re.match(r"^/projects/\d+", href):
                continue
            if href.startswith("/"):
                href = f"https://www.codeur.com{href}"
            href = href.split("?")[0]
            if href in seen:
                continue
            seen.add(href)

            title = a.get_text(" ", strip=True)
            container = a.find_parent(["article", "li", "div"]) or a
            budget_el = container.select_one("[class*='budget'], [class*='Budget']")
            date_el = container.select_one("[class*='date'], [class*='Date'], time")

            if not title or len(title) < 3:
                continue
            results.append(Job(
                title=title[:200],
                company="Codeur (client)",
                # Empty location so Codeur projects survive the app-level
                # France-only location filter — these missions are remote by nature.
                location=location or "",
                url=href,
                source=self.name,
                contract="Freelance",
                salary=budget_el.get_text(strip=True) if budget_el else None,
                date_posted=date_el.get_text(strip=True) if date_el else None,
                remote=True,
            ))
            if len(results) >= limit:
                break
        return results
