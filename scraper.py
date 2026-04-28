"""
Job scraper CLI — recherche d'offres d'emploi sur plusieurs sources françaises.

Usage:
    python scraper.py --keywords "développeur python" --location "Paris" --contract cdi
    python scraper.py -k "data scientist" -l "Lyon" --remote --limit 100
    python scraper.py -k "marketing" --sources indeed,hellowork,wttj --output csv
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from scrapers import ALL_SCRAPERS, Job
from scrapers.base import job_matches_contract

# Force UTF-8 stdout on Windows so accents and arrows render correctly.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv(Path(__file__).parent / ".env")
console = Console()


def parse_args():
    p = argparse.ArgumentParser(
        description="Scraper d'offres d'emploi multi-sources (FR).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Sources disponibles: " + ", ".join(ALL_SCRAPERS.keys()),
    )
    p.add_argument("-k", "--keywords", required=True, help="Mots-clés (ex: 'développeur python')")
    p.add_argument("-l", "--location", help="Lieu (ex: 'Paris', 'Lyon', '75')")
    p.add_argument(
        "-c", "--contract",
        choices=["cdi", "cdd", "freelance", "stage", "alternance", "interim"],
        help="Type de contrat",
    )
    p.add_argument("--remote", action="store_true", help="Uniquement les offres en télétravail")
    p.add_argument("-n", "--limit", type=int, default=30, help="Nombre max d'offres par source (défaut: 30)")
    p.add_argument("--max-age-hours", type=float, default=None, help="Âge max des offres en heures (si supporté côté source)")
    p.add_argument(
        "-s", "--sources",
        help="Sources à utiliser (séparées par virgule). Défaut: toutes les configurées.",
    )
    p.add_argument(
        "-o", "--output",
        choices=["table", "csv", "json"],
        default="table",
        help="Format de sortie (défaut: table)",
    )
    p.add_argument("-f", "--file", help="Fichier de sortie (sinon stdout)")
    p.add_argument("--workers", type=int, default=8, help="Threads parallèles (défaut: 8)")
    return p.parse_args()


def select_scrapers(requested: str | None):
    if requested:
        names = [n.strip() for n in requested.split(",") if n.strip()]
        unknown = [n for n in names if n not in ALL_SCRAPERS]
        if unknown:
            console.print(f"[red]Sources inconnues:[/red] {unknown}")
            sys.exit(1)
        return [(n, ALL_SCRAPERS[n]()) for n in names]
    return [(n, cls()) for n, cls in ALL_SCRAPERS.items()]


def run_one(name, scraper, args) -> tuple[str, list[Job], str | None]:
    if scraper.requires_credentials and not scraper.is_configured():
        return name, [], "non configuré (clé API manquante)"
    try:
        jobs = scraper.search(
            keywords=args.keywords,
            location=args.location,
            contract=args.contract,
            remote=args.remote,
            limit=args.limit,
            max_age_hours=args.max_age_hours,
        )
        if args.contract:
            jobs = [job for job in jobs if job_matches_contract(job, args.contract)]
        return name, jobs, None
    except Exception as e:
        return name, [], f"erreur: {type(e).__name__}: {e}"


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


def output_table(jobs: list[Job]):
    if not jobs:
        console.print("[yellow]Aucun résultat.[/yellow]")
        return
    table = Table(show_lines=False, header_style="bold cyan", row_styles=["", "dim"])
    table.add_column("Source", style="magenta", no_wrap=True)
    table.add_column("Titre", max_width=45)
    table.add_column("Entreprise", max_width=25)
    table.add_column("Lieu", max_width=20)
    table.add_column("Contrat", max_width=10)
    table.add_column("URL", overflow="fold")
    for j in jobs:
        table.add_row(
            str(j.source),
            str(j.title or "?"),
            str(j.company or "?"),
            str(j.location or "?"),
            str(j.contract or "")[:15],
            str(j.url or ""),
        )
    console.print(table)


def output_csv(jobs: list[Job], file_path: str | None):
    fields = ["source", "title", "company", "location", "contract", "salary", "date_posted", "remote", "url", "description"]
    fp = open(file_path, "w", newline="", encoding="utf-8") if file_path else sys.stdout
    try:
        w = csv.DictWriter(fp, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for j in jobs:
            w.writerow(j.to_dict())
    finally:
        if file_path:
            fp.close()


def output_json(jobs: list[Job], file_path: str | None):
    data = [j.to_dict() for j in jobs]
    text = json.dumps(data, indent=2, ensure_ascii=False)
    if file_path:
        Path(file_path).write_text(text, encoding="utf-8")
    else:
        print(text)


def main():
    args = parse_args()
    scrapers = select_scrapers(args.sources)

    console.print(
        f"[bold]Recherche:[/bold] [cyan]{args.keywords}[/cyan]"
        + (f" | [cyan]{args.location}[/cyan]" if args.location else "")
        + (f" | [cyan]{args.contract}[/cyan]" if args.contract else "")
        + (" | [cyan]remote[/cyan]" if args.remote else "")
        + (f" | [cyan]<= {args.max_age_hours}h[/cyan]" if args.max_age_hours is not None else "")
    )
    console.print(f"[bold]Sources:[/bold] {', '.join(n for n, _ in scrapers)}\n")

    all_jobs: list[Job] = []
    with console.status("[bold green]Scraping..."):
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(run_one, n, s, args): n for n, s in scrapers}
            for fut in as_completed(futures):
                name, jobs, err = fut.result()
                if err:
                    console.print(f"  [yellow]{name}[/yellow]: {err}")
                else:
                    console.print(f"  [green]{name}[/green]: {len(jobs)} offre(s)")
                all_jobs.extend(jobs)

    deduped = dedup(all_jobs)
    console.print(f"\n[bold]Total:[/bold] {len(all_jobs)} brutes, [bold green]{len(deduped)}[/bold green] uniques\n")

    if args.output == "table" and not args.file:
        output_table(deduped)
    elif args.output == "csv":
        output_csv(deduped, args.file)
        if args.file:
            console.print(f"[green]-> Ecrit dans {args.file}[/green]")
    elif args.output == "json":
        output_json(deduped, args.file)
        if args.file:
            console.print(f"[green]-> Ecrit dans {args.file}[/green]")


if __name__ == "__main__":
    main()
