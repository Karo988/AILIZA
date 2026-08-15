"""
AILIZA Nutzlast-Pruefung
========================
Die gemeinsame Kernpruefung fuer JEDE Ausgabe -- Text, Streaming-Ereignis,
Tool-Ergebnis, strukturierte Antwort, gespeicherter Datensatz.

Warum ein eigenes Modul: dieselbe Bewertung wird an Stellen gebraucht, die
sich gegenseitig nicht importieren duerfen (`main.py` fuer die Ausgabe an
den Client, `agent_runtime.py` fuer das, was vor der Ausgabe bereits in die
Datenbank geschrieben wird). Laege die Logik weiterhin in `main.py`, muesste
sie fuer den Speicherpfad ein zweites Mal entstehen -- und zwei Fassungen
derselben Sicherheitsregel driften auseinander, bis eine davon falsch ist.

Grundsatz: geprueft wird der Inhalt, nicht der Transportweg und nicht die
Dateiendung.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import re

try:
    from .data_governance import DataClass, classify
    from .redaction import reinsert
except ImportError:  # pragma: no cover
    from governance.data_governance import DataClass, classify
    from governance.redaction import reinsert


# Aus main.py hierher verlagert, weil die Geheimnis-Entfernung eine
# Governance-Grundfunktion ist und inzwischen an mehreren Stellen gebraucht
# wird -- auch dort, wo main.py nicht importiert werden darf.
#
# Betreiber-Entscheidung 2026-07-15: ein erkanntes Geheimnis blockiert NICHT
# den gesamten Text (die Nutzerin sah sonst nicht mehr, was sie schreiben
# wollte), sondern wird gezielt ersetzt. Und anders als personenbezogene
# Daten wird ein Geheimnis NIE wieder eingesetzt -- sonst landete der echte
# Schluessel unbemerkt in einem fertigen Entwurf, den die Nutzerin verschickt.
_SECRET_STRIP_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bsk-[\w\-]{15,}\b"),      # OpenAI
    re.compile(r"\bgsk_[\w\-]{15,}\b"),     # Groq
    re.compile(r"\beyJ[\w\-\.]+\b"),        # JWT
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{20,}\b"),
]


def strip_secrets_with_placeholder(text: str) -> tuple[str, bool]:
    """Entfernt erkannte Geheimnisse und ersetzt sie durch einen sichtbaren
    Platzhalter. Gibt (bereinigter_text, gefunden) zurueck.

    Der Originalwert wird an keiner Stelle zurueckgegeben oder gespeichert.
    """
    found = False
    for pattern in _SECRET_STRIP_PATTERNS:
        text, count = pattern.subn("[API-KEY ENTFERNT]", text)
        if count:
            found = True
    return text, found


# Nicht uebersteuerbare Klassen: was hier erkannt wird, geht auch mit
# Zustimmung nicht hinaus.
GESPERRTE_KLASSEN = {DataClass.CREDENTIALS, DataClass.SPECIAL_CATEGORY}

# Obergrenzen fuer die Tiefenpruefung. Eine Nutzlast mit zehntausenden Knoten
# ist kein normaler Betriebsfall, sondern ein Fehler oder ein Versuch, die
# Pruefung durch Aufwand auszuhebeln. Ueberschreitung fuehrt fail-closed zur
# Sperre, nicht zum ungeprueften Durchreichen.
MAX_NUTZLAST_KNOTEN = 20_000
MAX_NUTZLAST_TIEFE = 40

# Ersatztext fuer ein einzelnes zurueckgehaltenes Feld. Bewusst auf
# Feldebene: ein Ergebnis mit zwanzig Feldern, von denen eines problematisch
# ist, soll nicht vollstaendig verworfen werden.
FELD_ZURUECKGEHALTEN = "[Zurückgehalten: geschützte Daten]"


def erlaubte_reinsertion_map(
    reinsertion_map: dict[str, str] | None,
) -> tuple[dict[str, str], int]:
    """Filtert die Wiedereinsetzungs-Abbildung auf unbedenkliche Werte.

    redact() nimmt Geheimnisse zwar gar nicht erst in die Abbildung auf
    (dort nur Ersetzung durch [SECRET_REMOVED] ohne Map-Eintrag, belegt in
    test_secrets_are_never_in_reinsertion_map). Darauf allein zu bauen waere
    aber zu knapp: die Ausgangspruefung entfernt Geheimnisse aus der Antwort,
    und eine Abbildung mit Geheimnis wuerde sie direkt wieder hineinschreiben
    -- die Entfernung waere wirkungslos.

    Rueckgabe: (erlaubte Abbildung, Anzahl zurueckgehaltener Werte)
    """
    erlaubt: dict[str, str] = {}
    zurueckgehalten = 0
    for platzhalter, wert in (reinsertion_map or {}).items():
        _, wert_enthaelt_secret = strip_secrets_with_placeholder(wert)
        if wert_enthaelt_secret:
            zurueckgehalten += 1
            continue
        erlaubt[platzhalter] = wert
    return erlaubt, zurueckgehalten


def pruefe_texteinheit(text: str) -> tuple[str, bool, bool]:
    """Kernpruefung EINER Texteinheit -- die einzige Stelle, an der entschieden
    wird, ob ein Inhalt geheimnisbehaftet oder gesperrt ist.

    Bewusst ohne Audit, ohne Nutzertext und ohne Fehlerbehandlung: der
    jeweilige Aufrufer kennt seinen Kontext (Antwort, Ereignisfeld,
    Datenbankfeld) und entscheidet dort fail-closed. Genau dadurch teilen
    sich alle Pfade dieselbe Bewertung: gleicher Inhalt -> gleiches Urteil.

    Rueckgabe: (bereinigter Text, Geheimnis entfernt, gesperrte Klasse)
    """
    bereinigt, geheimnis_entfernt = strip_secrets_with_placeholder(text)
    klassifikation = classify(bereinigt)
    klassen = set(getattr(klassifikation, "data_classes", []) or [])
    return bereinigt, geheimnis_entfernt, bool(klassen & GESPERRTE_KLASSEN)


def _schluessel_ist_unbedenklich(schluessel: Any) -> bool:
    """Prueft einen Dictionary-Schluessel.

    Ein Schluessel ist genauso Inhalt wie ein Wert. Ein Ergebnis der Form
    {"sk-live-...": "gefunden"} oder {"max.mustermann@example.de": {...}}
    haette die Pruefung sonst passiert, weil nur Werte betrachtet wurden --
    aufgedeckt in einem Review durch die Betreiberin.

    Ein Tupel- oder Frozenset-Schluessel kann selbst Zeichenketten enthalten
    (z.B. ein Secret als einziges Element) -- Review deckte auf, dass Tupel
    pauschal als unbedenklich durchliessen; dieselbe Luecke besteht fuer
    frozenset. Jedes Element wird deshalb einzeln geprueft.
    """
    if isinstance(schluessel, (tuple, frozenset)):
        return all(_schluessel_ist_unbedenklich(element) for element in schluessel)
    if not isinstance(schluessel, str) or not schluessel:
        return True
    _, geheimnis, gesperrt = pruefe_texteinheit(schluessel)
    return not (geheimnis or gesperrt)


def pruefe_nutzlast(
    wert: Any,
    erlaubte_map: dict[str, str] | None = None,
    zaehler: dict[str, int] | None = None,
    tiefe: int = 0,
) -> Any:
    """Prueft eine beliebige Nutzlast rekursiv -- Text, Liste, Verschachtelung.

    Ein Zugangsschluessel in einem Tool-Ergebnisfeld ist derselbe Vorfall wie
    derselbe Schluessel im Antworttext; er darf nicht durchgehen, nur weil er
    in einem Dictionary steckt.

    Verhalten je Knoten:
      * Text            -> Kernpruefung, danach Wiedereinsetzung
      * Dict            -> Schluessel UND Werte; ein auffaelliger Schluessel
                           fuehrt zum Zurueckhalten des ganzen Paars
      * Liste/Tupel     -> rekursiv, Struktur bleibt erhalten
      * Zahl/Bool/None  -> unveraendert (kein Textinhalt)
      * alles andere    -> fail-closed ersetzt (nicht sicher bewertbar)

    Auffaellige Schluessel werden NICHT umbenannt: ein umbenannter Schluessel
    veraendert die Bedeutung der Struktur still. Das Paar entfaellt stattdessen
    sichtbar und wird gezaehlt.

    Wirft bei Ueberschreitung der Groessen-/Tiefengrenze -- der Aufrufer
    behandelt das fail-closed.
    """
    erlaubte_map = erlaubte_map or {}
    if zaehler is None:
        zaehler = {}

    zaehler["knoten"] = zaehler.get("knoten", 0) + 1
    if zaehler["knoten"] > MAX_NUTZLAST_KNOTEN or tiefe > MAX_NUTZLAST_TIEFE:
        raise ValueError("Nutzlast zu gross oder zu tief fuer eine sichere Pruefung")

    if isinstance(wert, str):
        if not wert:
            return wert
        bereinigt, geheimnis_entfernt, gesperrt = pruefe_texteinheit(wert)
        if gesperrt:
            zaehler["gesperrte_felder"] = zaehler.get("gesperrte_felder", 0) + 1
            return FELD_ZURUECKGEHALTEN
        if geheimnis_entfernt:
            zaehler["bereinigte_felder"] = zaehler.get("bereinigte_felder", 0) + 1
        if erlaubte_map:
            bereinigt, vollstaendig = reinsert(bereinigt, erlaubte_map)
            if not vollstaendig:
                zaehler["offene_platzhalter"] = zaehler.get("offene_platzhalter", 0) + 1
        return bereinigt

    if isinstance(wert, dict):
        geprueft: dict[Any, Any] = {}
        for schluessel, unterwert in wert.items():
            if not _schluessel_ist_unbedenklich(schluessel):
                zaehler["gesperrte_schluessel"] = zaehler.get("gesperrte_schluessel", 0) + 1
                zaehler["gesperrte_felder"] = zaehler.get("gesperrte_felder", 0) + 1
                continue
            geprueft[schluessel] = pruefe_nutzlast(
                unterwert, erlaubte_map, zaehler, tiefe + 1
            )
        return geprueft

    if isinstance(wert, (list, tuple)):
        elemente = [
            pruefe_nutzlast(element, erlaubte_map, zaehler, tiefe + 1) for element in wert
        ]
        return tuple(elemente) if isinstance(wert, tuple) else elemente

    if wert is None or isinstance(wert, (bool, int, float)):
        # Kein Textinhalt -- nichts, worin ein Geheimnis oder personenbezogene
        # Daten stehen koennten.
        return wert

    # Unbekannter Typ: nicht sicher bewertbar. Ereignisse und Tool-Ergebnisse
    # werden ohnehin als JSON gesendet, ein exotischer Typ ist hier bereits
    # ein Fehler -- und wird nicht ungeprueft durchgereicht.
    zaehler["gesperrte_felder"] = zaehler.get("gesperrte_felder", 0) + 1
    return FELD_ZURUECKGEHALTEN


@dataclass
class ApprovalStorageEntscheidung:
    """Ergebnis von prepare_for_approval_storage() -- siehe dort."""

    erlaubt: bool
    parameter: dict[str, Any]
    special_category_erkannt: bool
    ablehnungsgrund: str | None
    nutzerhinweis: str | None


_APPROVAL_SECRET_BLOCKED_MESSAGE = (
    "Diese Aktion kann nicht zur Freigabe gespeichert werden, weil die "
    "Parameter Zugangsdaten enthalten. Bitte entfernen Sie das Geheimnis "
    "aus der Anfrage und versuchen Sie es erneut."
)
_APPROVAL_CHECK_FAILED_MESSAGE = (
    "Diese Anfrage konnte nicht sicher geprüft werden und wird deshalb "
    "nicht zur Freigabe gespeichert. Bitte versuchen Sie es erneut."
)

def _pruefe_textfragment(text: str, ergebnis: dict[str, bool]) -> None:
    """Kernpruefung EINES Textfragments (String-Wert oder String-Schluessel)
    fuer prepare_for_approval_storage().

    Secret-Erkennung auf dem Original, Special-Category-Erkennung auf der
    um kanonische Redaktionsmarker bereinigten Kopie -- siehe
    _klassifikationskopie().
    """
    _, geheimnis_muster = strip_secrets_with_placeholder(text)
    klassifikation_original = classify(text)
    klassen_original = set(getattr(klassifikation_original, "data_classes", []) or [])
    if geheimnis_muster or DataClass.CREDENTIALS in klassen_original:
        ergebnis["secret"] = True

    klassifikationstext = _klassifikationskopie(text)
    klassifikation = classify(klassifikationstext)
    klassen = set(getattr(klassifikation, "data_classes", []) or [])
    if DataClass.SPECIAL_CATEGORY in klassen:
        ergebnis["special_category"] = True


def _kanonische_marker() -> frozenset[str]:
    try:
        from .redaction_v2 import RedactionEngineV2
    except ImportError:  # pragma: no cover
        from governance.redaction_v2 import RedactionEngineV2
    return RedactionEngineV2.canonical_violet_markers()


def _klassifikationskopie(text: str) -> str:
    """Neutralisiert AUSSCHLIESSLICH die kanonischen AILIZA-Redaktionsmarker
    (z.B. "[GESCHWAERZT: Gesundheit - Art. 9 DSGVO]") fuer die erneute
    Klassifikation -- NICHT fuer Secret-Erkennung, NICHT fuer die
    gespeicherte/ausgefuehrte Nutzlast.

    Hintergrund (Fall-2-Regression, Betreiber-Freigabe): der Marker selbst
    enthaelt woertlich den Kategorienamen ("Gesundheit") und die
    Rechtsgrundlage ("Art. 9 DSGVO"). classify() erkennt darin -- korrekt
    nach seinen eigenen Regeln, aber hier fehlerhaft angewendet -- erneut
    SPECIAL_CATEGORY, obwohl an dieser Stelle bereits redigiert wurde. Der
    Marker beschreibt nur, DASS redigiert wurde, er enthaelt selbst keine
    besondere personenbezogene Information.

    Nur EXAKTE kanonische Marker werden ersetzt (String-Vergleich, keine
    Wildcard wie r"\\[GESCHWAERZT:.*\\]"). Ein erfundener oder manipulierter
    Marker -- z.B. "[GESCHWAERZT: HIV - Art. 9 DSGVO]", der so nie von
    RedactionEngineV2 erzeugt wird -- bleibt unveraendert und damit
    klassifizierbar.
    """
    for marker in _kanonische_marker():
        text = text.replace(marker, "[AILIZA_REDACTED]")
    return text


def _scanne_tool_parameter(wert: Any, ergebnis: dict[str, bool], tiefe: int = 0) -> None:
    """Klassifiziert Tool-Parameter LESEND -- ohne sie zu veraendern.

    Anders als pruefe_nutzlast() (die einen bereinigten Wert zurueckgibt)
    darf diese Funktion die Werte nicht umschreiben: Tool-Parameter werden
    spaeter unveraendert zur Ausfuehrung gebraucht, ein Platzhaltersystem
    wie bei Text-Antworten existiert dafuer nicht. Sie meldet nur, OB ein
    Geheimnis-Muster oder eine besondere Kategorie vorkommt.

    Secret-Pruefung IMMER auf dem Originaltext -- niemals auf der
    Klassifikationskopie, sonst koennte ein manipuliertes Markerformat ein
    Secret verstecken. Special-Category-Pruefung dagegen auf der
    Klassifikationskopie, in der nur die kanonischen Redaktionsmarker
    neutralisiert sind (siehe _klassifikationskopie()).
    """
    if tiefe > MAX_NUTZLAST_TIEFE:
        ergebnis["nicht_bewertbar"] = True
        return

    if isinstance(wert, str):
        if not wert:
            return
        _pruefe_textfragment(wert, ergebnis)
        return

    if isinstance(wert, dict):
        for schluessel, unterwert in wert.items():
            # Derselbe Scanner fuer Schluessel wie fuer Werte -- ein
            # Schluessel wie {"HIV": True} ist genauso Inhalt wie ein Wert
            # (Betreiber-Freigabe: bisher wurden Schluessel nur auf
            # Geheimnisse geprueft, nicht auf besondere Kategorien).
            if isinstance(schluessel, str) and schluessel:
                _pruefe_textfragment(schluessel, ergebnis)
            elif not isinstance(schluessel, (str, int, float, bool)) and schluessel is not None:
                # Nicht-primitiver Schluesseltyp widerspricht dem fuer
                # input_params vorgesehenen JSON-artigen Datenmodell --
                # fail-closed statt zu raten.
                ergebnis["nicht_bewertbar"] = True
            _scanne_tool_parameter(unterwert, ergebnis, tiefe + 1)
        return

    if isinstance(wert, (list, tuple)):
        for element in wert:
            _scanne_tool_parameter(element, ergebnis, tiefe + 1)
        return

    if wert is None or isinstance(wert, (bool, int, float)):
        # Kein Textinhalt -- nichts, worin ein Geheimnis oder eine
        # besondere Kategorie stehen koennte.
        return

    # Unbekannter Typ (z.B. bytes): nicht sicher als "kein Geheimnis"
    # einstufbar. Sicherheitsreview-Fund: die erste Fassung liess einen
    # nicht behandelten Typ stillschweigend als unauffaellig durch. Fail-
    # closed statt zu raten.
    ergebnis["nicht_bewertbar"] = True


def prepare_for_approval_storage(parameters: dict[str, Any]) -> ApprovalStorageEntscheidung:
    """Klassifiziert Tool-Parameter vor der Persistenz in approval_requests.

    approval_requests.input_params ist technischer Ausfuehrungsspeicher:
    execute_approved_tool() liest genau diese Werte spaeter zur tatsaechlichen
    Ausfuehrung der genehmigten Aktion. Deshalb gilt hier eine andere Policy
    als bei einer Provider-Antwort oder einem Laufergebnis:

      * Operative Geschaeftsdaten und gewoehnliche personenbezogene Daten
        bleiben UNVERAENDERT. Eine Wiedereinsetzung wie bei Text-Antworten
        ist hier nicht moeglich -- es gibt kein Platzhaltersystem fuer
        Tool-Parameter. Ein veraenderter Wert wuerde spaeter eine andere,
        nicht die genehmigte Aktion ausfuehren.

      * Ein erkanntes Geheimnis fuehrt zur SOFORTIGEN Ablehnung der
        Freigabeanfrage -- nicht zur stillen Entfernung. Im Repository
        existiert kein sicherer Credential-/Referenz-Speicher (geprueft:
        `routers/vault.py`/`audit/vault.py` sind ein Audit-Hashkettenspeicher,
        kein Secret-Store). Ohne einen solchen Speicher gibt es keine
        Moeglichkeit, den echten Wert bei der spaeteren Ausfuehrung wieder
        bereitzustellen; eine Ausfuehrung mit einem Platzhalter waere eine
        stille Fehlausfuehrung mit vermeintlichem Erfolg -- schlimmer als
        eine klare Ablehnung mit verstaendlichem naechsten Schritt.

      * Eine erkannte besondere Kategorie (Art. 9/10 DSGVO) wird NICHT
        blockiert. Betreiber-Korrektur nach einer ersten Fassung, die hier
        einen Hardblock einfuehrte: interne Verarbeitung ist kein Egress.
        prepare_for_approval_storage() entscheidet ausschliesslich ueber
        einen INTERNEN technischen Ausfuehrungsspeicher -- ob ein Inhalt
        anschliessend an einen externen Provider/Dritten gehen darf, ist
        eine eigene, spaeter an der tatsaechlichen Egress-Entscheidung zu
        treffende Frage (eigenes Arbeitspaket: Responsibility Handoff bei
        nicht automatisch freigegebenem Egress). Besondere Kategorien
        werden hier nur markiert (special_category_erkannt=True) und
        auditiert, damit die Persistenz nicht unkontrolliert -- also
        unsichtbar -- erfolgt.

    Rueckgabe: ApprovalStorageEntscheidung. Bei erlaubt=False darf KEIN
    approval_requests-Datensatz angelegt werden.
    """
    ergebnis: dict[str, bool] = {}
    try:
        _scanne_tool_parameter(parameters, ergebnis)
    except Exception:
        # Fail-closed: eine nicht bewertbare Nutzlast wird wie ein
        # Geheimnis-Fund behandelt, nicht stillschweigend gespeichert.
        return ApprovalStorageEntscheidung(
            erlaubt=False,
            parameter={},
            special_category_erkannt=False,
            ablehnungsgrund="check_failed",
            nutzerhinweis=_APPROVAL_CHECK_FAILED_MESSAGE,
        )

    # Reihenfolge bewusst: Secret vor Special Category. Ein Text mit beidem
    # soll als "secret_detected" gemeldet werden -- die konkretere Diagnose
    # gewinnt, auch wenn beide Faelle hier zur Ablehnung fuehren.
    if ergebnis.get("secret") or ergebnis.get("nicht_bewertbar"):
        return ApprovalStorageEntscheidung(
            erlaubt=False,
            parameter={},
            special_category_erkannt=False,
            ablehnungsgrund="secret_detected" if ergebnis.get("secret") else "check_failed",
            nutzerhinweis=(
                _APPROVAL_SECRET_BLOCKED_MESSAGE
                if ergebnis.get("secret")
                else _APPROVAL_CHECK_FAILED_MESSAGE
            ),
        )

    # Special Category blockiert hier NICHT -- interne Verarbeitung ist
    # kein Egress (Betreiber-Korrektur). Sie wird lediglich markiert, damit
    # eine spaetere Egress-Entscheidung sie erkennen kann.
    return ApprovalStorageEntscheidung(
        erlaubt=True,
        parameter=parameters,
        special_category_erkannt=bool(ergebnis.get("special_category")),
        ablehnungsgrund=None,
        nutzerhinweis=None,
    )


def sichere_fassung_fuer_speicherung(wert: Any) -> Any:
    """Fail-closed-Variante fuer alles, was PERSISTIERT wird.

    Speichern ist Verarbeitung. Ein Datensatz, der vor der Governance
    geschrieben wird, ist auch dann noch da, wenn die Anzeige spaeter
    korrekt geschuetzt war. Laesst sich die Nutzlast nicht bewerten, wird
    nichts Ungeprueftes gespeichert.
    """
    try:
        return pruefe_nutzlast(wert, {}, {})
    except Exception:
        return FELD_ZURUECKGEHALTEN
