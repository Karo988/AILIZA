"""
AILIZA Gate 10 — Config Integrity
===================================
Sicherstellt dass AILIZA nur mit gültiger, unveränderter Governance-Konfiguration startet.

Was Gate 10 schützt:
  - Approval-Regeln (approval.py) — Risikolevel, Rollenmatrix, Timeouts
  - Kill-Switch-Logik (kill_switch.py) — Betriebsmodi, _MODE_BLOCKS
  - Sandbox-Regeln (sandbox.py) — ALWAYS_BLOCKED, sensible Pfade
  - Capability Manifest (capability_manifest.py) — No-Fallback-No-Go-Liste
  - Policy-Gateway (policy.py) — Datenziel-Matrix, Policy-Regeln
  - Datenklassifikation (governance/data_governance.py) — SPECIAL_CATEGORY etc.
  - Redaktion (governance/redaction.py) — _BLOCK_CLASSES, _SECRET_PATTERNS
  - Dokument-Sicherheitslogik (documents/document_handler.py) — Gate 6 Prompt-Injection

Welche Dateien geprüft werden:
  Definiert in GOVERNANCE_FILES_RELATIVE (relativ zu base_dir = apps/backend).
  Jede Datei wird mit SHA-256 gegen das Release-Manifest verglichen.

Was bei Fehlern passiert:
  - Fehlende Datei          → IntegrityStatus.MISSING_FILE → Start blockiert
  - Hash-Abweichung         → IntegrityStatus.HASH_MISMATCH → Start blockiert
  - Fehlendes Manifest      → IntegrityStatus.MISSING_MANIFEST → Start blockiert
  - Leeres Manifest         → IntegrityStatus.EMPTY_MANIFEST → Start blockiert
  - Unbekannte Datei        → IntegrityStatus.UNKNOWN_FILE → markiert (kein Block)
  Fail-closed: bei Unklarheit (Exception) → blockiert

Wie ein neuer Release-Hash erzeugt wird:
  from config_integrity import generate_integrity_manifest
  generate_integrity_manifest(
      base_dir="/pfad/zu/apps/backend",
      output_path="/pfad/zu/governance_integrity.json"
  )
  Diese Datei muss in Versionskontrolle eingecheckt werden. Bei jeder Governance-Änderung
  muss das Manifest neu generiert und durch einen autorisierten Committer signiert werden.

Audit-Metadaten (Gate 10 schreibt NUR diese):
  config_file, status, expected_hash_present, actual_hash_present, decision, timestamp
  NIEMALS: Dateiinhalte, Hashes im Klartext, Konfigurationsdetails.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Governance-Dateien die geprüft werden (relativ zu base_dir)
GOVERNANCE_FILES_RELATIVE: tuple[str, ...] = (
    "approval.py",
    "kill_switch.py",
    "sandbox.py",
    "capability_manifest.py",
    "policy.py",
    "governance/data_governance.py",
    "governance/redaction.py",
    "documents/document_handler.py",  # Gate 6: Prompt-Injection-Erkennung
)

# Name der Integrity-Manifest-Datei (liegt in base_dir)
INTEGRITY_MANIFEST_FILENAME = "governance_integrity.json"

MANIFEST_VERSION = "1.0"


class IntegrityStatus(str, Enum):
    OK = "ok"
    MISSING_FILE = "missing_file"
    HASH_MISMATCH = "hash_mismatch"
    MISSING_MANIFEST = "missing_manifest"
    EMPTY_MANIFEST = "empty_manifest"
    UNKNOWN_FILE = "unknown_file"
    INTEGRITY_ERROR = "integrity_error"


@dataclass(frozen=True)
class FileIntegrityResult:
    config_file: str              # Audit-safe: nur relativer Pfad, kein Inhalt
    status: str                   # IntegrityStatus-Wert
    expected_hash_present: bool   # War ein Hash im Manifest?
    actual_hash_present: bool     # Konnte die Datei gelesen werden?
    decision: str                 # "allowed" oder "blocked"

    def to_audit_dict(self) -> dict[str, Any]:
        """Audit-Light: NUR technische Metadaten, kein Dateiinhalt, kein Hash-Wert."""
        return {
            "config_file": self.config_file,
            "status": self.status,
            "expected_hash_present": self.expected_hash_present,
            "actual_hash_present": self.actual_hash_present,
            "decision": self.decision,
        }


@dataclass
class IntegrityCheckResult:
    overall_status: str           # IntegrityStatus-Wert
    all_ok: bool
    file_results: list[FileIntegrityResult]
    recommended_mode: str         # OperationMode-Wert
    unknown_files: list[str]
    checked_at: str

    def to_audit_dict(self) -> dict[str, Any]:
        """Audit-Light für gesamten Integrity-Check."""
        return {
            "overall_status": self.overall_status,
            "all_ok": self.all_ok,
            "recommended_mode": self.recommended_mode,
            "unknown_files_count": len(self.unknown_files),
            "file_count": len(self.file_results),
            "blocked_count": sum(1 for r in self.file_results if r.decision == "blocked"),
            "checked_at": self.checked_at,
        }


def _sha256_file(path: Path) -> str | None:
    """SHA-256 einer Datei. Gibt None zurück wenn Datei nicht lesbar."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def generate_integrity_manifest(
    base_dir: str | Path,
    output_path: str | Path | None = None,
    files: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """
    Berechnet SHA-256 aller Governance-Dateien und schreibt ein Release-Manifest.

    Muss nach jeder Governance-Änderung durch einen autorisierten Committer
    neu ausgeführt und eingecheckt werden.

    Args:
        base_dir: Basisverzeichnis (= apps/backend)
        output_path: Zieldatei (Default: base_dir/governance_integrity.json)
        files: Zu hashende Dateien (Default: GOVERNANCE_FILES_RELATIVE)

    Returns:
        Das erzeugte Manifest als Dict.
    """
    base = Path(base_dir).resolve()
    if output_path is None:
        output_path = base / INTEGRITY_MANIFEST_FILENAME
    output = Path(output_path)
    if files is None:
        files = GOVERNANCE_FILES_RELATIVE

    file_hashes: dict[str, str] = {}
    missing: list[str] = []

    for rel in files:
        p = base / rel
        h = _sha256_file(p)
        if h is None:
            missing.append(rel)
        else:
            file_hashes[rel] = h

    if missing:
        raise FileNotFoundError(
            f"Folgende Governance-Dateien fehlen beim Manifest-Generieren: {missing}"
        )

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "governance_files": file_hashes,
    }

    output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    logger.info("Integrity-Manifest geschrieben: %s (%d Dateien)", output, len(file_hashes))
    return manifest


