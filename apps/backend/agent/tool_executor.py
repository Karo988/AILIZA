"""
AILIZA Tool Executor
EU AI Act Art. 14: Menschliche Aufsicht
"""
from __future__ import annotations
import json, logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

def execute_tool_call(agent, tool_name, tool_args, task_id, tool_call_id=""):
    """Kompatibilitaetsadapter zum zentralen Gateway.

    Dieser Legacy-Einstiegspunkt darf keine registrierte Callable mehr direkt
    aufrufen. Unbekannte oder nicht im zentralen Policy-Modell enthaltene
    Tools werden vom Gateway fail-closed blockiert.
    """
    tool_info = agent._tool_registry.get(tool_name)
    if tool_info is None:
        agent.audit.log_tool_call(tool_name=tool_name, task_id=task_id, approved=False)
        return json.dumps({"error": f"Tool nicht gefunden: {tool_name}"})
    try:
        from ..gateway import guarded_tool_call

        result = guarded_tool_call(tool_name, tool_args)
        agent.audit.log_tool_call(
            tool_name=tool_name,
            task_id=task_id,
            approved=result.get("status") == "completed",
        )
        logger.info("Tool ueber Gateway verarbeitet: %s | task=%s", tool_name, task_id[:8])
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        agent.audit.log_tool_call(tool_name=tool_name, task_id=task_id, approved=False)
        logger.error("Tool-Fehler: %s | %s", tool_name, str(e)[:100])
        agent.audit.log_error(task_id=task_id, error=f"Tool {tool_name}: {str(e)}")
        return json.dumps({"error": str(e)[:200]})
