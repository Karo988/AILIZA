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
AILIZA_DATABASE_URL, z.B. Render Shell):

    python apps/backend/audit_memory_scope_cli.py
    python apps/backend/audit_memory_scope_cli.py --json
    python apps/backend/audit_memory_scope_cli.py --json > audit_report.json

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

try:
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")
except ImportError:
    pass


def _print_human_report(report: dict) -> None:
    print(f"Memory-Scope-Audit ({report['checked_at']})")
    print(f"Gesamtzahl memory_items: {report['total_memory_items']}")
    print()
    if report["has_violations"]:
        print("❌ INVARIANTEN VERLETZT:")
    else:
        print("✅ Keine Invarianten-Verletzungen gefunden.")
    for key, ids in report["violations"].items():
        marker = "❌" if ids else "  "
        print(f"  {marker} {key}: {len(ids)} Treffer" + (f" -- {ids}" if ids else ""))
    print()
    print("Info (kein harter Fehler, siehe Dokumentation):")
    for key, ids in report["info_only"].items():
        print(f"     {key}: {len(ids)} Treffer" + (f" -- {ids}" if ids else ""))
    print()
    if report["has_violations"]:
        print("Naechster Schritt: Verletzte Datensaetze pruefen (KEINE automatische")
        print("Reparatur durch dieses Script) und bewusste Korrektur-Migration planen.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rein lesender Bestandsbericht der Memory-Scope-/Owner-/Tenant-Invarianten.",
    )
    parser.add_argument("--json", action="store_true", help="Bericht als JSON statt Klartext ausgeben.")
    args = parser.parse_args()

    try:
        try:
            from database import audit_memory_scope_invariants
        except ImportError:
            from apps.backend.database import audit_memory_scope_invariants
        report = audit_memory_scope_invariants()
    except Exception as exc:
        print(f"❌ Audit fehlgeschlagen: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        _print_human_report(report)

    return 1 if report["has_violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
