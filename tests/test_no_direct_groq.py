import os


def test_main_has_no_direct_groq_call():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    main_path = os.path.join(here, "apps", "backend", "main.py")
    src = open(main_path, encoding="utf-8").read()
    assert "api.groq.com" not in src
    assert "urllib.request" not in src
    assert "import urllib" not in src


def test_main_uses_orchestrator():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    main_path = os.path.join(here, "apps", "backend", "main.py")
    src = open(main_path, encoding="utf-8").read()
    assert "ProviderOrchestrator" in src
