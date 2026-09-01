from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.determine_secret_scan_range import NULL_SHA, determine_range


REPO_ROOT = Path(__file__).parents[1]
WORKFLOW = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _commit(repo: Path, name: str, content: str) -> str:
    (repo / name).write_text(content, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-m", f"test {name}")
    return _git(repo, "rev-parse", "HEAD")


def _repo(tmp_path: Path, monkeypatch) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "AILIZA Test")
    _git(repo, "config", "user.email", "test@example.invalid")
    base = _commit(repo, "base.txt", "base")
    _git(repo, "update-ref", "refs/remotes/origin/main", base)
    monkeypatch.chdir(repo)
    return repo, base


def test_workflow_calls_tested_range_script():
    assert "python3 scripts/determine_secret_scan_range.py" in WORKFLOW
    assert "DEFAULT_BRANCH: ${{ github.event.repository.default_branch }}" in WORKFLOW
    assert "REF_NAME: ${{ github.ref_name }}" in WORKFLOW


def test_new_branch_push_uses_default_branch_merge_base(tmp_path, monkeypatch):
    repo, base = _repo(tmp_path, monkeypatch)
    _git(repo, "checkout", "-b", "feature")
    head = _commit(repo, "feature.txt", "feature")

    result = determine_range({
        "EVENT": "push",
        "BEFORE": NULL_SHA,
        "FALLBACK_SHA": head,
        "DEFAULT_BRANCH": "main",
        "REF_NAME": "feature",
    })

    assert result.log_opts == f"-m {base}..{head}"
    assert "Neuer Branch" in result.scope


def test_existing_push_uses_before_to_head(tmp_path, monkeypatch):
    repo, before = _repo(tmp_path, monkeypatch)
    head = _commit(repo, "next.txt", "next")

    result = determine_range({
        "EVENT": "push",
        "BEFORE": before,
        "FALLBACK_SHA": head,
        "DEFAULT_BRANCH": "main",
        "REF_NAME": "main",
    })

    assert result.log_opts == f"-m {before}..{head}"


def test_pull_request_uses_real_merge_base_when_main_advanced(tmp_path, monkeypatch):
    repo, base = _repo(tmp_path, monkeypatch)
    _git(repo, "checkout", "-b", "feature")
    feature_head = _commit(repo, "feature.txt", "feature")
    _git(repo, "checkout", "main")
    current_main = _commit(repo, "main.txt", "main advanced")

    result = determine_range({
        "EVENT": "pull_request",
        "BASE_SHA": current_main,
        "PR_HEAD_SHA": feature_head,
    })

    assert result.log_opts == f"-m {base}..{feature_head}"


def test_default_branch_creation_falls_back_to_full_history(tmp_path, monkeypatch):
    repo, head = _repo(tmp_path, monkeypatch)

    result = determine_range({
        "EVENT": "push",
        "BEFORE": NULL_SHA,
        "FALLBACK_SHA": head,
        "DEFAULT_BRANCH": "main",
        "REF_NAME": "main",
    })

    assert result.log_opts == "--all -m"
    assert "fail-closed" in result.scope


def test_invalid_sha_falls_back_without_being_passed_to_git(tmp_path, monkeypatch):
    _repo(tmp_path, monkeypatch)

    result = determine_range({
        "EVENT": "push",
        "BEFORE": "--all",
        "FALLBACK_SHA": "not-a-sha",
        "DEFAULT_BRANCH": "main",
        "REF_NAME": "feature",
    })

    assert result.log_opts == "--all -m"
