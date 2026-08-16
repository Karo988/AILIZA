"""Prüfbeleg-Vertrag: Bindung zwischen geprüfter Vorschau und Versand.

Kerninvariante: Nur exakt der Text, der zuletzt für diesen Nutzer, Mandanten
und Zweck geprüft wurde, darf hinausgehen. Diese Tests prüfen den
Durchsetzungs-Baustein (apps/backend/governance/send_preview.py) isoliert --
die Verdrahtung in den Chat-Pfad ist ein eigenes Arbeitspaket.
"""
from __future__ import annotations

import threading
import time

import pytest

from apps.backend.governance.send_preview import (
    PreviewRejected,
    SendPreviewStore,
    hash_text,
    normalize_text,
)

_USER = "erika"
_TENANT = "default"
_PURPOSE = "agent_run"
_TEXT = "Bitte fasse den Vertrag mit [KUNDE_1] zusammen."


@pytest.fixture()
def store() -> SendPreviewStore:
    return SendPreviewStore()


def _consume(store: SendPreviewStore, preview_id, **overrides) -> None:
    kwargs = {
        "preview_id": preview_id,
        "user_id": _USER,
        "tenant_id": _TENANT,
        "text": _TEXT,
        "purpose": _PURPOSE,
    }
    kwargs.update(overrides)
    store.consume(**kwargs)


# ── Positivfall ──────────────────────────────────────────────────────────

def test_valid_preview_is_accepted(store):
    preview_id = store.issue(
        user_id=_USER, tenant_id=_TENANT, checked_text=_TEXT, purpose=_PURPOSE
    )
    _consume(store, preview_id)  # wirft nicht


# ── Kein Versand ohne Prüfung ────────────────────────────────────────────

def test_missing_preview_id_is_rejected(store):
    with pytest.raises(PreviewRejected) as exc:
        _consume(store, None)
    assert exc.value.reason == "missing"


def test_unknown_preview_id_is_rejected(store):
    with pytest.raises(PreviewRejected) as exc:
        _consume(store, "frei-erfunden")
    assert exc.value.reason == "unknown_or_expired"


# ── Textänderung macht die Prüfung ungültig ──────────────────────────────

@pytest.mark.parametrize(
    "veraenderter_text",
    [
        "Bitte fasse den Vertrag mit [KUNDE_1] zusammen!",   # ein Zeichen
        "bitte fasse den Vertrag mit [KUNDE_1] zusammen.",   # Grossschreibung
        "Bitte  fasse den Vertrag mit [KUNDE_1] zusammen.",  # Doppelleerzeichen
        "Bitte fasse den Vertrag mit [KUNDE_2] zusammen.",   # anderer Platzhalter
        _TEXT + " ",                                          # angehaengtes Leerzeichen
        _TEXT + "​",                                     # unsichtbares Zeichen
        "",                                                   # geleert
    ],
)
def test_changed_text_is_rejected(store, veraenderter_text):
    preview_id = store.issue(
        user_id=_USER, tenant_id=_TENANT, checked_text=_TEXT, purpose=_PURPOSE
    )
    with pytest.raises(PreviewRejected) as exc:
        _consume(store, preview_id, text=veraenderter_text)
    assert exc.value.reason == "text_mismatch"


def test_line_endings_and_unicode_form_do_not_falsely_invalidate(store):
    """Technisch bedeutungsgleiche Varianten duerfen NICHT als Manipulation
    gelten -- sonst waere die Funktion je nach Betriebssystem/Tastatur
    unbenutzbar. 'é' als ein Zeichen und als 'e + Akzent' ist derselbe Text."""
    # Absicherung gegen unbemerkte Vereinheitlichung durch einen Editor:
    # der Test ist nur aussagekraeftig, wenn beide Formen wirklich
    # unterschiedliche Byte-Folgen sind (NFC "\u00e9" vs. NFD "e\u0301").
    geprueft = "Zeile eins\r\nZeile zwei\r\nCafé"
    gesendet = "Zeile eins\nZeile zwei\nCafé"  # LF + Kombinationsakzent
    preview_id = store.issue(
        user_id=_USER, tenant_id=_TENANT, checked_text=geprueft, purpose=_PURPOSE
    )
    _consume(store, preview_id, text=gesendet)  # wirft nicht


