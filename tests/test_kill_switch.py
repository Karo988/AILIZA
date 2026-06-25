import importlib


def _reload(monkeypatch, value):
    monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", value)
    from apps.backend import kill_switch
    importlib.reload(kill_switch)
    return kill_switch


def test_disabled_by_default(monkeypatch):
    ks = _reload(monkeypatch, "false")
    assert ks.is_external_llm_enabled() is False


def test_enabled_when_true(monkeypatch):
    ks = _reload(monkeypatch, "true")
    assert ks.is_external_llm_enabled() is True


def test_enforce_raises_when_disabled(monkeypatch):
    ks = _reload(monkeypatch, "false")
    from apps.backend.errors import AILIZAError
    try:
        ks.enforce_kill_switch()
        assert False, "should have raised"
    except AILIZAError as exc:
        assert exc.code == "kill_switch_active"
