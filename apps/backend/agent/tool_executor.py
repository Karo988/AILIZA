"""
AILIZA Tool Executor
EU AI Act Art. 14: Menschliche Aufsicht
"""
from __future__ import annotations
import json, logging, time
from typing import Any, Dict

logger = logging.getLogger(__name__)

def execute_tool_call(agent, tool_name, tool_args, task_id, tool_call_id=""):
    tool_info = agent._tool_registry.get(tool_name)
    if tool_info is None:
        agent.audit.log_tool_call(tool_name=tool_name, task_id=task_id, approved=False)
        return json.dumps({"error": f"Tool nicht gefunden: {tool_name}"})
    requires_approval = tool_info.get("requires_approval", False)
    if requires_approval and agent.human_oversight:
        approval = _request_approval(agent, tool_name, tool_args, task_id)
        if not approval["approved"]:
            agent.audit.log_tool_call(tool_name=tool_name, task_id=task_id, approved=False)
            return json.dumps({"error": f"Tool abgelehnt: {tool_name}"})
    agent.audit.log_tool_call(tool_name=tool_name, task_id=task_id, approved=True)
    try:
        func = tool_info["func"]
        result = func(**tool_args)
        logger.info("Tool ausgefuehrt: %s | task=%s", tool_name, task_id[:8])
        return json.dumps(result, ensure_ascii=False) if isinstance(result, (dict, list)) else str(result)
    except Exception as e:
        logger.error("Tool-Fehler: %s | %s", tool_name, str(e)[:100])
        agent.audit.log_error(task_id=task_id, error=f"Tool {tool_name}: {str(e)}")
        return json.dumps({"error": str(e)[:200]})

def _request_approval(agent, tool_name, tool_args, task_id):
    print(f"\n MENSCHLICHE AUFSICHT (EU AI Act Art. 14)")
    print(f"   Tool: {tool_name}")
    print(f"   Args: {json.dumps(tool_args, ensure_ascii=False)}")
    try:
        answer = input("   Genehmigen? (j/n): ").strip().lower()
        approved = answer in ("j","ja","y","yes")
    except (EOFError, KeyboardInterrupt):
        approved = False
    agent.audit.log_human_oversight(action=tool_name, decision="approved" if approved else "denied")
    return {"approved": approved}
