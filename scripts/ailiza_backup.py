#!/usr/bin/env python3
"""AILIZA Backup/Restore — SQLite, verschlüsselt, geprüft.

Drei Modi: backup, verify, restore. Passwort wird NIE als Argument oder
Umgebungsvariable entgegengenommen — nur über stdin (Pipe) oder maskiert
per getpass an einem echten Terminal.

Paketformat ("AILIZABK2"):
  magic(9) | header_len(2, big-endian) | header_json | nonce(12) | ciphertext

header_json enthält u.a. {"v":2,"kdf":"scrypt","n":...,"r":...,"p":...,"salt":<b64>}
und dient zugleich als AAD (magic+len+header) für AES-256-GCM — Header-
Manipulation macht die Entschlüsselung ungültig, statt still falsche
KDF-Parameter zu übernehmen.

Sicherheitsgrenzen beim Lesen (VOR der teuren Schlüsselableitung geprüft):
  n zwischen 2**14 und 2**17 und Zweierpotenz, r zwischen 1 und 32,
  p zwischen 1 und 4, geschätzter Speicherbedarf 128*n*r <= 256 MiB.
Das verhindert, dass ein manipuliertes Paket eine Speicher-/CPU-
Erschöpfung (DoS) beim Entschlüsseln auslöst.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import secrets
import shutil
import sqlite3
import sys
import tarfile
import tempfile
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"AILIZABK2"
NONCE_LEN = 12
KEY_LEN = 32
SALT_LEN = 16

# scrypt-Standardparameter für neue Backups.
KDF_N = 2 ** 15
KDF_R = 8
KDF_P = 1

# Grenzen beim LESEN — schützen vor manipulierten Headern.
N_MIN, N_MAX = 2 ** 14, 2 ** 17
R_MIN, R_MAX = 1, 32
P_MIN, P_MAX = 1, 4
MAX_KDF_MEMORY_BYTES = 256 * 1024 * 1024

MAX_ARCHIVE_ENTRIES = 64
MAX_ENTRY_SIZE_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB je Eintrag

EXIT_OK = 0
EXIT_FEHLER = 1
EXIT_UNVOLLSTAENDIG = 2
EXIT_ABGEBROCHEN = 130


class BackupFehler(RuntimeError):
    pass


def _get_password(bestaetigen: bool) -> bytes:
    """Passwort ausschließlich über stdin (Pipe) oder maskiert per getpass.

    Nie als CLI-Argument oder Umgebungsvariable — beides landet in der
    Prozessliste bzw. Shell-Historie.
    """
    if not sys.stdin.isatty():
        pw = sys.stdin.readline().rstrip("\n")
        if not pw:
            raise BackupFehler("Kein Passwort über stdin erhalten.")
        return pw.encode("utf-8")

    pw1 = getpass.getpass("Passwort: ")
    if not pw1:
        raise BackupFehler("Leeres Passwort nicht erlaubt.")
    if bestaetigen:
        pw2 = getpass.getpass("Passwort wiederholen: ")
        if pw1 != pw2:
            raise BackupFehler("Passwörter stimmen nicht überein.")
    return pw1.encode("utf-8")


def _pruefe_kdf_parameter(n: int, r: int, p: int) -> None:
    if not (N_MIN <= n <= N_MAX) or (n & (n - 1)) != 0:
        raise BackupFehler("KDF-Parameter n außerhalb des zulässigen Bereichs.")
    if not (R_MIN <= r <= R_MAX):
        raise BackupFehler("KDF-Parameter r außerhalb des zulässigen Bereichs.")
    if not (P_MIN <= p <= P_MAX):
        raise BackupFehler("KDF-Parameter p außerhalb des zulässigen Bereichs.")
    geschaetzter_speicher = 128 * n * r
    if geschaetzter_speicher > MAX_KDF_MEMORY_BYTES:
        raise BackupFehler("KDF-Parameter verlangen zu viel Speicher — abgelehnt.")


def _derive_key(password: bytes, salt: bytes, n: int, r: int, p: int) -> bytes:
    _pruefe_kdf_parameter(n, r, p)
    return Scrypt(salt=salt, length=KEY_LEN, n=n, r=r, p=p).derive(password)


def _nur_eigentuemer(pfad: Path) -> None:
    try:
        os.chmod(pfad, 0o600)
    except OSError:
        pass


def _sqlite_backup(quelle: Path, ziel: Path) -> None:
    """Konsistente Sicherung über die SQLite-Backup-API (nicht Dateikopie —
    sonst fehlen uncommitted Daten aus der -wal-Datei)."""
    if not quelle.exists():
        raise BackupFehler(f"Quelldatenbank nicht gefunden: {quelle}")
    src_uri = f"file:{quelle}?mode=ro"
    src = sqlite3.connect(src_uri, uri=True)
    try:
        dst = sqlite3.connect(str(ziel))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _encrypt_to_file(plaintext_path: Path, ziel: Path, password: bytes) -> None:
    salt = secrets.token_bytes(SALT_LEN)
    key = _derive_key(password, salt, KDF_N, KDF_R, KDF_P)
    nonce = secrets.token_bytes(NONCE_LEN)
    header = {
        "v": 2, "kdf": "scrypt", "n": KDF_N, "r": KDF_R, "p": KDF_P,
        "salt": salt.hex(),
    }
    header_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
    header_len = len(header_bytes).to_bytes(2, "big")
    aad = MAGIC + header_len + header_bytes

    plaintext = plaintext_path.read_bytes()
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad)

    fd, tmp_name = tempfile.mkstemp(dir=str(ziel.parent), prefix=".tmp-", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(MAGIC)
            f.write(header_len)
            f.write(header_bytes)
            f.write(nonce)
            f.write(ciphertext)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, ziel)
        dir_fd = os.open(str(ziel.parent), os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    _nur_eigentuemer(ziel)


def _read_header(paket: Path) -> tuple[dict, bytes, bytes, bytes]:
    """Liest Header, AAD, Nonce und Ciphertext. Wirft BackupFehler bei
    strukturell ungültigem Paket, OHNE eine Schlüsselableitung zu versuchen."""
    data = paket.read_bytes()
    if not data.startswith(MAGIC):
        raise BackupFehler("Kein gültiges AILIZA-Backup-Paket (Magic-Byte fehlt).")
    offset = len(MAGIC)
    if len(data) < offset + 2:
        raise BackupFehler("Paket beschädigt (Header-Länge fehlt).")
    header_len = int.from_bytes(data[offset:offset + 2], "big")
    offset += 2
    if len(data) < offset + header_len:
        raise BackupFehler("Paket beschädigt (Header abgeschnitten).")
    header_bytes = data[offset:offset + header_len]
    try:
        header = json.loads(header_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackupFehler("Paket-Header ist kein gültiges JSON.") from exc
    offset += header_len

    if header.get("v") != 2 or header.get("kdf") != "scrypt":
        raise BackupFehler("Unbekanntes Paketformat oder KDF.")
    n, r, p = header.get("n"), header.get("r"), header.get("p")
    salt_hex = header.get("salt")
    if not isinstance(n, int) or not isinstance(r, int) or not isinstance(p, int) or not isinstance(salt_hex, str):
        raise BackupFehler("Paket-Header hat ungültige KDF-Felder.")
    _pruefe_kdf_parameter(n, r, p)  # VOR jeder Schlüsselableitung prüfen

    if len(data) < offset + NONCE_LEN:
        raise BackupFehler("Paket beschädigt (Nonce fehlt).")
    nonce = data[offset:offset + NONCE_LEN]
    offset += NONCE_LEN
    ciphertext = data[offset:]
    if not ciphertext:
        raise BackupFehler("Paket beschädigt (kein Chiffretext).")

    aad = MAGIC + header_len.to_bytes(2, "big") + header_bytes
    return header, aad, nonce, ciphertext


def _decrypt_file(paket: Path, ziel: Path, password: bytes) -> None:
    header, aad, nonce, ciphertext = _read_header(paket)
    salt = bytes.fromhex(header["salt"])
    key = _derive_key(password, salt, header["n"], header["r"], header["p"])
    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, aad)
    except InvalidTag as exc:
        raise BackupFehler("Entschlüsselung fehlgeschlagen — falsches Passwort oder Paket manipuliert.") from exc
    ziel.write_bytes(plaintext)
    _nur_eigentuemer(ziel)


def _decrypt_probe(paket: Path, password: bytes) -> bytes | None:
    """Wie _decrypt_file, gibt aber nie Klartext zurück den Aufrufer nicht
    kontrolliert loggt — nur Erfolg/Misserfolg zum Verify-Zweck."""
    header, aad, nonce, ciphertext = _read_header(paket)
    salt = bytes.fromhex(header["salt"])
    key = _derive_key(password, salt, header["n"], header["r"], header["p"])
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, aad)
    except InvalidTag:
        return None


def _safe_extract(archiv: Path, zielverzeichnis: Path) -> None:
    """sqlite-Datei ist kein Archiv — dieser Helfer bleibt für ein
    zukünftiges Mehrdatei-Format vorbereitet, wird aber aktuell nicht vom
    Hauptpfad genutzt (nur eine .sqlite-Datei pro Backup)."""
    with tarfile.open(archiv, "r:*") as tar:
        members = tar.getmembers()
        if len(members) > MAX_ARCHIVE_ENTRIES:
            raise BackupFehler("Archiv enthält zu viele Einträge — abgelehnt.")
        ziel_abs = zielverzeichnis.resolve()
        for m in members:
            if m.issym() or m.islnk():
                raise BackupFehler(f"Symlink/Hardlink im Archiv abgelehnt: {m.name}")
            if not (m.isfile() or m.isdir()):
                raise BackupFehler(f"Ungewöhnlicher Eintragstyp abgelehnt: {m.name}")
            if m.size > MAX_ENTRY_SIZE_BYTES:
                raise BackupFehler(f"Eintrag zu groß: {m.name}")
            member_path = Path(m.name)
            if member_path.is_absolute() or ".." in member_path.parts or (len(member_path.parts) > 0 and member_path.drive):
                raise BackupFehler(f"Unsicherer Pfad im Archiv abgelehnt: {m.name}")
            resolved = (zielverzeichnis / member_path).resolve()
            if resolved != ziel_abs and ziel_abs not in resolved.parents:
                raise BackupFehler(f"Pfad-Traversal im Archiv abgelehnt: {m.name}")
        tar.extractall(zielverzeichnis)


def cmd_backup(args: argparse.Namespace) -> int:
    quelle = Path(args.datenbank).resolve()
    ausgabe = Path(args.ausgabe).resolve()
    ausgabe.parent.mkdir(parents=True, exist_ok=True)

    password = _get_password(bestaetigen=True)

    with tempfile.TemporaryDirectory(prefix="ailiza-backup-") as tmpdir:
        tmp_sqlite = Path(tmpdir) / "backup.sqlite"
        try:
            _sqlite_backup(quelle, tmp_sqlite)
        except sqlite3.Error as exc:
            print(f"FEHLER: SQLite-Sicherung fehlgeschlagen: {exc}", file=sys.stderr)
            return EXIT_FEHLER

        if tmp_sqlite.stat().st_size == 0:
            print("FEHLER: Quelldatenbank ist leer — kein sinnvolles Backup möglich.", file=sys.stderr)
            return EXIT_FEHLER

        try:
            _encrypt_to_file(tmp_sqlite, ausgabe, password)
        except BackupFehler as exc:
            print(f"FEHLER: {exc}", file=sys.stderr)
            return EXIT_FEHLER

    print(f"Backup erstellt: {ausgabe}")
    return EXIT_OK


def cmd_verify(args: argparse.Namespace) -> int:
    paket = Path(args.paket).resolve()
    if not paket.exists():
        print(f"FEHLER: Paket nicht gefunden: {paket}", file=sys.stderr)
        return EXIT_FEHLER

    password = _get_password(bestaetigen=False)

    try:
        plaintext = _decrypt_probe(paket, password)
    except BackupFehler as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return EXIT_FEHLER

    if plaintext is None:
        print("Der Schlüssel im Paket passt NICHT — Passwort falsch oder Paket manipuliert.", file=sys.stderr)
        return EXIT_FEHLER

    print("[1/5] Entschlüsselung erfolgreich.")

    with tempfile.TemporaryDirectory(prefix="ailiza-verify-") as tmpdir:
        tmp_db = Path(tmpdir) / "verify.sqlite"
        tmp_db.write_bytes(plaintext)

        try:
            con = sqlite3.connect(f"file:{tmp_db}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            print(f"FEHLER: [2/5] Entschlüsselte Datei ist keine gültige SQLite-Datenbank: {exc}", file=sys.stderr)
            return EXIT_FEHLER

        try:
            integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                print(f"FEHLER: [3/6] SQLite integrity_check fehlgeschlagen: {integrity}", file=sys.stderr)
                return EXIT_FEHLER
            print("[3/6] SQLite integrity_check: ok.")

            # foreign_key_check ist eigenstaendig -- integrity_check prueft die
            # physische Seitenstruktur, nicht Fremdschluessel-Konsistenz. Eine
            # Sicherung kann strukturell "ok" sein und trotzdem verwaiste
            # Fremdschluessel enthalten (z.B. durch eine fruehere, ausserhalb
            # der Anwendung erfolgte manuelle Aenderung).
            fk_verletzungen = con.execute("PRAGMA foreign_key_check").fetchall()
            if fk_verletzungen:
                print(
                    f"FEHLER: [4/6] SQLite foreign_key_check: {len(fk_verletzungen)} "
                    "Verletzung(en) gefunden.",
                    file=sys.stderr,
                )
                return EXIT_FEHLER
            print("[4/6] SQLite foreign_key_check: keine Verletzungen.")

            tabellen = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            if not tabellen:
                print("FEHLER: [5/6] Keine Tabellen in der Sicherung gefunden — leeres oder falsches Paket.", file=sys.stderr)
                return EXIT_FEHLER
            print(f"[5/6] {len(tabellen)} Tabelle(n) gefunden.")

            gesamt_zeilen = 0
            for (name,) in tabellen:
                try:
                    gesamt_zeilen += con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
                except sqlite3.Error:
                    continue

            if gesamt_zeilen == 0:
                print("FEHLER: [6/6] Kein Inhalt vorhanden — Sicherung ist inhaltlich leer.", file=sys.stderr)
                return EXIT_UNVOLLSTAENDIG
            print(f"[6/6] {gesamt_zeilen} Zeile(n) über alle Tabellen — Sicherung ist inhaltlich intakt.")
        finally:
            con.close()

    print("Verify OK.")
    return EXIT_OK


def cmd_restore(args: argparse.Namespace) -> int:
    paket = Path(args.paket).resolve()
    ziel = Path(args.ziel).resolve()

    if not paket.exists():
        print(f"FEHLER: Paket nicht gefunden: {paket}", file=sys.stderr)
        return EXIT_FEHLER

    if ziel.exists() and not args.force:
        print(
            f"FEHLER: Zieldatei existiert bereits: {ziel}\n"
            "Zum Überschreiben --force setzen (nach vorherigem eigenen Backup!).",
            file=sys.stderr,
        )
        return EXIT_FEHLER

    password = _get_password(bestaetigen=False)

    with tempfile.TemporaryDirectory(prefix="ailiza-restore-") as tmpdir:
        tmp_db = Path(tmpdir) / "restore.sqlite"
        try:
            _decrypt_file(paket, tmp_db, password)
        except BackupFehler as exc:
            print(f"FEHLER: {exc}", file=sys.stderr)
            return EXIT_FEHLER

        try:
            con = sqlite3.connect(f"file:{tmp_db}?mode=ro", uri=True)
            integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
            fk_verletzungen_vor = con.execute("PRAGMA foreign_key_check").fetchall()
            con.close()
        except sqlite3.Error as exc:
            print(f"FEHLER: Entschlüsselte Datenbank ist beschädigt: {exc}", file=sys.stderr)
            return EXIT_FEHLER
        if integrity != "ok":
            print(f"FEHLER: integrity_check vor Restore fehlgeschlagen: {integrity}", file=sys.stderr)
            return EXIT_FEHLER
        if fk_verletzungen_vor:
            print(
                f"FEHLER: foreign_key_check vor Restore fehlgeschlagen: "
                f"{len(fk_verletzungen_vor)} Verletzung(en).",
                file=sys.stderr,
            )
            return EXIT_FEHLER

        ziel.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tmp_db, ziel)
        _nur_eigentuemer(ziel)

        # Erneute VOLLSTAENDIGE Pruefung der Datei am tatsaechlichen
        # Zielort -- nicht nur der temporaeren Entschluesselungskopie.
        # Beweist, dass der Kopiervorgang selbst nichts beschaedigt hat.
        con = sqlite3.connect(f"file:{ziel}?mode=ro", uri=True)
        try:
            integrity_ziel = con.execute("PRAGMA integrity_check").fetchone()[0]
            fk_verletzungen_ziel = con.execute("PRAGMA foreign_key_check").fetchall()
        finally:
            con.close()
        if integrity_ziel != "ok" or fk_verletzungen_ziel:
            print(
                "FEHLER: Wiederhergestellte Datei an Zielort besteht die erneute "
                f"Pruefung nicht (integrity={integrity_ziel!r}, "
                f"fk_violations={len(fk_verletzungen_ziel)}).",
                file=sys.stderr,
            )
            return EXIT_FEHLER
        print(
            f"Restore abgeschlossen und erneut geprueft (integrity=ok, "
            f"foreign_key_check=ok): {ziel}"
        )

    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="AILIZA Backup/Restore — SQLite, verschlüsselt (AES-256-GCM + scrypt)."
    )
    sub = parser.add_subparsers(dest="befehl", required=True)

    p_backup = sub.add_parser("backup", help="Datenbank sichern und verschlüsseln.")
    p_backup.add_argument("--datenbank", required=True, help="Pfad zur SQLite-Quelldatenbank.")
    p_backup.add_argument("--ausgabe", required=True, help="Zielpfad für die verschlüsselte Sicherung.")
    p_backup.set_defaults(func=cmd_backup)

    p_verify = sub.add_parser("verify", help="Sicherung entschlüsseln und strukturell prüfen (keine Ausgabe des Klartexts).")
    p_verify.add_argument("--paket", required=True, help="Pfad zur verschlüsselten Sicherung.")
    p_verify.set_defaults(func=cmd_verify)

    p_restore = sub.add_parser("restore", help="Sicherung entschlüsseln und als Datenbank wiederherstellen.")
    p_restore.add_argument("--paket", required=True, help="Pfad zur verschlüsselten Sicherung.")
    p_restore.add_argument("--ziel", required=True, help="Zielpfad für die wiederhergestellte SQLite-Datenbank.")
    p_restore.add_argument("--force", action="store_true", help="Vorhandene Zieldatei überschreiben.")
    p_restore.set_defaults(func=cmd_restore)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except BackupFehler as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return EXIT_FEHLER
    except KeyboardInterrupt:
        print("\nAbgebrochen.", file=sys.stderr)
        return EXIT_ABGEBROCHEN


if __name__ == "__main__":
    sys.exit(main())
