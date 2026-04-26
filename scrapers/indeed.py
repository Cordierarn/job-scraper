from __future__ import annotations

import json
import re
from urllib.parse import urlencode
from bs4 import BeautifulSoup

from .base import Scraper, Job, normalize_contract

try:
    from curl_cffi import requests as cffi_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

CONTRACT_MAP = {
    "cdi": "permanent",
    "cdd": "temporary",
    "freelance": "subcontract",
    "stage": "internship",
    "alternance": "apprenticeship",
    "interim": "temporary",
}

BASE = "https://fr.indeed.com/jobs"
IMPERSONATE = "chrome124"


class Indeed(Scraper):
    """Indeed FR — utilise curl_cffi (TLS fingerprint Chrome) pour passer Cloudflare."""
    name = "indeed"

    def is_configured(self) -> bool:
        # Sans curl_cffi on prend juste un 403, autant le signaler clairement.
        return HAS_CURL_CFFI

    @property
    def requires_credentials(self) -> bool:
        return False

    def search(self, keywords, location=None, contract=None, remote=False, limit=50):
        if not HAS_CURL_CFFI:
            return []

        results: list[Job] = []
        seen: set[str] = set()
        per_page = 15
        c = normalize_contract(contract)
        for start in range(0, limit, per_page):
            params = {"q": keywords, "start": start}
            if location:
                params["l"] = location
            if c and c in CONTRACT_MAP:
                params["jt"] = CONTRACT_MAP[c]
            if remote:
                params["sc"] = "0kf:attr(DSQF7);"
            url = f"{BASE}?{urlencode(params)}"
            try:
                r = cffi_requests.get(
                    url,
                    impersonate=IMPERSONATE,
                    headers={"Accept-Language": "fr-FR,fr;q=0.9"},
                    timeout=self.timeout,
                )
            except Exception:
                break
            if r.status_code != 200:
                if start == 0:
                    return []
                break
            page_jobs = self._parse(r.text)
            new = 0
            for job in page_jobs:
                if not job.url or job.url in seen:
                    continue
                seen.add(job.url)
                results.append(job)
                new += 1
                if len(results) >= limit:
                    return results
            if new == 0:
                break
        return results[:limit]

    def _parse(self, html: str) -> list[Job]:
        jobs: list[Job] = []
        m = re.search(
            r'window\.mosaic\.providerData\["mosaic-provider-jobcards"\]\s*=\s*(\{.+?\});',
            html,
        )
        if m:
            try:
                data = json.loads(m.group(1))
                results = (
                    data.get("metaData", {})
                    .get("mosaicProviderJobCardsModel", {})
                    .get("results", [])
                )
                for r in results:
                    jk = r.get("jobkey", "")
                    url = (
                        f"https://fr.indeed.com/viewjob?jk={jk}"
                        if jk
                        else r.get("link", "")
                    )
                    jobs.append(Job(
                        title=r.get("title", ""),
                        company=r.get("company", "N/A"),
                        location=r.get("formattedLocation", ""),
                        url=url,
                        source=self.name,
                        contract=", ".join(r.get("jobTypes", [])) or None,
                        salary=(r.get("salarySnippet") or {}).get("text"),
                        date_posted=r.get("formattedRelativeTime"),
                        description=(r.get("snippet") or "")[:500],
                    ))
                if jobs:
                    return jobs
            except (json.JSONDecodeError, KeyError, AttributeError):
                pass

        soup = BeautifulSoup(html, "lxml")
        for card in soup.select("div.job_seen_beacon, a.tapItem, li[class*='css']"):
            title_el = card.select_one("h2 a, h2 span[title], a[data-jk]")
            company_el = card.select_one("[data-testid='company-name'], span.companyName")
            loc_el = card.select_one("[data-testid='text-location'], div.companyLocation")
            link = card.select_one("h2 a, a[data-jk]") or card
            href = link.get("href", "") if hasattr(link, "get") else ""
            jk = link.get("data-jk", "") if hasattr(link, "get") else ""
            if jk:
                href = f"https://fr.indeed.com/viewjob?jk={jk}"
            elif href.startswith("/"):
                href = f"https://fr.indeed.com{href}"
            title = title_el.get("title") or title_el.get_text(strip=True) if title_el else ""
            jobs.append(Job(
                title=title,
                company=company_el.get_text(strip=True) if company_el else "N/A",
                location=loc_el.get_text(strip=True) if loc_el else "",
                url=href,
                source=self.name,
            ))
        return jobs
