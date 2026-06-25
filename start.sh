#!/usr/bin/env bash
# AILIZA starten — Backend + Frontend + Handy-Link anzeigen
set -e

# Lokale IP ermitteln (funktioniert auf Linux, Mac, Termux)
IP=$(python3 -c "
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(('8.8.8.8', 80))
    print(s.getsockname()[0])
except:
    print('127.0.0.1')
finally:
    s.close()
" 2>/dev/null || echo "127.0.0.1")

echo ""
echo "╔══════════════════════════════════════╗"
echo "║          AILIZA startet...           ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "  Auf diesem PC:    http://localhost:8000"
echo "  Auf dem Handy:    http://$IP:8000"
echo ""
echo "  Handy-Schritte:"
echo "  1. Sicherstellen dass PC und Handy im gleichen WLAN sind"
echo "  2. Chrome auf dem Handy öffnen"
echo "  3. Adresse eingeben: http://$IP:8000"
echo "  4. Chrome-Menü (3 Punkte) → 'Zum Startbildschirm hinzufügen'"
echo ""
echo "  Zum Beenden: Strg+C"
echo ""

# Virtuelle Umgebung aktivieren
if [ -f .venv/bin/activate ]; then
  source .venv/bin/activate
elif [ -f venv/bin/activate ]; then
  source venv/bin/activate
fi

# Backend starten (statisches Frontend wird mitgeliefert)
cd apps/backend
uvicorn main:app --host 0.0.0.0 --port 8000
