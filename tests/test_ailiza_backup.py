"""Tests für scripts/ailiza_backup.py — Backup, Verify, Restore.

Läuft komplett gegen temporäre SQLite-Dateien, nie gegen eine echte
AILIZA-Datenbank. Prozess-Aufrufe des CLI (subprocess), damit stdin/Exit-
Codes real geprüft werden statt nur die Python-Funktionen direkt.
"""
from __future__ import annotations

import json
import os
import struct
import subprocess
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "ailiza_backup.py"


def _run(args: list[str], stdin_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin_text, capture_output=True, text=True, timeout=60,
    )


def _make_sqlite(path: Path, rows: list[str]) -> None:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")
    con.executemany("INSERT INTO t (val) VALUES (?)", [(r,) for r in rows])
    con.commit()
    con.close()


def _make_empty_sqlite(path: Path) -> None:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE t (id INTEGER)")
    con.commit()
    con.close()


@pytest.fixture
def quelle(tmp_path: Path) -> Path:
    p = tmp_path / "quelle.sqlite"
    _make_sqlite(p, ["hallo", "welt"])
    return p


def test_backup_verify_restore_roundtrip(tmp_path: Path, quelle: Path) -> None:
    paket = tmp_path / "backup.bak"
    r = _run(["backup", "--datenbank", str(quelle), "--ausgabe", str(paket)], "geheim123\n")
    assert r.returncode == 0, r.stderr
    assert paket.exists()

    r = _run(["verify", "--paket", str(paket)], "geheim123\n")
    assert r.returncode == 0, r.stderr
    assert "Verify OK." in r.stdout

    ziel = tmp_path / "restored.sqlite"
    r = _run(["restore", "--paket", str(paket), "--ziel", str(ziel)], "geheim123\n")
    assert r.returncode == 0, r.stderr

    con = sqlite3.connect(ziel)
    rows = con.execute("SELECT val FROM t ORDER BY id").fetchall()
    con.close()
    assert rows == [("hallo",), ("welt",)]


def test_verify_wrong_password_fails_closed(tmp_path: Path, quelle: Path) -> None:
    paket = tmp_path / "backup.bak"
    r = _run(["backup", "--datenbank", str(quelle), "--ausgabe", str(paket)], "richtig\n")
    assert r.returncode == 0

    r = _run(["verify", "--paket", str(paket)], "falsch\n")
    assert r.returncode == 1
    assert "passt NICHT" in r.stderr


def _make_sqlite_with_fk_violation(path: Path) -> None:
    """Elternzeile wird nach dem Einfuegen der Kindzeile geloescht, OHNE
    foreign_keys=ON zu setzen -- SQLite erlaubt das (Fremdschluessel sind
    standardmaessig nicht erzwungen), foreign_key_check muss die
    verwaiste Zeile trotzdem finden."""
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE eltern (id INTEGER PRIMARY KEY)")
    con.execute(
        "CREATE TABLE kinder (id INTEGER PRIMARY KEY, eltern_id INTEGER "
        "REFERENCES eltern(id))"
    )
    con.execute("INSERT INTO eltern (id) VALUES (1)")
    con.execute("INSERT INTO kinder (eltern_id) VALUES (1)")
    con.execute("DELETE FROM eltern WHERE id = 1")
    con.commit()
    con.close()


def test_verify_reports_foreign_key_violation_as_error(tmp_path: Path) -> None:
    """Gate 1 Backup/Restore-Finalisierung: integrity_check allein findet
    verwaiste Fremdschluessel NICHT (physische Seitenstruktur bleibt
    intakt) -- foreign_key_check muss das separat erkennen und verify
    fehlschlagen lassen, statt eine strukturell "ok", aber inhaltlich
    inkonsistente Sicherung als gut zu melden."""
    quelle = tmp_path / "fk_verletzt.sqlite"
    _make_sqlite_with_fk_violation(quelle)
    paket = tmp_path / "fk_verletzt.bak"

    r = _run(["backup", "--datenbank", str(quelle), "--ausgabe", str(paket)], "geheim\n")
    assert r.returncode == 0, r.stderr

    r = _run(["verify", "--paket", str(paket)], "geheim\n")
    assert r.returncode == 1, f"erwartet EXIT_FEHLER=1, bekam {r.returncode}: {r.stdout} {r.stderr}"
    assert "foreign_key_check" in r.stderr
    assert "Verify OK." not in r.stdout


def test_restore_refuses_database_with_foreign_key_violation(tmp_path: Path) -> None:
    quelle = tmp_path / "fk_verletzt2.sqlite"
    _make_sqlite_with_fk_violation(quelle)
    paket = tmp_path / "fk_verletzt2.bak"
    _run(["backup", "--datenbank", str(quelle), "--ausgabe", str(paket)], "geheim\n")

    ziel = tmp_path / "restored_fk.sqlite"
    r = _run(["restore", "--paket", str(paket), "--ziel", str(ziel)], "geheim\n")
    assert r.returncode == 1, f"erwartet EXIT_FEHLER=1, bekam {r.returncode}: {r.stdout} {r.stderr}"
    assert "foreign_key_check" in r.stderr
    assert not ziel.exists(), "Restore darf bei FK-Verletzung keine Zieldatei anlegen"


