from __future__ import annotations

import os
import time
from typing import Optional
from .base import Scraper, Job, normalize_contract

TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire"
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"

CONTRACT_MAP = {
    "cdi": "CDI",
    "cdd": "CDD",
    "freelance": "LIB",
    "interim": "MIS",
    # Stage et alternance n'ont pas de code typeContrat — utiliser natureContrat
    # ci-dessous (FS = stage, E1/E2 = apprentissage / professionnalisation).
}

# Major French cities → INSEE department code. France Travail's API filters
# offers far better by `departement` than by free-text in motsCles.
CITY_TO_DEPT = {
    "paris": "75",
    "marseille": "13", "marseilles": "13",
    "lyon": "69", "villeurbanne": "69",
    "toulouse": "31",
    "nice": "06", "cannes": "06", "antibes": "06",
    "nantes": "44", "saint-nazaire": "44",
    "montpellier": "34", "beziers": "34", "béziers": "34",
    "strasbourg": "67",
    "bordeaux": "33",
    "lille": "59", "roubaix": "59", "tourcoing": "59", "dunkerque": "59",
    "rennes": "35",
    "reims": "51",
    "le havre": "76", "rouen": "76",
    "saint-etienne": "42", "saint-étienne": "42",
    "toulon": "83",
    "grenoble": "38",
    "dijon": "21",
    "angers": "49",
    "nimes": "30", "nîmes": "30",
    "aix-en-provence": "13", "aix": "13",
    "brest": "29", "quimper": "29",
    "le mans": "72",
    "amiens": "80",
    "tours": "37",
    "limoges": "87",
    "clermont-ferrand": "63", "clermont": "63",
    "besancon": "25", "besançon": "25",
    "metz": "57",
    "perpignan": "66",
    "orleans": "45", "orléans": "45",
    "mulhouse": "68", "colmar": "68",
    "caen": "14",
    "nancy": "54",
    "argenteuil": "95",
    "montreuil": "93", "saint-denis": "93",
    "versailles": "78",
    "creteil": "94", "créteil": "94",
    "nanterre": "92", "boulogne": "92",
    "poitiers": "86",
    "pau": "64", "bayonne": "64",
    "la rochelle": "17",
    "annecy": "74",
    "chambery": "73", "chambéry": "73",
    "valence": "26",
    "avignon": "84",
}


class FranceTravail(Scraper):
    name = "france_travail"
    requires_credentials = True

    def __init__(self, **kw):
        super().__init__(**kw)
        self.client_id = os.getenv("FRANCE_TRAVAIL_CLIENT_ID", "")
        self.client_secret = os.getenv("FRANCE_TRAVAIL_CLIENT_SECRET", "")
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 30:
            return self._token
        r = self.session.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "api_offresdemploiv2 o2dsoffre",
            },
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        self._token = data["access_token"]
        self._token_expiry = time.time() + int(data.get("expires_in", 1500))
        return self._token

    def search(self, keywords, location=None, contract=None, remote=False, limit=50):
        token = self._get_token()
        location_text = (location or "").strip()
        query_terms = [keywords.strip()]
        params = {
            "range": f"0-{min(limit - 1, 149)}",
        }
        # France Travail rejects free-text locations in structured params.
        # Resolve common French cities to a department code, fall back to
        # commune (INSEE) for 5-digit input, else fold into the keyword query.
        if location_text:
            if location_text.isdigit() and len(location_text) == 5:
                params["commune"] = location_text
            elif location_text.isdigit() and len(location_text) in (1, 2):
                params["departement"] = location_text.zfill(2)
            else:
                dept = CITY_TO_DEPT.get(location_text.lower().strip())
                if dept:
                    params["departement"] = dept
                else:
                    query_terms.append(location_text)
        c = normalize_contract(contract)
        if c and c in CONTRACT_MAP:
            params["typeContrat"] = CONTRACT_MAP[c]
        elif c == "alternance":
            # E1 = apprentissage / E2 = contrat de professionnalisation.
            params["natureContrat"] = "E1,E2"
        elif c == "stage":
            # FS = stage / convention de stage.
            params["natureContrat"] = "FS"
        if remote:
            params["dureeHebdoMin"] = "0"
            query_terms.append("télétravail")

        params["motsCles"] = " ".join(term for term in query_terms if term)

        r = self.session.get(
            SEARCH_URL,
            params=params,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=self.timeout,
        )
        if r.status_code == 204:
            return []
        r.raise_for_status()
        data = r.json()
        jobs = []
        for offer in data.get("resultats", []):
            jobs.append(Job(
                title=offer.get("intitule", ""),
                company=(offer.get("entreprise") or {}).get("nom", "N/A"),
                location=(offer.get("lieuTravail") or {}).get("libelle", ""),
                url=f"https://candidat.francetravail.fr/offres/recherche/detail/{offer.get('id', '')}",
                source=self.name,
                contract=offer.get("typeContratLibelle"),
                salary=(offer.get("salaire") or {}).get("libelle"),
                date_posted=offer.get("dateCreation"),
                description=(offer.get("description") or "")[:500],
            ))
        return jobs
