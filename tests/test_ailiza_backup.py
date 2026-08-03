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
    """Ruft das Skript auf. Das Passwort geht ueber die Standardeingabe --
    das Skript nimmt es bewusst weder als Argument noch als Umgebungsvariable
    entgegen."""
    env = dict(os.environ)
    env["AILIZA_SECRET_KEY"] = "irrelevant-fuer-das-skript-aber-lang-genug"
    env.pop("AILIZA_BACKUP_PASSWORD", None)
    return subprocess.run(
        [sys.executable, str(SKRIPT), *args],
        cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=300,
        input=("" if passwort is None else passwort + "\n"),
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


def _kopf_lesen(archiv: Path) -> tuple[bytes, int, dict, bytes]:
    """Zerlegt ein Paket: (Kennung, Kopflaenge, Kopf-JSON, Restbytes)."""
    import json as _json
    roh = archiv.read_bytes()
    magic = roh[:9]
    kopf_len = int.from_bytes(roh[9:11], "big")
    kopf = _json.loads(roh[11:11 + kopf_len].decode("utf-8"))
    return magic, kopf_len, kopf, roh[11 + kopf_len:]


def _kopf_schreiben(archiv: Path, kopf: dict, rest: bytes,
                    magic: bytes = b"AILIZABK2") -> None:
    import json as _json
    kopf_bytes = _json.dumps(kopf, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
    archiv.write_bytes(
        magic + len(kopf_bytes).to_bytes(2, "big") + kopf_bytes + rest
    )


def test_salt_und_nonce_sind_je_sicherung_verschieden(tmp_path):
    """Ein wiederverwendeter Nonce bricht die Sicherheit von AES-GCM."""
    db = tmp_path / "daten" / "ailiza.sqlite"
    _datenbank_mit_inhalt(db)
    env = _env_datei(tmp_path / ".env")
    salts, nonces = [], []
    for i in range(2):
        ziel = tmp_path / f"s{i}"
        res = _lauf(["backup", "--db-path", str(db), "--env-file", str(env),
                     "--out", str(ziel)])
        assert res.returncode == 0, res.stdout + res.stderr
        _, _, kopf, rest = _kopf_lesen(_paket(ziel))
        salts.append(kopf["salt"])
        nonces.append(rest[:12])
    assert salts[0] != salts[1], "Salt wiederholt sich"
    assert nonces[0] != nonces[1], "Nonce wiederholt sich"


def test_kopf_enthaelt_alle_ableitungsparameter(gesichert):
    """Ohne die Parameter im Paket waere nicht nachvollziehbar, womit es
    erzeugt wurde -- und ein Wechsel der Vorgaben machte alte Pakete
    unlesbar."""
    _, _, kopf, _ = _kopf_lesen(gesichert["archiv"])
    for feld in ("v", "kdf", "n", "r", "p", "salt"):
        assert feld in kopf, f"Kopffeld {feld} fehlt"
    assert kopf["kdf"] == "scrypt"


# --- Mutationstests: jedes Kopffeld muss authentifiziert sein -------------

@pytest.mark.parametrize("feld,neuer_wert", [
    ("v", 1),          # Formatversion herabstufen
    ("kdf", "pbkdf2"), # Verfahren austauschen
    ("n", 2 ** 14),    # Ableitung schwaechen
    ("r", 1),
    ("p", 2),
])
def test_manipuliertes_kopffeld_wird_erkannt(gesichert, feld, neuer_wert):
    """Waeren die Parameter nicht als AAD authentifiziert, koennte ein
    Angreifer sie durch schwaechere ersetzen und das Paket bliebe
    verwendbar."""
    magic, _, kopf, rest = _kopf_lesen(gesichert["archiv"])
    kopf[feld] = neuer_wert
    _kopf_schreiben(gesichert["archiv"], kopf, rest, magic)
    res = _lauf(["verify", "--archive", str(gesichert["archiv"])])
    assert res.returncode == 1, (
        f"Manipulation von {feld} wurde NICHT erkannt: {res.stdout}"
    )


def test_manipuliertes_salt_wird_erkannt(gesichert):
    import base64 as _b64
    magic, _, kopf, rest = _kopf_lesen(gesichert["archiv"])
    roh = bytearray(_b64.b64decode(kopf["salt"]))
    roh[0] ^= 0xFF
    kopf["salt"] = _b64.b64encode(bytes(roh)).decode("ascii")
    _kopf_schreiben(gesichert["archiv"], kopf, rest, magic)
    assert _lauf(["verify", "--archive", str(gesichert["archiv"])]).returncode == 1


def test_manipulierte_dateikennung_wird_erkannt(gesichert):
    magic, _, kopf, rest = _kopf_lesen(gesichert["archiv"])
    _kopf_schreiben(gesichert["archiv"], kopf, rest, b"AILIZABK9")
    assert _lauf(["verify", "--archive", str(gesichert["archiv"])]).returncode == 1


def test_zusaetzliches_kopffeld_wird_erkannt(gesichert):
    """Auch ein hinzugefuegtes Feld aendert die AAD."""
    magic, _, kopf, rest = _kopf_lesen(gesichert["archiv"])
    kopf["zusatz"] = "x"
    _kopf_schreiben(gesichert["archiv"], kopf, rest, magic)
    assert _lauf(["verify", "--archive", str(gesichert["archiv"])]).returncode == 1


# --- Schranken gegen ueberzogene Ableitungsparameter ----------------------

@pytest.mark.parametrize("feld,wert", [
    ("n", 2 ** 30),   # wuerde ~1 TiB Arbeitsspeicher anfordern
    ("n", 2 ** 13),   # zu schwach
    ("n", 30000),     # keine Zweierpotenz
    ("r", 4096),
    ("p", 9999),
])
def test_ueberzogene_ableitungsparameter_werden_vor_der_ableitung_abgelehnt(
        gesichert, feld, wert):
    """Ohne Schranken koennte ein praepariertes Paket allein durch das
    Oeffnen beliebig viel Rechenzeit und Speicher binden."""
    magic, _, kopf, rest = _kopf_lesen(gesichert["archiv"])
    kopf[feld] = wert
    _kopf_schreiben(gesichert["archiv"], kopf, rest, magic)
    res = _lauf(["verify", "--archive", str(gesichert["archiv"])])
    assert res.returncode == 1
    assert "Traceback" not in res.stderr


def test_ueberlanger_kopf_wird_abgelehnt(gesichert):
    magic, _, kopf, rest = _kopf_lesen(gesichert["archiv"])
    kopf["fuellung"] = "A" * 8000
    _kopf_schreiben(gesichert["archiv"], kopf, rest, magic)
    res = _lauf(["verify", "--archive", str(gesichert["archiv"])])
    assert res.returncode == 1


def test_abgeschnittenes_paket_wird_abgelehnt(gesichert):
    roh = gesichert["archiv"].read_bytes()
    gesichert["archiv"].write_bytes(roh[:15])
    res = _lauf(["verify", "--archive", str(gesichert["archiv"])])
    assert res.returncode == 1
    assert "Traceback" not in res.stderr


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


# ---------------------------------------------------------------------------
# Archiv-Angriffe: Pfadausbruch, Verknuepfungen, Bomben
# ---------------------------------------------------------------------------

def _paket_mit_eintraegen(tmp_path: Path, bauen) -> Path:
    """Erzeugt ein gueltig verschluesseltes Paket mit praeparierten
    Archiveintraegen -- simuliert einen Angreifer, der das Passwort kennt."""
    import importlib.util
    import io
    import tarfile as _tar

    spec = importlib.util.spec_from_file_location("bk", SKRIPT)
    bk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bk)

    puffer = io.BytesIO()
    with _tar.open(fileobj=puffer, mode="w") as tar:
        bauen(tar, _tar)
    ziel = tmp_path / f"praepariert{bk.ARCHIVE_SUFFIX}"
    bk._encrypt_to_file(puffer.getvalue(), TEST_PASSWORT, ziel)
    return ziel


def test_pfadausbruch_im_archiv_wird_abgelehnt(tmp_path):
    def bauen(tar, _tar):
        info = _tar.TarInfo("../ausbruch.txt")
        info.size = 4
        tar.addfile(info, __import__("io").BytesIO(b"boes"))
    res = _lauf(["verify", "--archive", str(_paket_mit_eintraegen(tmp_path, bauen))])
    assert res.returncode == 1
    assert "Traceback" not in res.stderr


def test_absoluter_pfad_im_archiv_wird_abgelehnt(tmp_path):
    def bauen(tar, _tar):
        info = _tar.TarInfo("/etc/boese_datei")
        info.size = 4
        tar.addfile(info, __import__("io").BytesIO(b"boes"))
    res = _lauf(["verify", "--archive", str(_paket_mit_eintraegen(tmp_path, bauen))])
    assert res.returncode == 1


def test_symbolische_verknuepfung_im_archiv_wird_abgelehnt(tmp_path):
    def bauen(tar, _tar):
        info = _tar.TarInfo("link")
        info.type = _tar.SYMTYPE
        info.linkname = "/etc/passwd"
        tar.addfile(info)
    res = _lauf(["verify", "--archive", str(_paket_mit_eintraegen(tmp_path, bauen))])
    assert res.returncode == 1


def test_harte_verknuepfung_im_archiv_wird_abgelehnt(tmp_path):
    def bauen(tar, _tar):
        info = _tar.TarInfo("hardlink")
        info.type = _tar.LNKTYPE
        info.linkname = "ailiza.sqlite"
        tar.addfile(info)
    res = _lauf(["verify", "--archive", str(_paket_mit_eintraegen(tmp_path, bauen))])
    assert res.returncode == 1


def test_zu_viele_eintraege_werden_abgelehnt(tmp_path):
    def bauen(tar, _tar):
        import io as _io
        for i in range(200):
            info = _tar.TarInfo(f"datei{i}")
            info.size = 1
            tar.addfile(info, _io.BytesIO(b"x"))
    res = _lauf(["verify", "--archive", str(_paket_mit_eintraegen(tmp_path, bauen))])
    assert res.returncode == 1
    assert "Traceback" not in res.stderr


def test_geraetedatei_im_archiv_wird_abgelehnt(tmp_path):
    def bauen(tar, _tar):
        info = _tar.TarInfo("geraet")
        info.type = _tar.CHRTYPE
        tar.addfile(info)
    res = _lauf(["verify", "--archive", str(_paket_mit_eintraegen(tmp_path, bauen))])
    assert res.returncode == 1


def test_uebergrosser_eintrag_wird_abgelehnt(tmp_path):
    """Dekompressionsbombe: kleine Datei, riesige angekuendigte Groesse."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("bk", SKRIPT)
    bk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bk)

    def bauen(tar, _tar):
        import io as _io
        info = _tar.TarInfo("riesig")
        info.size = 8
        tar.addfile(info, _io.BytesIO(b"12345678"))

    archiv = _paket_mit_eintraegen(tmp_path, bauen)
    # Die Groessenpruefung selbst direkt gegen die Konstante belegen
    assert bk._MAX_EINTRAG_BYTES > 0 and bk._MAX_EINTRAEGE > 0
    res = _lauf(["verify", "--archive", str(archiv)])
    # Ohne Datenbank im Paket -> Abbruch, aber ohne Absturz
    assert res.returncode == 1
    assert "Traceback" not in res.stderr


# ---------------------------------------------------------------------------
# Atomizitaet, Aufraeumen, Parallelitaet
# ---------------------------------------------------------------------------

def test_kein_unfertiges_paket_bleibt_liegen(gesichert):
    """Ein abgebrochener Schreibvorgang darf keine Datei hinterlassen, die
    wie eine gueltige Sicherung aussieht."""
    ordner = gesichert["archiv"].parent
    reste = [p.name for p in ordner.iterdir() if p.name.startswith(".unfertig-")]
    assert not reste, f"Unfertige Dateien liegengeblieben: {reste}"


def test_abbruch_hinterlaesst_keine_teildatei(tmp_path, monkeypatch):
    """Schlaegt das Schreiben fehl, darf nichts zurueckbleiben."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("bk", SKRIPT)
    bk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bk)

    ziel = tmp_path / "abbruch" / f"x{bk.ARCHIVE_SUFFIX}"
    ziel.parent.mkdir(parents=True)
    orig = os.replace

    def kaputt(a, b):
        raise OSError("simulierter Abbruch beim Umbenennen")

    monkeypatch.setattr(bk.os, "replace", kaputt)
    with pytest.raises(OSError):
        bk._encrypt_to_file(b"testdaten", TEST_PASSWORT, ziel)
    monkeypatch.setattr(bk.os, "replace", orig)

    assert not ziel.exists(), "Teildatei als gueltiges Paket zurueckgeblieben"
    reste = [p.name for p in ziel.parent.iterdir()]
    assert not reste, f"Temporaere Datei nicht aufgeraeumt: {reste}"


