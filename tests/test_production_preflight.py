from scripts.production_preflight import evaluate


def _valid_env() -> dict[str, str]:
    return {
        "AILIZA_ENV": "production",
        "AILIZA_TEST_MODE": "false",
        "AILIZA_FORCE_HTTPS": "true",
        "AILIZA_CORS_ORIGINS": "https://ailiza.example.com",
        "AILIZA_SECRET_KEY": "j" * 32,
        "AILIZA_LOG_HMAC_KEY": "h" * 32,
        "AILIZA_DATABASE_URL": "postgresql+psycopg://example.invalid/ailiza",
        "AILIZA_EXTERNAL_LLM_ENABLED": "false",
    }


def test_valid_fail_closed_configuration_passes_without_provider_key():
    assert all(ok for _, ok, _ in evaluate(_valid_env()))


def test_wildcard_and_http_origins_are_rejected():
    for origins in ("*", "", "http://ailiza.example.com"):
        env = _valid_env()
        env["AILIZA_CORS_ORIGINS"] = origins
        result = {name: ok for name, ok, _ in evaluate(env)}
        assert result["cors_explicit_https"] is False


def test_external_llm_requires_at_least_one_key_without_exposing_it():
    env = _valid_env()
    env["AILIZA_EXTERNAL_LLM_ENABLED"] = "true"
    result = {name: ok for name, ok, _ in evaluate(env)}
    assert result["provider_configuration"] is False
    env["GROQ_API_KEY"] = "not-printed-by-evaluate"
    result = {name: ok for name, ok, _ in evaluate(env)}
    assert result["provider_configuration"] is True


def test_sqlite_is_not_accepted_as_production_database():
    env = _valid_env()
    env["AILIZA_DATABASE_URL"] = "sqlite:////data/ailiza.db"
    result = {name: ok for name, ok, _ in evaluate(env)}
    assert result["production_database"] is False
