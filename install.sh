#!/usr/bin/env bash
# AILIZA Schnell-Installation fuer Linux / macOS / Termux (Android)
set -e

MODE="${1:-core}"
PY="python3"

echo "=== AILIZA Installer ==="
echo "Modus: $MODE  (Optionen: core | full)"
echo ""

# Python pruefen
if ! command -v "$PY" &>/dev/null; then
  echo "FEHLER: Python 3 nicht gefunden."
  echo "Bitte installieren: https://python.org/downloads"
  exit 1
fi

PY_VER=$("$PY" -c 'import sys; print(sys.version_info.minor)')
if [ "$PY_VER" -lt 10 ]; then
  echo "FEHLER: Python 3.10+ benoetigt (gefunden: 3.$PY_VER)"
  exit 1
fi

# Virtuelle Umgebung
if [ ! -d ".venv" ]; then
  echo "Erstelle virtuelle Umgebung..."
  "$PY" -m venv .venv
fi

source .venv/bin/activate

echo "Installiere Abhaengigkeiten ($MODE)..."
if [ "$MODE" = "full" ]; then
  pip install --upgrade pip -q
  pip install -r apps/backend/requirements-full.txt -q
  echo "Lade Sprachmodell (de_core_news_sm, ~15 MB)..."
  python -m spacy download de_core_news_sm -q
else
  pip install --upgrade pip -q
  pip install -r apps/backend/requirements-core.txt -q
fi

# .env anlegen wenn nicht vorhanden
if [ ! -f apps/backend/.env ]; then
  cp apps/backend/.env.example apps/backend/.env 2>/dev/null || cat > apps/backend/.env << 'EOF'
# AILIZA Konfiguration
AILIZA_EXTERNAL_LLM_ENABLED=false
GROQ_API_KEY=
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
MISTRAL_API_KEY=
EOF
  echo ".env angelegt — bitte API-Keys eintragen."
fi

echo ""
echo "✓ AILIZA bereit!"
echo "Starten mit:  source .venv/bin/activate && uvicorn apps.backend.main:app --reload"
if [ "$MODE" = "core" ]; then
  echo "Tipp: Fuer volle KI-Features: bash install.sh full"
fi
