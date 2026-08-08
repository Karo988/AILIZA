@echo off
REM ===================================================================
REM  AILIZA - Sicherung erstellen (Doppelklick)
REM
REM  Laeuft OHNE lokal installiertes Python. Die Sicherung wird in einem
REM  Container ausgefuehrt -- Docker Desktop ist die einzige
REM  Voraussetzung. Das AILIZA-Abbild bringt Python und die
REM  Verschluesselungsbibliothek bereits mit.
REM
REM  Gesichert werden Datenbank UND Schluessel gemeinsam, verschluesselt
REM  in einem Paket. Anschliessend wird die Sicherung geprueft, indem
REM  sie testweise wiederhergestellt und ein verschluesselter Inhalt im
REM  Klartext gelesen wird.
REM ===================================================================
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"

set "ZIEL=%LOCALAPPDATA%\AILIZA\backups"
set "ABBILD=ailiza-ailiza"
set "VOLUME=ailiza_ailiza_data"

echo.
echo  AILIZA - Sicherung
echo  ==================
echo.

REM --- Docker vorhanden und bereit? ---------------------------------
docker version >nul 2>&1
if errorlevel 1 (
    echo  FEHLER: Docker Desktop laeuft nicht oder ist nicht installiert.
    echo.
    echo  Docker Desktop starten und warten, bis das Wal-Symbol unten
    echo  rechts ruhig steht. Dann diese Datei erneut doppelklicken.
    echo.
    pause
    exit /b 1
)

REM --- Ist die Datenbank ueberhaupt vorhanden? ----------------------
docker volume inspect "%VOLUME%" >nul 2>&1
if errorlevel 1 (
    echo  FEHLER: Kein AILIZA-Datenspeicher gefunden ^("%VOLUME%"^).
    echo.
    echo  Entweder wurde AILIZA noch nie gestartet, oder der
    echo  Projektordner wurde umbenannt. Zum Pruefen:
    echo      docker volume ls
    echo.
    pause
    exit /b 1
)

REM --- Abbild vorhanden? Sonst bauen. --------------------------------
docker image inspect "%ABBILD%" >nul 2>&1
if errorlevel 1 (
    echo  Abbild wird einmalig gebaut, das dauert einige Minuten...
    docker compose build ailiza
    if errorlevel 1 (
        echo.
        echo  FEHLER: Das Abbild konnte nicht gebaut werden.
        echo.
        pause
        exit /b 1
    )
)

REM --- .env vorhanden? Ohne Schluessel waere die Sicherung wertlos ---
if not exist ".env" (
    echo  FEHLER: Es gibt keine .env in diesem Ordner.
    echo.
    echo  Darin steht der Schluessel, mit dem die Chatinhalte
    echo  verschluesselt sind. Ohne ihn waere eine Sicherung wertlos --
    echo  die Inhalte blieben dauerhaft unlesbar. Abbruch.
    echo.
    pause
    exit /b 1
)

if not exist "%ZIEL%" mkdir "%ZIEL%" >nul 2>&1

REM --- NTFS-Berechtigungen einschraenken -----------------------------
REM  Die Sicherungen enthalten personenbezogene Daten und den
REM  Verschluesselungsschluessel. Unter Windows sind NTFS-Rechte
REM  massgeblich; das chmod im Python-Skript wirkt hier nicht.
REM  /inheritance:r entfernt geerbte Rechte, danach nur noch der
REM  aktuelle Nutzer, SYSTEM und die Administratorengruppe.
REM  Die Gruppen werden ueber ihre bekannten Sicherheitskennungen (SID)
REM  angesprochen, damit es auch auf nicht-deutschen Windows-Fassungen
REM  funktioniert: S-1-5-18 = SYSTEM, S-1-5-32-544 = Administratoren.
REM  Reihenfolge ist wesentlich: die Rechte werden gesetzt, BEVOR die erste
REM  sensible Datei entsteht. Umgekehrt gaebe es ein Zeitfenster, in dem
REM  das Paket fuer jedes Konto lesbar waere.
set "ACLFEHLER="
icacls "%ZIEL%" /inheritance:r >nul 2>&1 || set "ACLFEHLER=1"
icacls "%ZIEL%" /grant:r "%USERNAME%":(OI)(CI)F >nul 2>&1 || set "ACLFEHLER=1"
icacls "%ZIEL%" /grant:r *S-1-5-18:(OI)(CI)F >nul 2>&1 || set "ACLFEHLER=1"
icacls "%ZIEL%" /grant:r *S-1-5-32-544:(OI)(CI)F >nul 2>&1 || set "ACLFEHLER=1"

