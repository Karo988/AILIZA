# AILIZA gateway module
from . import runtime_gateway as _rt
from .runtime_gateway import (
    enforce_policy,
    execute_approved_tool,
    guarded_tool_call,
    request_approval_if_needed,
)

# Re-export as module-level names so monkeypatch.setattr(gateway, "write_audit_entry", ...)
# patches the binding that runtime_gateway actually uses at call time.
# We point these names at the runtime_gateway module attributes directly so that
# patching gateway.<name> also patches runtime_gateway.<name> (same object reference).
import sys as _sys
_self = _sys.modules[__name__]

def __getattr__(name: str):
    if name in ("write_audit_entry", "execute_tool", "create_approval_request", "get_approval_request"):
        return getattr(_rt, name)
    raise AttributeError(name)

def __setattr__(name: str, value):  # type: ignore[override]
    if name in ("write_audit_entry", "execute_tool", "create_approval_request", "get_approval_request"):
        setattr(_rt, name, value)
    else:
        object.__setattr__(_self, name, value)

__all__ = [
    "enforce_policy",
    "execute_approved_tool",
    "execute_tool",
    "create_approval_request",
    "get_approval_request",
    "guarded_tool_call",
    "request_approval_if_needed",
    "write_audit_entry",
]
