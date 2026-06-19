"""
Bootstrap-Script: Ersten Admin-Nutzer anlegen.
===============================================
Nur lokal/CLI ausfuehren — NIEMALS als API-Endpoint verfuegbar machen.

Verwendung:
    python apps/backend/create_admin.py

Umgebungsvariablen (oder .env):
    AILIZA_ADMIN_USER   — Nutzername (Default: admin)
    AILIZA_ADMIN_PASS   — Passwort (min. 12 Zeichen, Pflicht)
    AILIZA_ADMIN_TENANT — Mandant (Default: default)
    AILIZA_SETUP_DONE   — Wenn gesetzt, Script abgebrochen (Sicherheitssperre)
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# .env laden falls vorhanden
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")
except ImportError:
    pass


def _check_password_policy(pw: str) -> list[str]:
    """Gibt Liste der verletzten Regeln zurueck (leer = okay)."""
    errors = []
    if len(pw) < 12:
        errors.append("Mindestens 12 Zeichen erforderlich.")
    if not re.search(r"[A-Z]", pw):
        errors.append("Mindestens ein Großbuchstabe erforderlich.")
    if not re.search(r"[a-z]", pw):
        errors.append("Mindestens ein Kleinbuchstabe erforderlich.")
    if not re.search(r"\d", pw):
        errors.append("Mindestens eine Zahl erforderlich.")
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?]", pw):
        errors.append("Mindestens ein Sonderzeichen erforderlich.")
    return errors


def main() -> None:
    # Sicherheitssperre: Script nur einmal ausfuehren
    if os.getenv("AILIZA_SETUP_DONE"):
        print("❌ AILIZA_SETUP_DONE ist gesetzt — Bootstrap bereits abgeschlossen.")
        print("   Neuen Admin nur ueber POST /auth/register (mit Admin-Token) anlegen.")
        sys.exit(1)

    secret = os.getenv("AILIZA_SECRET_KEY", "")
    if len(secret) < 32:
        print("❌ AILIZA_SECRET_KEY ist nicht gesetzt oder zu kurz (< 32 Zeichen).")
        print("   Trage den Key in .env ein bevor du dieses Script ausfuehrst.")
        sys.exit(1)

    user_id = os.getenv("AILIZA_ADMIN_USER", "admin").strip()
    tenant_id = os.getenv("AILIZA_ADMIN_TENANT", "default").strip()
    password = os.getenv("AILIZA_ADMIN_PASS", "").strip()

    # Passwort interaktiv abfragen wenn nicht per Env gesetzt
    if not password:
        import getpass
        print(f"\nAdmin-Nutzer: {user_id!r}  |  Mandant: {tenant_id!r}")
        password = getpass.getpass("Passwort (min. 12 Zeichen, Groß+Klein+Zahl+Sonderzeichen): ")

    policy_errors = _check_password_policy(password)
    if policy_errors:
        print("\n❌ Passwort-Policy verletzt:")
        for err in policy_errors:
            print(f"   • {err}")
        sys.exit(1)

    # DB initialisieren und Nutzer anlegen
    try:
        from database import init_db, get_user, create_user
        from auth.models import UserCreate, UserInDB
    except ImportError:
        from apps.backend.database import init_db, get_user, create_user
        from apps.backend.auth.models import UserCreate, UserInDB

    init_db()

    existing = get_user(user_id, tenant_id)
    if existing:
        print(f"⚠️  Nutzer '{user_id}' im Mandanten '{tenant_id}' existiert bereits.")
        answer = input("Passwort ueberschreiben? (j/N): ").strip().lower()
        if answer != "j":
            print("Abgebrochen.")
            sys.exit(0)

    uc = UserCreate(user_id=user_id, tenant_id=tenant_id, role="admin", plain_password=password)
    u = UserInDB.from_create(uc)
    create_user(u.user_id, u.tenant_id, u.role, u.hashed_password)

    print(f"\n✅ Admin '{user_id}' (Mandant: '{tenant_id}') erfolgreich angelegt.")
    print("\n⚠️  WICHTIG: Setze jetzt in deiner .env:")
    print("   AILIZA_SETUP_DONE=true")
    print("   → Das sperrt dieses Script fuer zukuenftige Ausfuehrungen.\n")
    print("Login testen:")
    print(f'   curl -X POST http://localhost:8001/auth/login \\')
    print(f'     -H "Content-Type: application/json" \\')
    print(f'     -d \'{{"user_id":"{user_id}","password":"***"}}\'\n')


if __name__ == "__main__":
    main()