def test_zwei_sicherungen_kollidieren_nicht(tmp_path):
    """Zwei Laeufe auf dasselbe Ziel duerfen sich nicht gegenseitig
    ueberschreiben oder eine gemeinsame temporaere Datei benutzen."""
    import importlib.util
    import threading
    spec = importlib.util.spec_from_file_location("bk", SKRIPT)
    bk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bk)

    ordner = tmp_path / "parallel"
    ordner.mkdir()
    fehler = []

    def lauf(i):
        try:
            bk._encrypt_to_file(b"x" * 5000, TEST_PASSWORT,
                                ordner / f"p{i}{bk.ARCHIVE_SUFFIX}")
        except Exception as exc:      # noqa: BLE001
            fehler.append(exc)

    faeden = [threading.Thread(target=lauf, args=(i,)) for i in range(6)]
    for t in faeden:
        t.start()
    for t in faeden:
        t.join()

    assert not fehler, f"Fehler bei parallelen Sicherungen: {fehler}"
    fertige = sorted(ordner.glob(f"*{bk.ARCHIVE_SUFFIX}"))
    assert len(fertige) == 6
    assert not [p for p in ordner.iterdir() if p.name.startswith(".unfertig-")]


def test_temporaere_dateien_werden_bei_fehler_aufgeraeumt(tmp_path):
    """Auch der Fehlerpfad darf keine entschluesselte Datenbank
    zuruecklassen. Geprueft wird gegen einen EIGENEN, leeren Temp-Ordner --
    sonst zaehlt der Test fremde Prozesse mit und wird unzuverlaessig."""
    db = tmp_path / "daten" / "ailiza.sqlite"
    _datenbank_mit_inhalt(db)
    env = _env_datei(tmp_path / ".env")
    ziel = tmp_path / "s"
    assert _lauf(["backup", "--db-path", str(db), "--env-file", str(env),
                  "--out", str(ziel)]).returncode == 0

    eigener_temp = tmp_path / "temp"
    eigener_temp.mkdir()
    umgebung = dict(os.environ)
    umgebung["AILIZA_SECRET_KEY"] = "irrelevant-aber-lang-genug-fuer-den-test"
    umgebung.pop("AILIZA_BACKUP_PASSWORD", None)
    for var in ("TMPDIR", "TEMP", "TMP"):
        umgebung[var] = str(eigener_temp)

    for passwort in ("falsches-passwort-abcdef", TEST_PASSWORT):
        subprocess.run(
            [sys.executable, str(SKRIPT), "verify", "--archive", str(_paket(ziel))],
            cwd=str(REPO_ROOT), env=umgebung, capture_output=True, text=True,
            timeout=300, input=passwort + "\n",
        )
        reste = list(eigener_temp.iterdir())
        assert not reste, f"Temporaere Dateien zurueckgeblieben: {reste}"


