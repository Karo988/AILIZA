from __future__ import annotations
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from urllib.parse import urlparse

class Decision(str, Enum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"

@dataclass
class PolicyResult:
    decision: Decision
    reason: str
    tool: str
    input_summary: str
    metadata: dict = field(default_factory=dict)

    @property
    def allowed(self):
        return self.decision == Decision.ALLOWED

ALLOWED_SCHEMAS = {"http", "https"}
BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "169.254.169.254"}
BLOCKED_HOST_PATTERNS = [
    re.compile(r"^10\.\d+\.\d+\.\d+$"),
    re.compile(r"^172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+$"),
    re.compile(r"^192\.168\.\d+\.\d+$"),
    re.compile(r"\.internal$"),
    re.compile(r"\.local$"),
]
BLOCKED_QUERY_PATTERNS = [
    re.compile(r"\b(password|passwd|secret|api[_\s]?key|private[_\s]?key)\b", re.I),
]
MAX_QUERY_LENGTH = 500
MAX_URL_LENGTH = 2048


def check_fetch(url: str) -> PolicyResult:
    if len(url) > MAX_URL_LENGTH:
        return PolicyResult(Decision.BLOCKED, "URL zu lang", "fetch", url[:80])
    try:
        parsed = urlparse(url)
    except Exception:
        return PolicyResult(Decision.BLOCKED, "URL ungueltig", "fetch", url[:80])
    if parsed.scheme.lower() not in ALLOWED_SCHEMAS:
        return PolicyResult(Decision.BLOCKED, "Schema nicht erlaubt", "fetch", url[:80])
    host = parsed.hostname or ""
    if host.lower() in BLOCKED_HOSTS:
        return PolicyResult(Decision.BLOCKED, "Host gesperrt", "fetch", url[:80])
    for p in BLOCKED_HOST_PATTERNS:
        if p.search(host):
            return PolicyResult(Decision.BLOCKED, "Privater IP-Bereich", "fetch", url[:80])
    return PolicyResult(Decision.ALLOWED, "OK", "fetch", url[:80], {"url": url})


def check_search(query: str) -> PolicyResult:
    if len(query) > MAX_QUERY_LENGTH:
        return PolicyResult(Decision.BLOCKED, "Query zu lang", "search", query[:80])
    for p in BLOCKED_QUERY_PATTERNS:
        if p.search(query):
            return PolicyResult(Decision.BLOCKED, "Sensible Begriffe", "search", query[:80])
    return PolicyResult(Decision.ALLOWED, "OK", "search", query[:80], {"query": query})


def check_tool_call(tool: str, params: dict) -> PolicyResult:
    if tool == "fetch":
        return check_fetch(params.get("url", ""))
    elif tool == "search":
        return check_search(params.get("query", ""))
    return PolicyResult(Decision.BLOCKED, f"Unbekanntes Tool: {tool}", tool, str(params)[:80])