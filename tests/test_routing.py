from apps.backend.routing.router import route_request, estimate_tokens, Route
from apps.backend.governance.data_governance import DataClass


def test_simple_for_greeting():
    d = route_request("Hallo", [DataClass.PUBLIC])
    assert d.route == Route.SIMPLE


def test_risky_for_credentials():
    d = route_request("here is sk-xxx", [DataClass.CREDENTIALS])
    assert d.route == Route.RISKY


def test_document_route():
    d = route_request("scan this", [DataClass.PUBLIC], is_document=True)
    assert d.route == Route.DOCUMENT


def test_complex_for_large_token_estimate():
    big = " ".join(["word"] * 5000)
    d = route_request(big, [DataClass.PUBLIC])
    assert d.route == Route.COMPLEX


def test_budget_limits_present():
    d = route_request("eine etwas laengere normale anfrage mit mehreren woertern hier", [DataClass.PUBLIC])
    assert d.max_input_tokens > 0
    assert d.max_output_tokens > 0


def test_estimate_tokens():
    assert estimate_tokens("a b c") == int(3 * 1.3)
