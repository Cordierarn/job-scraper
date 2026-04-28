"""Bot Telegram qui scanne les alertes et notifie les nouvelles offres."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from .runner import run_alerts, load_alerts
from .telegram_client import TelegramClient


def cmd_test_telegram():
    tg = TelegramClient()
    if not tg.configured():
        print("❌ TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID manquant dans .env")
        return 1
    if tg.send("✅ <b>Test du Job Scraper Bot</b>\nLa connexion Telegram fonctionne."):
        print("✅ Message envoyé sur Telegram.")
        return 0
    print("❌ Échec d'envoi.")
    return 1


def cmd_list(alerts_file: str | None):
    alerts = load_alerts(alerts_file)
    print(f"\n{len(alerts)} alerte(s) actives:\n")
    for a in alerts:
        cont = f", contrat={a.contract}" if a.contract else ""
        rem = " [remote]" if a.remote else ""
        srcs = f", sources={','.join(a.sources)}" if a.sources else ""
        age = f", ≤{a.max_age_hours}h" if a.max_age_hours else ""
        print(f"  • {a.name}")
        print(f"      kw={a.keywords!r}  lieux={a.locations}{cont}{rem}{srcs}{age}")
    print()
    return 0


def cmd_once(dry_run: bool, alerts_file: str | None, state_file: str | None):
    summary = run_alerts(dry_run=dry_run, alerts_file=alerts_file, state_file=state_file)
    print("\n=== Résumé ===")
    for name, s in summary.items():
        print(f"  {name}: {s['new']} nouvelles / {s['total']} totales")
    return 0


def cmd_daemon(interval_hours: float, alerts_file: str | None, state_file: str | None):
    interval_s = int(interval_hours * 3600)
    print(f"🤖 Bot lancé en mode daemon — scan toutes les {interval_hours}h.")
    print("   (Ctrl+C pour arrêter)\n")
    while True:
        try:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n========== {ts} ==========")
            run_alerts(alerts_file=alerts_file, state_file=state_file)
        except KeyboardInterrupt:
            print("\n👋 Arrêt demandé.")
            return 0
        except Exception as e:
            print(f"⚠️  Erreur dans la boucle: {type(e).__name__}: {e}")
        next_ts = time.strftime("%H:%M:%S", time.localtime(time.time() + interval_s))
        print(f"💤 Prochain scan à {next_ts}")
        try:
            time.sleep(interval_s)
        except KeyboardInterrupt:
            print("\n👋 Arrêt demandé.")
            return 0


def _add_paths(p):
    p.add_argument("--alerts-file", default=None, help="Chemin vers un fichier d'alertes alternatif")
    p.add_argument("--state-file", default=None, help="Chemin vers un fichier d'état alternatif (seen.json)")


def main():
    parser = argparse.ArgumentParser(description="Bot Telegram d'alertes d'offres d'emploi.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("test", help="Envoie un message de test sur Telegram")
    p_list = sub.add_parser("list", help="Liste les alertes configurées")
    _add_paths(p_list)
    p_once = sub.add_parser("once", help="Scan unique (puis quitte)")
    p_once.add_argument("--dry-run", action="store_true", help="N'envoie rien sur Telegram, affiche juste")
    _add_paths(p_once)
    p_daemon = sub.add_parser("daemon", help="Boucle infinie de scans périodiques")
    p_daemon.add_argument("--interval", type=float, default=4.0, help="Heures entre scans (défaut: 4)")
    _add_paths(p_daemon)
    args = parser.parse_args()

    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    if args.cmd == "test":
        return cmd_test_telegram()
    if args.cmd == "list":
        return cmd_list(args.alerts_file)
    if args.cmd == "once":
        return cmd_once(args.dry_run, args.alerts_file, args.state_file)
    if args.cmd == "daemon":
        return cmd_daemon(args.interval, args.alerts_file, args.state_file)


if __name__ == "__main__":
    sys.exit(main() or 0)
