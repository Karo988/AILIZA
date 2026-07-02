"""
Gate 10 — Config Integrity Tests
==================================
Sicherstellt dass AILIZA nur mit gültiger, unveränderter Governance-Konfiguration startet.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "backend"))

from config_integrity import (
    GOVERNANCE_FILES_RELATIVE,
    INTEGRITY_MANIFEST_FILENAME,
    IntegrityCheckResult,
    IntegrityStatus,
    IntegrityViolationError,
    enforce_integrity,
    generate_integrity_manifest,
    verify_integrity,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

TEST_FILES = ("policy_a.py", "policy_b.py", "governance/rules.py")


@pytest.fixture
def governance_dir(tmp_path):
    """Legt ein minimales Governance-Verzeichnis mit Testdateien an."""
    (tmp_path / "governance").mkdir()
    for rel in TEST_FILES:
        p = tmp_path / rel
        p.write_text(f"# {rel}\nAPPROVAL_ROLES = {{}}\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def valid_manifest(governance_dir):
    """Generiert ein gültiges Manifest für die Testdateien."""
    manifest_path = governance_dir / INTEGRITY_MANIFEST_FILENAME
    generate_integrity_manifest(governance_dir, manifest_path, files=TEST_FILES)
    return manifest_path


# ── TestValidConfig ──────────────────────────────────────────────────────────

class TestValidConfig:
    """Gültige Konfiguration erlaubt normalen Start."""

    def test_valid_config_starts_normal(self, governance_dir, valid_manifest):
        result = verify_integrity(governance_dir, valid_manifest, files=TEST_FILES)
        assert result.all_ok is True
        assert result.overall_status == IntegrityStatus.OK.value
        assert result.recommended_mode == "normal"

    def test_valid_config_all_files_allowed(self, governance_dir, valid_manifest):
        result = verify_integrity(governance_dir, valid_manifest, files=TEST_FILES)
        for fr in result.file_results:
            assert fr.decision == "allowed", f"{fr.config_file} sollte allowed sein"
            assert fr.status == IntegrityStatus.OK.value

    def test_valid_config_no_blocked_files(self, governance_dir, valid_manifest):
        result = verify_integrity(governance_dir, valid_manifest, files=TEST_FILES)
        blocked = [r for r in result.file_results if r.decision == "blocked"]
        assert blocked == []

    def test_enforce_does_not_raise_on_valid_config(self, governance_dir, valid_manifest):
        enforce_integrity(governance_dir, valid_manifest, files=TEST_FILES)  # kein Raise

    def test_checked_at_is_iso_timestamp(self, governance_dir, valid_manifest):
        result = verify_integrity(governance_dir, valid_manifest, files=TEST_FILES)
        assert "T" in result.checked_at and "Z" in result.checked_at or "+" in result.checked_at


# ── TestMissingFile ──────────────────────────────────────────────────────────

class TestMissingFile:
    """Fehlende Policy-Datei blockiert den Start."""

    def test_missing_policy_file_blocks_start(self, governance_dir, valid_manifest):
        (governance_dir / "policy_a.py").unlink()
        result = verify_integrity(governance_dir, valid_manifest, files=TEST_FILES)
        assert result.all_ok is False

    def test_missing_file_status(self, governance_dir, valid_manifest):
        (governance_dir / "policy_b.py").unlink()
        result = verify_integrity(governance_dir, valid_manifest, files=TEST_FILES)
        statuses = {r.status for r in result.file_results}
        assert IntegrityStatus.MISSING_FILE.value in statuses

    def test_missing_file_decision_is_blocked(self, governance_dir, valid_manifest):
        (governance_dir / "governance" / "rules.py").unlink()
        result = verify_integrity(governance_dir, valid_manifest, files=TEST_FILES)
        missing = [r for r in result.file_results if r.status == IntegrityStatus.MISSING_FILE.value]
        assert all(r.decision == "blocked" for r in missing)

    def test_missing_file_actual_hash_not_present(self, governance_dir, valid_manifest):
        (governance_dir / "policy_a.py").unlink()
        result = verify_integrity(governance_dir, valid_manifest, files=TEST_FILES)
        missing = next(r for r in result.file_results if r.status == IntegrityStatus.MISSING_FILE.value)
        assert missing.actual_hash_present is False
        assert missing.expected_hash_present is True

    def test_missing_file_recommended_mode_is_kill_switch(self, governance_dir, valid_manifest):
        (governance_dir / "policy_a.py").unlink()
        result = verify_integrity(governance_dir, valid_manifest, files=TEST_FILES)
        assert result.recommended_mode == "kill_switch_active"

    def test_missing_file_enforce_raises(self, governance_dir, valid_manifest):
        (governance_dir / "policy_a.py").unlink()
        with pytest.raises(IntegrityViolationError) as exc_info:
            enforce_integrity(governance_dir, valid_manifest, files=TEST_FILES)
        assert "blockiert" in str(exc_info.value).lower() or "blocked" in str(exc_info.value).lower()


# ── TestHashMismatch ─────────────────────────────────────────────────────────

class TestHashMismatch:
    """Geändertes Capability Manifest / Provider-Profil blockiert Start."""

    def test_modified_capability_manifest_blocked(self, governance_dir, valid_manifest):
        target = governance_dir / "policy_a.py"
        target.write_text("# GEÄNDERT — unautorisierte Modifikation\n", encoding="utf-8")
        result = verify_integrity(governance_dir, valid_manifest, files=TEST_FILES)
        assert result.all_ok is False

    def test_modified_file_status_is_hash_mismatch(self, governance_dir, valid_manifest):
        (governance_dir / "policy_b.py").write_text(
            "APPROVAL_ROLES = {'admin': True}\n", encoding="utf-8"
        )
        result = verify_integrity(governance_dir, valid_manifest, files=TEST_FILES)
        mismatch = [r for r in result.file_results if r.status == IntegrityStatus.HASH_MISMATCH.value]
        assert len(mismatch) >= 1

    def test_modified_file_both_hashes_present(self, governance_dir, valid_manifest):
        (governance_dir / "governance" / "rules.py").write_text(
            "# injection attempt\nimport os; os.system('rm -rf /')\n", encoding="utf-8"
        )
        result = verify_integrity(governance_dir, valid_manifest, files=TEST_FILES)
        mismatch = next(r for r in result.file_results if r.status == IntegrityStatus.HASH_MISMATCH.value)
        assert mismatch.expected_hash_present is True
        assert mismatch.actual_hash_present is True

    def test_modified_file_decision_is_blocked(self, governance_dir, valid_manifest):
        (governance_dir / "policy_a.py").write_text("KILL_SWITCH = False\n", encoding="utf-8")
        result = verify_integrity(governance_dir, valid_manifest, files=TEST_FILES)
        mismatch = [r for r in result.file_results if r.status == IntegrityStatus.HASH_MISMATCH.value]
        assert all(r.decision == "blocked" for r in mismatch)

    def test_modified_file_enforce_raises(self, governance_dir, valid_manifest):
        (governance_dir / "policy_a.py").write_text("# tampered\n", encoding="utf-8")
        with pytest.raises(IntegrityViolationError):
            enforce_integrity(governance_dir, valid_manifest, files=TEST_FILES)

    def test_multiple_modified_files_all_blocked(self, governance_dir, valid_manifest):
        (governance_dir / "policy_a.py").write_text("# changed 1\n", encoding="utf-8")
        (governance_dir / "policy_b.py").write_text("# changed 2\n", encoding="utf-8")
        result = verify_integrity(governance_dir, valid_manifest, files=TEST_FILES)
        blocked = [r for r in result.file_results if r.decision == "blocked"]
        assert len(blocked) >= 2


# ── TestMissingManifest ───────────────────────────────────────────────────────

class TestMissingManifest:
    """Fehlendes oder leeres Integrity-Manifest blockiert Start."""

    def test_missing_manifest_blocks_start(self, governance_dir):
        manifest_path = governance_dir / "nonexistent_manifest.json"
        result = verify_integrity(governance_dir, manifest_path, files=TEST_FILES)
        assert result.all_ok is False
        assert result.overall_status == IntegrityStatus.MISSING_MANIFEST.value

    def test_missing_manifest_kill_switch_mode(self, governance_dir):
        result = verify_integrity(governance_dir, governance_dir / "nope.json", files=TEST_FILES)
        assert result.recommended_mode == "kill_switch_active"

    def test_empty_manifest_blocks_start(self, governance_dir):
        manifest_path = governance_dir / INTEGRITY_MANIFEST_FILENAME
        manifest_path.write_text(
            json.dumps({"manifest_version": "1.0", "governance_files": {}}),
            encoding="utf-8",
        )
        result = verify_integrity(governance_dir, manifest_path, files=TEST_FILES)
        assert result.all_ok is False
        assert result.overall_status == IntegrityStatus.EMPTY_MANIFEST.value

    def test_corrupt_manifest_json_blocks_start(self, governance_dir):
        manifest_path = governance_dir / INTEGRITY_MANIFEST_FILENAME
        manifest_path.write_text("{ this is not valid JSON", encoding="utf-8")
        result = verify_integrity(governance_dir, manifest_path, files=TEST_FILES)
        assert result.all_ok is False
        assert result.overall_status == IntegrityStatus.INTEGRITY_ERROR.value

    def test_empty_manifest_enforce_raises(self, governance_dir):
        manifest_path = governance_dir / INTEGRITY_MANIFEST_FILENAME
        manifest_path.write_text(
            json.dumps({"manifest_version": "1.0", "governance_files": {}}),
            encoding="utf-8",
        )
        with pytest.raises(IntegrityViolationError):
            enforce_integrity(governance_dir, manifest_path, files=TEST_FILES)


# ── TestUnknownFiles ──────────────────────────────────────────────────────────

class TestUnknownFiles:
    """Unbekannte Dateien im Manifest werden markiert — kein Hard-Block."""

    def test_unknown_file_in_manifest_is_detected(self, governance_dir, valid_manifest):
        # Füge eine unbekannte Datei ins Manifest ein
        raw = json.loads(valid_manifest.read_text())
        raw["governance_files"]["suspicious_extra.py"] = "abc123"
        valid_manifest.write_text(json.dumps(raw), encoding="utf-8")
        result = verify_integrity(governance_dir, valid_manifest, files=TEST_FILES)
        assert "suspicious_extra.py" in result.unknown_files

    def test_unknown_file_does_not_block_valid_config(self, governance_dir, valid_manifest):
        raw = json.loads(valid_manifest.read_text())
        raw["governance_files"]["extra_note.py"] = "deadbeef"
        valid_manifest.write_text(json.dumps(raw), encoding="utf-8")
        result = verify_integrity(governance_dir, valid_manifest, files=TEST_FILES)
        # Bekannte Dateien sind OK — unknown wird nur gemeldet
        known_results = [r for r in result.file_results if r.config_file in TEST_FILES]
        assert all(r.decision == "allowed" for r in known_results)

    def test_unknown_files_count_in_audit(self, governance_dir, valid_manifest):
        raw = json.loads(valid_manifest.read_text())
        raw["governance_files"]["x.py"] = "1"
        raw["governance_files"]["y.py"] = "2"
        valid_manifest.write_text(json.dumps(raw), encoding="utf-8")
        result = verify_integrity(governance_dir, valid_manifest, files=TEST_FILES)
        audit = result.to_audit_dict()
        assert audit["unknown_files_count"] == 2


# ── TestAuditCleanliness ─────────────────────────────────────────────────────

class TestAuditCleanliness:
    """Audit enthält keine Rohinhalte aus Config-Dateien."""

    def test_file_result_audit_dict_has_no_hash_values(self, governance_dir, valid_manifest):
        result = verify_integrity(governance_dir, valid_manifest, files=TEST_FILES)
        for fr in result.file_results:
            audit = fr.to_audit_dict()
            assert "sha256" not in str(audit).lower()
            assert "hash_value" not in audit
            assert "content" not in audit

    def test_file_result_audit_dict_keys(self, governance_dir, valid_manifest):
        result = verify_integrity(governance_dir, valid_manifest, files=TEST_FILES)
        required_keys = {"config_file", "status", "expected_hash_present",
                         "actual_hash_present", "decision"}
        for fr in result.file_results:
            audit = fr.to_audit_dict()
            assert required_keys.issubset(set(audit.keys()))

    def test_overall_audit_dict_has_no_file_contents(self, governance_dir, valid_manifest):
        result = verify_integrity(governance_dir, valid_manifest, files=TEST_FILES)
        audit = result.to_audit_dict()
        assert "governance_files" not in audit
        assert "hash" not in str(audit).lower()
        assert "content" not in audit

    def test_overall_audit_dict_required_keys(self, governance_dir, valid_manifest):
        result = verify_integrity(governance_dir, valid_manifest, files=TEST_FILES)
        audit = result.to_audit_dict()
        assert "overall_status" in audit
        assert "all_ok" in audit
        assert "recommended_mode" in audit
        assert "checked_at" in audit
        assert "blocked_count" in audit

    def test_policy_content_not_in_audit_on_mismatch(self, governance_dir, valid_manifest):
        (governance_dir / "policy_a.py").write_text(
            "SECRET_KEY='do-not-log-this'\nAPPROVAL_ROLES={}\n", encoding="utf-8"
        )
        result = verify_integrity(governance_dir, valid_manifest, files=TEST_FILES)
        for fr in result.file_results:
            audit_str = str(fr.to_audit_dict())
            assert "SECRET_KEY" not in audit_str
            assert "do-not-log-this" not in audit_str


# ── TestGenerateManifest ──────────────────────────────────────────────────────

class TestGenerateManifest:
    """generate_integrity_manifest() erzeugt korrektes Manifest."""

    def test_manifest_contains_all_files(self, governance_dir):
        m_path = governance_dir / INTEGRITY_MANIFEST_FILENAME
        manifest = generate_integrity_manifest(governance_dir, m_path, files=TEST_FILES)
        for rel in TEST_FILES:
            assert rel in manifest["governance_files"]

    def test_manifest_has_version(self, governance_dir):
        m_path = governance_dir / INTEGRITY_MANIFEST_FILENAME
        manifest = generate_integrity_manifest(governance_dir, m_path, files=TEST_FILES)
        assert "manifest_version" in manifest
        assert manifest["manifest_version"] == "1.0"

    def test_manifest_has_generated_at(self, governance_dir):
        m_path = governance_dir / INTEGRITY_MANIFEST_FILENAME
        manifest = generate_integrity_manifest(governance_dir, m_path, files=TEST_FILES)
        assert "generated_at" in manifest

    def test_manifest_written_to_disk(self, governance_dir):
        m_path = governance_dir / INTEGRITY_MANIFEST_FILENAME
        generate_integrity_manifest(governance_dir, m_path, files=TEST_FILES)
        assert m_path.exists()
        loaded = json.loads(m_path.read_text())
        assert "governance_files" in loaded

    def test_manifest_raises_on_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError) as exc_info:
            generate_integrity_manifest(tmp_path, files=("nonexistent.py",))
        assert "fehlen" in str(exc_info.value).lower()

    def test_regenerated_manifest_still_verifies(self, governance_dir):
        m_path = governance_dir / INTEGRITY_MANIFEST_FILENAME
        generate_integrity_manifest(governance_dir, m_path, files=TEST_FILES)
        result = verify_integrity(governance_dir, m_path, files=TEST_FILES)
        assert result.all_ok is True


# ── TestRealGovernanceFiles ───────────────────────────────────────────────────

class TestRealGovernanceFiles:
    """Smoke-Test mit den echten Governance-Dateien aus dem Projekt."""

    BACKEND = Path(__file__).parent.parent / "apps" / "backend"

    def test_all_governance_files_exist(self):
        for rel in GOVERNANCE_FILES_RELATIVE:
            p = self.BACKEND / rel
            assert p.exists(), f"Governance-Datei fehlt: {rel}"

    def test_generate_and_verify_real_files(self, tmp_path):
        m_path = tmp_path / INTEGRITY_MANIFEST_FILENAME
        generate_integrity_manifest(self.BACKEND, m_path)
        result = verify_integrity(self.BACKEND, m_path)
        assert result.all_ok is True
        assert result.recommended_mode == "normal"
        assert len(result.file_results) == len(GOVERNANCE_FILES_RELATIVE)

    def test_real_files_all_allowed_with_fresh_manifest(self, tmp_path):
        m_path = tmp_path / INTEGRITY_MANIFEST_FILENAME
        generate_integrity_manifest(self.BACKEND, m_path)
        result = verify_integrity(self.BACKEND, m_path)
        blocked = [r for r in result.file_results if r.decision == "blocked"]
        assert blocked == [], f"Unerwartete geblockte Dateien: {[r.config_file for r in blocked]}"

    def test_enforce_does_not_raise_on_real_files(self, tmp_path):
        m_path = tmp_path / INTEGRITY_MANIFEST_FILENAME
        generate_integrity_manifest(self.BACKEND, m_path)
        enforce_integrity(self.BACKEND, m_path)  # kein Raise

    def test_document_handler_in_governance_scope(self):
        """documents/document_handler.py muss im Integrity-Scope enthalten sein."""
        assert "documents/document_handler.py" in GOVERNANCE_FILES_RELATIVE

    def test_document_handler_file_exists(self):
        p = self.BACKEND / "documents" / "document_handler.py"
        assert p.exists(), "documents/document_handler.py fehlt im Projekt"


# ── TestDocumentHandlerIntegrity ──────────────────────────────────────────────

class TestDocumentHandlerIntegrity:
    """
    Gate 10 schützt Gate 6: Manipulation von document_handler.py führt zu
    HASH_MISMATCH und blockiertem Start — Prompt-Injection-Schutz ist unveränderbar.
    """

    import shutil

    BACKEND = Path(__file__).parent.parent / "apps" / "backend"
    DOC_FILES = GOVERNANCE_FILES_RELATIVE  # alle 8 Dateien inkl. document_handler.py

    @pytest.fixture
    def full_governance_dir(self, tmp_path):
        """Kopiert alle 8 Governance-Dateien inkl. document_handler.py."""
        import shutil
        for rel in self.DOC_FILES:
            src = self.BACKEND / rel
            dst = tmp_path / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return tmp_path

    @pytest.fixture
    def full_valid_manifest(self, full_governance_dir):
        m = full_governance_dir / INTEGRITY_MANIFEST_FILENAME
        generate_integrity_manifest(full_governance_dir, m)
        return m

    def test_tampered_document_handler_causes_hash_mismatch(
        self, full_governance_dir, full_valid_manifest
    ):
        """Manipulation der document_handler.py → HASH_MISMATCH → Start blockiert."""
        (full_governance_dir / "documents" / "document_handler.py").write_text(
            "# Gate 6 disabled\n_INJECTION_PATTERNS = []\ndef scan_document(f, c): return None\n",
            encoding="utf-8",
        )
        result = verify_integrity(full_governance_dir, full_valid_manifest)
        assert result.all_ok is False
        mismatch = [r for r in result.file_results if r.status == IntegrityStatus.HASH_MISMATCH.value]
        assert any(r.config_file == "documents/document_handler.py" for r in mismatch)

    def test_missing_document_handler_causes_missing_file(
        self, full_governance_dir, full_valid_manifest
    ):
        """Fehlende document_handler.py → MISSING_FILE → Start blockiert."""
        (full_governance_dir / "documents" / "document_handler.py").unlink()
        result = verify_integrity(full_governance_dir, full_valid_manifest)
        assert result.all_ok is False
        missing = [r for r in result.file_results if r.status == IntegrityStatus.MISSING_FILE.value]
        assert any(r.config_file == "documents/document_handler.py" for r in missing)

    def test_missing_document_handler_recommended_kill_switch(
        self, full_governance_dir, full_valid_manifest
    ):
        """Fehlende document_handler.py → recommended_mode == kill_switch_active."""
        (full_governance_dir / "documents" / "document_handler.py").unlink()
        result = verify_integrity(full_governance_dir, full_valid_manifest)
        assert result.recommended_mode == "kill_switch_active"

    def test_tampered_document_handler_enforce_raises(
        self, full_governance_dir, full_valid_manifest
    ):
        """enforce_integrity() wirft IntegrityViolationError bei manipulierter document_handler.py."""
        (full_governance_dir / "documents" / "document_handler.py").write_text(
            "# injection patterns removed\n_INJECTION_PATTERNS = []\n",
            encoding="utf-8",
        )
        with pytest.raises(IntegrityViolationError):
            enforce_integrity(full_governance_dir, full_valid_manifest)

    def test_audit_no_document_handler_content(
        self, full_governance_dir, full_valid_manifest
    ):
        """Audit enthält keine Inhalte aus document_handler.py."""
        (full_governance_dir / "documents" / "document_handler.py").write_text(
            "SECRET='injected-payload'\n_INJECTION_PATTERNS = []\n",
            encoding="utf-8",
        )
        result = verify_integrity(full_governance_dir, full_valid_manifest)
        for fr in result.file_results:
            audit_str = str(fr.to_audit_dict())
            assert "SECRET" not in audit_str
            assert "injected-payload" not in audit_str
            assert "_INJECTION_PATTERNS" not in audit_str

    def test_intact_document_handler_all_ok(
        self, full_governance_dir, full_valid_manifest
    ):
        """Unveränderter Zustand → all_ok=True, document_handler.py allowed."""
        result = verify_integrity(full_governance_dir, full_valid_manifest)
        assert result.all_ok is True
        doc_result = next(
            r for r in result.file_results if r.config_file == "documents/document_handler.py"
        )
        assert doc_result.decision == "allowed"
        assert doc_result.status == IntegrityStatus.OK.value
