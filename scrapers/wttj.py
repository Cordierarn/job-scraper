from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlencode
from bs4 import BeautifulSoup
from .base import Scraper, Job


class WTTJ(Scraper):
    """
    Welcome to the Jungle est une SPA dont les clés Algolia changent.
    On tente d'abord les recherches Algolia publiques, puis on retombe sur
    le scraping HTML best-effort si l'API ne répond pas.
    """
    name = "wttj"

    def search(self, keywords, location=None, contract=None, remote=False, limit=50, max_age_hours=None):
        algolia_jobs = self._search_algolia(keywords, location=location, remote=remote, limit=limit, contract=contract)
        if algolia_jobs:
            return algolia_jobs

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

    def _search_algolia(self, keywords, location=None, remote=False, limit=50, contract=None) -> list[Job]:
        try:
            env = self._load_env()
        except Exception:
            return []

        app_id = env.get("ALGOLIA_APPLICATION_ID") or env.get("PUBLIC_ALGOLIA_APPLICATION_ID")
        api_key = env.get("ALGOLIA_API_KEY_CLIENT") or env.get("PUBLIC_ALGOLIA_API_KEY_CLIENT")
        prefix = env.get("ALGOLIA_JOBS_INDEX_PREFIX") or env.get("PUBLIC_ALGOLIA_JOBS_INDEX_PREFIX")
        if not app_id or not api_key or not prefix:
            return []

        index_candidates = self._index_candidates(prefix)
        headers = {
            "X-Algolia-Application-Id": app_id,
            "X-Algolia-API-Key": api_key,
            "X-Algolia-Agent": "Algolia for JavaScript (4.24.0); Browser; JS Helper (3.16.2); react (18.3.1); next.js",
            "Origin": "https://www.welcometothejungle.com",
            "Referer": "https://www.welcometothejungle.com/fr/jobs",
        }
        query = " ".join(part for part in (keywords, location or None, "jobs") if part)
        if remote:
            query = f"{query} remote"

        for index_name in index_candidates:
            try:
                response = self.session.post(
                    f"https://csekhvms53-dsn.algolia.net/1/indexes/{index_name}/query",
                    headers=headers,
                    data=json.dumps({"params": urlencode({
                        "query": query,
                        "hitsPerPage": max(1, min(limit, 50)),
                        "page": 0,
                        "search_origin": "jobs",
                    })}),
                    timeout=self.timeout,
                )
            except Exception:
                continue
            if response.status_code != 200:
                continue
            payload = response.json()
            hits = payload.get("hits", [])
            jobs = [self._hit_to_job(hit) for hit in hits]
            jobs = [j for j in jobs if j and j.title and j.url]
            if contract:
                jobs = [j for j in jobs if self._matches_contract(contract, j)]
            if remote:
                jobs = [j for j in jobs if j.remote is not False]
            if jobs:
                return jobs[:limit]
        return []

    def _load_env(self) -> dict[str, Any]:
        env_urls = (
            "https://www.welcometothejungle.com/fr/api/env",
            "https://www.welcometothejungle.com/api/env",
        )
        for env_url in env_urls:
            r = self.session.get(env_url, timeout=self.timeout)
            if r.status_code != 200:
                continue
            m = re.search(r"window\.env\s*=\s*(\{.*?\});", r.text, re.S)
            if not m:
                continue
            return json.loads(m.group(1))
        raise RuntimeError("window.env introuvable")

    @staticmethod
    def _index_candidates(prefix: str) -> list[str]:
        suffixes = [
            "jobs_offer",
            "job_offer",
            "jobs_offers",
            "job_offers",
            "jobs",
            "job",
            "offer",
            "offers",
        ]
        prefixes = [prefix, prefix.replace("wttj_", "wk_", 1), "wk_jobs_production"]
        out: list[str] = []
        seen: set[str] = set()
        for p in prefixes:
            for s in suffixes:
                for candidate in (f"{p}_{s}", f"{p}_{s}_fr", f"{p}_{s}_en"):
                    if candidate not in seen:
                        seen.add(candidate)
                        out.append(candidate)
        return out

    @staticmethod
    def _hit_to_job(hit: dict[str, Any]) -> Job | None:
        title = _first(hit, "title", "job_title", "name", "label")
        url = _first(hit, "url", "job_url", "canonical_url", "absolute_url", "link")
        slug = _first(hit, "slug", "path")
        if not url and slug:
            url = slug if str(slug).startswith("http") else f"https://www.welcometothejungle.com{slug}"
        if not title or not url:
            return None

        company_obj = hit.get("company") or hit.get("organization") or hit.get("company_name")
        company = "N/A"
        if isinstance(company_obj, dict):
            company = str(company_obj.get("name") or company_obj.get("label") or company_obj.get("title") or "N/A")
        elif company_obj:
            company = str(company_obj)

        location = _first(hit, "location", "city", "place", "country") or ""
        if isinstance(location, dict):
            location = ", ".join(str(location.get(key) or "") for key in ("city", "region", "country") if location.get(key))
        contract = _first(hit, "contract", "contract_type", "job_type")
        description = _first(hit, "description", "summary", "excerpt", "job_description")
        remote = hit.get("remote")
        if remote is None:
            remote = hit.get("is_remote")
        salary = _salary_from_hit(hit)
        date_posted = _first(hit, "published_at", "created_at", "date_posted", "updated_at")
        return Job(
            title=str(title)[:200],
            company=str(company),
            location=str(location),
            url=str(url),
            source="wttj",
            contract=str(contract) if contract else None,
            salary=salary,
            date_posted=str(date_posted) if date_posted else None,
            description=str(description)[:500] if description else None,
            remote=bool(remote) if remote is not None else None,
        )

    @staticmethod
    def _matches_contract(contract: str, job: Job) -> bool:
        from .base import job_matches_contract
        return job_matches_contract(job, contract)


def _salary_from_hit(hit: dict[str, Any]) -> str | None:
    low = _first(hit, "salary_min", "min_salary", "min_amount")
    high = _first(hit, "salary_max", "max_salary", "max_amount")
    if low and high:
        return f"{low}-{high}"
    if low:
        return f"{low}+"
    if high:
        return str(high)
    return _first(hit, "salary", "salary_text")


def _first(hit: dict[str, Any], *keys: str):
    for key in keys:
        value = hit.get(key)
        if value not in (None, "", []):
            return value
    return None
