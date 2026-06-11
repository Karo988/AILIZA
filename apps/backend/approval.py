from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any
from urllib.parse import urlparse


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO = "auto"


@dataclass(frozen=True)
class RiskResult:
    risky: bool
    reason: str
    risk_level: str
    tool: str
    input_summary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


TRUSTED_DOMAINS: set[str] = {
    "wikipedia.org",
    "www.wikipedia.org",
    "github.com",
    "raw.githubusercontent.com",
    "docs.python.org",
    "pypi.org",
    "stackoverflow.com",
    "arxiv.org",
    "news.ycombinator.com",
}

COMPLEX_QUERY_THRESHOLD = 120

RISKY_QUERY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(hack|exploit|vulnerability|CVE-\d+|bypass|injection)\b", re.I),
    re.compile(r"\b(credit.?card|ssn|social.?security|bank.?account)\b", re.I),
    re.compile(r"\b(darkweb|dark.?net|tor.?browser)\b", re.I),
]


def assess_fetch_risk(url: str) -> RiskResult:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()

    if not host:
        return RiskResult(True, "URL host is missing", "high", "fetch", url[:80])

    if host in TRUSTED_DOMAINS:
        return RiskResult(False, f"Trusted domain: {host}", "low", "fetch", url[:80])

    return RiskResult(
        risky=True,
        reason=f"Unknown domain: {host}",
        risk_level="medium",
        tool="fetch",
        input_summary=url[:80],
    )


def assess_search_risk(query: str) -> RiskResult:
    if len(query) > COMPLEX_QUERY_THRESHOLD:
        return RiskResult(
            risky=True,
            reason=f"Complex query ({len(query)} characters)",
            risk_level="medium",
            tool="search",
            input_summary=query[:80],
        )

    for pattern in RISKY_QUERY_PATTERNS:
        if pattern.search(query):
            return RiskResult(
                risky=True,
                reason="Query contains potentially risky terms",
                risk_level="high",
                tool="search",
                input_summary=query[:80],
            )

    return RiskResult(False, "Query is low risk", "low", "search", query[:80])


def assess_risk(tool: str, params: dict[str, Any]) -> RiskResult:
    if tool == "fetch":
        return assess_fetch_risk(str(params.get("url", "")))

    if tool == "search":
        return assess_search_risk(str(params.get("query", "")))

    return RiskResult(True, f"Unknown tool: {tool}", "high", tool, str(params)[:80])