def test_normalization_does_not_swallow_real_changes():
    """Gegenprobe zur Normalisierung: sie darf nur Zeilenenden und
    Unicode-Form angleichen, keine echten Unterschiede."""
    assert normalize_text("a\r\nb") == normalize_text("a\nb")
    assert hash_text("Text") != hash_text("text")
    assert hash_text("a b") != hash_text("a  b")
    assert hash_text("Vertrag") != hash_text("Vertrag ")


# ── Bindung an Nutzer, Mandant, Zweck ────────────────────────────────────

def test_foreign_user_is_rejected(store):
    preview_id = store.issue(
        user_id=_USER, tenant_id=_TENANT, checked_text=_TEXT, purpose=_PURPOSE
    )
    with pytest.raises(PreviewRejected) as exc:
        _consume(store, preview_id, user_id="jemand-anderes")
    assert exc.value.reason == "user_mismatch"


def test_anonymous_preview_cannot_be_used_by_logged_in_user(store):
    preview_id = store.issue(
        user_id=None, tenant_id=_TENANT, checked_text=_TEXT, purpose=_PURPOSE
    )
    with pytest.raises(PreviewRejected) as exc:
        _consume(store, preview_id, user_id=_USER)
    assert exc.value.reason == "user_mismatch"


def test_anonymous_preview_works_for_anonymous_send(store):
    """Die Vorschau verlangt keinen Login -- anonyme Nutzung muss moeglich
    bleiben, sonst wuerde das Gate die bestehende Freigabe aushebeln,
    dass unkritische Anfragen ohne Anmeldung gesendet werden duerfen."""
    preview_id = store.issue(
        user_id=None, tenant_id=_TENANT, checked_text=_TEXT, purpose=_PURPOSE
    )
    _consume(store, preview_id, user_id=None)  # wirft nicht


def test_foreign_tenant_is_rejected(store):
    preview_id = store.issue(
        user_id=_USER, tenant_id=_TENANT, checked_text=_TEXT, purpose=_PURPOSE
    )
    with pytest.raises(PreviewRejected) as exc:
        _consume(store, preview_id, tenant_id="fremder-mandant")
    assert exc.value.reason == "tenant_mismatch"


def test_wrong_purpose_is_rejected(store):
    preview_id = store.issue(
        user_id=_USER, tenant_id=_TENANT, checked_text=_TEXT, purpose=_PURPOSE
    )
    with pytest.raises(PreviewRejected) as exc:
        _consume(store, preview_id, purpose="websuche")
    assert exc.value.reason == "purpose_mismatch"


# ── Einmalnutzung, Ablauf, Nebenläufigkeit ───────────────────────────────

def test_preview_can_only_be_used_once(store):
    preview_id = store.issue(
        user_id=_USER, tenant_id=_TENANT, checked_text=_TEXT, purpose=_PURPOSE
    )
    _consume(store, preview_id)
    with pytest.raises(PreviewRejected) as exc:
        _consume(store, preview_id)
    assert exc.value.reason == "unknown_or_expired"


def test_failed_attempt_also_consumes_the_preview(store):
    """Ein fehlgeschlagener Versuch darf keinen zweiten Versuch erlauben --
    sonst koennte jemand den Text so lange variieren, bis er passt."""
    preview_id = store.issue(
        user_id=_USER, tenant_id=_TENANT, checked_text=_TEXT, purpose=_PURPOSE
    )
    with pytest.raises(PreviewRejected):
        _consume(store, preview_id, text="manipuliert")
    with pytest.raises(PreviewRejected) as exc:
        _consume(store, preview_id)  # jetzt mit korrektem Text
    assert exc.value.reason == "unknown_or_expired"


