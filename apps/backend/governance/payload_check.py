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
