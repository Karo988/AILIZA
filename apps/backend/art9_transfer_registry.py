"""Geschlossene, zentral erklaerte Kennungen fuer die Art.-9-Pause.

Freigabevorgaenge speichern ausschliesslich die stabilen Kennungen. Die
Klartext-Erlaeuterungen und der AVV-Pruefstatus leben einmalig in diesen
Systemregistries und werden beim Lesen einer Freigabe dynamisch aufgeloest.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class Art9PurposeId(str, Enum):
    TREATMENT_SUMMARY = "treatment_summary"


class Art9RecipientId(str, Enum):
    CLINIC_PARTNER_01 = "clinic_partner_01"


class Art6LegalBasis(str, Enum):
    ART6_1_A = "art6_1_a"
    ART6_1_B = "art6_1_b"
    ART6_1_C = "art6_1_c"
    ART6_1_D = "art6_1_d"
    ART6_1_E = "art6_1_e"
    ART6_1_F = "art6_1_f"


class Art9Exception(str, Enum):
    ART9_2_A = "art9_2_a"
    ART9_2_B = "art9_2_b"
    ART9_2_C = "art9_2_c"
    ART9_2_D = "art9_2_d"
    ART9_2_E = "art9_2_e"
    ART9_2_F = "art9_2_f"
    ART9_2_G = "art9_2_g"
    ART9_2_H = "art9_2_h"
    ART9_2_I = "art9_2_i"
    ART9_2_J = "art9_2_j"


class Art9ProviderId(str, Enum):
    GROQ = "groq"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OPENROUTER = "openrouter"


@dataclass(frozen=True)
class PurposeRegistration:
    identifier: Art9PurposeId
    explanation_de: str


@dataclass(frozen=True)
class RecipientRegistration:
    identifier: Art9RecipientId
    explanation_de: str
    avv_required: bool
    avv_status: str


PURPOSE_REGISTRY: Mapping[Art9PurposeId, PurposeRegistration] = MappingProxyType({
    Art9PurposeId.TREATMENT_SUMMARY: PurposeRegistration(
        identifier=Art9PurposeId.TREATMENT_SUMMARY,
        explanation_de=(
            "Erstellung einer Behandlungszusammenfassung fuer die dokumentierte "
            "Weiterbehandlung durch einen benannten Versorgungspartner."
        ),
    ),
})


RECIPIENT_REGISTRY: Mapping[Art9RecipientId, RecipientRegistration] = MappingProxyType({
    Art9RecipientId.CLINIC_PARTNER_01: RecipientRegistration(
        identifier=Art9RecipientId.CLINIC_PARTNER_01,
        explanation_de=(
            "Vorregistrierter klinischer Kooperationspartner; die konkrete "
            "Rechtstraeger- und Vertragspruefung ist vor einer Aktivierung abzuschliessen."
        ),
        avv_required=True,
        avv_status="not_verified",
    ),
})


ART6_EXPLANATIONS: Mapping[Art6LegalBasis, str] = MappingProxyType({
    Art6LegalBasis.ART6_1_A: "Art. 6 Abs. 1 Buchstabe a DSGVO: Einwilligung",
    Art6LegalBasis.ART6_1_B: "Art. 6 Abs. 1 Buchstabe b DSGVO: Vertrag oder vorvertragliche Massnahme",
    Art6LegalBasis.ART6_1_C: "Art. 6 Abs. 1 Buchstabe c DSGVO: rechtliche Verpflichtung",
    Art6LegalBasis.ART6_1_D: "Art. 6 Abs. 1 Buchstabe d DSGVO: lebenswichtige Interessen",
    Art6LegalBasis.ART6_1_E: "Art. 6 Abs. 1 Buchstabe e DSGVO: oeffentliche Aufgabe",
    Art6LegalBasis.ART6_1_F: "Art. 6 Abs. 1 Buchstabe f DSGVO: berechtigte Interessen",
})


ART9_EXPLANATIONS: Mapping[Art9Exception, str] = MappingProxyType({
    Art9Exception.ART9_2_A: "Art. 9 Abs. 2 Buchstabe a DSGVO: ausdrueckliche Einwilligung",
    Art9Exception.ART9_2_B: "Art. 9 Abs. 2 Buchstabe b DSGVO: Arbeits-, Sozialschutz- oder Sozialrecht",
    Art9Exception.ART9_2_C: "Art. 9 Abs. 2 Buchstabe c DSGVO: lebenswichtige Interessen",
    Art9Exception.ART9_2_D: "Art. 9 Abs. 2 Buchstabe d DSGVO: besondere Organisation ohne Erwerbszweck",
    Art9Exception.ART9_2_E: "Art. 9 Abs. 2 Buchstabe e DSGVO: offensichtlich oeffentlich gemachte Daten",
    Art9Exception.ART9_2_F: "Art. 9 Abs. 2 Buchstabe f DSGVO: Rechtsansprueche und Gerichte",
    Art9Exception.ART9_2_G: "Art. 9 Abs. 2 Buchstabe g DSGVO: erhebliches oeffentliches Interesse",
    Art9Exception.ART9_2_H: "Art. 9 Abs. 2 Buchstabe h DSGVO: Gesundheitsvorsorge oder Behandlung",
    Art9Exception.ART9_2_I: "Art. 9 Abs. 2 Buchstabe i DSGVO: oeffentliche Gesundheit",
    Art9Exception.ART9_2_J: "Art. 9 Abs. 2 Buchstabe j DSGVO: Archiv, Forschung oder Statistik",
})


def approval_identifier_details(input_params: Mapping[str, Any]) -> dict[str, Any] | None:
    """Loest gespeicherte Kennungen fuer die Anzeige auf, ohne sie zu duplizieren."""
    try:
        purpose_id = Art9PurposeId(str(input_params["purpose"]))
        recipient_id = Art9RecipientId(str(input_params["recipient"]))
        art6_basis = Art6LegalBasis(str(input_params["art6_legal_basis"]))
        art9_exception = Art9Exception(str(input_params["art9_exception"]))
    except (KeyError, TypeError, ValueError):
        return None

    purpose = PURPOSE_REGISTRY[purpose_id]
    recipient = RECIPIENT_REGISTRY[recipient_id]
    return {
        "purpose": {
            "id": purpose.identifier.value,
            "explanation_de": purpose.explanation_de,
        },
        "recipient": {
            "id": recipient.identifier.value,
            "explanation_de": recipient.explanation_de,
            "avv_required": recipient.avv_required,
            "avv_status": recipient.avv_status,
        },
        "art6_legal_basis": {
            "id": art6_basis.value,
            "explanation_de": ART6_EXPLANATIONS[art6_basis],
        },
        "art9_exception": {
            "id": art9_exception.value,
            "explanation_de": ART9_EXPLANATIONS[art9_exception],
        },
    }
