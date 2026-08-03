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
  * Schluessel: 32 Byte, abgeleitet mit **scrypt** (n=2^15, r=8, p=1) aus dem
    Passwort und einem je Sicherung neu gezogenen 16-Byte-Salt
    (`os.urandom`). Die Parameter sind bewusst kostspielig (~100 ms, ~32 MB),
    damit ein schwaches Passwort nicht schnell durchprobiert werden kann.
  * Nonce: 12 Byte, je Sicherung neu aus `os.urandom`. Salt und Nonce werden
    im Klartext vorangestellt -- das ist beabsichtigt und unbedenklich, beide
    sind keine Geheimnisse.
  * Zusatzdaten (AAD): die Dateikennung, damit ein abgeschnittenes oder
    umetikettiertes Paket auffaellt.

Wichtig -- Echtheit kommt aus GCM, nicht aus der Pruefsummendatei:
Die begleitende `.sha256`-Datei erkennt nur zufaellige Beschaedigung. Ein
Angreifer koennte Paket und Pruefsumme gemeinsam austauschen. Die
eigentliche Manipulationserkennung leistet das Authentifizierungsmerkmal
von AES-GCM: ohne das Passwort laesst sich kein Paket erzeugen, das sich
entschluesseln laesst. Ein veraendertes Byte fuehrt zum Abbruch -- auch
wenn keine `.sha256`-Datei vorhanden ist.

Umgang mit Geheimnissen
-----------------------
Das Passwort wird interaktiv abgefragt oder ueber die Umgebungsvariable
AILIZA_BACKUP_PASSWORD uebergeben -- **niemals als Befehlszeilenargument**.
Argumente sind auf demselben Rechner in der Prozessliste sichtbar und landen
im Verlauf der Kommandozeile.

Im Containerbetrieb (backup-local.cmd) wird das Passwort ueber die
Standardeingabe erfragt und **nicht** per `docker run -e` gesetzt: Werte aus
`-e` erscheinen dauerhaft in `docker inspect`. Der AILIZA_SECRET_KEY gelangt
ausschliesslich als eingebundene Datei in den Container, nie als
Umgebungsvariable.

Ausgaben enthalten niemals Chattitel, Chatinhalte, den AILIZA_SECRET_KEY
oder das Sicherungspasswort. Die Abnahme meldet nur, ob die Entschluesselung
gelungen ist -- nicht, was dabei herauskam.
"""
from __future__ import annotations

import argparse
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
FORMAT_VERSION = 1
_MAGIC = b"AILIZABK1"
_SALT_LEN = 16
_NONCE_LEN = 12
# scrypt-Parameter: bewusst kostspielig, damit ein schwaches Passwort nicht
# trivial durchprobiert werden kann. n=2**15 braucht ~100 ms und ~32 MB.
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2 ** 15, 8, 1


class BackupError(RuntimeError):
    """Verstaendlicher Abbruchgrund -- wird ohne Stapelverfolgung ausgegeben."""


# ---------------------------------------------------------------------------
# Verschluesselung
# ---------------------------------------------------------------------------

def _nur_eigentuemer(pfad: Path) -> None:
    """Beschraenkt die Dateirechte auf die Eigentuemerin (0600).

    Betrifft das Sicherungspaket (enthaelt personenbezogene Daten) und die
    beim Wiederherstellen abgelegte Schluesseldatei (enthaelt den
    AILIZA_SECRET_KEY im Klartext). Ohne diese Einschraenkung entstehen sie
    mit 0644 und waeren auf einem Rechner mit mehreren Konten fuer jeden
    lesbar.

    Unter Windows hat chmod nur begrenzte Wirkung; NTFS-Rechte werden davon
    nicht veraendert. Der Aufruf schadet dort nicht, ersetzt aber keine
    ACL-Haertung -- deshalb liegen die Sicherungen unter
    %LOCALAPPDATA%, das bereits kontogebunden ist.
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