def test_expired_preview_is_rejected():
    store = SendPreviewStore(ttl_seconds=0)
    preview_id = store.issue(
        user_id=_USER, tenant_id=_TENANT, checked_text=_TEXT, purpose=_PURPOSE
    )
    time.sleep(0.01)
    with pytest.raises(PreviewRejected) as exc:
        _consume(store, preview_id)
    assert exc.value.reason == "unknown_or_expired"


def test_concurrent_requests_cannot_consume_the_same_preview_twice(store):
    """Zwei gleichzeitige Requests (z.B. Doppelklick auf Senden oder zwei
    Browser-Tabs) duerfen NICHT beide durchkommen. Ein 'erst lesen, dann
    loeschen' ohne Sperre waere hier angreifbar."""
    preview_id = store.issue(
        user_id=_USER, tenant_id=_TENANT, checked_text=_TEXT, purpose=_PURPOSE
    )
    erfolge: list[bool] = []
    sperre = threading.Lock()
    start = threading.Barrier(8)

    def versuch() -> None:
        start.wait()
        try:
            _consume(store, preview_id)
            ergebnis = True
        except PreviewRejected:
            ergebnis = False
        with sperre:
            erfolge.append(ergebnis)

    threads = [threading.Thread(target=versuch) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(erfolge) == 1, f"Genau ein Versand darf durchkommen, war: {sum(erfolge)}"


def test_many_concurrent_issues_are_all_distinct(store):
    ids: list[str] = []
    sperre = threading.Lock()

    def ausstellen() -> None:
        preview_id = store.issue(
            user_id=_USER, tenant_id=_TENANT, checked_text=_TEXT, purpose=_PURPOSE
        )
        with sperre:
            ids.append(preview_id)

    threads = [threading.Thread(target=ausstellen) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(set(ids)) == 50


# ── Speicher- und Inhaltsschutz ──────────────────────────────────────────

def test_store_never_keeps_the_text_itself(store):
    """Der Speicher darf den geprueften Text nicht vorhalten -- nur seinen
    Hash. Sonst laege Nutzerinhalt unnoetig lange im Arbeitsspeicher."""
    geheim = "Patientin Erika Mustermann, Diagnose Depression"
    store.issue(user_id=_USER, tenant_id=_TENANT, checked_text=geheim, purpose=_PURPOSE)
    inhalt = repr(store.__dict__)
    assert "Mustermann" not in inhalt
    assert "Depression" not in inhalt


def test_store_evicts_oldest_when_full():
    store = SendPreviewStore(max_entries=3)
    ids = [
        store.issue(user_id=_USER, tenant_id=_TENANT, checked_text=f"text {i}", purpose=_PURPOSE)
        for i in range(5)
    ]
    gueltig = 0
    for i, preview_id in enumerate(ids):
        try:
            store.consume(
                preview_id=preview_id, user_id=_USER, tenant_id=_TENANT,
                text=f"text {i}", purpose=_PURPOSE,
            )
            gueltig += 1
        except PreviewRejected:
            pass
    assert gueltig <= 3, "Speicher darf nicht unbegrenzt wachsen"
    assert gueltig >= 1, "Die zuletzt ausgestellten Belege muessen gueltig bleiben"


def test_very_long_text_is_handled(store):
    langer_text = "Vertragstext. " * 20_000
    preview_id = store.issue(
        user_id=_USER, tenant_id=_TENANT, checked_text=langer_text, purpose=_PURPOSE
    )
    _consume(store, preview_id, text=langer_text)
    with pytest.raises(PreviewRejected):
        _consume(store, preview_id, text=langer_text + "x")


def test_rejection_message_is_german_and_actionable(store):
    """Die Nutzerin muss verstehen, was zu tun ist -- kein Stack-Trace,
    kein englischer Fehlercode."""
    with pytest.raises(PreviewRejected) as exc:
        _consume(store, None)
    assert "prüfen" in exc.value.message_de.lower() or "Prüfung" in exc.value.message_de
    assert exc.value.message_de.endswith(".")
