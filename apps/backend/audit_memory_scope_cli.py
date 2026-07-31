"""
CLI-Entrypoint: Bestandsbericht der Memory-Scope-/Owner-/Tenant-Invarianten.
=============================================================================
Rein lesend (ruft ausschliesslich database.audit_memory_scope_invariants()
auf -- siehe dort fuer die Read-Only-Garantie und die genaue Definition der
geprueften Invarianten). Veraendert NIEMALS Daten. Gedacht, um den in PR M1
(Scope-/Owner-/Tenant-Invarianten im fachlichen Memory-Kern) angekuendigten
Produktions-Audit gegen die echte Datenbank (Render/Neon) auszufuehren --
diese Sandbox hat dazu keinen Netzwerkzugriff, daher konnte der Audit
bislang nur als Trockenlauf gegen eine leere lokale Dev-Datei nachgewiesen
werden.

Verwendung (aus einer Umgebung mit Zugriff auf die produktive
AILIZA_DATABASE_URL, z.B. Render Shell oder ein manueller GitHub-Actions-
Workflow):

    python apps/backend/audit_memory_scope_cli.py
    python apps/backend/audit_memory_scope_cli.py --json
    python apps/backend/audit_memory_scope_cli.py --json > audit_report.json
    python apps/backend/audit_memory_scope_cli.py --summary-only --json

--summary-only: unterdrueckt ALLE internen ID-Listen (Verletzungen und
Info-Werte) -- nur Zaehlwerte + has_violations bleiben erhalten. Gedacht
fuer Ausfuehrungen, deren Log oeffentlich einsehbar ist (z.B. Logs eines
Workflow-Laufs in einem oeffentlichen GitHub-Repository) -- interne
Datensatz-IDs sollen dort nicht auftauchen, auch wenn sie fuer sich
genommen keine Rohinhalte sind.

Exit-Codes (fuer Skripting/CI-Gates geeignet):
    0 -- keine Verletzungen gefunden (has_violations == False)
    1 -- mindestens eine Invarianten-Verletzung gefunden
    2 -- Fehler beim Ausfuehren des Audits (z.B. DB nicht erreichbar)

Sicherheitshinweise:
    - Dieses Script fuehrt KEINE Reparatur/Migration durch -- es liefert
      ausschliesslich einen Bericht. Eine etwaige Reparatur ist bewusst
      ein separater, spaeterer Schritt mit eigener Prüfung.
    - Es werden NUR interne ID-Listen und Zaehlwerte ausgegeben -- keine
      Memory-Rohinhalte (title/content/purpose), keine Nutzernamen im
      Klartext ausser den bereits in memory_items gespeicherten
      owner_user_id/tenant_id-Werten, die fuer die Diagnose zwingend
      benoetigt werden (kein zusaetzliches Leck ueber das Bestehende
      hinaus).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Repo-Root explizit auf sys.path bringen, BEVOR irgendein AILIZA-Modul
# importiert wird. Grund (Produktions-Audit-Run #1, Exit 2, Workflow-Run
# 30626472529): database.py importiert transitiv `cryptography`
# (governance/field_crypto.py). Fehlt dieses Paket (z.B. bei einer
# schlanken Minimal-Installation), wirft `from database import ...` ein
# ImportError -- der bisherige Fallback `from apps.backend.database import
# ...` schlug dann ZUSAETZLICH fehl, weil das Repo-Root beim direkten
# Skriptaufruf (`python apps/backend/audit_memory_scope_cli.py`) nicht in
# sys.path liegt (nur das Skript-Verzeichnis selbst wird automatisch
# hinzugefuegt). Das erzeugte die irrefuehrende Meldung
# "ModuleNotFoundError: No module named 'apps'", die den eigentlichen
# Fehler (fehlendes cryptography-Paket) verdeckte. Mit dem Repo-Root fest
# in sys.path funktioniert der Import unabhaengig vom Aufrufverzeichnis
# und unabhaengig davon, welches Paket im Einzelfall fehlt -- der echte
# Fehler wird dann klar sichtbar statt durch einen zweiten, irrefuehrenden
# ImportError ueberdeckt.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")
except ImportError:
    pass


def _summarize(report: dict) -> dict:
    """Reduziert einen Bericht auf reine Zaehlwerte -- keine internen
    ID-Listen. Fuer Ausgaben in oeffentlich einsehbare Logs (siehe
    --summary-only)."""
    return {
        "total_memory_items": report["total_memory_items"],
        "has_violations": report["has_violations"],
        "violations": {k: len(v) for k, v in report["violations"].items()},
        "info_only": {k: len(v) for k, v in report["info_only"].items()},
        "checked_at": report["checked_at"],
    }


def _print_human_report(report: dict, *, summary_only: bool) -> None:
    """report: bei summary_only=True bereits ueber _summarize() reduziert
    (violations/info_only-Werte sind dann int Zaehlwerte statt ID-Listen)."""
    print(f"Memory-Scope-Audit ({report['checked_at']})")
    print(f"Gesamtzahl memory_items: {report['total_memory_items']}")
    print()
    if report["has_violations"]:
        print("❌ INVARIANTEN VERLETZT:")
    else:
        print("✅ Keine Invarianten-Verletzungen gefunden.")
    for key, val in report["violations"].items():
        count = val if summary_only else len(val)
        marker = "❌" if count else "  "
        detail = "" if summary_only or not val else f" -- {val}"
        print(f"  {marker} {key}: {count} Treffer{detail}")
    print()
    print("Info (kein harter Fehler, siehe Dokumentation):")
    for key, val in report["info_only"].items():
        count = val if summary_only else len(val)
        detail = "" if summary_only or not val else f" -- {val}"
        print(f"     {key}: {count} Treffer{detail}")
    print()
    if report["has_violations"]:
        print("Naechster Schritt: Verletzte Datensaetze pruefen (KEINE automatische")
        print("Reparatur durch dieses Script) und bewusste Korrektur-Migration planen.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rein lesender Bestandsbericht der Memory-Scope-/Owner-/Tenant-Invarianten.",
    )
    parser.add_argument("--json", action="store_true", help="Bericht als JSON statt Klartext ausgeben.")
    parser.add_argument(
        "--summary-only", action="store_true",
        help="Unterdrueckt interne ID-Listen -- nur Zaehlwerte. Fuer oeffentlich einsehbare Logs.",
    )
    args = parser.parse_args()

    try:
        from apps.backend.database import audit_memory_scope_invariants
        report = audit_memory_scope_invariants()
    except Exception as exc:
        print(f"❌ Audit fehlgeschlagen: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    has_violations = report["has_violations"]
    output_report = _summarize(report) if args.summary_only else report

    if args.json:
        print(json.dumps(output_report, indent=2, default=str))
    else:
        _print_human_report(output_report, summary_only=args.summary_only)

    return 1 if has_violations else 0


if __name__ == "__main__":
    sys.exit(main())
