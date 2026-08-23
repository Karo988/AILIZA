from pathlib import Path

from apps.backend.sandbox import ActionClass, assess_local_action


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
    workspace = tmp_path / "AppData" / "Local" / "Temp" / "ailiza_workspace"
    workspace.mkdir(parents=True)
    target = workspace / "synthetic.txt"
    target.write_text("synthetic", encoding="utf-8")
    monkeypatch.setenv("AILIZA_WORKSPACE_PATH", str(workspace))

    result = assess_local_action(ActionClass.READ_FILE, str(target))

    assert result.allowed is True


def test_normal_workspace_remains_usable(monkeypatch) -> None:
    workspace = Path(__file__).resolve().parents[1]
    target = workspace / "README.md"
    monkeypatch.setenv("AILIZA_WORKSPACE_PATH", str(workspace))

    result = assess_local_action(ActionClass.READ_FILE, str(target))

    assert result.allowed is True
