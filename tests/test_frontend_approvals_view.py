from pathlib import Path


HTML = (Path(__file__).parents[1] / "apps" / "frontend" / "index.html").read_text(encoding="utf-8")


def test_approval_view_uses_filtered_backend_api_and_decision_routes():
    assert "view-approvals" in HTML
    assert "fetch(`${API}/approvals?status=pending`" in HTML
    assert "`${API}/approvals/${Number(approvalId)}/${decision}`" in HTML


def test_approval_view_does_not_render_input_params():
    section = HTML.split("// ── Freigabeoberflaeche", 1)[1].split("// ── Unternehmenswissen", 1)[0]
    assert "a.input_params" not in section
    assert 'a["input_params"]' not in section
    assert "memOvEsc(a.tool" in section
    assert "memOvEsc(a.risk_reason" in section


def test_approval_navigation_is_hidden_without_login():
    assert 'id="nav-approvals" style="display:none"' in HTML
    assert "setApprovalsNavVisible(false)" in HTML
    assert "setApprovalsNavVisible(true)" in HTML
