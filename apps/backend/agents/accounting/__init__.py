"""
Buchhaltungs-Agent — Referenz-Implementierung eines spezialisierten Sub-Agenten.
"""

from __future__ import annotations

import re
from typing import Any

try:
    from ..base_agent import BaseSpecializedAgent
except ImportError:
    from agents.base_agent import BaseSpecializedAgent

_VAT_RATES = {"standard": 0.19, "reduced": 0.07, "zero": 0.0}
_SKR03 = {
    "Büromaterial": "4930", "Reisekosten": "4670", "IT & Software": "4980",
    "Marketing": "4600", "Bewirtung": "4650", "Telekommunikation": "4920", "Miete": "4210",
}


class AccountingAgent(BaseSpecializedAgent):
    @property
    def name(self) -> str:
        return "accounting"

    @property
    def description(self) -> str:
        return "Buchhaltung: Belege erfassen, kategorisieren, MwSt. berechnen"

    @property
    def capabilities(self) -> list[str]:
        return ["rechnung", "beleg", "mwst", "mehrwertsteuer", "vat",
                "buchhaltung", "ausgabe", "einnahme", "steuernummer", "iban",
                "kategorie", "kosten", "invoice"]

    def get_system_prompt_extension(self) -> str:
        return ("Du bist im Buchhaltungs-Modus. Erfasse Belege strukturiert: Datum, Betrag, "
                "MwSt-Satz, Kategorie, Lieferant. Weise Ausgaben SKR03/SKR04 Konten zu wenn möglich. "
                "Weise auf fehlende Pflichtangaben laut §14 UStG hin.")

    def get_pii_types(self) -> list[str]:
        return ["IBAN", "STEUERNR", "UST_ID", "PERSON", "FIRMA"]

    def handle_tool_call(self, tool_name: str, args: dict[str, Any], user_id: str) -> dict[str, Any]:
        if tool_name == "parse_invoice":
            return self._parse_invoice(args.get("text", ""))
        if tool_name == "categorize_expense":
            return self._categorize(args)
        if tool_name == "calculate_vat":
            return self._calculate_vat(args)
        return {"error": f"Unbekanntes Tool: {tool_name}"}

    def matches_task(self, task: str) -> float:
        task_l = task.lower()
        score = sum(0.25 for cap in self.capabilities if cap in task_l)
        return min(1.0, score)

    def _parse_invoice(self, text: str) -> dict[str, Any]:
        result: dict[str, Any] = {"raw_text": text[:500]}
        m = re.search(r"(\d+[.,]\d{2})\s*€?", text)
        if m:
            result["amount"] = float(m.group(1).replace(",", "."))
        d = re.search(r"\d{1,2}[./]\d{1,2}[./]\d{2,4}", text)
        if d:
            result["date"] = d.group(0)
        u = re.search(r"DE\s*\d{9}", text)
        if u:
            result["ust_id"] = u.group(0)
        s = re.search(r"\d{2,3}\s*/\s*\d{3}\s*/\s*\d{4,5}", text)
        if s:
            result["steuernummer"] = s.group(0)
        missing = [f for f in ("amount", "date") if f not in result]
        result["missing_fields"] = missing
        result["valid_uStG14"] = len(missing) == 0
        return result

    def _categorize(self, args: dict) -> dict[str, Any]:
        combined = f"{args.get('description', '')} {args.get('vendor', '')}".lower()
        categories = {
            "Büromaterial": ["büro", "papier", "stift", "drucker", "toner"],
            "Reisekosten": ["bahn", "flug", "hotel", "taxi", "reise"],
            "IT & Software": ["software", "lizenz", "cloud", "hosting", "server"],
            "Marketing": ["werbung", "marketing", "anzeige"],
            "Bewirtung": ["restaurant", "essen", "bewirtung", "catering"],
            "Telekommunikation": ["telefon", "handy", "internet", "sim"],
            "Miete": ["miete", "coworking"],
        }
        for cat, kws in categories.items():
            if any(k in combined for k in kws):
                return {"category": cat, "skr03_account": _SKR03.get(cat, "4900"), "confidence": 0.8}
        return {"category": "Sonstige Betriebsausgaben", "skr03_account": "4900", "confidence": 0.3}

    def _calculate_vat(self, args: dict) -> dict[str, Any]:
        gross = float(args.get("gross_amount", 0))
        rate = _VAT_RATES.get(args.get("vat_rate", "standard"), 0.19)
        net = gross / (1 + rate) if rate > 0 else gross
        vat = gross - net
        return {"gross": round(gross, 2), "net": round(net, 2), "vat": round(vat, 2), "vat_rate": f"{rate*100:.0f}%"}


def _auto_register() -> None:
    try:
        from agents.registry import get_registry
        get_registry().register(AccountingAgent())
    except Exception:
        pass


_auto_register()
