"""AILIZA Model Intelligence — reine Empfehlungsschicht.

Waehlt ausschliesslich unter bereits freigegebenen Modellen
(status="approved") anhand harter Anforderungen (Faehigkeiten,
Datenschutz, Kontextgroesse, Region) und versionierter Benchmark-Scores.

Kein eigenes Freigaberecht: dieses Modul kann niemals einen Provider oder
ein Modell freigeben. Freigabe (status "candidate" -> "approved") ist ein
separater, menschlicher Schritt (siehe approve_model_candidate() in
apps.backend.database).

Nicht in den produktiven LLM-Aufrufpfad verdrahtet (Paket A, Umfang laut
Handoff bewusst begrenzt) -- recommend_model() liefert nur eine
Empfehlung + Audit-Eintrag, ruft selbst keinen Provider auf.
"""
from .models import ModelCandidate, RoutingRequest, RoutingDecision
from .model_router import ModelRouter

__all__ = ["ModelCandidate", "RoutingRequest", "RoutingDecision", "ModelRouter"]
