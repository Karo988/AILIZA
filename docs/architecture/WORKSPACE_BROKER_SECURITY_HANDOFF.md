# HANDOFF: authentisierter Workspace-Broker

Status: **unbestätigter HANDOFF-Vorschlag, nicht implementiert**
Ziel: separater Security-PR nach PR #108
Aktueller Schutz: Alle lokalen Workspace-Dateiaktionen enden fail-closed mit
`responsibility_handoff`. Weder Pfadname, Umgebungsvariable noch JSON-Datei
aktivieren einen Workspace.

## 1. Sicherheitsziel

Der Broker ist die einzige Komponente, die einen Workspace anlegen,
authentisieren und Dateioperationen darin ausführen darf. Ein nicht
vertrauenswürdiger Prozess unter demselben Benutzerkonto darf keinen
kontrollierten Workspace nachbilden, austauschen oder umleiten können.

Bedrohungsmodell:

- Angreiferprozess läuft mit derselben normalen Benutzeridentität wie AILIZA.
- Er kann normale Benutzerdateien, Umgebungsvariablen und JSON-Dateien ändern.
- Er kann Symlinks, Junctions, Reparse-Points, Mounts und Pfadwechsel versuchen.
- Er darf weder den Broker-Schlüssel noch dessen Registry verändern oder den
  Broker zu Operationen außerhalb des gebundenen Workspace bewegen können.

Nicht als Vertrauensnachweis zulässig:

- Verzeichnisname oder Verzeichnisform,
- `AILIZA_WORKSPACE_PATH`,
- ungeschützte Marker-, Konfigurations- oder Datenbankdatei,
- bloße Existenz am kanonischen Standardpfad,
- einmalige Pfadprüfung vor einer späteren Operation.

## 2. Prozess- und Vertrauensgrenze

Der Broker läuft unter einer getrennten, eingeschränkten Betriebssystemidentität.
Die AILIZA-Anwendung erhält keine Broker-Schlüssel und keinen direkten
Schreibzugriff auf die Broker-Registry. Kommunikation erfolgt über lokales,
authentisiertes IPC mit einem kleinen, versionierten Protokoll.

Mindestoperationen:

1. `provision_standard_workspace`
2. `register_existing_workspace` (zunächst deaktiviert; eigene Freigabe nötig)
3. `open_for_read`
4. `create_for_write`
5. `replace_atomically`
6. `delete_entry` und `move_entry` (separate Owner-Policy)
7. `get_status`

Der Broker nimmt relative Pfadsegmente entgegen, keine beliebigen absoluten
Zielpfade. Er gibt ein Handle oder einen brokerseitig ausgeführten Vorgang
zurück, niemals die Behauptung „dieser String ist sicher“.

## 3. Authentisierter Kontrollnachweis

Für jeden eingerichteten Workspace speichert ausschließlich der Broker:

- zufällige Workspace-ID,
- kanonischen Standardpfad,
- Volume-/Dateisystem-ID,
- stabile Verzeichnis-ID (plattformabhängig),
- Format- und Protokollversion,
- Erstellungszeit und Status,
- authentisierten Datensatz (MAC oder signierte Struktur).

Die Einrichtung erfolgt atomar. Bereits vorhandene, gleich benannte Ordner
werden nicht automatisch übernommen. Eine Migration muss Herkunft und aktuelle
Verzeichnisidentität gesondert bestätigen.

### Plattformbindung

- **Windows:** eingeschränktes Dienstkonto, ACL nur für Broker/Dienstkonto,
  geschützter Schlüssel über DPAPI im Dienstkontext; Öffnen mit
  Reparse-Point-Schutz und Identitätsprüfung über Handles.
- **macOS:** privilegierter Helper/XPC-Dienst, Schlüssel im für den Helper
  geschützten Keychain-Kontext. Nur
  `~/Library/Application Support/AILIZA/Workspace` ist als Standardpfad
  zulässig; der Pfad allein ist kein Vertrauensbeweis.
