#!/usr/bin/env python3
"""Bestimmt den fail-closed Git-Bereich fuer den CI-Secret-Scan.

Die Logik lebt bewusst ausserhalb des Workflow-YAML, damit echte Git-Graphen
in Unit-Tests geprueft werden koennen. Ausgegeben werden nur Commit-IDs und
eine technische Bereichsbeschreibung, keine Autoren- oder Inhaltsdaten.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


NULL_SHA = "0" * 40
SHA_PATTERN = re.compile(r"[0-9a-fA-F]{40}")
MERGE_OPTS = "-m"


@dataclass(frozen=True)
class ScanRange:
    log_opts: str
    scope: str


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _valid_commit(value: str) -> bool:
    if not SHA_PATTERN.fullmatch(value):
        return False
    return _git("cat-file", "-e", f"{value}^{{commit}}").returncode == 0


def _valid_branch(value: str) -> bool:
    return bool(value) and _git("check-ref-format", "--branch", value).returncode == 0


def _merge_base(left: str, right: str) -> str | None:
    result = _git("merge-base", left, right)
    merge_base = result.stdout.strip()
    if result.returncode != 0 or not SHA_PATTERN.fullmatch(merge_base):
        return None
    return merge_base


def _full_history(reason: str) -> ScanRange:
    return ScanRange(
        log_opts=f"--all {MERGE_OPTS}",
        scope=f"Vollstaendige Historie ({reason} — fail-closed)",
    )


def determine_range(env: Mapping[str, str]) -> ScanRange:
    event = env.get("EVENT", "").strip()
    before = env.get("BEFORE", "").strip()
    base_sha = env.get("BASE_SHA", "").strip()
    pr_head_sha = env.get("PR_HEAD_SHA", "").strip()
    fallback_sha = env.get("FALLBACK_SHA", "").strip()
    default_branch = env.get("DEFAULT_BRANCH", "").strip()
    ref_name = env.get("REF_NAME", "").strip()

    if event == "pull_request":
        if _valid_commit(base_sha) and _valid_commit(pr_head_sha):
            merge_base = _merge_base(base_sha, pr_head_sha)
            if merge_base:
                return ScanRange(
                    log_opts=f"{MERGE_OPTS} {merge_base}..{pr_head_sha}",
                    scope=(
                        f"Pull Request: {merge_base}..{pr_head_sha} "
                        "(Merge-Base ermittelt, Merge-Diffs mit -m)"
                    ),
                )
        return _full_history("Pull-Request-Bereich nicht sicher bestimmbar")

    if event == "push" and before != NULL_SHA:
        if _valid_commit(before) and _valid_commit(fallback_sha):
            return ScanRange(
                log_opts=f"{MERGE_OPTS} {before}..{fallback_sha}",
                scope=f"Push: {before}..{fallback_sha} (Merge-Diffs mit -m)",
            )
        return _full_history("Push-Bereich nicht sicher bestimmbar")

    if (
        event == "push"
        and before == NULL_SHA
        and _valid_branch(default_branch)
        and ref_name != default_branch
        and _valid_commit(fallback_sha)
    ):
        default_ref = f"refs/remotes/origin/{default_branch}"
        if _git("cat-file", "-e", f"{default_ref}^{{commit}}").returncode == 0:
            merge_base = _merge_base(default_ref, fallback_sha)
            if merge_base:
                return ScanRange(
                    log_opts=f"{MERGE_OPTS} {merge_base}..{fallback_sha}",
                    scope=(
                        f"Neuer Branch: {merge_base}..{fallback_sha} "
                        f"(Merge-Base mit {default_branch}, Merge-Diffs mit -m)"
                    ),
                )
        return _full_history("neuer Branch ohne sicheren Merge-Base")

    return _full_history("Bereich nicht eindeutig bestimmbar")


def _append(path_value: str, text: str) -> None:
    if not path_value:
        return
    path = Path(path_value)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def main() -> int:
    result = determine_range(os.environ)
    _append(os.environ.get("GITHUB_OUTPUT", ""), f"log_opts={result.log_opts}\n")
    _append(
        os.environ.get("GITHUB_STEP_SUMMARY", ""),
        f"### Secret-Scan — Pruefbereich\n{result.scope}\n",
    )
    print(f"Pruefbereich: {result.scope}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
