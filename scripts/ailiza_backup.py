#!/usr/bin/env python3
"""AILIZA — Sicherung, Wiederherstellung und Abnahmepruefung.

Warum dieses Skript existiert
-----------------------------
Die frueher in docs/AUTARKER_BETRIEB.md dokumentierte Anleitung rief
`sqlite3` im Container auf. Dieses Programm ist dort **nicht installiert**
(das Dockerfile installiert nur `libsqlite3-dev`, also die Bibliothek, nicht
das Kommandozeilenwerkzeug). Die Anleitung konnte deshalb nicht funktionieren.

Dieses Skript nutzt stattdessen die SQLite-Backup-Schnittstelle der
Python-Standardbibliothek (`Connection.backup`). Python ist im Container
zwangslaeufig vorhanden.

Warum nicht einfach die Datei kopieren
--------------------------------------
Eine laufende SQLite-Datenbank darf nicht per Dateikopie gesichert werden.
Im WAL-Modus liegen noch nicht uebertragene Aenderungen in einer separaten
`-wal`-Datei; eine Kopie allein der Hauptdatei waere unvollstaendig oder
beschaedigt. `Connection.backup` erzeugt dagegen einen in sich konsistenten
Stand -- auch waehrend AILIZA laeuft.

Warum Datenbank und Schluessel zusammen gesichert werden
-------------------------------------------------------
Chattitel, Chatinhalte, Projektnamen und -beschreibungen liegen mit
AES-256-GCM verschluesselt in der Datenbank (apps/backend/governance/
field_crypto.py). Der Schluessel wird aus AILIZA_SECRET_KEY abgeleitet.
Eine Sicherung ohne diesen Schluessel ist wertlos -- die Inhalte waeren
dauerhaft unlesbar. Beides gehoert deshalb in dasselbe Paket.

Das Sicherungspaket ist verschluesselt, weil es personenbezogene Daten
enthaelt.

Aufrufe
-------
    python3 scripts/ailiza_backup.py backup   --out ORDNER [...]
    python3 scripts/ailiza_backup.py verify   --archive DATEI [...]
    python3 scripts/ailiza_backup.py restore  --archive DATEI [...]

Verschluesselung des Sicherungspakets
-------------------------------------
Verfahren: **AES-256-GCM** (authentifizierte Verschluesselung, AEAD).
  * Schluessel: 32 Byte, abgeleitet mit **scrypt** aus dem Passwort und
    einem je Sicherung neu gezogenen 16-Byte-Salt (`os.urandom`).
    Vorgabe beim Erzeugen: n=2^15, r=8, p=1 (~100 ms, ~33 MB) -- bewusst
    kostspielig, damit ein schwaches Passwort nicht schnell durchprobiert
    werden kann.
  * Nonce: 12 Byte, je Sicherung neu aus `os.urandom`.
  * Zusatzdaten (AAD): der **vollstaendige Paketkopf** -- Dateikennung,
    Kopflaenge, Formatversion, KDF-Kennung, KDF-Parameter (n, r, p) und
    Salt. Damit ist jede Aenderung an diesen Feldern erkennbar. Waeren die
    Parameter nicht authentifiziert, koennte ein Angreifer sie durch
    schwaechere ersetzen.

Paketaufbau:

    "AILIZABK2" | Kopflaenge (2 Byte) | Kopf (JSON) | Nonce (12) | Chiffrat
    |________________________ AAD ________________________|

Schranken beim Lesen: n, r und p werden **vor** der Schluesselableitung
gegen feste Grenzen geprueft (n = 2^14..2^17 und Zweierpotenz, r = 1..32,
p = 1..4, Speicherbedarf 128*n*r hoechstens 256 MiB). Ohne diese Pruefung
koennte ein praepariertes Paket allein durch das Oeffnen beliebig viel
Rechenzeit und Arbeitsspeicher binden.

Wichtig -- Echtheit kommt aus GCM, nicht aus der Pruefsummendatei:
Die begleitende `.sha256`-Datei erkennt nur zufaellige Beschaedigung und
Uebertragungsfehler. Ein Angreifer koennte Paket und Pruefsumme gemeinsam
austauschen. Die eigentliche Manipulationserkennung leistet das
Authentifizierungsmerkmal von AES-GCM: ohne das Passwort laesst sich kein
Paket erzeugen, das sich entschluesseln laesst.

Arbeitsspeicher: Das Paket wird als Ganzes im Speicher ver- und
entschluesselt -- AES-GCM arbeitet in dieser Form nicht stromweise. Der
Bedarf betraegt grob das Zwei- bis Dreifache der Datenbankgroesse. Deshalb
gilt eine Obergrenze von 1 GiB je Paket; darueber bricht das Skript mit
einer verstaendlichen Meldung ab, statt den Rechner in den Speichermangel
zu treiben.

Umgang mit Geheimnissen
-----------------------
Das Sicherungspasswort wird **ausschliesslich ueber die Standardeingabe**
entgegengenommen -- am Terminal verdeckt (getpass), sonst als Zeile von
stdin. Bewusst NICHT als Umgebungsvariable: die wird an Kindprozesse
vererbt, erscheint bei `docker run -e` dauerhaft in `docker inspect` und
ist auf manchen Systemen ueber /proc lesbar. Bewusst NICHT als
Befehlszeilenargument: das steht in der Prozessliste.

Der AILIZA_SECRET_KEY gelangt ausschliesslich als eingebundene Datei in den
Container, nie als Umgebungsvariable.

Ausgaben enthalten niemals Chattitel, Chatinhalte, den AILIZA_SECRET_KEY
oder das Sicherungspasswort. Die Abnahme meldet nur, ob die Entschluesselung
gelungen ist -- nicht, was dabei herauskam. Fremde Prozessausgaben werden
nicht durchgereicht, weil eine Stapelverfolgung Bruchstuecke enthalten
koennte.

Exitcodes
---------
    0   Erfolg
    1   Abbruch (falsches Passwort, Manipulation, fehlende Voraussetzung)
    2   Abnahme unvollstaendig (z. B. kein Schluessel im Paket)
    130 durch Nutzerin abgebrochen
"""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ARCHIVE_SUFFIX = ".ailiza-backup"

