"""
AILIZA Compliance Scheduler
Startet woechentlichen Check automatisch im Hintergrund.
Jeden Montag 08:00 Uhr.
"""
from __future__ import annotations
import logging, threading, time
from datetime import datetime

logger = logging.getLogger(__name__)

class ComplianceScheduler:
    def __init__(self, data_dir="./data"):
        self.data_dir = data_dir
        self._thread = None
        self._running = False

    def start(self):
        from .weekly_checker import WeeklyComplianceChecker
        checker = WeeklyComplianceChecker(data_dir=self.data_dir)
        result = checker.run_if_due()
        if result.get("status") == "skipped":
            logger.info("Compliance-Check ueberspungen | naechster: %s", result.get("next_check"))
        self._running = True
        self._thread = threading.Thread(target=self._scheduler_loop, daemon=True, name="ailiza-compliance-scheduler")
        self._thread.start()
        logger.info("Compliance-Scheduler gestartet (woechentlich, Hintergrund)")

    def stop(self):
        self._running = False
        logger.info("Compliance-Scheduler gestoppt")

    def _scheduler_loop(self):
        from .weekly_checker import WeeklyComplianceChecker
        while self._running:
            time.sleep(24 * 60 * 60)
            if not self._running:
                break
            try:
                checker = WeeklyComplianceChecker(data_dir=self.data_dir)
                checker.run_if_due()
            except Exception as e:
                logger.error("Fehler im Compliance-Scheduler: %s", str(e)[:100])

def run_compliance_check_now(data_dir="./data"):
    from .weekly_checker import WeeklyComplianceChecker
    checker = WeeklyComplianceChecker(data_dir=data_dir)
    checker.run_check()