def _derive_key(password: str, salt: bytes) -> bytes:
    _, Scrypt = _require_crypto()
    return Scrypt(salt=salt, length=32, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P).derive(
        password.encode("utf-8")
    )


def _encrypt_to_file(plaintext: bytes, password: str, target: Path) -> None:
    AESGCM, _ = _require_crypto()
    salt = os.urandom(_SALT_LEN)
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(_derive_key(password, salt)).encrypt(nonce, plaintext, _MAGIC)
    tmp = target.with_suffix(target.suffix + ".unfertig")
    tmp.write_bytes(_MAGIC + salt + nonce + ct)
    _nur_eigentuemer(tmp)
    tmp.replace(target)  # atomar: entweder ganz oder gar nicht


def _decrypt_file(source: Path, password: str) -> bytes:
    AESGCM, _ = _require_crypto()
    blob = source.read_bytes()
    if not blob.startswith(_MAGIC):
        raise BackupError(
            f"{source.name} ist kein AILIZA-Sicherungspaket (Kennung fehlt)."
        )
    off = len(_MAGIC)
    salt = blob[off:off + _SALT_LEN]
    nonce = blob[off + _SALT_LEN:off + _SALT_LEN + _NONCE_LEN]
    ct = blob[off + _SALT_LEN + _NONCE_LEN:]
    try:
        return AESGCM(_derive_key(password, salt)).decrypt(nonce, ct, _MAGIC)
    except Exception as exc:
        # AES-GCM prueft beim Entschluesseln zugleich die Echtheit (AEAD).
        # Ein Fehlschlag bedeutet deshalb: falsches Passwort ODER das Paket
        # wurde veraendert. Beides fuehrt zum Abbruch -- welcher der beiden
        # Faelle vorliegt, ist absichtlich nicht unterscheidbar, sonst waere
        # das ein Hinweis fuer Angreifer.
        raise BackupError(
            "Paket konnte nicht geoeffnet werden.\n"
            "Entweder ist das Passwort falsch, oder der Inhalt wurde "
            "veraendert. Die Echtheitspruefung von AES-256-GCM hat "
            "angeschlagen -- das erkennt auch eine Manipulation, bei der "
            "Paket und Pruefsummendatei gemeinsam ausgetauscht wurden."
        ) from exc


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------

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
            return 2
        if verschluesselt == 0:
            print("[5/5] Kein verschluesselter Inhalt vorhanden -- "
                  "Entschluesselungstest entfaellt (leere Datenbank).")
            return 0

        secret = _read_secret_from_env(env_file)
        if not secret:
            print("[5/5] UNVOLLSTAENDIG: AILIZA_SECRET_KEY steht nicht in der "
                  "mitgesicherten Konfigurationsdatei.")
            return 2

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
    """Entpackt ohne Pfadausbruch (Schutz gegen praeparierte Archive)."""
    dest = dest.resolve()
    for member in tar.getmembers():
        ziel = (dest / member.name).resolve()
        if not str(ziel).startswith(str(dest)):
            raise BackupError(f"Unzulaessiger Pfad im Archiv: {member.name}")
        if member.issym() or member.islnk():
            raise BackupError(f"Verknuepfung im Archiv abgelehnt: {member.name}")
    tar.extractall(dest)


# ---------------------------------------------------------------------------
# Befehl: restore
# ---------------------------------------------------------------------------

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
    pw = os.environ.get("AILIZA_BACKUP_PASSWORD", "")
    if pw:
        return pw
    if not sys.stdin.isatty():
        raise BackupError(
            "Kein Passwort. Entweder AILIZA_BACKUP_PASSWORD setzen oder das "
            "Skript in einem Terminal ausfuehren."
        )
    pw = getpass.getpass("Passwort fuer das Sicherungspaket: ")
    if len(pw) < 12:
        raise BackupError("Passwort zu kurz -- mindestens 12 Zeichen.")
    if confirm and pw != getpass.getpass("Passwort wiederholen: "):
        raise BackupError("Die Passwoerter stimmen nicht ueberein.")
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
        print(f"\nFEHLER: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nAbgebrochen.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
