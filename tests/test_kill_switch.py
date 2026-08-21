import importlib
from pathlib import Path


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


def test_missing_env_stays_disabled_even_with_provider_key(monkeypatch):
    monkeypatch.delenv("AILIZA_EXTERNAL_LLM_ENABLED", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    from apps.backend import kill_switch
    importlib.reload(kill_switch)
    assert kill_switch.is_external_llm_enabled("groq") is False


def test_missing_yaml_blocks_fail_closed(monkeypatch, tmp_path: Path):
    ks = _reload(monkeypatch, "true")
    monkeypatch.setattr(ks, "_KILL_SWITCH_CONFIG_PATH", tmp_path / "missing.yaml")
    assert ks.is_external_llm_enabled("groq") is False


def test_invalid_yaml_blocks_fail_closed(monkeypatch, tmp_path: Path):
    ks = _reload(monkeypatch, "true")
    config = tmp_path / "kill_switch.yaml"
    config.write_text("global: [invalid", encoding="utf-8")
    monkeypatch.setattr(ks, "_KILL_SWITCH_CONFIG_PATH", config)
    assert ks.is_external_llm_enabled("groq") is False


def test_provider_requires_explicit_yaml_entry(monkeypatch):
    ks = _reload(monkeypatch, "true")
    assert ks.is_external_llm_enabled("unknown-provider") is False
