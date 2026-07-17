"""System-Prompt kennt alle echten Redaction-Platzhalter (Karo-Fund 2026-07-17).

Ursache des urspruenglichen Bugs: der System-Prompt in _ask_llm_directly()
listete eine veraltete Fantasie-Liste ([Wert], [Firma], [Datum] gibt es gar
nicht) und erwaehnte das [GESCHWAERZT: <Kategorie> - Art. X DSGVO]-Format
ueberhaupt nicht. Das Modell (Claude Haiku) hielt DESHALB die Kategorie-
Nennung im Platzhalter selbst fuer ein echtes Compliance-Warnsignal und
verweigerte die Aufgabe, obwohl es nie echte Daten sah.

Dieser Test verankert die Erwartung strukturell: JEDES Label, das die
Redaction-Engine tatsaechlich erzeugen kann, muss im System-Prompt vorkommen
-- sonst kann derselbe Fehler unbemerkt wieder einschleichen (z.B. wenn
jemand ein neues PII-Muster in redaction_v2.py ergaenzt, aber vergisst den
Prompt nachzuziehen).
"""
import os
import re

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")

from apps.backend.governance.redaction_v2 import RedactionEngineV2


def _extract_system_prompt() -> str:
    """Holt den system_prompt-String aus _ask_llm_directly ohne main.py
    komplett zu importieren (vermeidet schwere Abhaengigkeiten/Netzwerk-Setup
    beim reinen Text-Test)."""
    import inspect
    from apps.backend import main
    src = inspect.getsource(main._ask_llm_directly)
    match = re.search(r'system_prompt = \(\s*((?:.|\n)*?)\n    \)\n', src)
    assert match, "system_prompt-Definition in _ask_llm_directly nicht gefunden"
    # Alle string-literal-Teile zusammenfuegen (einfacher, robuster Ansatz:
    # den Quelltext direkt als Python-Ausdruck auswerten).
    code = "system_prompt = (\n" + match.group(1) + "\n)"
    ns: dict = {}
    exec(code, ns)  # noqa: S102 - reiner String-Zusammenbau, keine Fremdeingabe
    return ns["system_prompt"]


def test_all_normal_pii_labels_are_explained_to_the_llm():
    engine = RedactionEngineV2()
    prompt = _extract_system_prompt()
    labels = sorted(set(engine._normalize_label(k) for k in engine.PATTERNS if "secret" not in k))
    missing = [l for l in labels if f"[{l}]" not in prompt]
    assert not missing, f"System-Prompt kennt diese echten Redaction-Labels nicht: {missing}"


def test_violet_categories_covered_by_generalized_pattern_rule():
    # Robuster als eine feste Aufzaehlung aller 9 Kategorien: der Prompt muss
    # eine VERALLGEMEINERTE Regel enthalten, die JEDEN
    # "[GESCHWAERZT: <Kategorie> - Art. 9/10 DSGVO]"-Platzhalter abdeckt --
    # auch neue Kategorien, die spaeter in redaction_v2.py hinzukommen, ohne
    # dass jemand den Prompt manuell nachziehen muss. Zusaetzlich pruefen wir
    # exemplarisch, dass mindestens je ein Art.-9- und ein Art.-10-Beispiel
    # konkret genannt ist (Lesbarkeit/Klarheit fuers Modell).
    prompt = _extract_system_prompt()
    assert "beliebige Kategorie" in prompt, (
        "Verallgemeinerte Muster-Regel fuer GESCHWAERZT-Platzhalter fehlt -- "
        "ohne sie kann eine kuenftig neu hinzugefuegte Art.-9/10-Kategorie in "
        "redaction_v2.py erneut zu einer LLM-Verweigerung fuehren."
    )
    assert "Art. 9 DSGVO" in prompt and "Art. 10 DSGVO" in prompt
    assert "GESCHWAERZT: Gesundheit - Art. 9 DSGVO" in prompt  # konkretes Art.-9-Beispiel
    assert "GESCHWAERZT: Strafrechtliche Informationen - Art. 10 DSGVO" in prompt  # Art.-10-Beispiel
    # Alle tatsaechlichen VIOLET-Kategorien muessen zumindest in der
    # erlaeuternden Aufzaehlung ("z.B. Religion, Politik, ...") vorkommen,
    # damit das Modell weiss, WELCHE Art von Kategorien gemeint sind.
    engine = RedactionEngineV2()
    prose_hints = {
        "Religion/Weltanschauung": "Religion",
        "Politische Meinung": "Politik",
        "Herkunft": "Herkunft",
        "Biometrische Daten": "Biometrie",
        "Genetische Daten": "Genetik",
        "Gewerkschaftsbezug": "Gewerkschaftsbezug",
        "Sexualdaten/Familienstand": "Sexualdaten",
    }
    missing = [full for full, hint in prose_hints.items()
               if full in engine._VIOLET_CATEGORY_LABELS.values() and hint not in prompt]
    assert not missing, f"Kategorien fehlen auch als Beispiel-Hinweis im Prompt: {missing}"


def test_prompt_explicitly_forbids_refusal_due_to_placeholder_category_names():
    prompt = _extract_system_prompt()
    assert "keine echten" in prompt.lower() and "daten" in prompt.lower()
    assert "VERWEIGERE DIE AUFGABE NIEMALS" in prompt


def test_stale_fantasy_placeholders_are_gone():
    # Diese existierten nie in der echten Redaction-Engine und haben nur
    # verwirrt -- duerfen nicht mehr im Prompt stehen.
    prompt = _extract_system_prompt()
    for stale in ("[Wert]", "[Firma]", "[Datum]", "[Referenz-Nr.]"):
        assert stale not in prompt, f"Veralteter Fantasie-Platzhalter noch im Prompt: {stale}"