def test_empty_database_backup_verify_reports_incomplete_not_ok(tmp_path: Path) -> None:
    """B7-Regression: eine inhaltlich leere Sicherung darf NICHT Exit 0
    melden — sonst hält der Betreiber eine wertlose Sicherung für gut."""
    quelle = tmp_path / "leer.sqlite"
    _make_empty_sqlite(quelle)
    paket = tmp_path / "leer.bak"

    r = _run(["backup", "--datenbank", str(quelle), "--ausgabe", str(paket)], "geheim\n")
    assert r.returncode == 0

    r = _run(["verify", "--paket", str(paket)], "geheim\n")
    assert r.returncode == 2, f"erwartet EXIT_UNVOLLSTAENDIG=2, bekam {r.returncode}: {r.stdout} {r.stderr}"
    assert "Kein Inhalt" in r.stderr


def test_backup_missing_source_fails(tmp_path: Path) -> None:
    r = _run([
        "backup", "--datenbank", str(tmp_path / "existiert-nicht.sqlite"),
        "--ausgabe", str(tmp_path / "out.bak"),
    ], "geheim\n")
    assert r.returncode == 1
    assert "nicht gefunden" in r.stderr


def test_restore_refuses_overwrite_without_force(tmp_path: Path, quelle: Path) -> None:
    paket = tmp_path / "backup.bak"
    _run(["backup", "--datenbank", str(quelle), "--ausgabe", str(paket)], "geheim\n")

    ziel = tmp_path / "ziel.sqlite"
    ziel.write_text("vorhandene Datei — darf nicht verlorengehen")

    r = _run(["restore", "--paket", str(paket), "--ziel", str(ziel)], "geheim\n")
    assert r.returncode == 1
    assert "existiert bereits" in r.stderr
    assert ziel.read_text() == "vorhandene Datei — darf nicht verlorengehen"


def test_restore_with_force_overwrites(tmp_path: Path, quelle: Path) -> None:
    paket = tmp_path / "backup.bak"
    _run(["backup", "--datenbank", str(quelle), "--ausgabe", str(paket)], "geheim\n")

    ziel = tmp_path / "ziel.sqlite"
    ziel.write_text("wird ueberschrieben")

    r = _run(["restore", "--paket", str(paket), "--ziel", str(ziel), "--force"], "geheim\n")
    assert r.returncode == 0
    con = sqlite3.connect(ziel)
    assert con.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 2


def test_backup_captures_wal_committed_writes(tmp_path: Path) -> None:
    """SQLite-Backup-API statt Dateikopie: committed-Daten, die noch in der
    -wal-Datei liegen, müssen mitgesichert werden."""
    quelle = tmp_path / "wal.sqlite"
    con = sqlite3.connect(quelle)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")
    con.execute("INSERT INTO t (val) VALUES ('a')")
    con.commit()
    con.execute("INSERT INTO t (val) VALUES ('b')")
    con.commit()
    con.close()

    paket = tmp_path / "wal.bak"
    r = _run(["backup", "--datenbank", str(quelle), "--ausgabe", str(paket)], "geheim\n")
    assert r.returncode == 0, r.stderr

    ziel = tmp_path / "restored.sqlite"
    r = _run(["restore", "--paket", str(paket), "--ziel", str(ziel)], "geheim\n")
    assert r.returncode == 0
    con = sqlite3.connect(ziel)
    rows = con.execute("SELECT val FROM t ORDER BY id").fetchall()
    con.close()
    assert rows == [("a",), ("b",)]


@pytest.mark.skipif(os.name == "nt", reason="Windows schuetzt Dateien per DACL statt POSIX-Modusbits")
def test_backup_file_has_no_group_or_other_permissions(tmp_path: Path, quelle: Path) -> None:
    paket = tmp_path / "backup.bak"
    r = _run(["backup", "--datenbank", str(quelle), "--ausgabe", str(paket)], "geheim\n")
    assert r.returncode == 0
    mode = paket.stat().st_mode & 0o777
    assert mode == 0o600, f"erwartet 0600, bekam {oct(mode)}"


