"""
AILIZA Agent Loop - EU-konform
EU AI Act Art. 12, 14 | DSGVO Art. 5
"""
from __future__ import annotations
import json, logging, time, uuid
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

def run_conversation(agent, user_message, system_message=None, conversation_history=None, task_id=None, stream_callback=None):
    task_id = task_id or str(uuid.uuid4())
    start_time = time.time()
    messages = list(conversation_history or agent._messages)
    messages.append({"role": "user", "content": user_message})
    agent.audit.log_conversation_start(task_id=task_id, user_message_hash=agent.dsgvo.hash_content(user_message))
    try:
        effective_system = _build_system_message(agent, system_message)
        final_response, updated_messages = _agent_loop(agent=agent, messages=messages, system_message=effective_system, task_id=task_id, stream_callback=stream_callback)
        agent._messages = updated_messages
        agent.audit.log_conversation_end(task_id=task_id, success=True, duration_ms=int((time.time()-start_time)*1000))
        return {"final_response": final_response, "session_id": agent.session_id, "task_id": task_id, "user_id": agent.user_id}
    except Exception as e:
        agent.audit.log_error(task_id=task_id, error=str(e))
        raise

def _build_system_message(agent, custom_system=None):
    base = f"Du bist AILIZA v{agent.SYSTEM_VERSION}, ein EU-konformer AI Agent. Du unterliegt dem EU AI Act (2024/1689) und der DSGVO. Sei transparent, hilfreich und erklaere deine Aktionen."
    return f"{base}\n\n{custom_system}" if custom_system else base

def _agent_loop(agent, messages, system_message, task_id, stream_callback=None):
    from .tool_executor import execute_tool_call
    from .api_client import call_llm_api
    api_call_count = 0
    final_response = ""
    while api_call_count < agent.max_turns:
        api_call_count += 1
        response = call_llm_api(agent=agent, messages=messages, system_message=system_message, stream_callback=stream_callback)
        assistant_message = response.get("message", {})
        finish_reason = response.get("finish_reason", "stop")
        tool_calls = assistant_message.get("tool_calls", [])
        messages.append(assistant_message)
        if not tool_calls or finish_reason == "stop":
            final_response = assistant_message.get("content", "")
            break
        for tool_call in tool_calls:
            tool_name = tool_call.get("function", {}).get("name", "")
            tool_args_raw = tool_call.get("function", {}).get("arguments", "{}")
            try:
                tool_args = json.loads(tool_args_raw) if isinstance(tool_args_raw, str) else tool_args_raw
            except json.JSONDecodeError:
                tool_args = {}
            tool_result = execute_tool_call(agent=agent, tool_name=tool_name, tool_args=tool_args, task_id=task_id, tool_call_id=tool_call.get("id",""))
            messages.append({"role": "tool", "tool_call_id": tool_call.get("id",""), "content": str(tool_result)})
    else:
        final_response = "Maximale Anzahl an Schritten erreicht. Bitte formuliere deine Anfrage neu."
    return final_response, messages
