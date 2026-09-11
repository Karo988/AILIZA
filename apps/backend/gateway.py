"""Kompatibilitaetsmodul fuer den zentralen AILIZA-Gateway.

Die kanonische Implementierung liegt in
``apps.backend.gateway.runtime_gateway``. Dieses Modul bleibt fuer
Legacy-Importe erhalten, enthaelt aber keine eigene Policy- oder
Tool-Ausfuehrungslogik mehr.
"""
from __future__ import annotations

try:
    from .gateway import runtime_gateway as _runtime_gateway
except ImportError:  # Direkter Start mit apps/backend im PYTHONPATH
    from gateway import runtime_gateway as _runtime_gateway


def enforce_policy(tool_name, parameters):
    return _runtime_gateway.enforce_policy(tool_name, parameters)


def request_approval_if_needed(tool_name, parameters):
    return _runtime_gateway.request_approval_if_needed(tool_name, parameters)


def guarded_tool_call(tool_name, parameters):
    return _runtime_gateway.guarded_tool_call(tool_name, parameters)


def execute_approved_tool(approval_id):
    return _runtime_gateway.execute_approved_tool(approval_id)


__all__ = [
    "enforce_policy",
    "execute_approved_tool",
    "guarded_tool_call",
    "request_approval_if_needed",
]
