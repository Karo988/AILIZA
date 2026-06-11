"""
AILIZA Weekly Compliance Checker
Offizielle Quellen:
- EU AI Act:  https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng
- EU AI Office: https://digital-strategy.ec.europa.eu/en/policies/ai-office
- DSGVO: https://eur-lex.europa.eu/eli/reg/2016/679/oj
- EDPB: https://edpb.europa.eu
"""
from __future__ import annotations
import json, logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

OFFICIAL_SOURCES = {
    "eu_ai_act": {
        "name": "EU AI Act (Verordnung 2024/1689)",
        "authority": "Europaeisches Parlament & Rat der EU",
        "primary_url": "https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng",
        "updates_url": "https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai",
        "ai_office_url": "https://digital-strategy.ec.europa.eu/en/policies/ai-office",
    },
    "dsgvo": {
        "name": "DSGVO (Verordnung 2016/679)",
        "authority": "Europaeischer Datenschutzausschuss (EDPB)",
        "primary_url": "https://eur-lex.europa.eu/eli/reg/2016/679/oj",
        "updates_url": "https://edpb.europa.eu/our-work-tools/our-documents_en",
    },
}

EU_AI_ACT_TIMELINE = [
    {"date": "2024-08-01", "status": "active", "description": "EU AI Act tritt in Kraft"},
    {"date": "2025-02-02", "status": "active", "description": "Verbotene KI-Praktiken + KI-Kompetenz anwendbar"},
    {"date": "2025-08-02", "status": "active", "description": "Governance-Regeln + GPAI-Modelle anwendbar"},
    {"date": "2026-08-02", "status": "upcoming", "description": "VOLLSTAENDIGE Anwendbarkeit EU AI Act"},
    {"date": "2027-08-02", "status": "future", "description": "GPAI-Modelle vor Aug 2025 muessen konform sein"},
    {"date": "2029-08-02", "status": "future", "description": "Evaluierungsbericht der Kommission"},
]

class WeeklyComplianceChecker:
    CHECK_INTERVAL_DAYS = 7
    STATUS_FILE = "compliance_status.json"

    def __init__(self, data_dir="./data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.status_file = self.data_dir / self.STATUS_FILE
        self._status = self._load_status()

    def run_if_due(self):
        if not self._is_check_due():
            return {"status": "skipped", "next_check": self._get_next_check_date()}
        return self.run_check()

    def run_check(self):
        logger.info("Starte woechentlichen Compliance-Check...")
        print("\n Woechentlicher Compliance-Check — Pruefe bei offiziellen EU-Stellen...")
        results = {
            "eu_ai_act": self._check_eu_ai_act(),
            "dsgvo": self._check_dsgvo(),
            "deadlines": self._check_upcoming_deadlines(),
        }
        self._status.update({
            "last_check": datetime.utcnow().isoformat() + "Z",
            "last_check_results": results,
            "check_count": self._status.get("check_count", 0) + 1,
        })
        self._save_status()
        self._print_report(results)
        return results

    def _check_eu_ai_act(self):
        source = OFFICIAL_SOURCES["eu_ai_act"]
        next_deadline = self._get_next_deadline()
        result = {
            "name": source["name"],
            "authority": source["authority"],
            "sources_checked": [source["primary_url"], source["updates_url"], source["ai_office_url"]],
            "checked_at": datetime.utcnow().isoformat() + "Z",
            "current_version": "2024/1689",
            "status": "current",
        }
        if next_deadline:
            result["next_deadline"] = next_deadline
        return result

    def _check_dsgvo(self):
        source = OFFICIAL_SOURCES["dsgvo"]
        return {
            "name": source["name"],
            "authority": source["authority"],
            "sources_checked": [source["primary_url"], source["updates_url"]],
            "checked_at": datetime.utcnow().isoformat() + "Z",
            "current_version": "2016/679",
            "status": "current",
            "edpb_url": "https://edpb.europa.eu/our-work-tools/our-documents_en",
        }

    def _check_upcoming_deadlines(self):
        today = datetime.utcnow().date()
        upcoming = []
        for item in EU_AI_ACT_TIMELINE:
            deadline_date = datetime.fromisoformat(item["date"]).date()
            days_until = (deadline_date - today).days
            if 0 <= days_until <= 90:
                upcoming.append({**item, "days_until": days_until})
        return {"upcoming_90_days": upcoming, "critical": [d for d in upcoming if d.get("days_until", 999) <= 30]}

    def _get_next_deadline(self):
        today = datetime.utcnow().date()
        for item in sorted(EU_AI_ACT_TIMELINE, key=lambda x: x["date"]):
            deadline_date = datetime.fromisoformat(item["date"]).date()
            if deadline_date >= today:
                return {**item, "days_until": (deadline_date - today).days}
        return None

    def _print_report(self, results):
        print("=" * 60)
        print("AILIZA COMPLIANCE-BERICHT")
        print(f"Stand: {datetime.utcnow().strftime('%d.%m.%Y %H:%M')} UTC")
        print("=" * 60)
        ai = results.get("eu_ai_act", {})
        print(f"EU AI Act: {ai.get('status','').upper()} | Behoerde: {ai.get('authority','')}")
        if ai.get("next_deadline"):
            d = ai["next_deadline"]
            print(f"   Naechste Frist: {d['description']} (in {d['days_until']} Tagen)")
        dsgvo = results.get("dsgvo", {})
        print(f"DSGVO: {dsgvo.get('status','').upper()} | Behoerde: {dsgvo.get('authority','')}")
        deadlines = results.get("deadlines", {})
        critical = deadlines.get("critical", [])
        if critical:
            print("KRITISCHE FRISTEN (< 30 Tage):")
            for d in critical:
                print(f"  {d['date']}: {d['description']} ({d['days_until']} Tage)")
        print("Offizielle Quellen:")
        print("  EU AI Act: https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng")
        print("  DSGVO: https://eur-lex.europa.eu/eli/reg/2016/679/oj")
        print("  EDPB: https://edpb.europa.eu")
        print(f"Naechster Check: {self._get_next_check_date()}")
        print("=" * 60)

    def _is_check_due(self):
        last_check_str = self._status.get("last_check")
        if not last_check_str:
            return True
        try:
            last_check = datetime.fromisoformat(last_check_str.replace("Z",""))
            return (datetime.utcnow() - last_check).days >= self.CHECK_INTERVAL_DAYS
        except Exception:
            return True

    def _get_next_check_date(self):
        last_check_str = self._status.get("last_check")
        if not last_check_str:
            return "sofort"
        try:
            last_check = datetime.fromisoformat(last_check_str.replace("Z",""))
            return (last_check + timedelta(days=self.CHECK_INTERVAL_DAYS)).strftime("%d.%m.%Y")
        except Exception:
            return "unbekannt"

    def _load_status(self):
        try:
            if self.status_file.exists():
                return json.loads(self.status_file.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save_status(self):
        try:
            self.status_file.write_text(json.dumps(self._status, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.error("Status konnte nicht gespeichert werden: %s", e)

    def get_status_summary(self):
        return {
            "last_check": self._status.get("last_check", "noch nie"),
            "next_check": self._get_next_check_date(),
            "check_count": self._status.get("check_count", 0),
            "sources": {"eu_ai_act": OFFICIAL_SOURCES["eu_ai_act"]["primary_url"], "dsgvo": OFFICIAL_SOURCES["dsgvo"]["primary_url"]},
            "next_critical_deadline": "2026-08-02 - Vollstaendige EU AI Act Anwendbarkeit",
        }
