from apps.backend.governance.data_governance import classify, DataClass


def test_classify_secret():
    r = classify("my key is sk-abcdef1234567890abcdef")
    assert DataClass.CREDENTIALS in r.data_classes
    assert r.highest_risk_class == DataClass.CREDENTIALS
    assert r.needs_review


def test_classify_email():
    r = classify("contact me at max.mustermann@example.com please")
    assert DataClass.PERSONAL_DATA in r.data_classes


def test_classify_iban():
    r = classify("IBAN DE12345678901234567890 used")
    assert DataClass.FINANCIAL in r.data_classes


def test_classify_multiple_strictest_wins():
    r = classify("email a@b.de and api_key=secretvalue123")
    assert r.highest_risk_class == DataClass.CREDENTIALS


def test_classify_public():
    r = classify("the weather is nice today")
    assert r.highest_risk_class == DataClass.PUBLIC


def test_classify_empty():
    r = classify("")
    assert r.highest_risk_class == DataClass.PUBLIC
