"""Flask webapp pour le job scraper — UI interactive."""
from __future__ import annotations

import csv
import io
import json
import sys
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, send_file

from bot.dates import parse_job_date
from scrapers import ALL_SCRAPERS, Job
from scrapers.base import job_matches_contract

load_dotenv(Path(__file__).parent / ".env")

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False


@app.route("/")
def index():
    sources = []
    for name, cls in ALL_SCRAPERS.items():
        s = cls()
        sources.append({
            "name": name,
            "label": pretty_name(name),
            "configured": s.is_configured(),
            "needs_key": s.requires_credentials,
        })
    return render_template("index.html", sources=sources)


def pretty_name(slug: str) -> str:
    overrides = {
        "france_travail": "France Travail",
        "wttj": "Welcome to the Jungle",
        "linkedin": "LinkedIn",
        "jobspy": "JobSpy",
        "free_work": "Free-Work",
        "apec": "APEC",
        "hellowork": "HelloWork",
        "talent_com": "Talent.com",
        "codeur": "Codeur.com",
    }
    return overrides.get(slug, slug.replace("_", " ").title())


def run_one(name: str, scraper, payload: dict):
    if scraper.requires_credentials and not scraper.is_configured():
        return name, [], "non configuré (clé API manquante)"
    try:
        jobs = scraper.search(
            keywords=payload["keywords"],
            location=payload.get("location") or None,
            contract=payload.get("contract") or None,
            remote=bool(payload.get("remote")),
            limit=int(payload.get("limit") or 30),
            max_age_hours=payload.get("max_age_hours"),
        )
        requested_contract = payload.get("contract") or None
        if requested_contract:
            jobs = [job for job in jobs if job_matches_contract(job, requested_contract)]
        location = (payload.get("location") or "").strip()
        if location:
            jobs = [job for job in jobs if job_matches_location(job, location)]
        return name, jobs, None
    except Exception as e:
        return name, [], format_error(e)


def format_error(err: Exception) -> str:
    response = getattr(err, "response", None)
    if response is not None:
        body = (getattr(response, "text", "") or "").replace("\n", " ").strip()
        url = getattr(response, "url", "")
        details = f"{type(err).__name__}: {response.status_code}"
        if url:
            details += f" for {url}"
        if body:
            details += f" — {body[:180]}"
        return details[:240]
    return f"{type(err).__name__}: {str(err)[:220]}"


def job_matches_location(job: Job, requested_location: str) -> bool:
    if not requested_location:
        return True

    loc = normalize_text(job.location or "")
    if not loc:
        return True

    if job.source == "remotive":
        return False

    foreign_hints = (
        "usa",
        "united states",
        "brazil",
        "colombia",
        "philippines",
        "canada",
        "argentina",
        "germany",
        "latam",
        "asia",
        "oceania",
        "emea",
        "worldwide",
        "remote",
        "county",
        "ky",
    )
    return not any(hint in loc for hint in foreign_hints)


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def dedup(jobs: list[Job]) -> list[Job]:
    seen = set()
    out = []
    for j in jobs:
        k = j.dedup_key()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(j)
    return out


@app.route("/search", methods=["POST"])
def search():
    payload = request.get_json(force=True)
    if not payload.get("keywords", "").strip():
        return jsonify({"error": "Mots-clés obligatoires"}), 400
    if payload.get("max_age_hours") not in (None, ""):
        try:
            payload["max_age_hours"] = float(payload["max_age_hours"])
        except (TypeError, ValueError):
            return jsonify({"error": "max_age_hours doit être un nombre"}), 400
    else:
        payload["max_age_hours"] = None

    selected = payload.get("sources") or list(ALL_SCRAPERS.keys())
    scrapers = [(n, ALL_SCRAPERS[n]()) for n in selected if n in ALL_SCRAPERS]

    all_jobs: list[Job] = []
    statuses: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(scrapers)))) as ex:
        futures = {ex.submit(run_one, n, s, payload): n for n, s in scrapers}
        for fut in as_completed(futures):
            name, jobs, err = fut.result()
            statuses[name] = {"count": len(jobs), "error": err}
            all_jobs.extend(jobs)

    unique = dedup(all_jobs)
    return jsonify({
        "jobs": [_enrich(j.to_dict()) for j in unique],
        "statuses": statuses,
        "raw_count": len(all_jobs),
        "unique_count": len(unique),
    })


def _enrich(job: dict) -> dict:
    """Ajoute date_posted_iso (ISO 8601 UTC) parsé pour le tri/affichage côté front."""
    dt = parse_job_date(job.get("date_posted"))
    job["date_posted_iso"] = dt.isoformat() if dt else None
    return job


@app.route("/export/<fmt>", methods=["POST"])
def export(fmt):
    jobs = (request.get_json(force=True) or {}).get("jobs", [])
    if fmt == "csv":
        buf = io.StringIO()
        fields = ["source", "title", "company", "location", "contract", "salary", "date_posted", "remote", "url", "description"]
        writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for j in jobs:
            writer.writerow(j)
        return send_file(
            io.BytesIO(buf.getvalue().encode("utf-8-sig")),
            mimetype="text/csv",
            as_attachment=True,
            download_name="offres.csv",
        )
    if fmt == "json":
        data = json.dumps(jobs, indent=2, ensure_ascii=False).encode("utf-8")
        return send_file(
            io.BytesIO(data),
            mimetype="application/json",
            as_attachment=True,
            download_name="offres.json",
        )
    return jsonify({"error": "format invalide"}), 400


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print("\n  >> Job Scraper UI: http://127.0.0.1:5000\n")
    app.run(host="127.0.0.1", port=5000, debug=False)