# ---------------------------------------------------------------------------
# Groessengrenze und Laufzeit
# ---------------------------------------------------------------------------

def test_groessengrenze_ist_dokumentiert_und_wirksam(tmp_path):
    """Das Paket wird als Ganzes im Speicher verschluesselt. Ohne Grenze
    koennte eine sehr grosse Datenbank den Rechner in den Speichermangel
    treiben. Geprueft wird die Grenze selbst, mit herabgesetztem Wert."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("bk", SKRIPT)
    bk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bk)

    assert bk._MAX_PAKET_BYTES == 1024 * 1024 * 1024
    assert "Arbeitsspeicher" in SKRIPT.read_text(encoding="utf-8")

    bk._MAX_PAKET_BYTES = 1000          # nur in dieser Modulkopie
    with pytest.raises(bk.BackupError) as fehler:
        bk._encrypt_to_file(b"x" * 2000, TEST_PASSWORT,
                            tmp_path / f"zu_gross{bk.ARCHIVE_SUFFIX}")
    assert "groesser" in str(fehler.value)
    assert not list(tmp_path.glob("*")), "Teildatei trotz Abbruch angelegt"


@pytest.mark.slow
def test_groessere_datenbank_laufzeit_und_speicher(tmp_path):
    """Repraesentativ groessere Datenbank (rund 50 MB). Belegt Laufzeit und
    Spitzenspeicher, damit die Grenze aus _MAX_PAKET_BYTES eingeordnet
    werden kann."""
    import time
    import tracemalloc
    import importlib.util

    db = tmp_path / "daten" / "ailiza.sqlite"
    _datenbank_mit_inhalt(db)
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE gross(x)")
    block = "f" * 10000
    con.executemany("INSERT INTO gross VALUES(?)", [(block,)] * 5000)
    con.commit()
    con.close()
    groesse = db.stat().st_size
    assert groesse > 40 * 1024 * 1024, f"Testdatenbank zu klein: {groesse}"

    env = _env_datei(tmp_path / ".env")
    spec = importlib.util.spec_from_file_location("bk", SKRIPT)
    bk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bk)

    tracemalloc.start()
    start = time.monotonic()
    res = _lauf(["backup", "--db-path", str(db), "--env-file", str(env),
                 "--out", str(tmp_path / "s")])
    dauer = time.monotonic() - start
    _, spitze = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert res.returncode == 0, res.stdout + res.stderr
    assert _lauf(["verify", "--archive", str(_paket(tmp_path / "s"))]).returncode == 0
    print(f"\nDatenbank {groesse // (1024*1024)} MB — "
          f"Sicherung und Abnahme in {dauer:.1f} s")


# ---------------------------------------------------------------------------
# Schranken direkt pruefen
#
# Die Tests weiter oben, die ein Paket mit ueberzogenen Parametern
# manipulieren, bestehen auch OHNE Schrankenpruefung -- weil der veraenderte
# Kopf ohnehin die AAD-Authentifizierung bricht und der Abbruch von dort
# kommt. Ein Mutationstest hat genau das aufgedeckt. Die Schranken muessen
# deshalb unmittelbar geprueft werden.
#
# Die Reihenfolge ist sicherheitsrelevant: die Pruefung MUSS vor der
# Schluesselableitung laufen. Danach waere der Rechenaufwand bereits
# entstanden -- der Denial-of-Service also schon eingetreten.
# ---------------------------------------------------------------------------

def _modul():
    import importlib.util
    spec = importlib.util.spec_from_file_location("bk_direkt", SKRIPT)
    bk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bk)
    return bk


@pytest.mark.parametrize("n,r,p,grund", [
    (2 ** 30, 8, 1, "n weit ueber der Obergrenze"),
    (2 ** 13, 8, 1, "n unter der Untergrenze"),
    (30000, 8, 1, "n keine Zweierpotenz"),
    (2 ** 15, 4096, 1, "r ueber der Obergrenze"),
    (2 ** 15, 8, 9999, "p ueber der Obergrenze"),
    (2 ** 17, 32, 1, "Speicherbedarf ueber 256 MiB"),
    ("8", 8, 1, "n kein ganzzahliger Wert"),
    (True, 8, 1, "n ist ein Wahrheitswert"),
])
def test_kdf_schranken_lehnen_direkt_ab(n, r, p, grund):
    bk = _modul()
    with pytest.raises(bk.BackupError):
        bk._pruefe_kdf_parameter(n, r, p)


def test_kdf_schranken_lassen_die_vorgabe_durch():
    bk = _modul()
    bk._pruefe_kdf_parameter(bk._SCRYPT_N, bk._SCRYPT_R, bk._SCRYPT_P)


def test_schrankenpruefung_laeuft_vor_der_schluesselableitung(monkeypatch):
    """Liefe sie danach, waere der Rechenaufwand bereits entstanden -- der
    Denial-of-Service also schon eingetreten."""
    bk = _modul()

    def darf_nicht_laufen():
        raise AssertionError("Krypto-Aufbau vor der Schrankenpruefung")

    monkeypatch.setattr(bk, "_require_crypto", darf_nicht_laufen)
    with pytest.raises(bk.BackupError) as fehler:
        bk._derive_key("passwort", b"x" * 16, 2 ** 30, 8, 1)
    assert "ausserhalb" in str(fehler.value) or "Arbeitsspeicher" in str(fehler.value)


def test_pfadausbruch_wird_unabhaengig_vom_aufgeloesten_pfad_geprueft():
    """Der Mutationstest zeigte: der ".."-Test bestand auch ohne die
    ".."-Pruefung, weil die Pfadaufloesung ihn mit abfaengt. Beide Schichten
    sollen bestehen bleiben -- der Quelltext wird deshalb direkt geprueft."""
    quelltext = SKRIPT.read_text(encoding="utf-8")
    assert '".." in Path(name).parts' in quelltext, (
        "Ausdrueckliche ..-Pruefung fehlt (nur Pfadaufloesung ist zu wenig)"
    )
    assert "issym()" in quelltext and "islnk()" in quelltext
    assert "_MAX_EINTRAEGE" in quelltext and "_MAX_EINTRAG_BYTES" in quelltext
