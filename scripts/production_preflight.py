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


def _is_exact_https_origin(value: str) -> bool:
    try:
        parsed = urlparse(value)
        _ = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and not parsed.path
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    )


def _is_postgres_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        _ = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme in {"postgresql", "postgresql+psycopg"}
        and bool(parsed.hostname)
        and bool(parsed.path.strip("/"))
        and not parsed.fragment
    )


def evaluate(env: dict[str, str]) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []

    results.append(("production_mode", env.get("AILIZA_ENV", "").lower() == "production",
                    "AILIZA_ENV muss production sein"))
    results.append(("test_mode_disabled", not _true(env.get("AILIZA_TEST_MODE")),
                    "AILIZA_TEST_MODE darf nicht aktiv sein"))
    render_managed_tls = _true(env.get("RENDER"))
    application_redirect = _true(env.get("AILIZA_FORCE_HTTPS"))
    results.append(("https_enforced", render_managed_tls or application_redirect,
                    "Render-TLS oder anwendungseigener HTTPS-Redirect muss aktiv sein"))
    results.append(("hsts_enabled", _true(env.get("AILIZA_HSTS_ENABLED")) or application_redirect,
                    "HSTS muss explizit aktiviert sein"))

    raw_origins = env.get("AILIZA_CORS_ORIGINS", "")
    origins = [item.strip() for item in raw_origins.split(",") if item.strip()]
    origins_ok = bool(origins) and "*" not in origins and all(_is_exact_https_origin(origin) for origin in origins)
    results.append(("cors_explicit_https", origins_ok,
                    "mindestens eine exakte HTTPS-Origin, keine Wildcard"))

    results.append(("jwt_secret_present", len(env.get("AILIZA_SECRET_KEY", "")) >= 32,
                    "AILIZA_SECRET_KEY muss mindestens 32 Zeichen haben"))
    results.append(("audit_hmac_secret_present", len(env.get("AILIZA_LOG_HMAC_KEY", "")) >= 32,
                    "AILIZA_LOG_HMAC_KEY muss separat gesetzt sein"))

    database_url = env.get("AILIZA_DATABASE_URL", "")
    results.append(("production_database", _is_postgres_url(database_url),
                    "Produktionsdatenbank muss PostgreSQL sein"))

    external_enabled = _true(env.get("AILIZA_EXTERNAL_LLM_ENABLED"))
    provider_key_present = any(env.get(name, "").strip() for name in (
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