# Formatversion 2. Version 1 authentifizierte nur die Dateikennung und hatte
# die KDF-Parameter fest im Code -- ein Paket konnte damit nicht aussagen,
# womit es erzeugt wurde, und der Kopf war nicht gegen Veraenderung
# geschuetzt. Version 2 legt alle Ableitungsparameter in einen Kopf, der
# vollstaendig als AAD in die AES-GCM-Authentifizierung eingeht.
FORMAT_VERSION = 2
_MAGIC = b"AILIZABK2"
_LEN_BYTES = 2          # Laenge des Kopfes, big-endian
_NONCE_LEN = 12
_SALT_LEN = 16
_MAX_HEADER = 4096      # Obergrenze, damit ein manipulierter Wert nicht
                        # zu einer riesigen Speicheranforderung fuehrt

# scrypt-Vorgaben beim Erzeugen: bewusst kostspielig (~100 ms, ~33 MB),
# damit ein schwaches Passwort nicht schnell durchprobiert werden kann.
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2 ** 15, 8, 1

# Zulaessiger Bereich beim LESEN. Ohne diese Schranken koennte ein
# praepariertes Paket ueber n/r/p beliebig viel Rechenzeit und
# Arbeitsspeicher anfordern (scrypt braucht rund 128*n*r Byte) -- ein
# Denial-of-Service allein durch das Oeffnen einer Datei.
_KDF_GRENZEN = {
    "n": (2 ** 14, 2 ** 17),
    "r": (1, 32),
    "p": (1, 4),
}
_MAX_KDF_SPEICHER = 256 * 1024 * 1024   # 256 MiB

# Groessengrenzen. Das Paket wird als Ganzes im Arbeitsspeicher
# ver- und entschluesselt (AESGCM arbeitet nicht stromweise). Der Bedarf
# betraegt grob das Zwei- bis Dreifache der Datenbankgroesse. Die Grenze
# schuetzt davor, dass eine sehr grosse Datenbank oder ein praepariertes
# Paket den Rechner in den Speichermangel treibt.
_MAX_PAKET_BYTES = 1024 * 1024 * 1024        # 1 GiB
_MAX_EINTRAG_BYTES = 1024 * 1024 * 1024      # je Eintrag im Archiv
_MAX_EINTRAEGE = 64

# Exitcodes -- damit Aufrufer die Ursache unterscheiden koennen, ohne
# Meldungstexte auswerten zu muessen.
EXIT_OK = 0
EXIT_FEHLER = 1          # allgemeiner Abbruch
EXIT_UNVOLLSTAENDIG = 2  # Abnahme nicht abschliessbar (z. B. kein Schluessel im Paket)
EXIT_ABGEBROCHEN = 130


class BackupError(RuntimeError):
    """Verstaendlicher Abbruchgrund -- wird ohne Stapelverfolgung ausgegeben."""


def _nur_eigentuemer(pfad: Path) -> None:
    """Beschraenkt die Dateirechte auf die Eigentuemerin (0600).

    Betrifft das Sicherungspaket (enthaelt personenbezogene Daten) und die
    beim Wiederherstellen abgelegte Schluesseldatei (enthaelt den
    AILIZA_SECRET_KEY im Klartext). Ohne diese Einschraenkung entstehen sie
    mit 0644 und waeren auf einem Rechner mit mehreren Konten fuer jeden
    lesbar.

    Unter Windows hat chmod nur begrenzte Wirkung; NTFS-Rechte werden davon
    nicht veraendert. Dort setzt backup-local.cmd die Rechte des
    Zielordners per icacls, BEVOR die erste sensible Datei entsteht.
    """
    try:
        os.chmod(pfad, 0o600)
    except OSError:
        pass  # z. B. Dateisysteme ohne Rechteverwaltung -- kein Abbruchgrund


