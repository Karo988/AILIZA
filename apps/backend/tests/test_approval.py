from apps.backend.approval import assess_risk


def test_trusted_fetch_domain_is_low_risk() -> None:
    risk = assess_risk("fetch", {"url": "https://github.com/openai/codex"})

    assert risk.risky is False
    assert risk.risk_level == "low"


def test_unknown_fetch_domain_requires_approval() -> None:
    risk = assess_risk("fetch", {"url": "https://unknown-example.test/page"})

    assert risk.risky is True
    assert risk.risk_level == "medium"


def test_normal_search_query_is_low_risk() -> None:
    risk = assess_risk("search", {"query": "FastAPI SQLAlchemy audit logging"})

    assert risk.risky is False
    assert risk.risk_level == "low"


def test_risky_search_query_requires_approval() -> None:
    risk = assess_risk("search", {"query": "latest CVE exploit bypass"})

    assert risk.risky is True
    assert risk.risk_level == "high"
