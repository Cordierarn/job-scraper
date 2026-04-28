from __future__ import annotations

from .base import Scraper, Job, normalize_contract

# APEC contract type codes (verified via search URL params).
APEC_CONTRACT_IDS = {
    "cdi": "101888",
    "cdd": "101889",
    "alternance": "101890",
    "stage": "101891",
    "freelance": "101892",
}

# Reverse map: ID (and integer form) -> human label.
APEC_CONTRACT_LABELS = {
    "101888": "CDI",
    "101889": "CDD",
    "101890": "Alternance",
    "101891": "Stage",
    "101892": "Freelance",
}

SEARCH_URL = "https://www.apec.fr/cms/webservices/rechercheOffre"


class Apec(Scraper):
    name = "apec"

    def search(self, keywords, location=None, contract=None, remote=False, limit=50, max_age_hours=None):
        c = normalize_contract(contract)
        # APEC's "lieux" field requires numeric area IDs we don't resolve;
        # fold any free-text location into the keyword query instead.
        query = f"{keywords} {location}" if location else keywords
        body: dict = {
            "motsCles": query,
            "pagination": {"range": min(limit, 100), "startIndex": 0},
            "sorts": [{"type": "SCORE", "direction": "DESCENDING"}],
        }
        if c and c in APEC_CONTRACT_IDS:
            body["typesContrat"] = [APEC_CONTRACT_IDS[c]]
        if remote:
            body["teletravail"] = ["TOTAL", "PARTIEL"]

        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://www.apec.fr",
            "Referer": "https://www.apec.fr/candidat/recherche-emploi.html",
        }
        try:
            r = self.session.post(SEARCH_URL, json=body, headers=headers, timeout=self.timeout)
            if r.status_code != 200:
                return []
            data = r.json()
        except Exception:
            return []

        jobs = []
        for item in data.get("resultats", [])[:limit]:
            num = item.get("numeroOffre", "")
            raw_contract = item.get("typeContrat")
            # Fallback: if ID is unknown, prefer the human-readable label field if present.
            label = APEC_CONTRACT_LABELS.get(str(raw_contract))
            if not label:
                label = item.get("typeContratLibelle") or item.get("libelleTypeContrat")
            if not label and raw_contract and not str(raw_contract).isdigit():
                label = str(raw_contract)
            jobs.append(Job(
                title=item.get("intitule", ""),
                company=item.get("nomCommercial") or item.get("nomEntreprise", "N/A"),
                location=item.get("lieuTexte") or "",
                url=f"https://www.apec.fr/candidat/recherche-emploi.html/emploi/detail-offre/{num}" if num else "",
                source=self.name,
                contract=label,
                salary=item.get("salaireTexte"),
                date_posted=item.get("datePublication"),
                description=(item.get("texteOffre") or "")[:500],
            ))
        return jobs