class TestKdfBoundsRejectManipulatedHeader:
    """Mutation-getesteter Kernpunkt aus PR #80: ohne diese Grenzen kann ein
    manipuliertes Paket eine teure Schlüsselableitung erzwingen (DoS)."""

    def _make_package(self, tmp_path: Path, quelle: Path, header_patch: dict) -> Path:
        paket = tmp_path / "backup.bak"
        r = _run(["backup", "--datenbank", str(quelle), "--ausgabe", str(paket)], "geheim\n")
        assert r.returncode == 0

        raw = paket.read_bytes()
        magic = raw[:9]
        header_len = struct.unpack(">H", raw[9:11])[0]
        header = json.loads(raw[11:11 + header_len].decode("utf-8"))
        rest = raw[11 + header_len:]

        header.update(header_patch)
        new_header_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
        new_len = struct.pack(">H", len(new_header_bytes))

        manipuliert = tmp_path / "manipuliert.bak"
        manipuliert.write_bytes(magic + new_len + new_header_bytes + rest)
        return manipuliert

    def test_n_too_large_rejected(self, tmp_path: Path, quelle: Path) -> None:
        paket = self._make_package(tmp_path, quelle, {"n": 2 ** 20})
        r = _run(["verify", "--paket", str(paket)], "geheim\n")
        assert r.returncode == 1
        assert "KDF-Parameter" in r.stderr

    def test_n_not_power_of_two_rejected(self, tmp_path: Path, quelle: Path) -> None:
        paket = self._make_package(tmp_path, quelle, {"n": 2 ** 15 + 1})
        r = _run(["verify", "--paket", str(paket)], "geheim\n")
        assert r.returncode == 1
        assert "KDF-Parameter" in r.stderr

    def test_r_too_large_rejected(self, tmp_path: Path, quelle: Path) -> None:
        paket = self._make_package(tmp_path, quelle, {"r": 999})
        r = _run(["verify", "--paket", str(paket)], "geheim\n")
        assert r.returncode == 1
        assert "KDF-Parameter" in r.stderr

    def test_p_too_large_rejected(self, tmp_path: Path, quelle: Path) -> None:
        paket = self._make_package(tmp_path, quelle, {"p": 999})
        r = _run(["verify", "--paket", str(paket)], "geheim\n")
        assert r.returncode == 1
        assert "KDF-Parameter" in r.stderr

    def test_excessive_memory_estimate_rejected(self, tmp_path: Path, quelle: Path) -> None:
        # n=2**17 (max erlaubt einzeln) UND r=32 (max erlaubt einzeln)
        # zusammen sprengen die 256-MiB-Speichergrenze.
        paket = self._make_package(tmp_path, quelle, {"n": 2 ** 17, "r": 32})
        r = _run(["verify", "--paket", str(paket)], "geheim\n")
        assert r.returncode == 1
        assert "Speicher" in r.stderr

    def test_bounds_checked_before_key_derivation(self, tmp_path: Path, quelle: Path, monkeypatch) -> None:
        """Direkter Funktionsaufruf: _read_header muss bei ungültigen
        Parametern werfen, BEVOR _derive_key je aufgerufen wird."""
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        import importlib
        import ailiza_backup
        importlib.reload(ailiza_backup)

        called = {"derive": False}

        def _spy(*a, **kw):
            called["derive"] = True
            raise AssertionError("Schlüsselableitung darf bei ungültigen KDF-Parametern nie aufgerufen werden.")

        monkeypatch.setattr(ailiza_backup, "_derive_key", _spy)

        with pytest.raises(ailiza_backup.BackupFehler):
            ailiza_backup._pruefe_kdf_parameter(2 ** 20, 8, 1)
        assert called["derive"] is False


def test_password_never_accepted_as_cli_argument() -> None:
    """Statische Prüfung: keiner der Subparser darf ein --passwort-Argument
    definieren — Passwörter als Argument landen in der Prozessliste."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import importlib
    import ailiza_backup
    importlib.reload(ailiza_backup)

    parser = None
    import argparse as _argparse
    import inspect
    src = inspect.getsource(ailiza_backup)
    assert "--passwort" not in src and "--password" not in src


def test_corrupted_magic_bytes_rejected(tmp_path: Path, quelle: Path) -> None:
    paket = tmp_path / "backup.bak"
    _run(["backup", "--datenbank", str(quelle), "--ausgabe", str(paket)], "geheim\n")
    raw = bytearray(paket.read_bytes())
    raw[0:9] = b"NICHTGUT!"
    kaputt = tmp_path / "kaputt.bak"
    kaputt.write_bytes(bytes(raw))

    r = _run(["verify", "--paket", str(kaputt)], "geheim\n")
    assert r.returncode == 1
    assert "Magic-Byte" in r.stderr


def test_path_traversal_in_archive_rejected(tmp_path: Path) -> None:
    """_safe_extract ist für ein künftiges Mehrdatei-Format vorbereitet —
    dieser Test hält den Schutz auch dann scharf, wenn er noch nicht vom
    Hauptpfad genutzt wird (Mutation-getesteter Fund aus PR #80)."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import importlib
    import ailiza_backup
    importlib.reload(ailiza_backup)
    import tarfile

    boese_pfade = ["../../../etc/passwd", "/etc/passwd"]
    for boese_pfad in boese_pfade:
        archiv = tmp_path / "boese.tar"
        with tarfile.open(archiv, "w") as tar:
            info = tarfile.TarInfo(name=boese_pfad)
            data = b"nutzlast"
            info.size = len(data)
            import io
            tar.addfile(info, io.BytesIO(data))

        zielverzeichnis = tmp_path / "extrahiert"
        zielverzeichnis.mkdir(exist_ok=True)
        with pytest.raises(ailiza_backup.BackupFehler):
            ailiza_backup._safe_extract(archiv, zielverzeichnis)
        archiv.unlink()
