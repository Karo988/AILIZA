from apps.backend.main import answer_simple_question


def test_greeting():
    assert answer_simple_question("Hallo") == "Hallo!"


def test_identity():
    assert "AILIZA" in answer_simple_question("Wer bist du?")


def test_calculation():
    assert answer_simple_question("Was ist 2 plus 3") == "5"


def test_unknown_returns_none():
    assert answer_simple_question("Schreibe ein Gedicht ueber den Sommer") is None
