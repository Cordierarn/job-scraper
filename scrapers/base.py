from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Optional
import re
import unicodedata
import requests

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

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

    def __init__(self, timeout: int = 20):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": DEFAULT_UA,
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
    ) -> list[Job]:
        raise NotImplementedError