def _require_crypto():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    except ImportError as exc:  # pragma: no cover
        raise BackupError(
            "Das Paket 'cryptography' fehlt. Es ist Teil von "
            "apps/backend/requirements-core.txt -- bitte in derselben "
            "Python-Umgebung installieren."
        ) from exc
    return AESGCM, Scrypt


def _pruefe_kdf_parameter(n: int, r: int, p: int) -> None:
    """Begrenzt die aus dem Paket gelesenen Ableitungsparameter.

    Ohne diese Pruefung koennte ein praepariertes Paket ueber grosse Werte
    beliebig viel Rechenzeit und Arbeitsspeicher anfordern -- ein
    Denial-of-Service allein durch das Oeffnen einer Datei. Die Pruefung
    laeuft VOR der Schluesselableitung.
    """
    for name, wert in (("n", n), ("r", r), ("p", p)):
        if not isinstance(wert, int) or isinstance(wert, bool):
            raise BackupError(f"Ungueltiger Ableitungsparameter {name}.")
        unten, oben = _KDF_GRENZEN[name]
        if not unten <= wert <= oben:
            raise BackupError(
                f"Ableitungsparameter {name}={wert} liegt ausserhalb des "
                f"zulaessigen Bereichs ({unten}..{oben}). Paket abgelehnt."
            )
    if n & (n - 1) != 0:
        raise BackupError("Ableitungsparameter n muss eine Zweierpotenz sein.")
    bedarf = 128 * n * r
    if bedarf > _MAX_KDF_SPEICHER:
        raise BackupError(
            f"Die Ableitungsparameter wuerden rund {bedarf // (1024*1024)} MiB "
            "Arbeitsspeicher anfordern. Paket abgelehnt."
        )