- **Linux:** systemd-Dienst unter eigenem Service-User, Registry und Schlüssel
  in einem nur für diesen User zugänglichen Zustandsverzeichnis. Für Headless-
  Betrieb muss die Einrichtung ohne interaktiven Desktop möglich sein.

Die konkrete Schlüssel- und IPC-Auswahl pro Plattform braucht vor Umsetzung
einen Security-Review. Keine Plattform darf auf eine ungeschützte JSON-Markierung
zurückfallen.

### Installation, Rotation, Schlüsselverlust und Wiederherstellung

- **Erstinstallation:** Der Broker erzeugt seine Dienstidentität, das
  plattformgeschützte Schlüsselmaterial und den ersten Registry-Datensatz in
  einer atomaren Einrichtung. Ein bereits vorhandener Workspace wird dabei
  nicht still übernommen.
- **Rotation:** Schlüssel erhalten eine nicht zurücksetzbare Generation. Eine
  Rotation authentisiert den bisherigen Zustand, schreibt Registry und neuen
  Schlüssel atomar um und verwirft die alte Generation erst nach erfolgreicher
  Verifikation. Teilrotationen führen zu `responsibility_handoff`.
- **Schlüsselverlust:** AILIZA erzeugt keinen Ersatzschlüssel im interaktiven
  Prozess und rekonstruiert Vertrauen nicht aus Pfad oder Marker. Der Workspace
  bleibt gesperrt, bis eine protokollierte administrative Wiederherstellung
  abgeschlossen ist.
- **Wiederherstellung:** Registry- oder Workspace-Backups sind zunächst
  untrusted. Workspace-, Volume- und Verzeichnisidentität werden erneut gebunden;
  Abweichungen benötigen einen eigenen, nachvollziehbaren Migrationsentscheid.
- **Deinstallation/Neuinstallation:** Zurückgebliebene Ordner oder Registry-
  Fragmente aktivieren nichts automatisch. Eine neue Broker-Identität verlangt
  eine neue kontrollierte Einrichtung oder genehmigte Migration.

## 4. Pfad- und TOCTOU-Regeln

Vor **jeder** Dateioperation muss der Broker:

1. vom registrierten Workspace-Handle bzw. dessen stabiler Identität ausgehen,
2. Segmente ohne Link-Following öffnen,
3. Symlinks, Junctions, Reparse-Points und unerwartete Mount-Wechsel ablehnen,
4. Volume-/Dateisystem- und Verzeichnisidentität erneut mit der Registry
   vergleichen,
5. die Operation über das geprüfte Handle ausführen,
6. bei atomarem Ersetzen auch temporäres Ziel und finales Ziel an dieselbe
   Workspace-Grenze binden.

Eine Abfolge `resolve(path)` und anschließend `open(path)` reicht nicht, weil
ein gleichberechtigter Prozess den Pfad dazwischen austauschen kann.

## 5. Fail-closed-Lebenszyklus

`responsibility_handoff` bleibt das Ergebnis bei:

- Broker nicht installiert, nicht erreichbar oder nicht authentisierbar,
- fehlendem oder gesperrtem Schlüsselmaterial,
- unbekannter Protokoll-/Formatversion,
- fehlendem Registry-Eintrag,
- Abweichung von Workspace-, Volume- oder Verzeichnis-ID,
- Umbenennung, Verschiebung, Kopie oder Wiederherstellung auf ein anderes Volume,
- Link-/Reparse-/Mount-Fund,
- unvollständiger oder abgebrochener Einrichtung,
- unklarer Migration eines alten Workspace-Pfads.

Fehler dürfen nicht durch einen In-Process-Fallback, eine Umgebungsvariable oder
eine lokale Markerdatei in „allow“ umgewandelt werden.

## 6. Anwendungsintegration

Der Security-PR ersetzt den heutigen Handoff nicht pauschal durch Freigabe.
Er führt einen broker-authentisierten Ausführungspfad ein:

