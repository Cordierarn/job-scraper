from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from .base import Scraper, Job
from .freshness import filter_jobs_by_freshness
from .base import normalize_text


class WTTJ(Scraper):
    """
    Welcome to the Jungle est une SPA dont les clés Algolia changent.
    On tente d'abord les recherches Algolia publiques, puis on retombe sur
    le scraping HTML best-effort si l'API ne répond pas.
    """
    name = "wttj"

    FALLBACK_APP_ID = "CSEKHVMS53"
    FALLBACK_API_KEY = "4bd8f6215d0cc52b26430765769e65a0"
    FALLBACK_INDEX = "wttj_jobs_production_fr"

    def search(self, keywords, location=None, contract=None, remote=False, limit=50, max_age_hours=None):
        algolia_jobs = self._search_algolia(
            keywords, location=location, remote=remote, limit=limit, contract=contract,
            max_age_hours=max_age_hours,
        )
        if algolia_jobs:
            # Le filtre numericFilters Algolia a déjà fait le tri côté serveur,
            # mais on repasse une couche client pour les hits sans timestamp parseable.
            return filter_jobs_by_freshness(algolia_jobs, max_age_hours) if max_age_hours is not None else algolia_jobs

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
        return filter_jobs_by_freshness(results, max_age_hours) if max_age_hours is not None else results

    def _search_algolia(self, keywords, location=None, remote=False, limit=50, contract=None,
                         max_age_hours=None) -> list[Job]:
        credentials = self._credentials_candidates()
        query = " ".join(part for part in (keywords, location or None) if part)

        for app_id, api_key, index_name in credentials:
            headers = {
                "X-Algolia-Application-Id": app_id,
                "X-Algolia-API-Key": api_key,
                "Content-Type": "application/json",
                "Origin": "https://www.welcometothejungle.com",
                "Referer": "https://www.welcometothejungle.com/",
            }
            body: dict[str, Any] = {
                "query": query,
                "hitsPerPage": max(1, min(limit * 2, 100)),
            }
            filters = self._contract_filter(contract)
            if filters:
                body["filters"] = filters
            # Filtre temporel server-side : Algolia renvoie alors les offres
            # fraîches en priorité dans la fenêtre (sinon le tri par pertinence
                # peut écarter du top-100 toutes les offres récentes).
            if max_age_hours is not None and max_age_hours > 0:
                from datetime import datetime, timedelta, timezone
                cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
                body["numericFilters"] = [
                    f"published_at_timestamp >= {int(cutoff.timestamp())}"
                ]

            try:
                response = self.session.post(
                    f"https://{app_id.lower()}-dsn.algolia.net/1/indexes/{index_name}/query",
                    headers=headers,
                    json=body,
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
                jobs = [j for j in jobs if j.remote is True]
            if location:
                jobs = [j for j in jobs if self._matches_location(location, j)]
            if jobs:
                return jobs[:limit]
        return []

    def _credentials_candidates(self) -> list[tuple[str, str, str]]:
        out: list[tuple[str, str, str]] = []
        seen: set[tuple[str, str, str]] = set()

        try:
            env = self._load_env()
            app_id = env.get("ALGOLIA_APPLICATION_ID") or env.get("PUBLIC_ALGOLIA_APPLICATION_ID")
            api_key = env.get("ALGOLIA_API_KEY_CLIENT") or env.get("PUBLIC_ALGOLIA_API_KEY_CLIENT")
            prefix = env.get("ALGOLIA_JOBS_INDEX_PREFIX") or env.get("PUBLIC_ALGOLIA_JOBS_INDEX_PREFIX")
            if app_id and api_key and prefix:
                for index_name in self._index_candidates(str(prefix)):
                    triple = (str(app_id), str(api_key), index_name)
                    if triple not in seen:
                        seen.add(triple)
                        out.append(triple)
        except Exception:
            pass

        fallback = (self.FALLBACK_APP_ID, self.FALLBACK_API_KEY, self.FALLBACK_INDEX)
        if fallback not in seen:
            out.insert(0, fallback)
        return out

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
            "",  # le préfixe brut + langue (ex: wttj_jobs_production_fr)
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
                base = f"{p}_{s}" if s else p
                for candidate in (f"{base}_fr", f"{base}_en", base):
                    if candidate and candidate not in seen:
                        seen.add(candidate)
                        out.append(candidate)
        return out

    @staticmethod
    def _hit_to_job(hit: dict[str, Any]) -> Job | None:
        title = _first(hit, "title", "job_title", "name", "label")
        url = _first(hit, "url", "job_url", "canonical_url", "absolute_url", "link")
        slug = _first(hit, "slug", "path")
        org_slug = _nested_first(hit, ("organization", "slug"), ("company", "slug"))
        if not url and slug:
            if str(slug).startswith("http"):
                url = slug
            elif str(slug).startswith("/"):
                url = f"https://www.welcometothejungle.com{slug}"
            elif org_slug:
                url = f"https://www.welcometothejungle.com/fr/companies/{org_slug}/jobs/{slug}"
            else:
                url = f"https://www.welcometothejungle.com/fr/jobs/{slug}"
        if not title or not url:
            return None

        company_obj = hit.get("company") or hit.get("organization") or hit.get("company_name")
        company = "N/A"
        if isinstance(company_obj, dict):
            company = str(company_obj.get("name") or company_obj.get("label") or company_obj.get("title") or "N/A")
        elif company_obj:
            company = str(company_obj)

        location = _location_from_hit(hit)
        if isinstance(location, dict):
            location = ", ".join(str(location.get(key) or "") for key in ("city", "region", "country") if location.get(key))
        contract = _first(hit, "contract", "contract_type", "job_type")
        description = _first(hit, "description", "summary", "excerpt", "job_description")
        remote = hit.get("remote")
        if remote is None:
            remote = hit.get("is_remote")
        remote_bool: bool | None
        if isinstance(remote, bool):
            remote_bool = remote
        elif isinstance(remote, str):
            remote_bool = remote.strip().lower() in {"full", "fulltime", "true", "yes"}
        else:
            remote_bool = None
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
            remote=remote_bool,
        )

    @staticmethod
    def _matches_contract(contract: str, job: Job) -> bool:
        from .base import job_matches_contract
        return job_matches_contract(job, contract)

    @staticmethod
    def _contract_filter(contract: str | None) -> str | None:
        if not contract:
            return None
        mapping = {
            "alternance": "apprenticeship",
            "stage": "internship",
            "cdi": "permanent",
            "cdd": "fixed_term",
            "freelance": "freelance",
            "interim": "temporary",
        }
        key = mapping.get(str(contract).lower().strip())
        if not key:
            return None
        return f"contract_type:{key}"

    @staticmethod
    def _matches_location(requested_location: str, job: Job) -> bool:
        needle = normalize_text(requested_location)
        if not needle:
            return True
        hay = normalize_text(job.location or "")
        return needle in hay


