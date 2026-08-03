"""Tests fuer scripts/ailiza_backup.py — Sicherung, Wiederherstellung, Abnahme.

Warum diese Datei existiert
---------------------------
Die Nachweise fuer PR #80 wurden zunaechst als Einzelaufrufe in der Shell
gefuehrt. Das ist nicht reproduzierbar: ein spaeteres Refactoring koennte
den Schutz still aushebeln, ohne dass es auffaellt. Insbesondere die
sicherheitsrelevanten Zusicherungen -- keine Ausgabe von Nutzerinhalten,
keine Geheimnisse in stdout/stderr, Ablehnung bei falschem Schluessel --
muessen bei jedem Testlauf erneut geprueft werden.

Alle Tests laufen gegen temporaere SQLite-Wegwerfdatenbanken. Es wird
niemals eine echte Datenbank, eine echte .env oder ein Docker-Volume
angefasst. Der Docker-Pfad selbst ist hier nicht testbar (kein Daemon in
CI) -- geprueft wird der `--db-path`-Pfad, der im Container mit denselben
Argumenten aufgerufen wird.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKRIPT = REPO_ROOT / "scripts" / "ailiza_backup.py"

# Bewusst auffaellige Testwerte: sie muessen in KEINER Ausgabe erscheinen.
TEST_SECRET = "testschluessel-mindestens-32-zeichen-lang-abc"
TEST_PASSWORT = "testpasswort-fuer-das-paket"
TEST_TITEL = "Krankenakte Musterfrau"
TEST_INHALT = "DIAGNOSE-GEHEIM-4711"

pytestmark = pytest.mark.skipif(
    not SKRIPT.exists(), reason="scripts/ailiza_backup.py nicht vorhanden"
)


def _lauf(args: list[str], *, passwort: str | None = TEST_PASSWORT
          ) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["AILIZA_SECRET_KEY"] = "irrelevant-fuer-das-skript-aber-lang-genug"
    if passwort is not None:
        env["AILIZA_BACKUP_PASSWORD"] = passwort
    else:
        env.pop("AILIZA_BACKUP_PASSWORD", None)
    return subprocess.run(
        [sys.executable, str(SKRIPT), *args],
        cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=180,
    )


def _datenbank_mit_inhalt(pfad: Path, *, wal: bool = True) -> None:
    """Legt eine AILIZA-Datenbank mit einem verschluesselten Chat an."""
    pfad.parent.mkdir(parents=True, exist_ok=True)
    code = (
        "from apps.backend.database import init_db, save_user_chat\n"
        "init_db()\n"
        f"save_user_chat('c1','default','karo',messages=[{{'role':'user',"
        f"'content':{TEST_INHALT!r}}}],title={TEST_TITEL!r})\n"
    )
    env = dict(os.environ,
               AILIZA_SECRET_KEY=TEST_SECRET,
               AILIZA_DATABASE_URL=f"sqlite:///{pfad}")
    res = subprocess.run([sys.executable, "-c", code], cwd=str(REPO_ROOT),
                         env=env, capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stdout + res.stderr
    if wal:
        con = sqlite3.connect(str(pfad))
        con.execute("PRAGMA journal_mode=WAL")
        con.close()


def _env_datei(pfad: Path, schluessel: str = TEST_SECRET) -> Path:
    pfad.write_text(f"AILIZA_SECRET_KEY={schluessel}\nGROQ_API_KEY=\n",
                    encoding="utf-8")
    return pfad


def _paket(ordner: Path) -> Path:
    treffer = sorted(ordner.glob("*.ailiza-backup"))
    assert treffer, f"Kein Sicherungspaket in {ordner}"
    return treffer[0]


@pytest.fixture
def gesichert(tmp_path):
    """Eine fertige, abnahmefaehige Sicherung samt Quelldaten."""
    db = tmp_path / "daten" / "ailiza.sqlite"
    _datenbank_mit_inhalt(db)
    env = _env_datei(tmp_path / ".env")
    ziel = tmp_path / "sicherungen"
    res = _lauf(["backup", "--db-path", str(db), "--env-file", str(env),
                 "--out", str(ziel)])
    assert res.returncode == 0, res.stdout + res.stderr
    return {"db": db, "env": env, "archiv": _paket(ziel),
            "ausgabe": res.stdout + res.stderr, "tmp": tmp_path}


# ---------------------------------------------------------------------------
# Grundfunktion
# ---------------------------------------------------------------------------

def test_backup_und_abnahme_laufen_durch(gesichert):
    res = _lauf(["verify", "--archive", str(gesichert["archiv"])])
    assert res.returncode == 0, res.stdout + res.stderr
    assert "ABNAHME BESTANDEN" in res.stdout


def test_sicherung_ist_eine_einzelne_datei_ohne_wal_reste(gesichert):
    """Die Backup-API erzeugt einen in sich geschlossenen Stand. Laegen
    -wal/-shm daneben, waere die Sicherung ohne sie unvollstaendig."""
    ordner = gesichert["archiv"].parent
    reste = [p.name for p in ordner.iterdir() if p.suffix in ("-wal", "-shm")]
    assert not reste, f"Unerwartete Begleitdateien: {reste}"


def test_keine_dateikopie_sondern_backup_api():
    """Struktureller Schutz: eine spaetere Umstellung auf shutil.copy der
    laufenden Datenbank waere ein stiller Datenintegritaets-Rueckschritt."""
    quelltext = SKRIPT.read_text(encoding="utf-8")
    assert ".backup(" in quelltext, "SQLite-Backup-API wird nicht verwendet"


# ---------------------------------------------------------------------------
# Keine Ausgabe von Inhalten oder Geheimnissen
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("geheim", [
    TEST_TITEL, TEST_INHALT, TEST_SECRET, TEST_PASSWORT, "Musterfrau",
])
def test_backup_gibt_keine_inhalte_oder_geheimnisse_aus(gesichert, geheim):
    assert geheim not in gesichert["ausgabe"], (
        f"{geheim!r} steht in der Ausgabe von `backup`"
    )


@pytest.mark.parametrize("geheim", [
    TEST_TITEL, TEST_INHALT, TEST_SECRET, TEST_PASSWORT, "Musterfrau",
])
def test_abnahme_gibt_keine_inhalte_oder_geheimnisse_aus(gesichert, geheim):
    res = _lauf(["verify", "--archive", str(gesichert["archiv"])])
    gesamt = res.stdout + res.stderr
    assert geheim not in gesamt, f"{geheim!r} steht in der Ausgabe von `verify`"


def test_abnahme_meldet_erfolg_ohne_klartext(gesichert):
    """Auch eine gekuerzte Vorschau des Chattitels waere ein Datenleck."""
    res = _lauf(["verify", "--archive", str(gesichert["archiv"])])
    assert "Entschluesselung geprueft" in res.stdout
    # kein Bruchstueck des Titels, auch nicht die ersten Zeichen
    assert TEST_TITEL[:8] not in res.stdout


def test_fehlerpfad_gibt_keine_geheimnisse_aus(gesichert):
    """Auch im Fehlerfall darf nichts durchsickern -- weder aus einer
    Stapelverfolgung des Unterprozesses noch aus der Fehlermeldung."""
    res = _lauf(["verify", "--archive", str(gesichert["archiv"])],
                passwort="ein-voellig-falsches-passwort")
    gesamt = res.stdout + res.stderr
    assert res.returncode != 0
    for geheim in (TEST_TITEL, TEST_INHALT, TEST_SECRET, TEST_PASSWORT):
        assert geheim not in gesamt


def test_passwort_wird_nicht_als_argument_uebergeben():
    """Befehlszeilenargumente sind in der Prozessliste sichtbar."""
    quelltext = SKRIPT.read_text(encoding="utf-8")
    assert "--password" not in quelltext
    assert "--passwort" not in quelltext


def test_startskript_uebergibt_passwort_nicht_per_docker_env():
    """Werte aus `docker run -e` erscheinen dauerhaft in `docker inspect`."""
    cmd = REPO_ROOT / "backup-local.cmd"
    if not cmd.exists():
        pytest.skip("backup-local.cmd nicht vorhanden")
    inhalt = cmd.read_text(encoding="utf-8", errors="replace")
    assert "-e AILIZA_BACKUP_PASSWORD" not in inhalt
    assert "-e AILIZA_SECRET_KEY" not in inhalt
    assert "--env AILIZA_" not in inhalt


# ---------------------------------------------------------------------------
# Ablehnung: falsches Passwort, falscher Schluessel, Manipulation
# ---------------------------------------------------------------------------

def test_falsches_passwort_wird_abgelehnt(gesichert):
    res = _lauf(["verify", "--archive", str(gesichert["archiv"])],
                passwort="falsches-passwort-123456")
    assert res.returncode == 1


def test_falscher_schluessel_im_paket_wird_abgelehnt(tmp_path):
    """Der heikelste Fall: Pruefsumme stimmt, Datenbank ist unversehrt,
    Chats sind vorhanden -- und die Inhalte waeren trotzdem fuer immer
    unlesbar, weil die .env aus einer anderen Installation stammt."""
    db = tmp_path / "daten" / "ailiza.sqlite"
    _datenbank_mit_inhalt(db)
    falsche_env = _env_datei(tmp_path / "falsch.env",
                             "ein-ganz-anderer-schluessel-mit-32-zeichen")
    ziel = tmp_path / "sicherungen"
    res = _lauf(["backup", "--db-path", str(db), "--env-file",
                 str(falsche_env), "--out", str(ziel)])
    assert res.returncode == 0, "Die Sicherung selbst gelingt -- das ist die Falle"

    res = _lauf(["verify", "--archive", str(_paket(ziel))])
    assert res.returncode == 1, "Falscher Schluessel wurde NICHT erkannt"
    assert "passt NICHT" in res.stderr


def test_manipuliertes_paket_wird_erkannt(gesichert):
    archiv = gesichert["archiv"]
    daten = bytearray(archiv.read_bytes())
    daten[len(daten) // 2] ^= 0xFF
    archiv.write_bytes(bytes(daten))
    res = _lauf(["verify", "--archive", str(archiv)])
    assert res.returncode == 1


def test_manipulation_wird_auch_ohne_pruefsummendatei_erkannt(gesichert):
    """Ein Angreifer koennte Paket UND .sha256 gemeinsam austauschen. Die
    Erkennung muss deshalb aus der AEAD-Authentifizierung kommen, nicht aus
    der Pruefsummendatei."""
    archiv = gesichert["archiv"]
    sidecar = archiv.with_suffix(archiv.suffix + ".sha256")
    if sidecar.exists():
        sidecar.unlink()
    daten = bytearray(archiv.read_bytes())
    daten[-20] ^= 0xFF
    archiv.write_bytes(bytes(daten))
    res = _lauf(["verify", "--archive", str(archiv)])
    assert res.returncode == 1, "AEAD-Authentifizierung greift nicht"


def test_fremde_datei_wird_als_kein_paket_erkannt(tmp_path):
    fremd = tmp_path / "beliebig.ailiza-backup"
    fremd.write_bytes(b"kein AILIZA-Paket")
    res = _lauf(["verify", "--archive", str(fremd)])
    assert res.returncode == 1


# ---------------------------------------------------------------------------
# Kryptografie: etabliertes AEAD, zufaelliger Salt, eindeutiger Nonce
# ---------------------------------------------------------------------------

def test_etabliertes_aead_und_passwortableitung():
    quelltext = SKRIPT.read_text(encoding="utf-8")
    assert "AESGCM" in quelltext, "Kein etabliertes AEAD-Verfahren"
    assert "Scrypt" in quelltext, "Keine etablierte Passwortableitung"
    assert "os.urandom" in quelltext, "Kein kryptografischer Zufall"


def test_salt_und_nonce_sind_je_sicherung_verschieden(tmp_path):
    """Ein wiederverwendeter Nonce bricht die Sicherheit von AES-GCM."""
    db = tmp_path / "daten" / "ailiza.sqlite"
    _datenbank_mit_inhalt(db)
    env = _env_datei(tmp_path / ".env")
    koepfe = []
    for i in range(2):
        ziel = tmp_path / f"s{i}"
        res = _lauf(["backup", "--db-path", str(db), "--env-file", str(env),
                     "--out", str(ziel)])
        assert res.returncode == 0, res.stdout + res.stderr
        # Kennung(9) + Salt(16) + Nonce(12)
        koepfe.append(_paket(ziel).read_bytes()[9:37])
    assert koepfe[0] != koepfe[1], "Salt/Nonce wiederholen sich"


def test_paket_enthaelt_keinen_klartext(gesichert):
    """Weder Inhalt noch Schluessel duerfen im Paket auffindbar sein."""
    roh = gesichert["archiv"].read_bytes()
    for geheim in (TEST_TITEL, TEST_INHALT, TEST_SECRET):
        assert geheim.encode() not in roh


# ---------------------------------------------------------------------------
# Dateirechte
# ---------------------------------------------------------------------------

@pytest.mark.skipif(os.name == "nt", reason="POSIX-Rechte; Windows nutzt icacls")
def test_paket_nur_fuer_eigentuemerin_lesbar(gesichert):
    assert gesichert["archiv"].stat().st_mode & 0o077 == 0, (
        "Sicherungspaket ist fuer andere Konten lesbar"
    )


@pytest.mark.skipif(os.name == "nt", reason="POSIX-Rechte; Windows nutzt icacls")
def test_wiederhergestellte_schluesseldatei_nur_fuer_eigentuemerin(gesichert, tmp_path):
    ziel = tmp_path / "neu" / "ailiza.sqlite"
    res = _lauf(["restore", "--archive", str(gesichert["archiv"]),
                 "--to", str(ziel)])
    assert res.returncode == 0, res.stdout + res.stderr
    env_datei = ziel.parent / "env-aus-sicherung"
    assert env_datei.exists()
    assert env_datei.stat().st_mode & 0o077 == 0, (
        "Schluesseldatei ist fuer andere Konten lesbar"
    )


def test_startskript_setzt_ntfs_rechte():
    """Unter Windows sind NTFS-Rechte massgeblich; chmod wirkt dort nicht."""
    cmd = REPO_ROOT / "backup-local.cmd"
    if not cmd.exists():
        pytest.skip("backup-local.cmd nicht vorhanden")
    inhalt = cmd.read_text(encoding="utf-8", errors="replace")
    assert "icacls" in inhalt
    assert "/inheritance:r" in inhalt, "Geerbte Rechte werden nicht entfernt"


# ---------------------------------------------------------------------------
# Wiederherstellung
# ---------------------------------------------------------------------------

def test_restore_in_leeres_ziel(gesichert, tmp_path):
    ziel = tmp_path / "neu" / "ailiza.sqlite"
    res = _lauf(["restore", "--archive", str(gesichert["archiv"]),
                 "--to", str(ziel)])
    assert res.returncode == 0, res.stdout + res.stderr
    assert ziel.exists()
    con = sqlite3.connect(f"file:{ziel}?mode=ro", uri=True)
    try:
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert con.execute("SELECT count(*) FROM user_chats").fetchone()[0] == 1
    finally:
        con.close()


def test_restore_ueberschreibt_nicht_ohne_force(gesichert, tmp_path):
    ziel = tmp_path / "neu" / "ailiza.sqlite"
    assert _lauf(["restore", "--archive", str(gesichert["archiv"]),
                  "--to", str(ziel)]).returncode == 0
    res = _lauf(["restore", "--archive", str(gesichert["archiv"]),
                 "--to", str(ziel)])
    assert res.returncode == 1
    assert "existiert bereits" in res.stderr


def test_force_sichert_bisherigen_stand_vorher(gesichert, tmp_path):
    """Auch ein bewusstes Ueberschreiben muss umkehrbar bleiben."""
    ziel = tmp_path / "neu" / "ailiza.sqlite"
    assert _lauf(["restore", "--archive", str(gesichert["archiv"]),
                  "--to", str(ziel)]).returncode == 0
    res = _lauf(["restore", "--archive", str(gesichert["archiv"]),
                 "--to", str(ziel), "--force"])
    assert res.returncode == 0, res.stdout + res.stderr
    vorher = list(ziel.parent.glob("*_vor-restore_*.sqlite"))
    assert vorher, "Kein Sicherungsstand vor dem Ueberschreiben angelegt"
    con = sqlite3.connect(f"file:{vorher[0]}?mode=ro", uri=True)
    try:
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        con.close()


def test_entschluesselung_nach_restore(gesichert, tmp_path):
    """Abnahmekriterium: nach der Wiederherstellung muss der Inhalt mit dem
    mitgesicherten Schluessel lesbar sein. Der Klartext bleibt im Test und
    wird nicht ausgegeben."""
    ziel = tmp_path / "neu" / "ailiza.sqlite"
    assert _lauf(["restore", "--archive", str(gesichert["archiv"]),
                  "--to", str(ziel)]).returncode == 0
    code = (
        "from apps.backend.database import list_user_chats\n"
        "r = list_user_chats('default','karo')\n"
        f"assert r[0]['title'] == {TEST_TITEL!r}\n"
        f"assert r[0]['messages'][0]['content'] == {TEST_INHALT!r}\n"
        "print('LESBAR')\n"
    )
    env = dict(os.environ, AILIZA_SECRET_KEY=TEST_SECRET,
               AILIZA_DATABASE_URL=f"sqlite:///{ziel}")
    res = subprocess.run([sys.executable, "-c", code], cwd=str(REPO_ROOT),
                         env=env, capture_output=True, text=True, timeout=120)
    assert "LESBAR" in res.stdout, res.stdout + res.stderr


# ---------------------------------------------------------------------------
# WAL und Randfaelle
# ---------------------------------------------------------------------------

def test_sicherung_bei_gleichzeitigem_schreibvorgang(tmp_path):
    db = tmp_path / "daten" / "ailiza.sqlite"
    _datenbank_mit_inhalt(db)
    env = _env_datei(tmp_path / ".env")
    schreiber = sqlite3.connect(str(db))
    schreiber.execute("CREATE TABLE parallel(x)")
    schreiber.execute("INSERT INTO parallel VALUES ('waehrend der sicherung')")
    schreiber.commit()
    try:
        res = _lauf(["backup", "--db-path", str(db), "--env-file", str(env),
                     "--out", str(tmp_path / "s")])
        assert res.returncode == 0, res.stdout + res.stderr
    finally:
        schreiber.close()


def test_nur_im_wal_liegende_daten_sind_enthalten(tmp_path):
    """Der gefaehrlichste Fall: waeren nicht uebertragene Aenderungen nicht
    in der Sicherung, gingen die letzten Daten unbemerkt verloren -- und die
    Sicherung saehe trotzdem fehlerfrei aus."""
    db = tmp_path / "daten" / "ailiza.sqlite"
    _datenbank_mit_inhalt(db)
    con = sqlite3.connect(str(db))
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE spaet(x)")
    con.execute("INSERT INTO spaet VALUES ('nur im wal')")
    con.commit()
    assert (db.parent / (db.name + "-wal")).exists(), "Vorbedingung: WAL aktiv"

    env = _env_datei(tmp_path / ".env")
    ziel = tmp_path / "s"
    res = _lauf(["backup", "--db-path", str(db), "--env-file", str(env),
                 "--out", str(ziel)])
    con.close()
    assert res.returncode == 0, res.stdout + res.stderr

    wieder = tmp_path / "neu" / "ailiza.sqlite"
    assert _lauf(["restore", "--archive", str(_paket(ziel)),
                  "--to", str(wieder)]).returncode == 0
    pruef = sqlite3.connect(f"file:{wieder}?mode=ro", uri=True)
    try:
        assert pruef.execute("SELECT x FROM spaet").fetchone()[0] == "nur im wal"
    finally:
        pruef.close()


def test_pfad_mit_leerzeichen_und_umlauten(tmp_path):
    ordner = tmp_path / "Karo Müller" / "AILIZA Daten"
    db = ordner / "ailiza.sqlite"
    _datenbank_mit_inhalt(db)
    env = _env_datei(ordner / ".env")
    ziel = tmp_path / "Sicherungen für Karo"
    res = _lauf(["backup", "--db-path", str(db), "--env-file", str(env),
                 "--out", str(ziel)])
    assert res.returncode == 0, res.stdout + res.stderr
    assert _lauf(["verify", "--archive", str(_paket(ziel))]).returncode == 0


def test_quelle_schreibgeschuetzt_lesbar(tmp_path):
    """Im Container wird /data schreibgeschuetzt eingebunden."""
    db = tmp_path / "daten" / "ailiza.sqlite"
    _datenbank_mit_inhalt(db)
    env = _env_datei(tmp_path / ".env")
    os.chmod(db.parent, 0o555)
    try:
        res = _lauf(["backup", "--db-path", str(db), "--env-file", str(env),
                     "--out", str(tmp_path / "s")])
        assert res.returncode == 0, res.stdout + res.stderr
    finally:
        os.chmod(db.parent, 0o755)


# ---------------------------------------------------------------------------
# Fehlende Voraussetzungen -> verstaendlicher Abbruch statt Absturz
# ---------------------------------------------------------------------------

def test_fehlende_env_bricht_verstaendlich_ab(tmp_path):
    """Ohne Schluessel waere die Sicherung wertlos -- lieber gar keine."""
    db = tmp_path / "daten" / "ailiza.sqlite"
    _datenbank_mit_inhalt(db)
    res = _lauf(["backup", "--db-path", str(db),
                 "--env-file", str(tmp_path / "gibtsnicht.env"),
                 "--out", str(tmp_path / "s")])
    assert res.returncode == 1
    assert "Traceback" not in res.stderr, "Stapelverfolgung statt Klartextmeldung"


def test_fehlende_datenbank_bricht_verstaendlich_ab(tmp_path):
    env = _env_datei(tmp_path / ".env")
    res = _lauf(["backup", "--db-path", str(tmp_path / "gibtsnicht.sqlite"),
                 "--env-file", str(env), "--out", str(tmp_path / "s")])
    assert res.returncode == 1
    assert "Traceback" not in res.stderr


def test_fehlendes_paket_bricht_verstaendlich_ab(tmp_path):
    res = _lauf(["verify", "--archive", str(tmp_path / "gibtsnicht.ailiza-backup")])
    assert res.returncode == 1
    assert "Traceback" not in res.stderr
