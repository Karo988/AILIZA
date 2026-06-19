from apps.backend import database
from apps.backend.reflection import reflection_skill
from apps.backend.governance.data_governance import DataClass


def setup_module(module):
    database.init_db()


def test_credentials_blocked():
    res = reflection_skill.store_fact("default", "api_key=supersecretvalue123", purpose="test")
    assert res["stored"] is False


def test_special_category_blocked_explicit():
    res = reflection_skill.store_fact("default", "neutral content",
                                      data_classes=[DataClass.SPECIAL_CATEGORY], purpose="test")
    assert res["stored"] is False


def test_store_and_retrieve_public():
    r = reflection_skill.store_fact("tenant_r", "Kunde bevorzugt Rueckruf vormittags",
                                    data_classes=[DataClass.PUBLIC], purpose="crm")
    assert r["stored"] is True
    facts = reflection_skill.retrieve_facts("tenant_r", "crm", provider_profile_active=True)
    assert any(f["id"] == r["fact_id"] for f in facts)


def test_retrieve_requires_provider_profile():
    reflection_skill.store_fact("tenant_r2", "info", data_classes=[DataClass.PUBLIC], purpose="crm")
    assert reflection_skill.retrieve_facts("tenant_r2", "crm", provider_profile_active=False) == []


def test_retrieve_requires_purpose():
    assert reflection_skill.retrieve_facts("tenant_r2", "", provider_profile_active=True) == []