def _salary_from_hit(hit: dict[str, Any]) -> str | None:
    low = _first(hit, "salary_min", "salary_minimum", "min_salary", "min_amount")
    high = _first(hit, "salary_max", "salary_maximum", "max_salary", "max_amount")
    currency = _first(hit, "salary_currency")
    period = _first(hit, "salary_period")
    if low and high:
        return f"{low}-{high}" + (f" {currency}" if currency else "") + (f" {period}" if period else "")
    if low:
        return f"{low}+" + (f" {currency}" if currency else "") + (f" {period}" if period else "")
    if high:
        return f"{high}" + (f" {currency}" if currency else "") + (f" {period}" if period else "")
    return _first(hit, "salary", "salary_text")


def _first(hit: dict[str, Any], *keys: str):
    for key in keys:
        value = hit.get(key)
        if value not in (None, "", []):
            return value
    return None


def _nested_first(hit: dict[str, Any], *paths: tuple[str, ...]):
    for path in paths:
        value: Any = hit
        ok = True
        for key in path:
            if not isinstance(value, dict):
                ok = False
                break
            value = value.get(key)
        if ok and value not in (None, "", []):
            return value
    return None


def _location_from_hit(hit: dict[str, Any]) -> str:
    offices = hit.get("offices") or []
    if isinstance(offices, list) and offices:
        first = offices[0] if isinstance(offices[0], dict) else None
        if first:
            city = first.get("city") or first.get("local_city")
            district = first.get("district") or first.get("local_district")
            state = first.get("state") or first.get("local_state")
            country = first.get("country")
            parts = [str(v) for v in (city, district, state, country) if v]
            if parts:
                return ", ".join(parts)
    location = _first(hit, "location", "city", "place", "country")
    return str(location or "")
