"""Security-Vertrag fuer Workspace-Dateiaktionen ohne authentisierten Broker."""

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path, PureWindowsPath

import pytest

import apps.backend.sandbox as sandbox
from apps.backend.sandbox import (
    ActionClass,
    WorkspaceError,
    _is_forbidden_workspace_root,
    _is_sensitive_path,
    _is_unc_path,
    assess_local_action,
    initialize_custom_workspace,
    initialize_managed_workspace,
)


@pytest.mark.parametrize(
    "action",
    [
        ActionClass.READ_FILE,
        ActionClass.WRITE_FILE,
        ActionClass.APPEND_FILE,
        ActionClass.LIST_DIRECTORY,
        ActionClass.COPY_FILE,
        ActionClass.DELETE_FILE,
        ActionClass.MOVE_FILE,
        ActionClass.RENAME_FILE,
    ],
)
def test_every_workspace_file_action_hands_off_before_path_access(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    action: ActionClass,
) -> None:
    target = tmp_path / "does-not-exist" / "nested" / "synthetic.txt"

    def unexpected_path_access(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Dateipfad wurde vor dem Broker-Handoff ausgewertet")

    monkeypatch.setattr(sandbox, "_get_workspace", unexpected_path_access)
    monkeypatch.setattr(sandbox, "_resolve_strict", unexpected_path_access)

    result = assess_local_action(action, str(target))

    assert result.allowed is False
    assert result.decision == "responsibility_handoff"
    assert result.responsibility_handoff is True
    assert result.in_workspace is False
    assert not target.parent.exists()


def test_correctly_named_workspace_with_forged_json_marker_is_not_trusted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "AILIZA" / "Workspace"
    workspace.mkdir(parents=True)
    marker = workspace / ".ailiza-workspace.json"
    marker.write_text(
        '{"version": 1, "canonical_path": "synthetic-copy"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("AILIZA_WORKSPACE_PATH", str(workspace))

    result = assess_local_action(ActionClass.READ_FILE, str(workspace / "synthetic.txt"))

    assert result.decision == "responsibility_handoff"
    assert marker.exists(), "Die untrusted Datei wird weder gelesen noch destruktiv entfernt"


def test_copied_json_marker_is_not_trusted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source_marker = source / ".ailiza-workspace.json"
    source_marker.write_text(
        '{"version": 1, "canonical_path": "synthetic-source"}',
        encoding="utf-8",
    )
    copied_workspace = tmp_path / "copied" / "AILIZA" / "Workspace"
    copied_workspace.mkdir(parents=True)
    copied_marker = shutil.copy2(source_marker, copied_workspace / source_marker.name)
    monkeypatch.setenv("AILIZA_WORKSPACE_PATH", str(copied_workspace))

    result = assess_local_action(
        ActionClass.LIST_DIRECTORY,
        str(copied_workspace),
    )

    assert result.decision == "responsibility_handoff"
    assert Path(copied_marker).read_bytes() == source_marker.read_bytes()


def test_json_marker_api_is_completely_removed_as_trust_proof() -> None:
    assert not hasattr(sandbox, "_WORKSPACE_MARKER")
    assert not hasattr(sandbox, "_write_workspace_marker")
    assert not hasattr(sandbox, "_has_valid_workspace_marker")


def test_managed_workspace_setup_requires_broker_without_side_effect(tmp_path: Path) -> None:
    candidate = tmp_path / "AILIZA" / "Workspace"

    with pytest.raises(WorkspaceError, match="authentisierter Workspace-Broker"):
        initialize_managed_workspace(tmp_path)

    assert not candidate.exists()


def test_custom_workspace_setup_requires_broker_without_side_effect(tmp_path: Path) -> None:
    candidate = tmp_path / "custom" / "AILIZA" / "Workspace"

    with pytest.raises(WorkspaceError, match="authentisierter Workspace-Broker"):
        initialize_custom_workspace(tmp_path / "custom")

    assert not candidate.exists()


def test_custom_path_environment_variable_is_not_a_trust_proof(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "AILIZA" / "Workspace"
    workspace.mkdir(parents=True)
    monkeypatch.setenv("AILIZA_WORKSPACE_PATH", str(workspace))

    result = assess_local_action(ActionClass.WRITE_FILE, str(workspace / "output.txt"))

    assert result.decision == "responsibility_handoff"
    assert result.allowed is False


def test_macos_application_support_exception_is_only_the_canonical_standard_path() -> None:
    home = Path("synthetic-home")
    canonical = home / "Library" / "Application Support" / "AILIZA" / "Workspace"
    copied_elsewhere = (
        Path("other-home") / "Library" / "Application Support" / "AILIZA" / "Workspace"
    )
    wrong_product = home / "Library" / "Application Support" / "Other" / "Workspace"
    application_support = home / "Library" / "Application Support"
    nested_application_support = (
        home
        / "workspace"
        / "testdata"
        / "Library"
        / "Application Support"
        / "AILIZA"
        / "Workspace"
    )

    assert _is_forbidden_workspace_root(
        canonical,
        platform_name="darwin",
        home=home,
    ) is False
    assert _is_forbidden_workspace_root(
        copied_elsewhere,
        platform_name="darwin",
        home=home,
    ) is True
    assert _is_forbidden_workspace_root(
        wrong_product,
        platform_name="darwin",
        home=home,
    ) is True
    assert _is_forbidden_workspace_root(
        application_support,
        platform_name="darwin",
        home=home,
    ) is True
    assert _is_forbidden_workspace_root(
        nested_application_support,
        platform_name="darwin",
        home=home,
    ) is True
    assert _is_forbidden_workspace_root(
        canonical,
        platform_name="linux",
        home=home,
    ) is True


def test_macos_canonical_path_still_hands_off_without_broker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    workspace = home / "Library" / "Application Support" / "AILIZA" / "Workspace"
    workspace.mkdir(parents=True)
    monkeypatch.setenv("AILIZA_WORKSPACE_PATH", str(workspace))

    result = assess_local_action(ActionClass.READ_FILE, str(workspace / "synthetic.txt"))

    assert result.decision == "responsibility_handoff"


def test_mixed_case_windows_browser_profile_remains_sensitive() -> None:
    path = PureWindowsPath(
        r"C:\Users\Demo\aPpDaTa\LoCaL\GoOgLe\ChRoMe\UsEr DaTa\Profile 1"
    )

    assert _is_forbidden_workspace_root(path) is True
    assert _is_sensitive_path(path) is True


def test_unc_windows_browser_profile_remains_sensitive() -> None:
    path = PureWindowsPath(
        r"\\server\share\AppData\Local\Microsoft\Edge\User Data\Default"
    )

    assert _is_forbidden_workspace_root(path) is True
    assert _is_sensitive_path(path) is True
    assert _is_unc_path(path) is True


def test_unc_candidate_hands_off_without_filesystem_access(monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = PureWindowsPath(r"\\server\share\AILIZA\Workspace")
    monkeypatch.setenv("AILIZA_WORKSPACE_PATH", str(workspace))

    result = assess_local_action(ActionClass.READ_FILE, str(workspace / "synthetic.txt"))

    assert result.decision == "responsibility_handoff"
    assert result.allowed is False


def test_real_ci_platform_matches_runner_and_macos_rule() -> None:
    expected = os.getenv("AILIZA_EXPECTED_CI_PLATFORM", "").strip()
    actual = (
        "windows" if os.name == "nt" else
        "macos" if sys.platform == "darwin" else
        "linux"
    )
    if expected:
        assert actual == expected

    if actual == "macos":
        home = Path.home()
        canonical = (
            home / "Library" / "Application Support" / "AILIZA" / "Workspace"
        )
        assert sandbox._is_canonical_macos_standard_workspace(canonical) is True
        assert _is_forbidden_workspace_root(canonical) is False
        assert _is_forbidden_workspace_root(
            home / "Library" / "Application Support",
        ) is True
        result = assess_local_action(ActionClass.READ_FILE, str(canonical / "synthetic.txt"))
        assert result.decision == "responsibility_handoff"


def test_real_platform_link_or_junction_hands_off(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "workspace-link"

    if os.name == "nt":
        completed = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
            check=False,
            capture_output=True,
            text=True,
            errors="replace",
        )
        assert completed.returncode == 0, completed.stderr or completed.stdout
        attributes = getattr(os.lstat(link), "st_file_attributes", 0)
        assert attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
    else:
        link.symlink_to(target, target_is_directory=True)
        assert link.is_symlink()

    try:
        result = assess_local_action(ActionClass.LIST_DIRECTORY, str(link))
        assert result.decision == "responsibility_handoff"
    finally:
        if os.name == "nt" and link.exists():
            os.rmdir(link)