def verify_integrity(
    base_dir: str | Path,
    manifest_path: str | Path | None = None,
    files: tuple[str, ...] | None = None,
) -> IntegrityCheckResult:
    """
    Prüft alle Governance-Dateien gegen das Release-Manifest.

    Fail-closed: jede Ausnahme führt zu INTEGRITY_ERROR + blocked.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    base = Path(base_dir).resolve()
    if manifest_path is None:
        manifest_path = base / INTEGRITY_MANIFEST_FILENAME
    manifest_p = Path(manifest_path)
    if files is None:
        files = GOVERNANCE_FILES_RELATIVE

    # Manifest laden
    if not manifest_p.exists():
        logger.warning("Integrity-Manifest fehlt: %s", manifest_p)
        return IntegrityCheckResult(
            overall_status=IntegrityStatus.MISSING_MANIFEST.value,
            all_ok=False,
            file_results=[],
            recommended_mode="kill_switch_active",
            unknown_files=[],
            checked_at=now_iso,
        )

    try:
        raw = manifest_p.read_text(encoding="utf-8")
        manifest = json.loads(raw)
    except Exception as exc:
        logger.warning("Integrity-Manifest nicht lesbar: %s", exc)
        return IntegrityCheckResult(
            overall_status=IntegrityStatus.INTEGRITY_ERROR.value,
            all_ok=False,
            file_results=[],
            recommended_mode="kill_switch_active",
            unknown_files=[],
            checked_at=now_iso,
        )

    expected_hashes: dict[str, str] = manifest.get("governance_files", {})

    if not expected_hashes:
        return IntegrityCheckResult(
            overall_status=IntegrityStatus.EMPTY_MANIFEST.value,
            all_ok=False,
            file_results=[],
            recommended_mode="kill_switch_active",
            unknown_files=[],
            checked_at=now_iso,
        )

    # Prüfe alle registrierten Dateien
    file_results: list[FileIntegrityResult] = []
    all_ok = True

    for rel in files:
        p = base / rel
        expected = expected_hashes.get(rel)
        actual = _sha256_file(p)

        expected_present = expected is not None
        actual_present = actual is not None

        if not actual_present:
            status = IntegrityStatus.MISSING_FILE
            decision = "blocked"
            all_ok = False
        elif not expected_present:
            status = IntegrityStatus.HASH_MISMATCH
            decision = "blocked"
            all_ok = False
        elif actual != expected:
            status = IntegrityStatus.HASH_MISMATCH
            decision = "blocked"
            all_ok = False
        else:
            status = IntegrityStatus.OK
            decision = "allowed"

        result = FileIntegrityResult(
            config_file=rel,
            status=status.value,
            expected_hash_present=expected_present,
            actual_hash_present=actual_present,
            decision=decision,
        )
        file_results.append(result)

        # Audit-Light loggen — kein Inhalt, keine Hashes
        log_entry = result.to_audit_dict()
        log_entry["timestamp"] = now_iso
        if decision == "blocked":
            logger.warning("Config-Integrity BLOCKED: %s", json.dumps(log_entry))
        else:
            logger.debug("Config-Integrity OK: %s", rel)

    # Unbekannte Dateien im Manifest (nicht in GOVERNANCE_FILES_RELATIVE)
    known_set = set(files)
    unknown_files = [f for f in expected_hashes if f not in known_set]
    if unknown_files:
        logger.info("Integrity: %d unbekannte Dateien im Manifest: %s", len(unknown_files), unknown_files)

    overall = IntegrityStatus.OK if all_ok else IntegrityStatus.HASH_MISMATCH
    # Spezifischer Status wenn nur eine Art von Problem vorliegt
    if not all_ok:
        statuses = {r.status for r in file_results}
        if statuses == {IntegrityStatus.MISSING_FILE.value}:
            overall = IntegrityStatus.MISSING_FILE

    recommended_mode = "normal" if all_ok else "kill_switch_active"

    return IntegrityCheckResult(
        overall_status=overall.value,
        all_ok=all_ok,
        file_results=file_results,
        recommended_mode=recommended_mode,
        unknown_files=unknown_files,
        checked_at=now_iso,
    )


def enforce_integrity(
    base_dir: str | Path,
    manifest_path: str | Path | None = None,
    files: tuple[str, ...] | None = None,
) -> None:
    """
    Wirft IntegrityViolationError wenn die Governance-Konfiguration nicht integer ist.
    Muss beim App-Start aufgerufen werden — vor allen anderen Initialisierungen.
    """
    try:
        result = verify_integrity(base_dir, manifest_path, files)
    except Exception as exc:
        raise IntegrityViolationError(
            f"Integrity-Check fehlgeschlagen (fail-closed): {exc}"
        ) from exc

    if not result.all_ok:
        blocked = [r.config_file for r in result.file_results if r.decision == "blocked"]
        raise IntegrityViolationError(
            f"Governance-Konfiguration integer verletzt — Start blockiert. "
            f"Status: {result.overall_status}. "
            f"Betroffene Dateien: {blocked or 'Manifest-Fehler'}. "
            f"Empfohlener Modus: {result.recommended_mode}."
        )


class IntegrityViolationError(RuntimeError):
    """Wird geworfen wenn die Governance-Konfiguration nicht integer ist."""
