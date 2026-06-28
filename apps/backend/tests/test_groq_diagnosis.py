"""
Tests für GET /api/debug/groq-diagnosis
=========================================
Prüft:
1. Models API 403 → diagnosis=groq_key_not_authorized_for_project
2. Models API ok, Zielmodell nicht in Liste → groq_model_not_allowed_for_key
3. Direkter Chat ok → groq_ok (oder groq_ok_route_hint)
4. Direkter Chat ok aber Models API hatte Fehler → gemischte Diagnose
5. Keine Secrets im Response
6. key_fingerprint enthält nicht den echten Key-Wert
7. Models API 401 → diagnosis=groq_key_invalid
8. Chat 400 → diagnosis=groq_request_format_bug
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
from unittest.mock import MagicMock, patch

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "true")

import pytest
from fastapi.testclient import TestClient
from apps.backend.main import app

client = TestClient(app, raise_server_exceptions=False)

_FAKE_KEY = "gsk_test1234567890abcdef"
_FAKE_MODEL = "llama-3.1-8b-instant"


def _http_error(code: int, body: dict | None = None) -> urllib.error.HTTPError:
    """Erstellt einen urllib.error.HTTPError mit optionalem JSON-Body."""
    fp = MagicMock()
    fp.read.return_value = json.dumps(body or {}).encode()
    return urllib.error.HTTPError(
        url="https://api.groq.com/...",
        code=code,
        msg=f"HTTP {code}",
        hdrs=MagicMock(),
        fp=fp,
    )


def _models_ok_response(model_ids: list[str]) -> MagicMock:
    """Mock für erfolgreiche Models-API-Antwort."""
    resp = MagicMock()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    resp.getcode.return_value = 200
    resp.read.return_value = json.dumps({
        "data": [{"id": m} for m in model_ids]
    }).encode()
    return resp


def _chat_ok_response(text: str = "AILIZA_GROQ_OK") -> MagicMock:
    """Mock für erfolgreichen Chat-Completion-Response."""
    resp = MagicMock()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    resp.getcode.return_value = 200
    resp.read.return_value = json.dumps({
        "choices": [{"message": {"content": text}}]
    }).encode()
    return resp


# ── 1. Models API 403 → Key nicht für Projekt autorisiert ────────────────────

class TestGroqDiagnosisModels403:

    def test_models_api_403_diagnosis_not_authorized(self, monkeypatch):
        """Models API 403 → diagnosis=groq_key_not_authorized_for_project."""
        monkeypatch.setenv("GROQ_API_KEY", _FAKE_KEY)
        monkeypatch.setenv("GROQ_MODEL", _FAKE_MODEL)

        with patch("urllib.request.urlopen", side_effect=_http_error(403)):
            resp = client.get("/api/debug/groq-diagnosis")

        assert resp.status_code == 200
        data = resp.json()
        assert data["diagnosis"] == "groq_key_not_authorized_for_project"
        assert "403" in data["next_action_de"] or "Projekt" in data["next_action_de"]
        assert data["models_api"]["models_api_ok"] is False
        assert data["models_api"]["models_api_status_code"] == 403

    def test_models_api_401_diagnosis_key_invalid(self, monkeypatch):
        """Models API 401 → diagnosis=groq_key_invalid."""
        monkeypatch.setenv("GROQ_API_KEY", _FAKE_KEY)
        monkeypatch.setenv("GROQ_MODEL", _FAKE_MODEL)

        with patch("urllib.request.urlopen", side_effect=_http_error(401)):
            resp = client.get("/api/debug/groq-diagnosis")

        assert resp.status_code == 200
        data = resp.json()
        assert data["diagnosis"] == "groq_key_invalid"


# ── 2. Models API ok, Zielmodell nicht in Liste ───────────────────────────────

class TestGroqDiagnosisModelNotInList:

    def test_target_model_missing_from_list(self, monkeypatch):
        """Zielmodell nicht in accessible_model_ids → groq_model_not_allowed_for_key."""
        monkeypatch.setenv("GROQ_API_KEY", _FAKE_KEY)
        monkeypatch.setenv("GROQ_MODEL", "llama-3.3-70b-versatile")

        call_count = 0
        def fake_urlopen(req, timeout=10):
            nonlocal call_count
            call_count += 1
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "models" in url and "completions" not in url:
                # Models API → liefert nur llama-3.1-8b-instant
                return _models_ok_response(["llama-3.1-8b-instant", "llama-3.1-70b-versatile"])
            # Chat test für alternatives Modell
            return _chat_ok_response("AILIZA_GROQ_OK")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            resp = client.get("/api/debug/groq-diagnosis")

        data = resp.json()
        assert data["diagnosis"] == "groq_model_not_allowed_for_key"
        assert data["models_api"]["target_model_in_accessible_models"] is False
        assert "llama-3.3-70b-versatile" not in data["models_api"]["accessible_model_ids"]

    def test_accessible_model_ids_in_response(self, monkeypatch):
        """accessible_model_ids muss die Modell-Liste enthalten."""
        monkeypatch.setenv("GROQ_API_KEY", _FAKE_KEY)
        monkeypatch.setenv("GROQ_MODEL", "nonexistent-model")

        def fake_urlopen(req, timeout=10):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "models" in url and "completions" not in url:
                return _models_ok_response(["llama-3.1-8b-instant", "llama-3.1-70b-versatile"])
            return _chat_ok_response()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            resp = client.get("/api/debug/groq-diagnosis")

        data = resp.json()
        assert "llama-3.1-8b-instant" in data["models_api"]["accessible_model_ids"]


# ── 3. Direkter Chat ok → groq_ok ────────────────────────────────────────────

class TestGroqDiagnosisChatOk:

    def test_models_ok_chat_ok_diagnosis_groq_ok(self, monkeypatch):
        """Models API ok, Zielmodell in Liste, Chat ok → diagnosis=groq_ok."""
        monkeypatch.setenv("GROQ_API_KEY", _FAKE_KEY)
        monkeypatch.setenv("GROQ_MODEL", _FAKE_MODEL)

        def fake_urlopen(req, timeout=10):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "models" in url and "completions" not in url:
                return _models_ok_response([_FAKE_MODEL, "llama-3.1-70b-versatile"])
            return _chat_ok_response("AILIZA_GROQ_OK")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            resp = client.get("/api/debug/groq-diagnosis")

        data = resp.json()
        assert data["diagnosis"] == "groq_ok"
        assert data["chat_test"]["chat_ok"] is True
        assert data["models_api"]["target_model_in_accessible_models"] is True

    def test_chat_ok_note_mentions_routing(self, monkeypatch):
        """Bei chat_ok soll note auf AILIZA-Routing hinweisen (falls provider-test trotzdem fehlschlägt)."""
        monkeypatch.setenv("GROQ_API_KEY", _FAKE_KEY)
        monkeypatch.setenv("GROQ_MODEL", _FAKE_MODEL)

        def fake_urlopen(req, timeout=10):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "models" in url and "completions" not in url:
                return _models_ok_response([_FAKE_MODEL])
            return _chat_ok_response("AILIZA_GROQ_OK")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            resp = client.get("/api/debug/groq-diagnosis")

        data = resp.json()
        note = data.get("note", "")
        assert "routing" in note.lower() or "ailiza" in note.lower()


# ── 4. Models ok, Zielmodell in Liste, Chat 403 → UI/API nicht synchron ──────

class TestGroqDiagnosisChatForbidden:

    def test_models_ok_target_in_list_chat_403(self, monkeypatch):
        """Modell in Liste, Chat gibt 403 → groq_model_permission_ui_saved_but_api_still_forbidden."""
        monkeypatch.setenv("GROQ_API_KEY", _FAKE_KEY)
        monkeypatch.setenv("GROQ_MODEL", _FAKE_MODEL)

        call_count = 0
        def fake_urlopen(req, timeout=10):
            nonlocal call_count
            call_count += 1
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "models" in url and "completions" not in url:
                return _models_ok_response([_FAKE_MODEL])
            raise _http_error(403, {"error": {"code": "model_access_denied",
                                               "type": "forbidden",
                                               "message": "Access denied to model"}})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            resp = client.get("/api/debug/groq-diagnosis")

        data = resp.json()
        assert data["diagnosis"] == "groq_model_permission_ui_saved_but_api_still_forbidden"
        assert data["chat_test"]["chat_ok"] is False
        assert data["chat_test"]["raw_error_category"] == "forbidden_model_or_project"

    def test_chat_400_diagnosis_request_format_bug(self, monkeypatch):
        """Chat gibt 400 → diagnosis=groq_request_format_bug."""
        monkeypatch.setenv("GROQ_API_KEY", _FAKE_KEY)
        monkeypatch.setenv("GROQ_MODEL", _FAKE_MODEL)

        def fake_urlopen(req, timeout=10):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "models" in url and "completions" not in url:
                return _models_ok_response([_FAKE_MODEL])
            raise _http_error(400, {"error": {"message": "Invalid request"}})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            resp = client.get("/api/debug/groq-diagnosis")

        data = resp.json()
        assert data["diagnosis"] == "groq_request_format_bug"
        assert data["chat_test"]["raw_error_category"] == "bad_request"


# ── 5. Sicherheit — kein Secret im Response ──────────────────────────────────

class TestGroqDiagnosisSecurity:

    def test_no_api_key_in_response(self, monkeypatch):
        """Der echte API-Key darf niemals im Response erscheinen."""
        monkeypatch.setenv("GROQ_API_KEY", _FAKE_KEY)
        monkeypatch.setenv("GROQ_MODEL", _FAKE_MODEL)

        with patch("urllib.request.urlopen", side_effect=_http_error(403)):
            resp = client.get("/api/debug/groq-diagnosis")

        response_text = resp.text
        assert _FAKE_KEY not in response_text, "Echter API-Key im Response gefunden!"
        # Nur Prefix (4 Zeichen) erlaubt
        assert "gsk_" in response_text  # Prefix ok
        assert "test1234567890abcdef" not in response_text  # Rest des Keys verboten

    def test_key_fingerprint_is_sha256_not_key(self, monkeypatch):
        """key_fingerprint muss SHA256-Hash sein, nicht der Key selbst."""
        monkeypatch.setenv("GROQ_API_KEY", _FAKE_KEY)
        monkeypatch.setenv("GROQ_MODEL", _FAKE_MODEL)

        expected_fp = hashlib.sha256(_FAKE_KEY.encode()).hexdigest()[:12]

        with patch("urllib.request.urlopen", side_effect=_http_error(403)):
            resp = client.get("/api/debug/groq-diagnosis")

        data = resp.json()
        fingerprint = data["env"]["groq_key_fingerprint"]
        assert fingerprint == expected_fp, f"Fingerprint falsch: {fingerprint!r} != {expected_fp!r}"
        assert _FAKE_KEY not in fingerprint

    def test_key_prefix_only_4_chars(self, monkeypatch):
        """groq_key_prefix zeigt nur die ersten 4 Zeichen."""
        monkeypatch.setenv("GROQ_API_KEY", _FAKE_KEY)
        monkeypatch.setenv("GROQ_MODEL", _FAKE_MODEL)

        with patch("urllib.request.urlopen", side_effect=_http_error(403)):
            resp = client.get("/api/debug/groq-diagnosis")

        data = resp.json()
        prefix = data["env"]["groq_key_prefix"]
        assert prefix == "gsk_"
        assert len(prefix) == 4

    def test_no_key_when_not_set(self, monkeypatch):
        """Wenn kein Key gesetzt → key_present=false, frühe Diagnose."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.setenv("GROQ_MODEL", _FAKE_MODEL)

        resp = client.get("/api/debug/groq-diagnosis")
        data = resp.json()
        assert data["env"]["groq_key_present"] is False
        assert data["diagnosis"] == "groq_key_invalid"
        assert data["env"]["groq_key_prefix"] == "(not set)"

    def test_groq_error_message_max_120_chars(self, monkeypatch):
        """Sanitisierte Fehlermeldung darf maximal 120 Zeichen lang sein."""
        monkeypatch.setenv("GROQ_API_KEY", _FAKE_KEY)
        monkeypatch.setenv("GROQ_MODEL", _FAKE_MODEL)

        long_msg = "A" * 500  # Sehr lange Meldung

        def fake_urlopen(req, timeout=10):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "models" in url and "completions" not in url:
                return _models_ok_response([_FAKE_MODEL])
            raise _http_error(403, {"error": {"message": long_msg, "code": "test"}})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            resp = client.get("/api/debug/groq-diagnosis")

        data = resp.json()
        msg = data["chat_test"].get("groq_error_message_sanitized", "") or ""
        assert len(msg) <= 120, f"Fehlermeldung zu lang: {len(msg)} Zeichen"