1. Policy entscheidet, ob die gewünschte Operation grundsätzlich zulässig ist.
2. Broker authentisiert Workspace und Zielidentität.
3. Broker führt die Operation über Handles aus.
4. Audit protokolliert Workspace-ID, Operation, Entscheidung und Fehlerklasse,
   aber keine Dateiinhalte oder Schlüssel.
5. Nur ein vollständig erfolgreicher Broker-Vorgang liefert `allow`.

Direkte `Path.open`, `read_text`, `write_text`, `unlink`, `rename` oder
vergleichbare Workspace-Zugriffe außerhalb des Broker-Adapters werden durch
Code-Suche und Tests gesperrt.

## 7. Migration

Bestehende Ordner und alte `.ailiza-workspace.json`-Dateien gelten als
**untrusted input**. Die JSON-Datei wird ignoriert und nicht importiert.

Vorgeschlagener Ablauf:

1. Nutzer erhält Handoff mit verständlicher Erklärung.
2. Broker prüft den erlaubten kanonischen Pfad und die aktuelle Identität.
3. Bereits vorhandener Inhalt wird nicht automatisch als vertrauenswürdig
   übernommen. Übernahme erfordert einen eigenen, protokollierten Owner-Schritt.
4. Broker legt Registry-Eintrag und Schlüsselmaterial atomar an.
5. Erst danach werden Dateioperationen freigeschaltet.

## 8. Pflichtprüfungen des Security-PRs

Positive Tests:

- frische, atomare Einrichtung auf jeder unterstützten Plattform,
- Lesen, Erstellen und atomarer Ersatz über Broker-Handles,
- Neustart mit unveränderter authentisierter Registry,
- nicht dateibasierte AILIZA-Funktionen bleiben unverändert.

Gegenproben, die ohne den jeweiligen Schutz rot werden müssen:

- vollständig nachgebildetes `AILIZA/Workspace` mit gefälschter JSON-Markierung,
- kopierter authentisierter Datensatz ohne Broker-Schlüssel,
- Registry-Manipulation durch normalen Benutzerprozess,
- Austausch des Verzeichnisses nach Vorprüfung,
- Symlink/Junction/Reparse-Point in jeder Pfadposition,
- Umbenennung, Verschiebung und Volume-Wechsel,
- Broker-Ausfall, Schlüsselverlust und Versionsabweichung,
- parallele Einrichtung und abgebrochene atomare Einrichtung,
- macOS-Lookalike außerhalb des exakten Standardpfads,
- UNC-/Netzwerkpfad und unerwarteter Mount.

Zusätzlich erforderlich:

- vollständige Python-Suiten und vorhandene Frontend-CI,
- Linux-Lauf, in dem Symlink-Tests tatsächlich ausgeführt werden,
- plattformspezifische Windows- und macOS-Tests,
- offizieller Gate-10-Manifestgenerator,
- dokumentierter Security-Review vor Merge,
- Mutationen zurückgenommen und sauberer Arbeitsbaum.

## 9. Abnahmekriterien

Der Handoff darf erst in `allow` übergehen, wenn alle Punkte belegt sind:

- echte getrennte OS-Identität,
- geschützte Registry und Schlüsselverwaltung,
- authentisiertes lokales IPC,
- handlebasierte, no-follow Dateioperationen,
- stabile Workspace-/Volume-/Verzeichnisbindung,
- vollständige Fail-closed-Lebenszyklusbehandlung,
- keine JSON-/Pfad-/Env-Vertrauensabkürzung,
- grüne Tests einschließlich Mutations-Gegenproben,
- positiver Security-Review.

Bis dahin bleibt Option A aktiv: **kein autonomes Erstellen, Öffnen, Lesen,
Auflisten, Schreiben, Anhängen, Kopieren, Verschieben, Umbenennen, Löschen oder
Abfragen von Workspace-Metadaten; stattdessen `responsibility_handoff`.**