def _derive_key(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    # Schranken ZUERST -- vor jedem Rechenaufwand. Liefe die Pruefung
    # spaeter, waere der Denial-of-Service bereits eingetreten.
    _pruefe_kdf_parameter(n, r, p)
    _, Scrypt = _require_crypto()
    return Scrypt(salt=salt, length=32, n=n, r=r, p=p).derive(
        password.encode("utf-8")
    )


def _baue_kopf(salt: bytes, n: int, r: int, p: int) -> bytes:
    """Erzeugt den Paketkopf. Er geht vollstaendig als AAD in die
    Authentifizierung ein -- jede Aenderung an Version, Verfahren,
    Parametern oder Salt laesst das Entschluesseln fehlschlagen."""
    kopf = {
        "v": FORMAT_VERSION,
        "kdf": "scrypt",
        "n": n, "r": r, "p": p,
        "salt": base64.b64encode(salt).decode("ascii"),
    }
    return json.dumps(kopf, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _encrypt_to_file(plaintext: bytes, password: str, target: Path) -> None:
    """Verschluesselt und schreibt atomar.

    Die temporaere Datei entsteht im ZIELVERZEICHNIS (nicht in /tmp), damit
    das abschliessende Umbenennen auf demselben Dateisystem stattfindet und
    damit atomar ist. Vor dem Umbenennen wird fsync ausgefuehrt: ohne das
    koennte nach einem Stromausfall ein Paket existieren, dessen Inhalt noch
    im Schreibpuffer stand. Ein unvollstaendiges Paket darf nie wie ein
    gueltiges aussehen.
    """
    AESGCM, _ = _require_crypto()
    if len(plaintext) > _MAX_PAKET_BYTES:
        raise BackupError(
            f"Die Daten sind mit {len(plaintext) // (1024*1024)} MiB groesser "
            f"als die Grenze von {_MAX_PAKET_BYTES // (1024*1024)} MiB. "
            "Das Paket wird als Ganzes im Arbeitsspeicher verschluesselt; "
            "eine hoehere Grenze braeuchte entsprechend mehr RAM."
        )
    salt = os.urandom(_SALT_LEN)
    nonce = os.urandom(_NONCE_LEN)
    kopf = _baue_kopf(salt, _SCRYPT_N, _SCRYPT_R, _SCRYPT_P)
    aad = _MAGIC + len(kopf).to_bytes(_LEN_BYTES, "big") + kopf
    ct = AESGCM(_derive_key(password, salt, _SCRYPT_N, _SCRYPT_R, _SCRYPT_P)).encrypt(
        nonce, plaintext, aad
    )

    target.parent.mkdir(parents=True, exist_ok=True)
    # Kollisionsfreier Name: verhindert, dass zwei gleichzeitig laufende
    # Sicherungen dieselbe temporaere Datei beschreiben.
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=".unfertig-", suffix=ARCHIVE_SUFFIX
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(aad)
            fh.write(nonce)
            fh.write(ct)
            fh.flush()
            os.fsync(fh.fileno())
        _nur_eigentuemer(tmp)
        os.replace(tmp, target)      # atomar
        _sync_verzeichnis(target.parent)
    except BaseException:
        tmp.unlink(missing_ok=True)  # auch bei Abbruch nichts liegen lassen
        raise


def _sync_verzeichnis(ordner: Path) -> None:
    """Sorgt dafuer, dass der Verzeichniseintrag selbst dauerhaft ist."""
    try:
        fd = os.open(str(ordner), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except (OSError, AttributeError):
        pass  # unter Windows nicht verfuegbar -- dort ist replace bereits atomar


def _decrypt_file(source: Path, password: str) -> bytes:
    AESGCM, _ = _require_crypto()
    groesse = source.stat().st_size
    if groesse > _MAX_PAKET_BYTES + _MAX_HEADER + 1024:
        raise BackupError(
            f"Das Paket ist mit {groesse // (1024*1024)} MiB groesser als die "
            "zulaessige Grenze. Abgelehnt, bevor etwas eingelesen wird."
        )
    blob = source.read_bytes()
    if not blob.startswith(_MAGIC):
        raise BackupError(
            f"{source.name} ist kein AILIZA-Sicherungspaket (Kennung fehlt "
            "oder stammt aus einer aelteren Formatversion)."
        )
    off = len(_MAGIC)
    if len(blob) < off + _LEN_BYTES:
        raise BackupError("Paket ist abgeschnitten (Kopf unvollstaendig).")
    kopf_len = int.from_bytes(blob[off:off + _LEN_BYTES], "big")
    if not 0 < kopf_len <= _MAX_HEADER:
        raise BackupError("Paketkopf hat eine unzulaessige Laenge.")
    off += _LEN_BYTES
    kopf_bytes = blob[off:off + kopf_len]
    if len(kopf_bytes) != kopf_len:
        raise BackupError("Paket ist abgeschnitten (Kopf unvollstaendig).")
    aad = _MAGIC + kopf_len.to_bytes(_LEN_BYTES, "big") + kopf_bytes
    off += kopf_len

    try:
        kopf = json.loads(kopf_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise BackupError("Paketkopf ist nicht lesbar.") from exc
    if not isinstance(kopf, dict):
        raise BackupError("Paketkopf hat ein unerwartetes Format.")
    if kopf.get("v") != FORMAT_VERSION:
        raise BackupError(
            f"Nicht unterstuetzte Formatversion: {kopf.get('v')!r}. "
            f"Erwartet: {FORMAT_VERSION}."
        )
    if kopf.get("kdf") != "scrypt":
        raise BackupError(f"Unbekanntes Ableitungsverfahren: {kopf.get('kdf')!r}.")
    try:
        salt = base64.b64decode(kopf["salt"], validate=True)
    except (KeyError, ValueError) as exc:
        raise BackupError("Salt im Paketkopf fehlt oder ist ungueltig.") from exc
    if len(salt) != _SALT_LEN:
        raise BackupError("Salt im Paketkopf hat eine unzulaessige Laenge.")

    # Schranken VOR der Ableitung -- sonst waere schon das Oeffnen angreifbar.
    _pruefe_kdf_parameter(kopf.get("n"), kopf.get("r"), kopf.get("p"))

    nonce = blob[off:off + _NONCE_LEN]
    ct = blob[off + _NONCE_LEN:]
    if len(nonce) != _NONCE_LEN or not ct:
        raise BackupError("Paket ist abgeschnitten (Daten fehlen).")

    schluessel = _derive_key(password, salt, kopf["n"], kopf["r"], kopf["p"])
    try:
        return AESGCM(schluessel).decrypt(nonce, ct, aad)
    except Exception as exc:
        # AES-GCM prueft beim Entschluesseln zugleich die Echtheit (AEAD).
        # Der Kopf geht als AAD mit ein: eine Aenderung an Version,
        # Verfahren, Parametern oder Salt faellt hier ebenso auf wie eine
        # Aenderung am Inhalt.
        #
        # Ein Fehlschlag bedeutet: falsches Passwort ODER Manipulation.
        # Welcher der beiden Faelle vorliegt, wird absichtlich nicht
        # unterschieden -- das waere ein Hinweis fuer Angreifer.
        raise BackupError(
            "Paket konnte nicht geoeffnet werden.\n"
            "Entweder ist das Passwort falsch, oder das Paket wurde "
            "veraendert. Die Echtheitspruefung von AES-256-GCM hat "
            "angeschlagen -- sie umfasst Inhalt UND Kopf (Formatversion, "
            "Verfahren, Ableitungsparameter, Salt) und erkennt auch eine "
            "Manipulation, bei der Paket und Pruefsummendatei gemeinsam "
            "ausgetauscht wurden."
        ) from exc


def _sqlite_backup(src: Path, dst: Path) -> None:
    """Konsistente Sicherung ueber die SQLite-Backup-Schnittstelle.

    Funktioniert auch bei aktivem WAL und geoeffneter Datenbank. Ergebnis ist
    genau eine Datei ohne `-wal`/`-shm`-Begleiter.
    """
    if not src.exists():
        raise BackupError(f"Datenbank nicht gefunden: {src}")
    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    try:
        target = sqlite3.connect(str(dst))
        try:
            with target:
                source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def _integrity_ok(db: Path) -> tuple[bool, str]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        result = con.execute("PRAGMA integrity_check").fetchone()[0]
        return result == "ok", result
    finally:
        con.close()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------

def _docker(args: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, **kw)


def _fetch_db_from_container(container: str, db_in_container: str, dest: Path) -> None:
    """Sichert im Container und holt das Ergebnis heraus.

    Die Sicherung entsteht IM Container, weil nur dort die Datenbankdatei
    liegt (benanntes Docker-Volume). Anschliessend wird die temporaere Datei
    im Container wieder geloescht -- sie enthaelt personenbezogene Daten.
    """
    tmp_in_container = "/tmp/ailiza_backup_tmp.sqlite"
    code = (
        "import sqlite3;"
        f"s=sqlite3.connect('file:{db_in_container}?mode=ro',uri=True);"
        f"t=sqlite3.connect('{tmp_in_container}');"
        "t.__enter__();s.backup(t);t.__exit__(None,None,None);"
        "t.close();s.close();print('OK')"
    )
    res = _docker(["exec", container, "python3", "-c", code])
    if res.returncode != 0 or "OK" not in res.stdout:
        raise BackupError(
            "Sicherung im Container fehlgeschlagen.\n"
            f"{(res.stderr or res.stdout).strip()[:500]}"
        )
    try:
        cp = _docker(["cp", f"{container}:{tmp_in_container}", str(dest)])
        if cp.returncode != 0:
            raise BackupError(f"Herauskopieren fehlgeschlagen: {cp.stderr.strip()[:300]}")
    finally:
        _docker(["exec", container, "rm", "-f", tmp_in_container])


def _resolve_container(name: str | None) -> str | None:
    if name:
        return name
    res = _docker(["compose", "-p", "ailiza", "ps", "-q", "ailiza"])
    cid = res.stdout.strip().splitlines()
    return cid[0] if res.returncode == 0 and cid else None


# ---------------------------------------------------------------------------
# Befehl: backup
# ---------------------------------------------------------------------------

def cmd_backup(args) -> int:
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    password = _get_password(confirm=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        db_copy = tmp_path / "ailiza.sqlite"

        if args.db_path:
            _sqlite_backup(Path(args.db_path).expanduser().resolve(), db_copy)
            quelle = str(args.db_path)
        else:
            container = _resolve_container(args.container)
            if not container:
                raise BackupError(
                    "Kein laufender AILIZA-Container gefunden. Entweder AILIZA "
                    "starten, oder die Datenbank direkt angeben:\n"
                    "  --db-path C:\\Pfad\\zu\\ailiza.sqlite"
                )
            _fetch_db_from_container(container, args.db_in_container, db_copy)
            quelle = f"container:{container}:{args.db_in_container}"

        ok, detail = _integrity_ok(db_copy)
        if not ok:
            raise BackupError(
                f"Abbruch: Die Sicherung ist nicht unversehrt (integrity_check: {detail}). "
                "Es wurde KEIN Paket geschrieben."
            )

        env_src = Path(args.env_file).expanduser().resolve()
        if not env_src.exists():
            raise BackupError(
                f"Konfigurationsdatei nicht gefunden: {env_src}\n"
                "Ohne den darin enthaltenen Schluessel waere die Sicherung "
                "wertlos -- die Chatinhalte blieben dauerhaft unlesbar. "
                "Abbruch. Mit --no-env laesst sich das bewusst uebergehen."
                if not args.no_env else ""
            )
        if env_src.exists():
            shutil.copy2(env_src, tmp_path / "env")

        meta = {
            "format_version": FORMAT_VERSION,
            "erstellt_am": datetime.now(timezone.utc).isoformat(),
            "quelle": quelle,
            "enthaelt_env": env_src.exists(),
            "db_sha256": _sha256(db_copy),
            "db_bytes": db_copy.stat().st_size,
        }
        (tmp_path / "meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        tar_bytes = tmp_path / "paket.tar"
        with tarfile.open(tar_bytes, "w") as tar:
            for name in ("ailiza.sqlite", "meta.json", "env"):
                p = tmp_path / name
                if p.exists():
                    tar.add(p, arcname=name)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive = out_dir / f"ailiza_{stamp}{ARCHIVE_SUFFIX}"
        _encrypt_to_file(tar_bytes.read_bytes(), password, archive)

    checksum = _sha256(archive)
    (archive.with_suffix(archive.suffix + ".sha256")).write_text(
        f"{checksum}  {archive.name}\n", encoding="utf-8"
    )

    print(f"Sicherung erstellt: {archive}")
    print(f"  Groesse:    {archive.stat().st_size / 1024:.1f} kB")
    print(f"  Pruefsumme: {checksum[:32]}...")
    print(f"  Enthaelt:   Datenbank{' + Schluesseldatei' if meta['enthaelt_env'] else ' (OHNE Schluessel!)'}")
    print()
    print("NAECHSTER SCHRITT -- ohne ihn ist die Sicherung nicht abgenommen:")
    print(f"  python3 scripts/ailiza_backup.py verify --archive \"{archive}\"")
    return 0


# ---------------------------------------------------------------------------
# Befehl: verify — der eigentliche Abnahmetest
# ---------------------------------------------------------------------------

def cmd_verify(args) -> int:
    """Prueft eine Sicherung, indem sie tatsaechlich wiederhergestellt wird.

    Abnahmekriterium: Datenbank UND Schluessel werden auf einer frischen,
    temporaeren Instanz wiederhergestellt und ein verschluesselter Inhalt
    wird im Klartext gelesen. Alles darunter beweist nichts -- eine Datei,
    die sich oeffnen laesst, kann trotzdem unlesbare Inhalte enthalten.
    """
    archive = Path(args.archive).expanduser().resolve()
    if not archive.exists():
        raise BackupError(f"Sicherungspaket nicht gefunden: {archive}")

    sidecar = archive.with_suffix(archive.suffix + ".sha256")
    if sidecar.exists():
        erwartet = sidecar.read_text(encoding="utf-8").split()[0]
        tatsaechlich = _sha256(archive)
        if erwartet != tatsaechlich:
            raise BackupError(
                "Pruefsumme weicht ab -- das Paket wurde nachtraeglich "
                f"veraendert oder ist beschaedigt.\n  erwartet:     {erwartet}\n"
                f"  tatsaechlich: {tatsaechlich}"
            )
        print("[1/5] Pruefsumme stimmt.")
    else:
        print("[1/5] Keine Pruefsummendatei daneben -- uebersprungen.")

    password = _get_password(confirm=False)
    payload = _decrypt_file(archive, password)
    print("[2/5] Entschluesselung des Pakets erfolgreich.")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        tar_file = tmp_path / "paket.tar"
        tar_file.write_bytes(payload)
        with tarfile.open(tar_file, "r") as tar:
            _safe_extract(tar, tmp_path)

        db = tmp_path / "ailiza.sqlite"
        if not db.exists():
            raise BackupError("Im Paket ist keine Datenbank enthalten.")

        ok, detail = _integrity_ok(db)
        if not ok:
            raise BackupError(f"Datenbank ist beschaedigt (integrity_check: {detail}).")
        print(f"[3/5] Datenbank unversehrt (integrity_check: {detail}).")

        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            tabellen = con.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table'"
            ).fetchone()[0]
            chats = con.execute("SELECT count(*) FROM user_chats").fetchone()[0]
            verschluesselt = con.execute(
                "SELECT count(*) FROM user_chats WHERE title LIKE 'enc:v1:%'"
            ).fetchone()[0]
        finally:
            con.close()
        print(f"[4/5] {tabellen} Tabellen, {chats} Chats "
              f"({verschluesselt} davon verschluesselt).")

        env_file = tmp_path / "env"
        if not env_file.exists():
            print("[5/5] UNVOLLSTAENDIG: Kein Schluessel im Paket -- "
                  "verschluesselte Inhalte koennen nicht geprueft werden.")
            return EXIT_UNVOLLSTAENDIG
        if verschluesselt == 0:
            print("[5/5] Kein verschluesselter Inhalt vorhanden -- "
                  "Entschluesselungstest entfaellt (leere Datenbank).")
            return 0

        secret = _read_secret_from_env(env_file)
        if not secret:
            print("[5/5] UNVOLLSTAENDIG: AILIZA_SECRET_KEY steht nicht in der "
                  "mitgesicherten Konfigurationsdatei.")
            return EXIT_UNVOLLSTAENDIG

        _decrypt_probe(db, secret)
        print("[5/5] Entschluesselung geprueft -- der mitgesicherte "
              "Schluessel passt zu dieser Datenbank.")

    print()
    print("ABNAHME BESTANDEN: Datenbank und Schluessel wurden auf einer frischen "
          "Instanz wiederhergestellt und verschluesselte Inhalte gelesen.")
    return 0


def _decrypt_probe(db: Path, secret: str) -> None:
    """Prueft, ob der mitgesicherte Schluessel zu dieser Datenbank passt.

    Gibt den entschluesselten Klartext NICHT zurueck und schreibt ihn nirgends
    hin. Der Unterprozess meldet ausschliesslich "OK" oder scheitert -- ein
    Chattitel kann personenbezogene Daten enthalten und gehoert weder in ein
    Terminalprotokoll noch in eine Rueckgabe, die versehentlich ausgegeben
    werden koennte.

    Laeuft in einem Unterprozess, weil field_crypto den Schluessel beim Import
    aus der Umgebung liest -- ein spaeteres Setzen wuerde nicht mehr greifen.
    Der Schluessel wird ueber die Umgebung des Unterprozesses uebergeben, nicht
    als Befehlszeilenargument: Argumente sind auf demselben Rechner in der
    Prozessliste sichtbar, die Umgebung eines fremden Prozesses ist es nicht.
    """
    repo = Path(__file__).resolve().parent.parent
    code = (
        "import sqlite3,sys;"
        "sys.path.insert(0,%r);" % str(repo) +
        "from apps.backend.governance.field_crypto import decrypt_field;"
        "c=sqlite3.connect('file:%s?mode=ro',uri=True);" % db.as_posix() +
        "r=c.execute(\"SELECT title FROM user_chats WHERE title LIKE 'enc:v1:%' LIMIT 1\").fetchone();"
        "t=decrypt_field(r[0]);"
        # Nur eine Zusicherung ausgeben, niemals den Klartext selbst.
        "sys.exit(0 if isinstance(t,str) and t else 3)"
    )
    env = dict(os.environ, AILIZA_SECRET_KEY=secret)
    env.pop("AILIZA_FIELD_ENCRYPTION_KEY", None)
    res = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, env=env, cwd=str(repo))
    if res.returncode != 0:
        # Bewusst ohne stderr des Unterprozesses: eine Stapelverfolgung koennte
        # Bruchstuecke des Inhalts oder des Schluessels enthalten.
        raise BackupError(
            "Der Schluessel im Paket passt NICHT zu dieser Datenbank. Die "
            "Inhalte waeren nach einer Wiederherstellung unlesbar. "
            "Wahrscheinliche Ursache: Die .env stammt aus einer anderen "
            "AILIZA-Installation als die Datenbank."
        )


def _read_secret_from_env(path: Path) -> str | None:
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("AILIZA_SECRET_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    """Entpackt nur, was ein AILIZA-Paket enthalten darf.

    Ein Sicherungspaket ist zwar authentifiziert -- ohne das Passwort laesst
    sich keines erzeugen. Diese Pruefungen greifen trotzdem, weil das
    Passwort kompromittiert sein kann und weil ein Fehler hier Dateien
    ausserhalb des Zielordners ueberschreiben wuerde. Verteidigung in der
    Tiefe.

    Abgewiesen werden: Pfadausbruch ueber "..", absolute Pfade,
    Laufwerksangaben, symbolische und harte Verknuepfungen, Geraetedateien,
    zu viele Eintraege und zu grosse Eintraege (Dekompressionsbombe).
    """
    dest = dest.resolve()
    mitglieder = tar.getmembers()
    if len(mitglieder) > _MAX_EINTRAEGE:
        raise BackupError(
            f"Paket enthaelt {len(mitglieder)} Eintraege, erlaubt sind "
            f"hoechstens {_MAX_EINTRAEGE}. Abgelehnt."
        )

    gesamt = 0
    for m in mitglieder:
        name = m.name
        if name.startswith("/") or name.startswith("\\"):
            raise BackupError(f"Absoluter Pfad im Archiv abgelehnt: {name}")
        if len(name) > 1 and name[1] == ":":
            raise BackupError(f"Laufwerksangabe im Archiv abgelehnt: {name}")
        if ".." in Path(name).parts:
            raise BackupError(f"Pfadausbruch im Archiv abgelehnt: {name}")
        if m.issym() or m.islnk():
            raise BackupError(f"Verknuepfung im Archiv abgelehnt: {name}")
        if not (m.isfile() or m.isdir()):
            raise BackupError(f"Unzulaessiger Eintragstyp im Archiv: {name}")
        if m.size > _MAX_EINTRAG_BYTES:
            raise BackupError(
                f"Eintrag {name} ist mit {m.size // (1024*1024)} MiB zu gross."
            )
        gesamt += m.size
        if gesamt > _MAX_PAKET_BYTES:
            raise BackupError(
                "Der entpackte Inhalt waere groesser als die zulaessige "
                "Grenze (moegliche Dekompressionsbombe). Abgelehnt."
            )
        ziel = (dest / name).resolve()
        if ziel != dest and dest not in ziel.parents:
            raise BackupError(f"Unzulaessiger Pfad im Archiv: {name}")

    tar.extractall(dest)


def cmd_restore(args) -> int:
    archive = Path(args.archive).expanduser().resolve()
    ziel = Path(args.to).expanduser().resolve()

    if ziel.exists() and not args.force:
        raise BackupError(
            f"Zieldatei existiert bereits: {ziel}\n\n"
            "Der vorgesehene Weg ist eine Wiederherstellung in ein NEUES, "
            "leeres Ziel -- danach pruefen, und erst dann bewusst umschalten. "
            "Ein direktes Ueberschreiben vernichtet den aktuellen Datenbestand.\n\n"
            "Falls das Ueberschreiben wirklich gewollt ist: --force ergaenzen. "
            "Der bestehende Stand wird dann zuvor automatisch daneben "
            "gesichert."
        )

    password = _get_password(confirm=False)

    # Zwangssicherung vor dem Ueberschreiben. Auch mit --force darf ein
    # bestehender Datenbestand nicht ersatzlos verschwinden -- eine falsche
    # Wiederherstellung waere sonst nicht mehr rueckgaengig zu machen.
    if ziel.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        vorher = ziel.with_name(f"{ziel.stem}_vor-restore_{stamp}{ziel.suffix}")
        _sqlite_backup(ziel, vorher)
        _nur_eigentuemer(vorher)
        print(f"Bisheriger Stand gesichert: {vorher}")
    payload = _decrypt_file(archive, password)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        tar_file = tmp_path / "paket.tar"
        tar_file.write_bytes(payload)
        with tarfile.open(tar_file, "r") as tar:
            _safe_extract(tar, tmp_path)

        db = tmp_path / "ailiza.sqlite"
        ok, detail = _integrity_ok(db)
        if not ok:
            raise BackupError(f"Abbruch: Paket beschaedigt (integrity_check: {detail}).")

        ziel.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db, ziel)
        print(f"Datenbank wiederhergestellt nach: {ziel}")

        env_file = tmp_path / "env"
        if env_file.exists():
            env_ziel = ziel.parent / "env-aus-sicherung"
            shutil.copy2(env_file, env_ziel)
            _nur_eigentuemer(env_ziel)  # enthaelt den Schluessel im Klartext
            print(f"Schluesseldatei abgelegt unter:   {env_ziel}")
            print()
            print("WICHTIG: Diese Datei enthaelt den Schluessel, mit dem die "
                  "Inhalte verschluesselt wurden. Nur mit ihm sind die "
                  "wiederhergestellten Chats lesbar. Inhalt als .env "
                  "uebernehmen, bevor AILIZA gestartet wird.")
    return 0


# ---------------------------------------------------------------------------

def _get_password(*, confirm: bool) -> str:
    """Liest das Sicherungspasswort -- ausschliesslich ueber die Standardeingabe.

    Bewusst KEINE Umgebungsvariable: Umgebungsvariablen werden an
    Kindprozesse vererbt, erscheinen bei `docker run -e` dauerhaft in
    `docker inspect` und sind auf manchen Systemen ueber /proc lesbar.
    Bewusst KEIN Befehlszeilenargument: Argumente stehen in der Prozessliste
    und im Verlauf der Kommandozeile.

    Am Terminal wird verdeckt abgefragt (getpass). Ohne Terminal -- etwa im
    Container mit `docker run -i` oder in Tests -- wird eine Zeile von der
    Standardeingabe gelesen.
    """
    if sys.stdin is not None and sys.stdin.isatty():
        pw = getpass.getpass("Passwort fuer das Sicherungspaket: ")
        if len(pw) < 12:
            raise BackupError("Passwort zu kurz -- mindestens 12 Zeichen.")
        if confirm and pw != getpass.getpass("Passwort wiederholen: "):
            raise BackupError("Die Passwoerter stimmen nicht ueberein.")
        return pw

    zeile = sys.stdin.readline()
    if not zeile:
        raise BackupError(
            "Kein Passwort empfangen. Das Passwort wird ueber die "
            "Standardeingabe erwartet, z. B.:\n"
            "  echo GEHEIM | python3 scripts/ailiza_backup.py verify --archive ...\n"
            "Es wird bewusst weder als Argument noch als Umgebungsvariable "
            "entgegengenommen."
        )
    pw = zeile.rstrip("\r\n")
    if len(pw) < 12:
        raise BackupError("Passwort zu kurz -- mindestens 12 Zeichen.")
    return pw


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="AILIZA — Sicherung, Wiederherstellung, Abnahmepruefung.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="befehl", required=True)

    b = sub.add_parser("backup", help="Sicherung erstellen")
    b.add_argument("--out", default="backups", help="Zielordner (Standard: backups)")
    b.add_argument("--env-file", default=".env", help="Konfigurationsdatei mit dem Schluessel")
    b.add_argument("--no-env", action="store_true",
                   help="Ohne Schluessel sichern (die Inhalte waeren unlesbar)")
    b.add_argument("--container", default=None, help="Containername oder -kennung")
    b.add_argument("--db-in-container", default="/data/ailiza.sqlite")
    b.add_argument("--db-path", default=None,
                   help="Datenbank direkt statt ueber Docker")
    b.set_defaults(func=cmd_backup)

    v = sub.add_parser("verify", help="Sicherung abnehmen (Wiederherstellungstest)")
    v.add_argument("--archive", required=True)
    v.set_defaults(func=cmd_verify)

    r = sub.add_parser("restore", help="Sicherung einspielen")
    r.add_argument("--archive", required=True)
    r.add_argument("--to", required=True, help="Zielpfad der Datenbankdatei")
    r.add_argument("--force", action="store_true", help="Vorhandene Datei ueberschreiben")
    r.set_defaults(func=cmd_restore)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except BackupError as exc:
        # Verstaendliche Meldung ohne Stapelverfolgung. BackupError-Texte
        # sind bewusst frei von Geheimnissen und Nutzerinhalten.
        print(f"\nFEHLER: {exc}", file=sys.stderr)
        return EXIT_FEHLER
    except KeyboardInterrupt:
        print("\nAbgebrochen.", file=sys.stderr)
        return EXIT_ABGEBROCHEN


if __name__ == "__main__":
    raise SystemExit(main())
