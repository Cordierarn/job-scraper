from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Optional
import random
import re
import unicodedata
import requests

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
]

DEFAULT_UA = USER_AGENTS[0]


def get_random_user_agent() -> str:
    return random.choice(USER_AGENTS)

CONTRACT_ALIASES = {
    "cdi": {"cdi", "permanent", "perm", "indefinite"},
    "cdd": {"cdd", "fixed", "temporary", "contract"},
    "freelance": {"freelance", "independant", "indépendant", "liberal", "self-employed"},
    "stage": {"stage", "internship", "intern"},
    "alternance": {"alternance", "apprentissage", "apprenticeship", "apprentice"},
    "interim": {"interim", "intérim", "temp"},
}


def normalize_contract(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = str(value).lower().strip()
    for canonical, aliases in CONTRACT_ALIASES.items():
        if v in aliases or canonical in v:
            return canonical
    return v


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def job_matches_contract(job: "Job", requested_contract: Optional[str]) -> bool:
    contract = normalize_contract(requested_contract)
    if not contract:
        return True

    if normalize_contract(job.contract) == contract:
        return True

    haystack = normalize_text(" ".join(
        str(part or "")
        for part in (job.contract, job.title, job.company, job.location, job.description)
    ))

    if contract == "alternance":
        positive = (
            "alternance",
            "alternant",
            "alternante",
            "apprentissage",
            "apprenti",
            "apprentice",
            "apprenticeship",
            "contrat pro",
            "contrat professionnalisation",
            "contrat de professionnalisation",
            "professionalisation",
            "professionalization",
        )
        if any(term in haystack for term in positive):
            return True
        return False

    aliases = CONTRACT_ALIASES.get(contract, set())
    return any(alias in haystack for alias in aliases)


@dataclass
class Job:
    title: str
    company: str
    location: str
    url: str
    source: str
    contract: Optional[str] = None
    salary: Optional[str] = None
    date_posted: Optional[str] = None
    description: Optional[str] = None
    remote: Optional[bool] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def dedup_key(self) -> str:
        return self.url.split("?")[0].rstrip("/").lower()


class Scraper:
    name: str = "base"
    requires_credentials: bool = False

    def __init__(self, timeout: int = 20, user_agent: str | None = None):
        self.timeout = timeout
        self.session = requests.Session()
        self.user_agent = user_agent or get_random_user_agent()
        self.session.headers.update({
            "User-Agent": self.user_agent,
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        })

    def is_configured(self) -> bool:
        return True

    def search(
        self,
        keywords: str,
        location: Optional[str] = None,
        contract: Optional[str] = None,
        remote: bool = False,
        limit: int = 50,
        max_age_hours: Optional[float] = None,
    ) -> list[Job]:
        raise NotImplementedError
