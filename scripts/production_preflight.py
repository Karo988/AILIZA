#!/usr/bin/env python3
"""Fail-closed Vorprüfung der AILIZA-Produktionsumgebung.

Gibt ausschließlich Prüfnamen und Status aus, niemals Werte von Secrets,
Tokens oder Datenbank-URLs. Exit 0 bedeutet nur: technische Pflichtvariablen
sind plausibel gesetzt. Verträge, Backups, Restore und Geschäftsabnahme werden
dadurch nicht ersetzt.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse


def _true(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes"}


def evaluate(env: dict[str, str]) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []

    results.append(("production_mode", env.get("AILIZA_ENV", "").lower() == "production",
                    "AILIZA_ENV muss production sein"))
    results.append(("test_mode_disabled", not _true(env.get("AILIZA_TEST_MODE")),
                    "AILIZA_TEST_MODE darf nicht aktiv sein"))
    results.append(("https_enforced", _true(env.get("AILIZA_FORCE_HTTPS")),
                    "AILIZA_FORCE_HTTPS muss true sein"))

    raw_origins = env.get("AILIZA_CORS_ORIGINS", "")
    origins = [item.strip() for item in raw_origins.split(",") if item.strip()]
    origins_ok = bool(origins) and "*" not in origins and all(
        urlparse(origin).scheme == "https" and bool(urlparse(origin).netloc)
        for origin in origins
    )
    results.append(("cors_explicit_https", origins_ok,
                    "mindestens eine exakte HTTPS-Origin, keine Wildcard"))

    results.append(("jwt_secret_present", len(env.get("AILIZA_SECRET_KEY", "")) >= 32,
                    "AILIZA_SECRET_KEY muss mindestens 32 Zeichen haben"))
    results.append(("audit_hmac_secret_present", len(env.get("AILIZA_LOG_HMAC_KEY", "")) >= 32,
                    "AILIZA_LOG_HMAC_KEY muss separat gesetzt sein"))

    database_url = env.get("AILIZA_DATABASE_URL", "")
    results.append(("production_database", database_url.startswith(("postgresql://", "postgresql+psycopg://")),
                    "Produktionsdatenbank muss PostgreSQL sein"))

    external_enabled = _true(env.get("AILIZA_EXTERNAL_LLM_ENABLED"))
    provider_key_present = any(env.get(name, "") for name in (
        "GROQ_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"
    ))
    results.append(("provider_configuration", (not external_enabled) or provider_key_present,
                    "bei aktivierten externen LLMs muss mindestens ein Provider-Key gesetzt sein"))
    return results


def main() -> int:
    results = evaluate(dict(os.environ))
    for name, ok, hint in results:
        print(f"{'OK' if ok else 'FEHLER'} {name}: {hint}")
    failures = sum(not ok for _, ok, _ in results)
    print(f"ERGEBNIS: {'BESTANDEN' if failures == 0 else 'GESPERRT'} ({failures} Fehler)")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
