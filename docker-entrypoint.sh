#!/bin/sh
# Fail-closed Startpruefung: AILIZA laeuft nur mit einem gueltigen
# JWT-Secret an. Ohne Pruefung wuerde jwt_handler.py die Authentifizierung
# still deaktivieren -- der Container liefe scheinbar normal, aber Login
# und Registrierung schluegen unverstaendlich fehl.
set -e

if [ -z "${AILIZA_SECRET_KEY}" ]; then
  echo "FEHLER: AILIZA_SECRET_KEY ist nicht gesetzt." >&2
  echo "Bitte .env anlegen (Vorlage: .env.example) und einen Wert mit" >&2
  echo "mindestens 32 Zeichen setzen, z. B.:" >&2
  echo "  python -c \"import secrets; print(secrets.token_urlsafe(48))\"" >&2
  exit 1
fi

# Laenge ohne Ausgabe des Wertes pruefen (kein Secret in Logs).
if [ "$(printf %s "${AILIZA_SECRET_KEY}" | wc -c)" -lt 32 ]; then
  echo "FEHLER: AILIZA_SECRET_KEY ist zu kurz (mindestens 32 Zeichen noetig)." >&2
  echo "Der aktuelle Wert wird aus Sicherheitsgruenden nicht angezeigt." >&2
  exit 1
fi

exec "$@"
