import shutil
from pathlib import Path, PureWindowsPath

import pytest

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


def test_sensitive_workspace_root_is_rejected(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "AppData"
    workspace.mkdir()
    target = workspace / "notes.txt"
    target.write_text("secret", encoding="utf-8")
    monkeypatch.setenv("AILIZA_WORKSPACE_PATH", str(workspace))

    result = assess_local_action(ActionClass.READ_FILE, str(target))

    assert result.allowed is False
    assert "geschuetzten Pfad" in result.reason


def test_dedicated_workspace_below_broad_user_folder_is_usable(
    monkeypatch, tmp_path: Path,
) -> None:
    workspace = initialize_custom_workspace(
        tmp_path / "AppData" / "Local" / "Temp",
    )
    target = workspace / "synthetic.txt"
    target.write_text("synthetic", encoding="utf-8")
    monkeypatch.setenv("AILIZA_WORKSPACE_PATH", str(workspace))

    result = assess_local_action(ActionClass.READ_FILE, str(target))

    assert result.allowed is True


def test_managed_workspace_is_created_and_remains_usable(
    monkeypatch, tmp_path: Path,
) -> None:
    workspace = initialize_managed_workspace(tmp_path)
    target = workspace / "synthetic.txt"
    target.write_text("synthetic", encoding="utf-8")
    monkeypatch.setenv("AILIZA_WORKSPACE_PATH", str(workspace))

    result = assess_local_action(ActionClass.READ_FILE, str(target))

    assert result.allowed is True


def test_custom_location_creates_dedicated_child_in_documents(
    monkeypatch, tmp_path: Path,
) -> None:
    documents = tmp_path / "Documents"
    workspace = initialize_custom_workspace(documents)
    target = workspace / "synthetic.txt"
    target.write_text("synthetic", encoding="utf-8")
    monkeypatch.setenv("AILIZA_WORKSPACE_PATH", str(workspace))

    result = assess_local_action(ActionClass.READ_FILE, str(target))

    assert workspace == (documents / "AILIZA" / "Workspace").resolve()
    assert result.allowed is True


def test_arbitrary_unmarked_folder_cannot_be_configured(
    monkeypatch, tmp_path: Path,
) -> None:
    workspace = tmp_path / "ordinary-folder"
    workspace.mkdir()
    target = workspace / "synthetic.txt"
    target.write_text("synthetic", encoding="utf-8")
    monkeypatch.setenv("AILIZA_WORKSPACE_PATH", str(workspace))

    result = assess_local_action(ActionClass.READ_FILE, str(target))

    assert result.allowed is False
    assert "kontrollierten AILIZA-Einrichtungsweg" in result.reason


def test_workspace_marker_cannot_be_copied_to_another_folder(
    monkeypatch, tmp_path: Path,
) -> None:
    workspace = initialize_custom_workspace(tmp_path / "first")
    copied_workspace = tmp_path / "second" / "AILIZA" / "Workspace"
    copied_workspace.mkdir(parents=True)
    shutil.copy2(
        workspace / ".ailiza-workspace.json",
        copied_workspace / ".ailiza-workspace.json",
    )
    target = copied_workspace / "synthetic.txt"
    target.write_text("synthetic", encoding="utf-8")
    monkeypatch.setenv("AILIZA_WORKSPACE_PATH", str(copied_workspace))

    result = assess_local_action(ActionClass.READ_FILE, str(target))

    assert result.allowed is False
    assert "kontrollierten AILIZA-Einrichtungsweg" in result.reason


def test_workspace_replaced_by_link_is_rechecked_before_operation(
    monkeypatch, tmp_path: Path,
) -> None:
    workspace = initialize_custom_workspace(tmp_path)
    real_workspace = workspace.parent / "Workspace-real"
    workspace.rename(real_workspace)
    try:
        workspace.symlink_to(real_workspace, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        real_workspace.rename(workspace)
        pytest.skip(f"Symlink-Semantik auf diesem System nicht verfuegbar: {exc}")
    target = real_workspace / "synthetic.txt"
    target.write_text("synthetic", encoding="utf-8")
    monkeypatch.setenv("AILIZA_WORKSPACE_PATH", str(workspace))

    result = assess_local_action(ActionClass.READ_FILE, str(workspace / target.name))

    assert result.allowed is False
    assert "Symlink oder eine Junction" in result.reason


@pytest.mark.parametrize("profile_parts", [
    ("AppData", "Local", "Google", "Chrome", "User Data", "Profile 1"),
    ("AppData", "Local", "Microsoft", "Edge", "User Data", "Default"),
    ("AppData", "Roaming", "Mozilla", "Firefox", "Profiles", "demo.default-release"),
])
def test_windows_browser_profile_cannot_be_workspace(
    monkeypatch, tmp_path: Path, profile_parts: tuple[str, ...],
) -> None:
    workspace = tmp_path.joinpath(*profile_parts)
    workspace.mkdir(parents=True)
    target = workspace / "synthetic.txt"
    target.write_text("synthetic", encoding="utf-8")
    monkeypatch.setenv("AILIZA_WORKSPACE_PATH", str(workspace))

    result = assess_local_action(ActionClass.READ_FILE, str(target))

    assert result.allowed is False
    assert "geschuetzten Pfad" in result.reason


@pytest.mark.parametrize("protected_part", [".ssh", ".aws", ".gnupg"])
def test_credential_folder_is_rejected_at_any_depth(
    monkeypatch, tmp_path: Path, protected_part: str,
) -> None:
    workspace = tmp_path / "nested" / protected_part / "ailiza"
    workspace.mkdir(parents=True)
    target = workspace / "synthetic.txt"
    target.write_text("synthetic", encoding="utf-8")
    monkeypatch.setenv("AILIZA_WORKSPACE_PATH", str(workspace))

    result = assess_local_action(ActionClass.READ_FILE, str(target))

    assert result.allowed is False
    assert "geschuetzten Pfad" in result.reason


@pytest.mark.parametrize("suffix", [".pem", ".p12", ".pfx"])
def test_certificate_access_inside_workspace_requires_owner_approval(
    monkeypatch, tmp_path: Path, suffix: str,
) -> None:
    workspace = initialize_custom_workspace(tmp_path)
    target = workspace / f"synthetic-certificate{suffix}"
    target.write_text("synthetic", encoding="utf-8")
    monkeypatch.setenv("AILIZA_WORKSPACE_PATH", str(workspace))

    result = assess_local_action(ActionClass.READ_FILE, str(target))

    assert result.allowed is False
    assert result.requires_owner_approval is True


def test_mixed_case_windows_browser_profile_is_rejected() -> None:
    path = PureWindowsPath(
        r"C:\Users\Demo\aPpDaTa\LoCaL\GoOgLe\ChRoMe\UsEr DaTa\Profile 1"
    )

    assert _is_forbidden_workspace_root(path) is True
    assert _is_sensitive_path(path) is True


def test_unc_windows_browser_profile_is_rejected() -> None:
    path = PureWindowsPath(
        r"\\server\share\AppData\Local\Microsoft\Edge\User Data\Default"
    )

    assert _is_forbidden_workspace_root(path) is True
    assert _is_sensitive_path(path) is True
    assert _is_unc_path(path) is True


def test_unc_workspace_is_rejected_before_filesystem_access(monkeypatch) -> None:
    workspace = PureWindowsPath(r"\\server\share\AILIZA\Workspace")
    monkeypatch.setenv("AILIZA_WORKSPACE_PATH", str(workspace))

    result = assess_local_action(
        ActionClass.READ_FILE,
        str(workspace / "synthetic.txt"),
    )

    assert result.allowed is False
    assert "UNC- und Netzwerkpfade" in result.reason


def test_custom_setup_rejects_browser_profile_parent(tmp_path: Path) -> None:
    profile = (
        tmp_path / "AppData" / "Local" / "Microsoft" / "Edge" /
        "User Data" / "Default"
    )

    with pytest.raises(WorkspaceError, match="geschuetzten Pfad"):
        initialize_custom_workspace(profile)


def test_link_from_workspace_into_browser_profile_is_blocked(
    monkeypatch, tmp_path: Path,
) -> None:
    workspace = initialize_custom_workspace(
        tmp_path / "AppData" / "Local" / "Temp",
    )
    profile = (
        tmp_path / "external" / "AppData" / "Local" / "Google" /
        "Chrome" / "User Data" / "Profile 1"
    )
    profile.mkdir(parents=True)
    history = profile / "History"
    history.write_text("synthetic", encoding="utf-8")
    link = workspace / "profile-link"
    try:
        link.symlink_to(profile, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Symlink/Junction-Semantik auf diesem System nicht verfuegbar: {exc}")
    monkeypatch.setenv("AILIZA_WORKSPACE_PATH", str(workspace))

    result = assess_local_action(ActionClass.READ_FILE, str(link / "History"))

    assert result.allowed is False
    assert result.requires_owner_approval is True
