"""AP1: Vorlagen aus der Wissensbibliothek starten einen neuen Chat.

Vorher landete jede Vorlage im bereits geoeffneten Chat (useWissen() setzte
nur den Text ins bestehende Eingabefeld). Das fuehrte dazu, dass mehrere
Vorlagen sich gegenseitig ueberschrieben bzw. den laufenden Chat vermischten.

Diese Tests pruefen das tatsaechlich ausgelieferte Frontend (TestClient GET
"/", wie ein Browser) -- nicht eine ungenutzte Quelldatei.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi.testclient import TestClient

from apps.backend.main import app


@pytest.fixture()
def served_index() -> str:
    client = TestClient(app)
    response = client.get("/", headers={"accept": "text/html"})
    assert response.status_code == 200
    return response.text


def _use_wissen_function(served_index: str) -> str:
    start = served_index.index("function useWissen(")
    end = served_index.index("function ", start + 10)
    return served_index[start:end]


def test_wissen_cards_pass_prompt_and_title(served_index):
    assert 'onclick="useWissen(${JSON.stringify(w.p)' in served_index
    assert "${JSON.stringify(w.title)" in served_index


def test_use_wissen_creates_a_new_chat_id(served_index):
    fn = _use_wissen_function(served_index)
    assert "currentChatId=createChatId()" in fn


def test_use_wissen_saves_previous_chat_before_switching(served_index):
    fn = _use_wissen_function(served_index)
    assert fn.index("saveCurrentChat()") < fn.index("currentChatId=createChatId()")


def test_use_wissen_registers_new_chat_with_title_in_sidebar(served_index):
    fn = _use_wissen_function(served_index)
    assert "registerChatListEntry(currentChatId,title)" in fn
    assert "renderRecent()" in fn


def test_use_wissen_inserts_draft_without_auto_send(served_index):
    fn = _use_wissen_function(served_index)
    assert "inp.value=prompt" in fn
    assert "sendMessage()" not in fn


def test_use_wissen_switches_to_chat_view(served_index):
    fn = _use_wissen_function(served_index)
    assert 'document.getElementById("view-chat").classList.add("active")' in fn


def test_explicit_template_title_survives_first_message(served_index):
    """saveCurrentChat() darf einen per Vorlage vergebenen Titel nicht durch
    den Text der ersten Nachricht ueberschreiben."""
    start = served_index.index("function saveCurrentChat(")
    end = served_index.index("function renderChat(")
    fn = served_index[start:end]
    assert "prev&&prev.explicit" in fn
    assert "explicit:prev?prev.explicit:false" in fn


def test_register_chat_list_entry_marks_chat_explicit(served_index):
    start = served_index.index("function registerChatListEntry(")
    end = served_index.index("function useWissen(")
    fn = served_index[start:end]
    assert "explicit:true" in fn
