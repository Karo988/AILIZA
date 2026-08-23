"""Produktionsnachweis: Workspace-Tools beruehren vor dem Handoff keine Datei."""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.backend.tools import standard_tools


class _ForbiddenPath:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("Produktionswerkzeug hat Path vor responsibility_handoff erzeugt")


@pytest.mark.parametrize(
    ("tool_name", "kwargs", "expected_action"),
    [
        ("tool_read_file", {"path": "synthetic/input.txt"}, "read_file"),
        (
            "tool_write_file",
            {"path": "synthetic/new.txt", "content": "synthetic", "mode": "write"},
            "write_file",
        ),
        (
            "tool_write_file",
            {"path": "synthetic/log.txt", "content": "synthetic", "mode": "append"},
            "append_file",
        ),
        ("tool_list_directory", {"path": "synthetic"}, "list_directory"),
        ("tool_read_pdf", {"path": "synthetic/document.pdf"}, "read_file"),
        ("tool_read_image", {"path": "synthetic/image.png"}, "read_file"),
    ],
)
def test_every_production_workspace_tool_hands_off_before_pathlib(
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
    kwargs: dict[str, str],
    expected_action: str,
) -> None:
    monkeypatch.setattr(standard_tools, "Path", _ForbiddenPath)

    result = getattr(standard_tools, tool_name)(**kwargs)

    assert result["allowed"] is False
    assert result["decision"] == "responsibility_handoff"
    assert result["responsibility_handoff"] is True
    assert result["action_class"] == expected_action
    assert "authentisierter Workspace-Broker" in result["reason"]


def test_write_tool_does_not_create_parent_or_file_without_broker(tmp_path: Path) -> None:
    target = tmp_path / "new-parent" / "new-file.txt"

    result = standard_tools.tool_write_file(
        str(target),
        "synthetischer Inhalt",
        mode="write",
    )

    assert result["decision"] == "responsibility_handoff"
    assert not target.parent.exists()
    assert not target.exists()


def test_append_tool_does_not_modify_existing_file_without_broker(tmp_path: Path) -> None:
    target = tmp_path / "existing.txt"
    target.write_text("synthetischer Ausgang", encoding="utf-8")
    before = target.read_bytes()

    result = standard_tools.tool_write_file(
        str(target),
        "synthetischer Zusatz",
        mode="append",
    )

    assert result["decision"] == "responsibility_handoff"
    assert target.read_bytes() == before


def test_non_file_standard_tools_continue_to_work() -> None:
    calculation = standard_tools.tool_calculate("2+2")
    current_time = standard_tools.tool_get_time("Europe/Berlin")

    assert calculation["result"] == 4
    assert current_time["timezone"] == "Europe/Berlin"
    assert current_time["datetime_utc"].endswith("Z")