REM  Ergebnis nachpruefen statt nur setzen. Zwei Dinge muessen stimmen:
REM  keine Vererbung mehr aktiv, und kein Zugriff fuer "Jeder"
REM  (S-1-1-0) oder "Authentifizierte Benutzer" (S-1-5-11).
icacls "%ZIEL%" 2>nul | findstr /C:"(I)" >nul && set "ACLFEHLER=1"
icacls "%ZIEL%" 2>nul | findstr /R /C:"Everyone" /C:"Jeder" /C:"S-1-1-0" /C:"S-1-5-11" >nul && set "ACLFEHLER=1"

if defined ACLFEHLER (
    echo.
    echo  ================================================================
    echo   WARNUNG: Die Zugriffsrechte des Sicherungsordners konnten nicht
    echo   zuverlaessig eingeschraenkt werden.
    echo.
    echo   Der Ordner  %ZIEL%
    echo   ist moeglicherweise fuer andere Konten auf diesem Rechner
    echo   lesbar. Die Sicherung enthaelt personenbezogene Daten UND den
    echo   Verschluesselungsschluessel.
    echo.
    echo   Aktuelle Rechte:
    icacls "%ZIEL%"
    echo  ================================================================
    echo.
    choice /C JN /N /M "  Trotzdem fortfahren? [J/N] "
    if errorlevel 2 (
        echo  Abgebrochen. Keine Sicherung erstellt.
        pause
        exit /b 1
    )
)

echo  Ziel: %ZIEL%
echo.
echo  Gleich wird ein Passwort fuer das Sicherungspaket abgefragt.
echo  Mindestens 12 Zeichen. OHNE DIESES PASSWORT IST DIE SICHERUNG
echo  NICHT WIEDERHERSTELLBAR - sicher aufbewahren.
echo.

REM  -i (nicht -it): Passworteingabe funktioniert, ohne dass eine
REM  Pseudokonsole noetig ist. Bei Doppelklick gibt es kein TTY.
docker run --rm -i ^
    -v "%VOLUME%":/data:ro ^
    -v "%CD%\scripts":/skripte:ro ^
    -v "%CD%\apps":/app/apps:ro ^
    -v "%CD%\.env":/konfig/.env:ro ^
    -v "%ZIEL%":/sicherungen ^
    -w /app ^
    "%ABBILD%" ^
    python3 /skripte/ailiza_backup.py backup ^
        --db-path /data/ailiza.sqlite ^
        --env-file /konfig/.env ^
        --out /sicherungen

if errorlevel 1 goto :fehler

echo.
echo  ------------------------------------------------------------
echo   Sicherung liegt unter: %ZIEL%
echo.
echo   WICHTIG: Dieser Ordner liegt auf DERSELBEN Festplatte wie
echo   AILIZA. Er schuetzt vor versehentlichem Loeschen, aber NICHT
echo   vor Festplattendefekt, Diebstahl oder Verschluesselungs-
echo   trojanern. Das Paket zusaetzlich auf einen externen
echo   Datentraeger kopieren.
echo  ------------------------------------------------------------
echo.
pause
exit /b 0

:fehler
echo.
echo  Die Sicherung wurde NICHT erstellt. Meldung oben beachten.
echo.
pause
exit /b 1
